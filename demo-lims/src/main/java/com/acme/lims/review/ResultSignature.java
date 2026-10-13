package com.acme.lims.review;

import java.util.Date;

public class ResultSignature {

    private long sigId;
    private long resultId;
    private String signedBy;
    private Date signedAt;
    private String signatureMeaning;
    private String signatureHash;

    public long getSigId() { return sigId; }
    public void setSigId(long sigId) { this.sigId = sigId; }

    public long getResultId() { return resultId; }
    public void setResultId(long resultId) { this.resultId = resultId; }

    public String getSignedBy() { return signedBy; }
    public void setSignedBy(String signedBy) { this.signedBy = signedBy; }

    public Date getSignedAt() { return signedAt; }
    public void setSignedAt(Date signedAt) { this.signedAt = signedAt; }

    public String getSignatureMeaning() { return signatureMeaning; }
    public void setSignatureMeaning(String signatureMeaning) { this.signatureMeaning = signatureMeaning; }

    public String getSignatureHash() { return signatureHash; }
    public void setSignatureHash(String signatureHash) { this.signatureHash = signatureHash; }
}
