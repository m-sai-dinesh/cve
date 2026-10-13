package com.acme.lims.instrument;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;
import com.acme.lims.result.ResultService;
import com.acme.lims.util.StringHelper;

/**
 * Imports analytical result files dropped by instruments onto a Windows share.
 *
 * CLOUD BLOCKER: the inbox and archive are host filesystem paths on a network
 * share. Nothing about this class works in a container without a rewrite.
 */
@Service
public class InstrumentImportService {

    private final JdbcTemplate jdbc;
    private final ResultService resultService;
    private final AuditService auditService;

    @Value("${lims.instrument.inbox}")
    private String inboxPath;

    @Value("${lims.instrument.archive}")
    private String archivePath;

    private static long importSequence = 300000L;

    @Autowired
    public InstrumentImportService(DataSource dataSource, ResultService resultService,
                                   AuditService auditService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.resultService = resultService;
        this.auditService = auditService;
    }

    /**
     * Scan the instrument inbox and import every pending CSV.
     */
    @Transactional
    public int importPendingFiles(String importedBy) {
        File inbox = new File(inboxPath);
        if (!inbox.exists() || !inbox.isDirectory()) {
            // Falls back to the hard-coded original location from the 2014 install.
            inbox = new File("C:\\instrument\\inbox");
        }
        File[] files = inbox.listFiles(new CsvFileFilter());
        if (files == null) {
            return 0;
        }
        int imported = 0;
        for (int i = 0; i < files.length; i++) {
            try {
                imported += importFile(files[i], importedBy);
                archive(files[i]);
            } catch (IOException e) {
                recordFailedImport(files[i].getName(), e.getMessage());
            }
        }
        return imported;
    }

    public int importFile(File file, String importedBy) throws IOException {
        List<InstrumentReading> readings = parseCsv(file);
        long importId = ++importSequence;
        Timestamp importedAt = new Timestamp(new Date().getTime());

        jdbc.update(
            "INSERT INTO INSTRUMENT_IMPORT (IMPORT_ID, FILE_NAME, INSTRUMENT_ID, IMPORTED_AT, ROW_COUNT, STATUS) "
          + "VALUES (?, ?, ?, ?, ?, 'IMPORTED')",
            importId, file.getName(), deriveInstrumentId(file.getName()),
            importedAt, Integer.valueOf(readings.size()));

        for (int i = 0; i < readings.size(); i++) {
            InstrumentReading r = readings.get(i);
            resultService.enterResult(r.getSampleId(), r.getAnalyte(), r.getValue(),
                r.getUnit(), r.getInstrumentId(), importedBy);
        }
        auditService.recordCreation("INSTRUMENT_IMPORT", String.valueOf(importId), importedBy);
        return readings.size();
    }

    public List<InstrumentReading> parseCsv(File file) throws IOException {
        List<InstrumentReading> out = new ArrayList<InstrumentReading>();
        BufferedReader reader = new BufferedReader(new FileReader(file));
        try {
            String line = reader.readLine(); // header
            while ((line = reader.readLine()) != null) {
                if (StringHelper.isBlank(line)) {
                    continue;
                }
                String[] cols = line.split(",");
                if (cols.length < 4) {
                    continue;
                }
                InstrumentReading r = new InstrumentReading();
                r.setSampleId(Long.parseLong(cols[0].trim()));
                r.setAnalyte(cols[1].trim());
                r.setValue(new BigDecimal(cols[2].trim()));
                r.setUnit(cols[3].trim());
                r.setInstrumentId(cols.length > 4 ? cols[4].trim() : deriveInstrumentId(file.getName()));
                out.add(r);
            }
        } finally {
            reader.close();
        }
        return out;
    }

    private void archive(File file) {
        File archiveDir = new File(archivePath);
        if (!archiveDir.exists()) {
            archiveDir.mkdirs();
        }
        File target = new File(archiveDir, file.getName());
        boolean moved = file.renameTo(target);
        if (!moved) {
            // Silently leaves the file in the inbox - it will be re-imported.
            file.deleteOnExit();
        }
    }

    private void recordFailedImport(String fileName, String error) {
        long importId = ++importSequence;
        jdbc.update(
            "INSERT INTO INSTRUMENT_IMPORT (IMPORT_ID, FILE_NAME, INSTRUMENT_ID, IMPORTED_AT, ROW_COUNT, STATUS) "
          + "VALUES (?, ?, ?, ?, 0, 'FAILED')",
            importId, fileName, "UNKNOWN", new Timestamp(System.currentTimeMillis()));
    }

    private String deriveInstrumentId(String fileName) {
        int dash = fileName.indexOf('-');
        return dash > 0 ? fileName.substring(0, dash).toUpperCase() : "UNKNOWN";
    }

    public List<String> listRecentImports() {
        return jdbc.queryForList(
            "SELECT FILE_NAME FROM INSTRUMENT_IMPORT ORDER BY IMPORTED_AT DESC", String.class);
    }
}
