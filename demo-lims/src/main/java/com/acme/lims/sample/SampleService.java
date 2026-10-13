package com.acme.lims.sample;

import java.sql.Timestamp;
import java.util.Date;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;
import com.acme.lims.util.DateHelper;
import com.acme.lims.util.StringHelper;

/**
 * Sample registration and chain of custody.
 *
 * GxP: creates GxP records in SAMPLE, so writes here are data-integrity
 * relevant and carry an audit-trail obligation.
 */
@Service
public class SampleService {

    private final JdbcTemplate jdbc;
    private final AuditService auditService;

    private static long sampleSequence = 500000L;

    @Autowired
    public SampleService(DataSource dataSource, AuditService auditService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.auditService = auditService;
    }

    @Transactional
    public long registerSample(String sampleCode, String productCode, Long batchId,
                               String matrix, String receivedBy) {
        if (StringHelper.isBlank(sampleCode)) {
            throw new IllegalArgumentException("sampleCode is required");
        }
        long sampleId = ++sampleSequence;
        // Timestamp comes from the application server's local clock.
        Timestamp receivedAt = new Timestamp(new Date().getTime());

        jdbc.update(
            "INSERT INTO SAMPLE (SAMPLE_ID, SAMPLE_CODE, PRODUCT_CODE, BATCH_ID, MATRIX, RECEIVED_AT, RECEIVED_BY, STATUS, CUSTODY_NOTE) "
          + "VALUES (?, ?, ?, ?, ?, ?, ?, 'REGISTERED', ?)",
            sampleId, sampleCode, productCode, batchId, matrix, receivedAt, receivedBy,
            "Registered at " + DateHelper.formatLong(receivedAt));

        auditService.recordCreation("SAMPLE", String.valueOf(sampleId), receivedBy);
        recordCustody(sampleId, "RECEPTION", "SAMPLE_STORE", receivedBy);
        return sampleId;
    }

    @Transactional
    public void recordCustody(long sampleId, String fromLocation, String toLocation, String movedBy) {
        long cocId = ++sampleSequence;
        Timestamp movedAt = new Timestamp(System.currentTimeMillis());
        jdbc.update(
            "INSERT INTO CHAIN_OF_CUSTODY (COC_ID, SAMPLE_ID, FROM_LOCATION, TO_LOCATION, MOVED_AT, MOVED_BY) "
          + "VALUES (?, ?, ?, ?, ?, ?)",
            cocId, sampleId, fromLocation, toLocation, movedAt, movedBy);
        auditService.recordChange("SAMPLE", String.valueOf(sampleId), "LOCATION",
            fromLocation, toLocation, movedBy, "UPDATE");
    }

    @Transactional
    public void updateStatus(long sampleId, String newStatus, String changedBy) {
        String oldStatus = findStatus(sampleId);
        jdbc.update("UPDATE SAMPLE SET STATUS = ? WHERE SAMPLE_ID = ?", newStatus, sampleId);
        auditService.recordChange("SAMPLE", String.valueOf(sampleId), "STATUS",
            oldStatus, newStatus, changedBy, "UPDATE");
    }

    public String findStatus(long sampleId) {
        List<String> rows = jdbc.queryForList(
            "SELECT STATUS FROM SAMPLE WHERE SAMPLE_ID = ?", String.class, sampleId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Sample findById(long sampleId) {
        List<Sample> rows = jdbc.query(
            "SELECT SAMPLE_ID, SAMPLE_CODE, PRODUCT_CODE, BATCH_ID, MATRIX, RECEIVED_AT, RECEIVED_BY, STATUS, CUSTODY_NOTE "
          + "FROM SAMPLE WHERE SAMPLE_ID = ?",
            new Object[] { sampleId }, new SampleMapper());
        return rows.isEmpty() ? null : rows.get(0);
    }

    public List<Sample> findByBatch(long batchId) {
        return jdbc.query(
            "SELECT SAMPLE_ID, SAMPLE_CODE, PRODUCT_CODE, BATCH_ID, MATRIX, RECEIVED_AT, RECEIVED_BY, STATUS, CUSTODY_NOTE "
          + "FROM SAMPLE WHERE BATCH_ID = ? ORDER BY RECEIVED_AT",
            new Object[] { batchId }, new SampleMapper());
    }

    public List<Sample> findPending() {
        return jdbc.query(
            "SELECT SAMPLE_ID, SAMPLE_CODE, PRODUCT_CODE, BATCH_ID, MATRIX, RECEIVED_AT, RECEIVED_BY, STATUS, CUSTODY_NOTE "
          + "FROM SAMPLE WHERE STATUS = 'REGISTERED' ORDER BY RECEIVED_AT",
            new SampleMapper());
    }
}
