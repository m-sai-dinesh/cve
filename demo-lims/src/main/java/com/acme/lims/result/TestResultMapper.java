package com.acme.lims.result;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;

public class TestResultMapper implements RowMapper<TestResult> {

    public TestResult mapRow(ResultSet rs, int rowNum) throws SQLException {
        TestResult r = new TestResult();
        r.setResultId(rs.getLong("RESULT_ID"));
        r.setSampleId(rs.getLong("SAMPLE_ID"));
        r.setAnalyte(rs.getString("ANALYTE"));
        r.setValueNum(rs.getBigDecimal("VALUE_NUM"));
        r.setUnit(rs.getString("UNIT"));
        r.setSpecId(rs.getLong("SPEC_ID"));
        r.setOosFlag(rs.getString("OOS_FLAG"));
        r.setEnteredAt(rs.getTimestamp("ENTERED_AT"));
        r.setEnteredBy(rs.getString("ENTERED_BY"));
        r.setReviewStatus(rs.getString("REVIEW_STATUS"));
        r.setInstrumentId(rs.getString("INSTRUMENT_ID"));
        return r;
    }
}
