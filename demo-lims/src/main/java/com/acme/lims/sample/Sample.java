package com.acme.lims.sample;

import java.util.Date;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "SAMPLE")
public class Sample {

    @Id
    @Column(name = "SAMPLE_ID")
    private long sampleId;

    @Column(name = "SAMPLE_CODE")
    private String sampleCode;

    @Column(name = "PRODUCT_CODE")
    private String productCode;

    @Column(name = "BATCH_ID")
    private Long batchId;

    @Column(name = "MATRIX")
    private String matrix;

    @Column(name = "RECEIVED_AT")
    private Date receivedAt;

    @Column(name = "RECEIVED_BY")
    private String receivedBy;

    @Column(name = "STATUS")
    private String status;

    @Column(name = "CUSTODY_NOTE")
    private String custodyNote;

    public long getSampleId() { return sampleId; }
    public void setSampleId(long sampleId) { this.sampleId = sampleId; }

    public String getSampleCode() { return sampleCode; }
    public void setSampleCode(String sampleCode) { this.sampleCode = sampleCode; }

    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }

    public Long getBatchId() { return batchId; }
    public void setBatchId(Long batchId) { this.batchId = batchId; }

    public String getMatrix() { return matrix; }
    public void setMatrix(String matrix) { this.matrix = matrix; }

    public Date getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Date receivedAt) { this.receivedAt = receivedAt; }

    public String getReceivedBy() { return receivedBy; }
    public void setReceivedBy(String receivedBy) { this.receivedBy = receivedBy; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getCustodyNote() { return custodyNote; }
    public void setCustodyNote(String custodyNote) { this.custodyNote = custodyNote; }
}
