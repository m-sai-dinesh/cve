package com.acme.lims.batch;

import java.util.ArrayList;
import java.util.List;

public class ReleaseCheck {

    private final long batchId;
    private final List<String> blockers = new ArrayList<String>();

    public ReleaseCheck(long batchId) {
        this.batchId = batchId;
    }

    public void addBlocker(String blocker) {
        this.blockers.add(blocker);
    }

    public boolean isReleasable() {
        return blockers.isEmpty();
    }

    public long getBatchId() {
        return batchId;
    }

    public String getBlockers() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < blockers.size(); i++) {
            if (i > 0) {
                sb.append("; ");
            }
            sb.append(blockers.get(i));
        }
        return sb.toString();
    }

    public List<String> getBlockerList() {
        return blockers;
    }
}
