package com.acme.lims.batch;

import java.sql.Timestamp;
import java.util.Date;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;
import com.acme.lims.review.ReviewService;
import com.acme.lims.sample.Sample;
import com.acme.lims.sample.SampleService;

/**
 * Batch disposition and release.
 *
 * This is the highest-criticality flow in AcmeLIMS: the Qualified Person's
 * release decision is what puts product on the market.
 */
@Service
public class BatchReleaseService {

    private final JdbcTemplate jdbc;
    private final AuditService auditService;
    private final ReviewService reviewService;
    private final SampleService sampleService;

    @Autowired
    public BatchReleaseService(DataSource dataSource, AuditService auditService,
                               ReviewService reviewService, SampleService sampleService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.auditService = auditService;
        this.reviewService = reviewService;
        this.sampleService = sampleService;
    }

    /**
     * Release a batch for distribution. Requires every sample result approved
     * and no open major deviation.
     */
    @PreAuthorize("hasRole('QP')")
    @Transactional
    public void releaseBatch(long batchId, String qpName, String qpPassword) {
        if (!reviewService.verifyReviewer(qpName, qpPassword)) {
            throw new SecurityException("Release signature rejected: credentials not verified");
        }
        ReleaseCheck check = evaluateReleaseReadiness(batchId);
        if (!check.isReleasable()) {
            throw new IllegalStateException("Batch not releasable: " + check.getBlockers());
        }
        applyDisposition(batchId, "RELEASED", qpName);
    }

    @PreAuthorize("hasRole('QP')")
    @Transactional
    public void rejectBatch(long batchId, String qpName, String qpPassword, String reason) {
        if (!reviewService.verifyReviewer(qpName, qpPassword)) {
            throw new SecurityException("Release signature rejected: credentials not verified");
        }
        applyDisposition(batchId, "REJECTED", qpName);
        auditService.recordChange("BATCH", String.valueOf(batchId), "REJECTION_REASON",
            null, reason, qpName, "REJECT");
    }

    @Transactional
    public void quarantineBatch(long batchId, String by, String reason) {
        applyDisposition(batchId, "QUARANTINE", by);
        auditService.recordChange("BATCH", String.valueOf(batchId), "QUARANTINE_REASON",
            null, reason, by, "UPDATE");
    }

    private void applyDisposition(long batchId, String disposition, String by) {
        String previous = findDisposition(batchId);
        Timestamp at = new Timestamp(new Date().getTime());
        jdbc.update(
            "UPDATE BATCH SET DISPOSITION = ?, DISPOSITION_BY = ?, DISPOSITION_AT = ?, QP_NAME = ? WHERE BATCH_ID = ?",
            disposition, by, at, by, batchId);
        auditService.recordChange("BATCH", String.valueOf(batchId), "DISPOSITION",
            previous, disposition, by, "UPDATE");
    }

    public ReleaseCheck evaluateReleaseReadiness(long batchId) {
        ReleaseCheck check = new ReleaseCheck(batchId);
        List<Sample> samples = sampleService.findByBatch(batchId);
        if (samples.isEmpty()) {
            check.addBlocker("no samples registered against this batch");
        }
        for (int i = 0; i < samples.size(); i++) {
            Sample s = samples.get(i);
            if (!reviewService.isFullyReviewed(s.getSampleId())) {
                check.addBlocker("sample " + s.getSampleCode() + " has unreviewed results");
            }
        }
        Integer openDeviations = jdbc.queryForObject(
            "SELECT COUNT(*) FROM DEVIATION WHERE BATCH_ID = ? AND STATUS = 'OPEN' AND SEVERITY IN ('MAJOR','CRITICAL')",
            Integer.class, batchId);
        if (openDeviations != null && openDeviations.intValue() > 0) {
            check.addBlocker(openDeviations + " open major/critical deviation(s)");
        }
        Integer openCapa = jdbc.queryForObject(
            "SELECT COUNT(*) FROM CAPA C JOIN DEVIATION D ON D.DEVIATION_ID = C.DEVIATION_ID "
          + "WHERE D.BATCH_ID = ? AND C.STATUS <> 'CLOSED'",
            Integer.class, batchId);
        if (openCapa != null && openCapa.intValue() > 0) {
            check.addBlocker(openCapa + " open CAPA(s)");
        }
        return check;
    }

    public String findDisposition(long batchId) {
        List<String> rows = jdbc.queryForList(
            "SELECT DISPOSITION FROM BATCH WHERE BATCH_ID = ?", String.class, batchId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<ProductBatch> findAwaitingDisposition() {
        return jdbc.query(
            "SELECT BATCH_ID, BATCH_NUMBER, PRODUCT_CODE, MANUFACTURED_AT, DISPOSITION, DISPOSITION_BY, DISPOSITION_AT, QP_NAME "
          + "FROM BATCH WHERE DISPOSITION IS NULL OR DISPOSITION = 'QUARANTINE' ORDER BY MANUFACTURED_AT",
            new BatchMapper());
    }

    public ProductBatch findById(long batchId) {
        List<ProductBatch> rows = jdbc.query(
            "SELECT BATCH_ID, BATCH_NUMBER, PRODUCT_CODE, MANUFACTURED_AT, DISPOSITION, DISPOSITION_BY, DISPOSITION_AT, QP_NAME "
          + "FROM BATCH WHERE BATCH_ID = ?",
            new Object[] { batchId }, new BatchMapper());
        return rows.isEmpty() ? null : rows.get(0);
    }
}
