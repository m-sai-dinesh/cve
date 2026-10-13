package com.acme.lims.result;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.util.Date;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;
import com.acme.lims.sample.SampleService;

/**
 * Test result entry and out-of-specification (OOS) evaluation.
 *
 * GxP: HIGH criticality. An incorrect OOS decision here can release
 * non-conforming product.
 */
@Service
public class ResultService {

    private final JdbcTemplate jdbc;
    private final AuditService auditService;
    private final SampleService sampleService;
    private final SpecificationService specificationService;

    private static long resultSequence = 900000L;

    @Autowired
    public ResultService(DataSource dataSource, AuditService auditService,
                         SampleService sampleService, SpecificationService specificationService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.auditService = auditService;
        this.sampleService = sampleService;
        this.specificationService = specificationService;
    }

    @Transactional
    public long enterResult(long sampleId, String analyte, BigDecimal value, String unit,
                            String instrumentId, String enteredBy) {
        TestSpecification spec = specificationService.findEffectiveSpec(sampleId, analyte);
        boolean oos = evaluateOos(value, spec);

        long resultId = ++resultSequence;
        Timestamp enteredAt = new Timestamp(new Date().getTime());

        jdbc.update(
            "INSERT INTO RESULT (RESULT_ID, SAMPLE_ID, ANALYTE, VALUE_NUM, UNIT, SPEC_ID, OOS_FLAG, ENTERED_AT, ENTERED_BY, REVIEW_STATUS, INSTRUMENT_ID) "
          + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_REVIEW', ?)",
            resultId, sampleId, analyte, value, unit,
            spec == null ? null : Long.valueOf(spec.getSpecId()),
            oos ? "Y" : "N", enteredAt, enteredBy, instrumentId);

        auditService.recordCreation("RESULT", String.valueOf(resultId), enteredBy);
        sampleService.updateStatus(sampleId, "IN_TESTING", enteredBy);

        if (oos) {
            raiseOosDeviation(resultId, sampleId, analyte, value, spec, enteredBy);
        }
        return resultId;
    }

    public boolean evaluateOos(BigDecimal value, TestSpecification spec) {
        if (value == null || spec == null) {
            return false;
        }
        if (spec.getLowerLimit() != null && value.compareTo(spec.getLowerLimit()) < 0) {
            return true;
        }
        if (spec.getUpperLimit() != null && value.compareTo(spec.getUpperLimit()) > 0) {
            return true;
        }
        return false;
    }

    @Transactional
    public void raiseOosDeviation(long resultId, long sampleId, String analyte,
                                  BigDecimal value, TestSpecification spec, String raisedBy) {
        long deviationId = ++resultSequence;
        Timestamp raisedAt = new Timestamp(System.currentTimeMillis());
        String description = "OOS on " + analyte + ": observed " + value
            + (spec == null ? " (no effective specification)" : " outside " + spec.describeRange());
        jdbc.update(
            "INSERT INTO DEVIATION (DEVIATION_ID, BATCH_ID, RESULT_ID, SEVERITY, DESCRIPTION, RAISED_AT, RAISED_BY, STATUS) "
          + "VALUES (?, (SELECT BATCH_ID FROM SAMPLE WHERE SAMPLE_ID = ?), ?, 'MAJOR', ?, ?, ?, 'OPEN')",
            deviationId, sampleId, resultId, description, raisedAt, raisedBy);
        auditService.recordCreation("DEVIATION", String.valueOf(deviationId), raisedBy);
    }

    @Transactional
    public void correctResult(long resultId, BigDecimal newValue, String changedBy) {
        TestResult existing = findById(resultId);
        if (existing == null) {
            throw new IllegalArgumentException("unknown result " + resultId);
        }
        jdbc.update("UPDATE RESULT SET VALUE_NUM = ? WHERE RESULT_ID = ?", newValue, resultId);
        auditService.recordChange("RESULT", String.valueOf(resultId), "VALUE_NUM",
            String.valueOf(existing.getValueNum()), String.valueOf(newValue), changedBy, "UPDATE");
    }

    @Transactional
    public void setReviewStatus(long resultId, String status, String changedBy) {
        String old = findById(resultId) == null ? null : findById(resultId).getReviewStatus();
        jdbc.update("UPDATE RESULT SET REVIEW_STATUS = ? WHERE RESULT_ID = ?", status, resultId);
        auditService.recordChange("RESULT", String.valueOf(resultId), "REVIEW_STATUS",
            old, status, changedBy, "UPDATE");
    }

    public TestResult findById(long resultId) {
        List<TestResult> rows = jdbc.query(
            "SELECT RESULT_ID, SAMPLE_ID, ANALYTE, VALUE_NUM, UNIT, SPEC_ID, OOS_FLAG, ENTERED_AT, ENTERED_BY, REVIEW_STATUS, INSTRUMENT_ID "
          + "FROM RESULT WHERE RESULT_ID = ?",
            new Object[] { resultId }, new TestResultMapper());
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<TestResult> findBySample(long sampleId) {
        return jdbc.query(
            "SELECT RESULT_ID, SAMPLE_ID, ANALYTE, VALUE_NUM, UNIT, SPEC_ID, OOS_FLAG, ENTERED_AT, ENTERED_BY, REVIEW_STATUS, INSTRUMENT_ID "
          + "FROM RESULT WHERE SAMPLE_ID = ? ORDER BY ENTERED_AT",
            new Object[] { sampleId }, new TestResultMapper());
    }

    public List<TestResult> findAwaitingReview() {
        return jdbc.query(
            "SELECT RESULT_ID, SAMPLE_ID, ANALYTE, VALUE_NUM, UNIT, SPEC_ID, OOS_FLAG, ENTERED_AT, ENTERED_BY, REVIEW_STATUS, INSTRUMENT_ID "
          + "FROM RESULT WHERE REVIEW_STATUS = 'PENDING_REVIEW' ORDER BY ENTERED_AT",
            new TestResultMapper());
    }
}
