package com.acme.lims.audit;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;

public class AuditEntryMapper implements RowMapper<AuditEntry> {

    public AuditEntry mapRow(ResultSet rs, int rowNum) throws SQLException {
        AuditEntry e = new AuditEntry();
        e.setAuditId(rs.getLong("AUDIT_ID"));
        e.setEntityName(rs.getString("ENTITY_NAME"));
        e.setEntityKey(rs.getString("ENTITY_KEY"));
        e.setFieldName(rs.getString("FIELD_NAME"));
        e.setOldValue(rs.getString("OLD_VALUE"));
        e.setNewValue(rs.getString("NEW_VALUE"));
        e.setChangedBy(rs.getString("CHANGED_BY"));
        e.setChangedAt(rs.getTimestamp("CHANGED_AT"));
        e.setActionType(rs.getString("ACTION_TYPE"));
        return e;
    }
}
