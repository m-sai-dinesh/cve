package com.acme.lims.review;

import java.security.MessageDigest;
import java.sql.Timestamp;
import java.util.Date;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;
import com.acme.lims.result.ResultService;
import com.acme.lims.result.TestResult;

/**
 * Second-person review and electronic signature of test results.
 *
 * This is the 21 CFR Part 11 subpart C flow: the reviewer re-enters their
 * password, the signature records its meaning, and the event is audit-trailed.
 */
@Service
public class ReviewService {

    private final JdbcTemplate jdbc;
    private final AuditService auditService;
    private final ResultService resultService;
    private final PasswordEncoder passwordEncoder;

    private static long signatureSequence = 700000L;

    @Autowired
    public ReviewService(DataSource dataSource, AuditService auditService,
                         ResultService resultService, PasswordEncoder passwordEncoder) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.auditService = auditService;
        this.resultService = resultService;
        this.passwordEncoder = passwordEncoder;
    }

    /**
     * Approve a result. Requires password re-entry (Part 11 signature manifestation).
     */
    @Transactional
    public long approveResult(long resultId, String reviewerUsername, String reviewerPassword,
                              String signatureMeaning) {
        if (!verifyReviewer(reviewerUsername, reviewerPassword)) {
            throw new SecurityException("Electronic signature rejected: credentials not verified");
        }
        TestResult result = resultService.findById(resultId);
        if (result == null) {
            throw new IllegalArgumentException("unknown result " + resultId);
        }
        if (reviewerUsername.equals(result.getEnteredBy())) {
            throw new IllegalStateException("Four-eyes violation: reviewer may not be the originator");
        }

        long sigId = ++signatureSequence;
        Timestamp signedAt = new Timestamp(new Date().getTime());
        String hash = signatureHash(resultId, reviewerUsername, signatureMeaning, signedAt);

        jdbc.update(
            "INSERT INTO RESULT_SIGNATURE (SIG_ID, RESULT_ID, SIGNED_BY, SIGNED_AT, SIGNATURE_MEANING, SIGNATURE_HASH) "
          + "VALUES (?, ?, ?, ?, ?, ?)",
            sigId, resultId, reviewerUsername, signedAt, signatureMeaning, hash);

        resultService.setReviewStatus(resultId, "APPROVED", reviewerUsername);
        auditService.recordSignature("RESULT", String.valueOf(resultId), reviewerUsername, signatureMeaning);
        return sigId;
    }

    @Transactional
    public void rejectResult(long resultId, String reviewerUsername, String reviewerPassword, String reason) {
        if (!verifyReviewer(reviewerUsername, reviewerPassword)) {
            throw new SecurityException("Electronic signature rejected: credentials not verified");
        }
        resultService.setReviewStatus(resultId, "REJECTED", reviewerUsername);
        auditService.recordChange("RESULT", String.valueOf(resultId), "REVIEW_STATUS",
            "PENDING_REVIEW", "REJECTED: " + reason, reviewerUsername, "REJECT");
    }

    public boolean verifyReviewer(String username, String rawPassword) {
        List<String> hashes = jdbc.queryForList(
            "SELECT PASSWORD_HASH FROM LIMS_USER WHERE USERNAME = ? AND ACTIVE_FLAG = 'Y'",
            String.class, username);
        if (hashes.isEmpty()) {
            return false;
        }
        return passwordEncoder.matches(rawPassword, hashes.get(0));
    }

    public List<ResultSignature> findSignatures(long resultId) {
        return jdbc.query(
            "SELECT SIG_ID, RESULT_ID, SIGNED_BY, SIGNED_AT, SIGNATURE_MEANING, SIGNATURE_HASH "
          + "FROM RESULT_SIGNATURE WHERE RESULT_ID = ? ORDER BY SIGNED_AT",
            new Object[] { resultId }, new SignatureMapper());
    }

    public boolean isFullyReviewed(long sampleId) {
        Integer pending = jdbc.queryForObject(
            "SELECT COUNT(*) FROM RESULT WHERE SAMPLE_ID = ? AND REVIEW_STATUS <> 'APPROVED'",
            Integer.class, sampleId);
        return pending != null && pending.intValue() == 0;
    }

    private String signatureHash(long resultId, String user, String meaning, Timestamp at) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            String payload = resultId + "|" + user + "|" + meaning + "|" + at.getTime();
            byte[] digest = md.digest(payload.getBytes("UTF-8"));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < digest.length; i++) {
                sb.append(String.format("%02x", Byte.valueOf(digest[i])));
            }
            return sb.toString();
        } catch (Exception e) {
            return "UNHASHED";
        }
    }
}
