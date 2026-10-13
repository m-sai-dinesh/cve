package com.acme.lims.result;

import java.math.BigDecimal;
import java.util.Date;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "TEST_SPECIFICATION")
public class TestSpecification {

    @Id
    @Column(name = "SPEC_ID")
    private long specId;

    @Column(name = "PRODUCT_CODE")
    private String productCode;

    @Column(name = "ANALYTE")
    private String analyte;

    @Column(name = "LOWER_LIMIT")
    private BigDecimal lowerLimit;

    @Column(name = "UPPER_LIMIT")
    private BigDecimal upperLimit;

    @Column(name = "UNIT")
    private String unit;

    @Column(name = "EFFECTIVE_FROM")
    private Date effectiveFrom;

    @Column(name = "VERSION")
    private int version;

    public String describeRange() {
        return "[" + lowerLimit + ", " + upperLimit + "] " + unit;
    }

    public long getSpecId() { return specId; }
    public void setSpecId(long specId) { this.specId = specId; }

    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }

    public String getAnalyte() { return analyte; }
    public void setAnalyte(String analyte) { this.analyte = analyte; }

    public BigDecimal getLowerLimit() { return lowerLimit; }
    public void setLowerLimit(BigDecimal lowerLimit) { this.lowerLimit = lowerLimit; }

    public BigDecimal getUpperLimit() { return upperLimit; }
    public void setUpperLimit(BigDecimal upperLimit) { this.upperLimit = upperLimit; }

    public String getUnit() { return unit; }
    public void setUnit(String unit) { this.unit = unit; }

    public Date getEffectiveFrom() { return effectiveFrom; }
    public void setEffectiveFrom(Date effectiveFrom) { this.effectiveFrom = effectiveFrom; }

    public int getVersion() { return version; }
    public void setVersion(int version) { this.version = version; }
}
