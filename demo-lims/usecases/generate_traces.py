"""Generate OpenTelemetry traces for the AcmeLIMS demo use cases.

In a full lab setup you attach the OpenTelemetry Java agent to AcmeLIMS and run
``usecases/*.http``; the agent exports OTLP spans and ModernRx ingests them.
Running the agent needs Java 17 + Maven + a populated H2 database, which no
longer has to be true of the machine giving the demo — so this script produces
the *same OTLP/JSON payload* the agent would, from the real call structure of
the Java source.

The call chains below mirror the actual method bodies in demo-lims/src. Keeping
them honest matters: these spans become `runtime hits` and `use-case membership`,
which feed the Runtime term of the decomposition similarity matrix.

    python demo-lims/usecases/generate_traces.py
"""
from __future__ import annotations

import gzip
import json
import random
from pathlib import Path

# Gzipped: the uncompressed payload is ~8 MB, which has no business living in a
# git repository. The trace ingester reads .json and .json.gz alike.
OUT = Path(__file__).resolve().parent / "acmelims-traces.json.gz"

P = "com.acme.lims"

# Each use case: (name, invocations, [(fqn, depth, self_ms)])
USE_CASES: list[tuple[str, int, list[tuple[str, int, float]]]] = [
    ("Register sample", 240, [
        (f"{P}.sample.SampleController.register", 0, 1.1),
        (f"{P}.sample.SampleService.registerSample", 1, 2.4),
        (f"{P}.util.StringHelper.isBlank", 2, 0.02),
        (f"{P}.util.DateHelper.formatLong", 2, 0.08),
        (f"{P}.audit.AuditService.recordCreation", 2, 1.6),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
        (f"{P}.sample.SampleService.recordCustody", 2, 2.0),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
    ]),
    ("Enter result", 610, [
        (f"{P}.result.ResultController.enter", 0, 1.0),
        (f"{P}.result.ResultService.enterResult", 1, 3.6),
        (f"{P}.result.SpecificationService.findEffectiveSpec", 2, 4.2),
        (f"{P}.result.ResultService.evaluateOos", 2, 0.05),
        (f"{P}.audit.AuditService.recordCreation", 2, 1.6),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
        (f"{P}.sample.SampleService.updateStatus", 2, 2.2),
        (f"{P}.sample.SampleService.findStatus", 3, 0.9),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
    ]),
    ("Enter OOS result", 48, [
        (f"{P}.result.ResultController.enter", 0, 1.0),
        (f"{P}.result.ResultService.enterResult", 1, 3.6),
        (f"{P}.result.SpecificationService.findEffectiveSpec", 2, 4.2),
        (f"{P}.result.ResultService.evaluateOos", 2, 0.05),
        (f"{P}.result.TestSpecification.describeRange", 3, 0.03),
        (f"{P}.result.ResultService.raiseOosDeviation", 2, 3.1),
        (f"{P}.audit.AuditService.recordCreation", 3, 1.6),
        (f"{P}.audit.AuditService.recordChange", 4, 1.4),
    ]),
    ("Review and sign result", 520, [
        (f"{P}.review.ReviewController.approve", 0, 1.0),
        (f"{P}.review.ReviewService.approveResult", 1, 4.0),
        (f"{P}.review.ReviewService.verifyReviewer", 2, 62.0),   # bcrypt
        (f"{P}.result.ResultService.findById", 2, 1.2),
        (f"{P}.result.ResultService.setReviewStatus", 2, 2.3),
        (f"{P}.result.ResultService.findById", 3, 1.2),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
        (f"{P}.audit.AuditService.recordSignature", 2, 1.7),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
    ]),
    ("Release batch", 96, [
        (f"{P}.batch.BatchController.release", 0, 1.0),
        (f"{P}.batch.BatchReleaseService.releaseBatch", 1, 5.5),
        (f"{P}.review.ReviewService.verifyReviewer", 2, 62.0),
        (f"{P}.batch.BatchReleaseService.evaluateReleaseReadiness", 2, 11.0),
        (f"{P}.sample.SampleService.findByBatch", 3, 3.4),
        (f"{P}.review.ReviewService.isFullyReviewed", 3, 1.9),
        (f"{P}.batch.ReleaseCheck.addBlocker", 3, 0.01),
        (f"{P}.batch.BatchReleaseService.findDisposition", 2, 1.1),
        (f"{P}.audit.AuditService.recordChange", 2, 1.4),
    ]),
    ("Print certificate of analysis", 310, [
        (f"{P}.reporting.ReportingController.coa", 0, 1.0),
        (f"{P}.reporting.CoaReportService.buildCoaData", 1, 18.5),
    ]),
    ("Trend report", 140, [
        (f"{P}.reporting.ReportingController.trend", 0, 1.0),
        (f"{P}.reporting.CoaReportService.buildTrendData", 1, 22.0),
    ]),
    ("OOS summary dashboard", 85, [
        (f"{P}.reporting.ReportingController.oos", 0, 1.0),
        (f"{P}.reporting.CoaReportService.buildOosSummary", 1, 26.0),
        (f"{P}.reporting.ReportingController.backlog", 0, 1.0),
        (f"{P}.reporting.CoaReportService.buildReviewBacklog", 1, 6.0),
    ]),
    ("Nightly stability pull", 14, [
        (f"{P}.scheduler.StabilityPullJob.pullDueTimepoints", 0, 4.0),
        (f"{P}.sample.SampleService.registerSample", 1, 2.4),
        (f"{P}.util.StringHelper.isBlank", 2, 0.02),
        (f"{P}.util.DateHelper.formatLong", 2, 0.08),
        (f"{P}.audit.AuditService.recordCreation", 2, 1.6),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
        (f"{P}.sample.SampleService.recordCustody", 2, 2.0),
        (f"{P}.audit.AuditService.recordChange", 3, 1.4),
    ]),
    ("Instrument file import", 72, [
        (f"{P}.scheduler.StabilityPullJob.pollInstrumentInbox", 0, 2.0),
        (f"{P}.instrument.InstrumentImportService.importPendingFiles", 1, 14.0),
        (f"{P}.instrument.CsvFileFilter.accept", 2, 0.01),
        (f"{P}.instrument.InstrumentImportService.importFile", 2, 9.0),
        (f"{P}.instrument.InstrumentImportService.parseCsv", 3, 12.0),
        (f"{P}.util.StringHelper.isBlank", 4, 0.02),
        (f"{P}.result.ResultService.enterResult", 3, 3.6),
        (f"{P}.result.SpecificationService.findEffectiveSpec", 4, 4.2),
        (f"{P}.audit.AuditService.recordCreation", 3, 1.6),
    ]),
    ("Admin creates analyst", 9, [
        (f"{P}.admin.AdminController.create", 0, 1.0),
        (f"{P}.admin.UserAdminService.createUser", 1, 70.0),
        (f"{P}.audit.AuditService.recordCreation", 2, 1.6),
        (f"{P}.admin.AdminController.assignRole", 0, 1.0),
        (f"{P}.admin.UserAdminService.assignRole", 1, 2.2),
        (f"{P}.audit.AuditService.recordChange", 2, 1.4),
    ]),
]

