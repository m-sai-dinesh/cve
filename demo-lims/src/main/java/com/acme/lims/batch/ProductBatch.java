package com.acme.lims.batch;

import java.util.Date;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "BATCH")
public class ProductBatch {

    @Id
    @Column(name = "BATCH_ID")
    private long batchId;

    @Column(name = "BATCH_NUMBER")
    private String batchNumber;

    @Column(name = "PRODUCT_CODE")
    private String productCode;

    @Column(name = "MANUFACTURED_AT")
    private Date manufacturedAt;

    @Column(name = "DISPOSITION")
    private String disposition;

    @Column(name = "DISPOSITION_BY")
    private String dispositionBy;

    @Column(name = "DISPOSITION_AT")
    private Date dispositionAt;

    @Column(name = "QP_NAME")
    private String qpName;

    public boolean isReleased() { return "RELEASED".equals(disposition); }

    public long getBatchId() { return batchId; }
    public void setBatchId(long batchId) { this.batchId = batchId; }

    public String getBatchNumber() { return batchNumber; }
    public void setBatchNumber(String batchNumber) { this.batchNumber = batchNumber; }

    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }

    public Date getManufacturedAt() { return manufacturedAt; }
    public void setManufacturedAt(Date manufacturedAt) { this.manufacturedAt = manufacturedAt; }

    public String getDisposition() { return disposition; }
    public void setDisposition(String disposition) { this.disposition = disposition; }

    public String getDispositionBy() { return dispositionBy; }
    public void setDispositionBy(String dispositionBy) { this.dispositionBy = dispositionBy; }

    public Date getDispositionAt() { return dispositionAt; }
    public void setDispositionAt(Date dispositionAt) { this.dispositionAt = dispositionAt; }

    public String getQpName() { return qpName; }
    public void setQpName(String qpName) { this.qpName = qpName; }
}
