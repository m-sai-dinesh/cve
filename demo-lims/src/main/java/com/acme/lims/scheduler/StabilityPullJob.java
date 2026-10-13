package com.acme.lims.scheduler;

import java.sql.Timestamp;
import java.util.Date;
import java.util.List;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import com.acme.lims.audit.AuditService;
import com.acme.lims.instrument.InstrumentImportService;
import com.acme.lims.sample.SampleService;

/**
 * Nightly stability-study pull.
 *
 * SCHEDULING BLOCKER: @Scheduled on a singleton means two instances behind a
 * load balancer both run the job. There is no leader election and no lock, so
 * this component cannot simply be scaled horizontally.
 */
@Component
public class StabilityPullJob {

    private final JdbcTemplate jdbc;
    private final SampleService sampleService;
    private final InstrumentImportService instrumentImportService;
    private final AuditService auditService;

    private static long studySequence = 100000L;

    @Autowired
    public StabilityPullJob(DataSource dataSource, SampleService sampleService,
                            InstrumentImportService instrumentImportService,
                            AuditService auditService) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.sampleService = sampleService;
        this.instrumentImportService = instrumentImportService;
        this.auditService = auditService;
    }

    @Scheduled(cron = "${lims.stability.pull.cron}")
    @Transactional
    public void pullDueTimepoints() {
        List<Map<String, Object>> due = jdbc.queryForList(
            "SELECT STUDY_ID, PRODUCT_CODE, TIMEPOINT, CONDITION_TEXT FROM STABILITY_STUDY "
          + "WHERE PULLED_AT IS NULL ORDER BY STUDY_ID");

        for (int i = 0; i < due.size(); i++) {
            Map<String, Object> row = due.get(i);
            Long studyId = Long.valueOf(String.valueOf(row.get("STUDY_ID")));
            String productCode = String.valueOf(row.get("PRODUCT_CODE"));
            String timepoint = String.valueOf(row.get("TIMEPOINT"));

            long sampleId = sampleService.registerSample(
                "STB-" + studyId + "-" + timepoint, productCode, null,
                "STABILITY", "SCHEDULER");

            jdbc.update(
                "UPDATE STABILITY_STUDY SET PULLED_AT = ?, SAMPLE_ID = ? WHERE STUDY_ID = ?",
                new Timestamp(new Date().getTime()), sampleId, studyId);

            auditService.recordChange("STABILITY_STUDY", String.valueOf(studyId), "PULLED_AT",
                null, "pulled as sample " + sampleId, "SCHEDULER", "UPDATE");
        }
    }

    @Scheduled(cron = "${lims.instrument.poll.cron}")
    public void pollInstrumentInbox() {
        instrumentImportService.importPendingFiles("SCHEDULER");
    }

    @Scheduled(fixedDelay = 86400000L)
    public void purgeStaleImports() {
        jdbc.update("DELETE FROM INSTRUMENT_IMPORT WHERE STATUS = 'FAILED'");
    }

    private static synchronized long nextStudyId() {
        return ++studySequence;
    }
}
