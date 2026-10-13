package com.acme.lims.sample;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;

public class SampleMapper implements RowMapper<Sample> {

    public Sample mapRow(ResultSet rs, int rowNum) throws SQLException {
        Sample s = new Sample();
        s.setSampleId(rs.getLong("SAMPLE_ID"));
        s.setSampleCode(rs.getString("SAMPLE_CODE"));
        s.setProductCode(rs.getString("PRODUCT_CODE"));
        s.setBatchId(rs.getLong("BATCH_ID"));
        s.setMatrix(rs.getString("MATRIX"));
        s.setReceivedAt(rs.getTimestamp("RECEIVED_AT"));
        s.setReceivedBy(rs.getString("RECEIVED_BY"));
        s.setStatus(rs.getString("STATUS"));
        s.setCustodyNote(rs.getString("CUSTODY_NOTE"));
        return s;
    }
}
