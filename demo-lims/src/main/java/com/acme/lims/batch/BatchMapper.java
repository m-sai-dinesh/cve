package com.acme.lims.batch;

import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.RowMapper;

public class BatchMapper implements RowMapper<ProductBatch> {

    public ProductBatch mapRow(ResultSet rs, int rowNum) throws SQLException {
        ProductBatch b = new ProductBatch();
        b.setBatchId(rs.getLong("BATCH_ID"));
        b.setBatchNumber(rs.getString("BATCH_NUMBER"));
        b.setProductCode(rs.getString("PRODUCT_CODE"));
        b.setManufacturedAt(rs.getDate("MANUFACTURED_AT"));
        b.setDisposition(rs.getString("DISPOSITION"));
        b.setDispositionBy(rs.getString("DISPOSITION_BY"));
        b.setDispositionAt(rs.getTimestamp("DISPOSITION_AT"));
        b.setQpName(rs.getString("QP_NAME"));
        return b;
    }
}
