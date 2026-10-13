package com.acme.lims.result;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;

/**
 * Serves effective test specifications.
 *
 * Specifications are GxP master data: an out-of-date limit silently changes
 * every OOS decision downstream.
 */
@Service
public class SpecificationService {

    private final JdbcTemplate jdbc;
    private final AuditService auditService;

    // In-memory cache, never invalidated across instances (statelessness blocker).
    private static final Map<String, TestSpecification> SPEC_CACHE = new HashMap<String, TestSpecification>();

    @Autowired
    public SpecificationService(DataSource dataSource, AuditService auditService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.auditService = auditService;
    }

    public TestSpecification findEffectiveSpec(long sampleId, String analyte) {
        String cacheKey = sampleId + "|" + analyte;
        if (SPEC_CACHE.containsKey(cacheKey)) {
            return SPEC_CACHE.get(cacheKey);
        }
        List<TestSpecification> rows = jdbc.query(
            "SELECT S.SPEC_ID, S.PRODUCT_CODE, S.ANALYTE, S.LOWER_LIMIT, S.UPPER_LIMIT, S.UNIT, S.EFFECTIVE_FROM, S.VERSION "
          + "FROM TEST_SPECIFICATION S JOIN SAMPLE SA ON SA.PRODUCT_CODE = S.PRODUCT_CODE "
          + "WHERE SA.SAMPLE_ID = ? AND S.ANALYTE = ? ORDER BY S.VERSION DESC",
            new Object[] { sampleId, analyte }, new SpecMapper());
        TestSpecification spec = rows.isEmpty() ? null : rows.get(0);
        SPEC_CACHE.put(cacheKey, spec);
        return spec;
    }

    public List<TestSpecification> findByProduct(String productCode) {
        return jdbc.query(
            "SELECT SPEC_ID, PRODUCT_CODE, ANALYTE, LOWER_LIMIT, UPPER_LIMIT, UNIT, EFFECTIVE_FROM, VERSION "
          + "FROM TEST_SPECIFICATION WHERE PRODUCT_CODE = ? ORDER BY ANALYTE, VERSION DESC",
            new Object[] { productCode }, new SpecMapper());
    }

    @Transactional
    public void reviseSpecification(long specId, java.math.BigDecimal lower,
                                    java.math.BigDecimal upper, String changedBy) {
        jdbc.update("UPDATE TEST_SPECIFICATION SET LOWER_LIMIT = ?, UPPER_LIMIT = ?, VERSION = VERSION + 1 WHERE SPEC_ID = ?",
            lower, upper, specId);
        auditService.recordChange("TEST_SPECIFICATION", String.valueOf(specId), "LIMITS",
            null, lower + ".." + upper, changedBy, "UPDATE");
        SPEC_CACHE.clear();
    }

    private static class SpecMapper implements RowMapper<TestSpecification> {
        public TestSpecification mapRow(ResultSet rs, int rowNum) throws SQLException {
            TestSpecification s = new TestSpecification();
            s.setSpecId(rs.getLong("SPEC_ID"));
            s.setProductCode(rs.getString("PRODUCT_CODE"));
            s.setAnalyte(rs.getString("ANALYTE"));
            s.setLowerLimit(rs.getBigDecimal("LOWER_LIMIT"));
            s.setUpperLimit(rs.getBigDecimal("UPPER_LIMIT"));
            s.setUnit(rs.getString("UNIT"));
            s.setEffectiveFrom(rs.getDate("EFFECTIVE_FROM"));
            s.setVersion(rs.getInt("VERSION"));
            return s;
        }
    }
}
