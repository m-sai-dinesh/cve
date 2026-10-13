package com.acme.lims.result;

import java.math.BigDecimal;
import java.util.Date;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "RESULT")
public class TestResult {

    @Id
    @Column(name = "RESULT_ID")
    private long resultId;

    @Column(name = "SAMPLE_ID")
    private long sampleId;

    @Column(name = "ANALYTE")
    private String analyte;

    @Column(name = "VALUE_NUM")
    private BigDecimal valueNum;

    @Column(name = "UNIT")
    private String unit;

    @Column(name = "SPEC_ID")
    private Long specId;

    @Column(name = "OOS_FLAG")
    private String oosFlag;

    @Column(name = "ENTERED_AT")
    private Date enteredAt;

    @Column(name = "ENTERED_BY")
    private String enteredBy;

    @Column(name = "REVIEW_STATUS")
    private String reviewStatus;

    @Column(name = "INSTRUMENT_ID")
    private String instrumentId;

    public boolean isOos() { return "Y".equals(oosFlag); }

    public long getResultId() { return resultId; }
    public void setResultId(long resultId) { this.resultId = resultId; }

    public long getSampleId() { return sampleId; }
    public void setSampleId(long sampleId) { this.sampleId = sampleId; }

    public String getAnalyte() { return analyte; }
    public void setAnalyte(String analyte) { this.analyte = analyte; }

    public BigDecimal getValueNum() { return valueNum; }
    public void setValueNum(BigDecimal valueNum) { this.valueNum = valueNum; }

    public String getUnit() { return unit; }
    public void setUnit(String unit) { this.unit = unit; }

    public Long getSpecId() { return specId; }
    public void setSpecId(Long specId) { this.specId = specId; }

    public String getOosFlag() { return oosFlag; }
    public void setOosFlag(String oosFlag) { this.oosFlag = oosFlag; }

    public Date getEnteredAt() { return enteredAt; }
    public void setEnteredAt(Date enteredAt) { this.enteredAt = enteredAt; }

    public String getEnteredBy() { return enteredBy; }
    public void setEnteredBy(String enteredBy) { this.enteredBy = enteredBy; }

    public String getReviewStatus() { return reviewStatus; }
    public void setReviewStatus(String reviewStatus) { this.reviewStatus = reviewStatus; }

    public String getInstrumentId() { return instrumentId; }
    public void setInstrumentId(String instrumentId) { this.instrumentId = instrumentId; }
}
