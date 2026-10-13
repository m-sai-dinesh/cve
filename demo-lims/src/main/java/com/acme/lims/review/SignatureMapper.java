package com.acme.lims.review;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;

public class SignatureMapper implements RowMapper<ResultSignature> {

    public ResultSignature mapRow(ResultSet rs, int rowNum) throws SQLException {
        ResultSignature s = new ResultSignature();
        s.setSigId(rs.getLong("SIG_ID"));
        s.setResultId(rs.getLong("RESULT_ID"));
        s.setSignedBy(rs.getString("SIGNED_BY"));
        s.setSignedAt(rs.getTimestamp("SIGNED_AT"));
        s.setSignatureMeaning(rs.getString("SIGNATURE_MEANING"));
        s.setSignatureHash(rs.getString("SIGNATURE_HASH"));
        return s;
    }
}
