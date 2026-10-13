package com.acme.lims.instrument;

import java.math.BigDecimal;

public class InstrumentReading {

    private long sampleId;
    private String analyte;
    private BigDecimal value;
    private String unit;
    private String instrumentId;

    public long getSampleId() { return sampleId; }
    public void setSampleId(long sampleId) { this.sampleId = sampleId; }

    public String getAnalyte() { return analyte; }
    public void setAnalyte(String analyte) { this.analyte = analyte; }

    public BigDecimal getValue() { return value; }
    public void setValue(BigDecimal value) { this.value = value; }

    public String getUnit() { return unit; }
    public void setUnit(String unit) { this.unit = unit; }

    public String getInstrumentId() { return instrumentId; }
    public void setInstrumentId(String instrumentId) { this.instrumentId = instrumentId; }
}
