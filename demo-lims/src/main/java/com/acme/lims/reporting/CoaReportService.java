package com.acme.lims.reporting;

import java.sql.Timestamp;
import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * Certificate of Analysis generation.
 *
 * Read-only against GxP data: this reads RESULT, SAMPLE, BATCH and
 * TEST_SPECIFICATION but never writes them, so it is a reporting-only
 * component and a natural first candidate to lift to the cloud.
 */
@Service
public class CoaReportService {

    private final JdbcTemplate jdbc;

    @Value("${lims.reports.output.dir}")
    private String outputDir;

    @Autowired
    public CoaReportService(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public List<Map<String, Object>> buildCoaData(long batchId) {
        return jdbc.queryForList(
            "SELECT B.BATCH_NUMBER, B.PRODUCT_CODE, B.DISPOSITION, S.SAMPLE_CODE, "
          + "R.ANALYTE, R.VALUE_NUM, R.UNIT, R.OOS_FLAG, SP.LOWER_LIMIT, SP.UPPER_LIMIT "
          + "FROM BATCH B "
          + "JOIN SAMPLE S ON S.BATCH_ID = B.BATCH_ID "
          + "JOIN RESULT R ON R.SAMPLE_ID = S.SAMPLE_ID "
          + "LEFT JOIN TEST_SPECIFICATION SP ON SP.SPEC_ID = R.SPEC_ID "
          + "WHERE B.BATCH_ID = ? AND R.REVIEW_STATUS = 'APPROVED' "
          + "ORDER BY S.SAMPLE_CODE, R.ANALYTE",
            batchId);
    }

    public List<Map<String, Object>> buildTrendData(String productCode, String analyte) {
        return jdbc.queryForList(
            "SELECT B.BATCH_NUMBER, R.VALUE_NUM, R.UNIT, R.ENTERED_AT "
          + "FROM RESULT R "
          + "JOIN SAMPLE S ON S.SAMPLE_ID = R.SAMPLE_ID "
          + "JOIN BATCH B ON B.BATCH_ID = S.BATCH_ID "
          + "WHERE B.PRODUCT_CODE = ? AND R.ANALYTE = ? AND R.REVIEW_STATUS = 'APPROVED' "
          + "ORDER BY R.ENTERED_AT",
            productCode, analyte);
    }

    public List<Map<String, Object>> buildOosSummary() {
        return jdbc.queryForList(
            "SELECT B.PRODUCT_CODE, COUNT(*) AS OOS_COUNT "
          + "FROM RESULT R JOIN SAMPLE S ON S.SAMPLE_ID = R.SAMPLE_ID "
          + "JOIN BATCH B ON B.BATCH_ID = S.BATCH_ID "
          + "WHERE R.OOS_FLAG = 'Y' GROUP BY B.PRODUCT_CODE ORDER BY OOS_COUNT DESC");
    }

    public List<Map<String, Object>> buildReviewBacklog() {
        return jdbc.queryForList(
            "SELECT R.REVIEW_STATUS, COUNT(*) AS N FROM RESULT R GROUP BY R.REVIEW_STATUS");
    }

    /**
     * Records that a CoA was produced. This is the one write in the reporting
     * module and it touches no GxP record - only the report register.
     */
    public void registerGeneratedCoa(long batchId, String generatedBy, String filePath) {
        jdbc.update(
            "INSERT INTO COA_REPORT (COA_ID, BATCH_ID, GENERATED_AT, GENERATED_BY, FILE_PATH) "
          + "VALUES (?, ?, ?, ?, ?)",
            Long.valueOf(System.currentTimeMillis() % 1000000000L), batchId,
            new Timestamp(System.currentTimeMillis()), generatedBy, filePath);
    }

    public String resolveOutputPath(String fileName) {
        return outputDir + "\\" + fileName;
    }
}
