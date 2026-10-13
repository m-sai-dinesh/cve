package com.acme.lims.instrument;

import java.io.File;
import java.io.FilenameFilter;

public class CsvFileFilter implements FilenameFilter {

    public boolean accept(File dir, String name) {
        String lower = name.toLowerCase();
        return lower.endsWith(".csv") || lower.endsWith(".txt");
    }
}
