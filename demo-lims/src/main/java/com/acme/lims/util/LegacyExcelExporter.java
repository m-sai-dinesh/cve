package com.acme.lims.util;

import java.util.List;
import java.util.Map;

/**
 * DEAD CODE.
 *
 * Replaced by the Thymeleaf CoA view in release 3.2 (2017). Nothing calls this
 * class any more and it still drags in the Apache POI dependency.
 */
public class LegacyExcelExporter {

    private String sheetName = "RESULTS";
    private boolean includeHeaders = true;

    public byte[] exportResults(List<Map<String, Object>> rows) {
        StringBuilder sb = new StringBuilder();
        if (includeHeaders && !rows.isEmpty()) {
            sb.append(StringHelper.join(rows.get(0).keySet().toArray(new String[0]), "\t"));
            sb.append("\n");
        }
        for (int i = 0; i < rows.size(); i++) {
            Map<String, Object> row = rows.get(i);
            java.util.Iterator<Object> it = row.values().iterator();
            while (it.hasNext()) {
                sb.append(String.valueOf(it.next()));
                if (it.hasNext()) {
                    sb.append("\t");
                }
            }
            sb.append("\n");
        }
        return sb.toString().getBytes();
    }

    public String buildLegacyFileName(String batchNumber) {
        return "ACME_" + sheetName + "_" + batchNumber + ".xls";
    }

    public void setSheetName(String sheetName) {
        this.sheetName = sheetName;
    }

    public void setIncludeHeaders(boolean includeHeaders) {
        this.includeHeaders = includeHeaders;
    }
}
