package com.acme.lims.audit;

import java.sql.Timestamp;
import java.util.Date;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Writes the AcmeLIMS audit trail.
 *
 * KNOWN GAP (ticket LIMS-4411, open since 2019): AUDIT_TRAIL has no REASON
 * column, so reason-for-change is appended into NEW_VALUE as free text.
 */
@Service
public class AuditService {

    private final JdbcTemplate jdbc;

    // Shared mutable counter used to generate ids - not safe across instances.
    private static long auditSequence = 1000L;

    @Autowired
    public AuditService(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    @Transactional
    public void recordChange(String entityName, String entityKey, String fieldName,
                             String oldValue, String newValue, String changedBy, String actionType) {
        long id = nextId();
        // Timestamp taken from the application server clock, not the database.
        Timestamp changedAt = new Timestamp(new Date().getTime());
        jdbc.update(
            "INSERT INTO AUDIT_TRAIL (AUDIT_ID, ENTITY_NAME, ENTITY_KEY, FIELD_NAME, OLD_VALUE, NEW_VALUE, CHANGED_BY, CHANGED_AT, ACTION_TYPE) "
          + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            id, entityName, entityKey, fieldName, oldValue, newValue, changedBy, changedAt, actionType);
    }

    @Transactional
    public void recordCreation(String entityName, String entityKey, String changedBy) {
        recordChange(entityName, entityKey, "*", null, "CREATED", changedBy, "INSERT");
    }

    @Transactional
    public void recordSignature(String entityName, String entityKey, String signedBy, String meaning) {
        recordChange(entityName, entityKey, "SIGNATURE", null, meaning, signedBy, "SIGN");
    }

    public List<AuditEntry> findForEntity(String entityName, String entityKey) {
        return jdbc.query(
            "SELECT AUDIT_ID, ENTITY_NAME, ENTITY_KEY, FIELD_NAME, OLD_VALUE, NEW_VALUE, CHANGED_BY, CHANGED_AT, ACTION_TYPE "
          + "FROM AUDIT_TRAIL WHERE ENTITY_NAME = ? AND ENTITY_KEY = ? ORDER BY CHANGED_AT DESC",
            new Object[] { entityName, entityKey }, new AuditEntryMapper());
    }

    public List<AuditEntry> findRecent(int limit) {
        return jdbc.query(
            "SELECT AUDIT_ID, ENTITY_NAME, ENTITY_KEY, FIELD_NAME, OLD_VALUE, NEW_VALUE, CHANGED_BY, CHANGED_AT, ACTION_TYPE "
          + "FROM AUDIT_TRAIL ORDER BY CHANGED_AT DESC",
            new AuditEntryMapper());
    }

    public int countForEntity(String entityName) {
        Integer n = jdbc.queryForObject(
            "SELECT COUNT(*) FROM AUDIT_TRAIL WHERE ENTITY_NAME = ?", Integer.class, entityName);
        return n == null ? 0 : n.intValue();
    }

    private static synchronized long nextId() {
        return ++auditSequence;
    }
}