SERVICE = "acme-lims"
BASE_NS = 1_760_000_000_000_000_000  # fixed epoch → reproducible fixtures


def main() -> None:
    rng = random.Random(42)
    spans: list[dict] = []
    clock = BASE_NS
    trace_no = 0

    for usecase, invocations, chain in USE_CASES:
        for _ in range(invocations):
            trace_no += 1
            trace_id = f"{trace_no:032x}"
            # Parent span ids by depth, so children attach to the right parent.
            parent_at_depth: dict[int, str] = {}
            span_no = 0
            t = clock
            for fqn, depth, self_ms in chain:
                span_no += 1
                span_id = f"{(trace_no * 1000 + span_no):016x}"
                jitter = 1.0 + rng.uniform(-0.25, 0.45)
                dur_ns = int(self_ms * jitter * 1_000_000)
                cls, _, method = fqn.rpartition(".")
                spans.append({
                    "traceId": trace_id,
                    "spanId": span_id,
                    "parentSpanId": parent_at_depth.get(depth - 1, ""),
                    "name": f"{cls.rsplit('.', 1)[-1]}.{method}",
                    "kind": "SPAN_KIND_INTERNAL" if depth else "SPAN_KIND_SERVER",
                    "startTimeUnixNano": str(t),
                    "endTimeUnixNano": str(t + dur_ns),
                    "attributes": [
                        {"key": "code.namespace", "value": {"stringValue": cls}},
                        {"key": "code.function", "value": {"stringValue": method}},
                        {"key": "modernrx.usecase", "value": {"stringValue": usecase}},
                    ],
                    "status": {"code": "STATUS_CODE_OK"},
                })
                parent_at_depth[depth] = span_id
                t += dur_ns
            clock = t + 1_000_000

    payload = {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": SERVICE}},
                {"key": "service.version", "value": {"stringValue": "3.11.0"}},
                {"key": "telemetry.sdk.language", "value": {"stringValue": "java"}},
            ]},
            "scopeSpans": [{
                "scope": {"name": "io.opentelemetry.spring-webmvc", "version": "1.32.0"},
                "spans": spans,
            }],
        }]
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    with gzip.open(OUT, "wb", compresslevel=9) as fh:
        fh.write(raw)
    # ASCII only: the Windows console defaults to cp1252 and would raise on arrows.
    print(f"wrote {OUT.name}: {len(spans)} spans across {trace_no} traces, "
          f"{len(USE_CASES)} use cases "
          f"({len(raw) / 1e6:.1f} MB raw -> {OUT.stat().st_size / 1e3:.0f} KB gzipped)")


if __name__ == "__main__":
    main()
