"""Engine 7, part 1 — the risk-based assurance plan (PRD §14.3).

CSA (FDA, Sept 2025) scales assurance effort to risk rather than documenting
everything equally. This module turns the GxP tier of each component into the
concrete activities, evidence and reviewer that the tier calls for:

    HIGH    scripted testing of critical functions + independent review
    MEDIUM  unscripted / exploratory testing with recorded results
    LOW     vendor or automated evidence, ad-hoc testing

It also produces the shadow/differential testing plan, the data-migration
checks, the traceability matrix and the rollback plan (PRD §14.5-§14.8).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...db.graph import KnowledgeGraph

# PRD §14.3, as a table rather than prose so the pack can render it directly.
ASSURANCE_BY_TIER: dict[str, dict[str, Any]] = {
    "HIGH": {
        "approach": "Scripted testing of critical functions with independent review",
        "rationale": (
            "A failure here can release non-conforming product or corrupt a GxP "
            "record, so CSA directs the greatest assurance effort to it."
        ),
        "activities": [
            "Scripted test cases covering every critical function, with expected results pre-approved",
            "Negative and boundary testing of the critical decision logic",
            "Independent review of test design, execution and results by someone not involved in the change",
            "Full audit-trail verification: every change to a GxP record produces a complete, attributable entry",
            "Electronic-signature verification where applicable (manifestation, meaning, non-repudiation)",
            "Data-migration verification with record counts and checksums per regulated table",
            "Regression testing of all consuming integrations",
        ],
        "evidence": [
            "Approved test protocol with pre-defined acceptance criteria",
            "Executed test scripts with actual results, dated and signed",
            "Independent reviewer sign-off",
            "Screenshots or system-generated records of the audit-trail entries produced",
            "Data-migration reconciliation report",
            "Deviation records for any failure, with resolution and retest",
        ],
        "reviewer": "QA (independent of the implementation team)",
        "approval": "QA approval required before production cutover",
    },
    "MEDIUM": {
        "approach": "Unscripted / exploratory testing with recorded results",
        "rationale": (
            "These components read GxP data or enforce access control. A failure "
            "is serious but does not directly alter a regulated record, so CSA "
            "permits a lighter, more efficient approach."
        ),
        "activities": [
            "Exploratory testing of the main flows against documented intended use",
            "Recorded results for each session: who tested, what was exercised, what happened",
            "Verification that read models agree with the source of record",
            "Access-control testing: each role sees and does only what it should",
            "Automated regression suite execution",
        ],
        "evidence": [
            "Test session records with tester, date, scope and outcome",
            "Automated test run output retained as system-generated evidence",
            "Reconciliation of read-model output against source records",
        ],
        "reviewer": "System owner, with QA review of the summary",
        "approval": "System owner approval; QA notified",
    },
    "LOW": {
        "approach": "Vendor and automated evidence with ad-hoc testing",
        "rationale": (
            "No GxP data path. CSA explicitly permits leveraging vendor "
            "documentation and automated evidence here, and spending the saved "
            "effort on the high-risk components instead."
        ),
        "activities": [
            "Automated build, unit and integration tests in the qualified pipeline",
            "Smoke testing after deployment",
            "Vendor/platform documentation reviewed and retained for managed services",
        ],
        "evidence": [
            "Pipeline run records (build, test, deploy) retained as system-generated evidence",
            "Smoke-test output",
            "Vendor qualification documents for any managed service used",
        ],
        "reviewer": "Technical lead",
        "approval": "Technical lead approval; no QA gate",
    },
}


@dataclass
class ComponentAssurance:
    node_id: str
    name: str
    tier: str
    tags: list[str] = field(default_factory=list)
    intended_use: str = ""
    approach: str = ""
    activities: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    reviewer: str = ""
    critical_functions: list[str] = field(default_factory=list)
    regulated_tables: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def describe_intended_use(kg: KnowledgeGraph, cid: str) -> str:
    """A plain-language statement of what a component is for (PRD §14.2).

    Built from its name, its GxP tags and the regulated tables it touches, so
    the pack states intended use per component rather than asserting one
    sentence about the whole system.
    """
    node = kg.node(cid) or {}
    name = str(node.get("name") or cid)
    tags = set(node.get("gxpTags") or [])

    writes: set[str] = set()
    reads: set[str] = set()
    for m in [cid, *kg.children(cid)]:
        for t in kg.out_neighbors(m, "WRITES"):
            writes.add(str((kg.node(t) or {}).get("name")))
        for t in kg.out_neighbors(m, "READS"):
            reads.add(str((kg.node(t) or {}).get("name")))
    reads -= writes

    purpose: list[str] = []
    if "PRODUCT_RELEASE" in tags:
        purpose.append("records the batch disposition decision that releases product for distribution")
    if "E_SIGNATURE" in tags:
        purpose.append("applies and verifies electronic signatures on regulated records")
    if "AUDIT_TRAIL" in tags:
        purpose.append("creates the audit-trail entries for changes to GxP data")
    if "ACCESS_CONTROL" in tags:
        purpose.append("authenticates users and enforces role-based authorisation")
    if "DATA_INTEGRITY" in tags and writes:
        purpose.append(f"creates and modifies GxP records in {', '.join(sorted(writes)[:4])}")
    if "REPORTING_ONLY" in tags and not writes:
        purpose.append(f"reports on GxP data in {', '.join(sorted(reads)[:4])} without modifying it")
    if "TIME_SOURCE" in tags:
        purpose.append("stamps records with the time of the recorded event")

    if not purpose:
        if reads:
            purpose.append(f"reads {', '.join(sorted(reads)[:3])} in support of other components")
        else:
            purpose.append("provides supporting logic with no GxP data path")

    return f"{name} {'; '.join(purpose)}."


def critical_functions(kg: KnowledgeGraph, cid: str) -> list[str]:
    """The specific operations a HIGH-tier component must be tested on.

    Naming the methods matters: "test the batch release service" is not a test
    protocol, whereas "releaseBatch: rejects release when a major deviation is
    open" is one.
    """
    out: list[str] = []
    for mid in kg.children(cid):
        md = kg.node(mid) or {}
        tier = str(md.get("gxpTier") or "LOW")
        tags = set(md.get("gxpTags") or [])
        if tier != "HIGH" and not tags & {"PRODUCT_RELEASE", "E_SIGNATURE", "AUDIT_TRAIL"}:
            continue
        name = str(md.get("name"))
        writes = [str((kg.node(t) or {}).get("name")) for t in kg.out_neighbors(mid, "WRITES")]
        detail = f"{name}()"
        if tags & {"PRODUCT_RELEASE"}:
            detail += " - batch disposition is recorded only when every precondition holds"
        elif tags & {"E_SIGNATURE"}:
            detail += " - signature is rejected without valid credentials, and its meaning is recorded"
        elif tags & {"AUDIT_TRAIL"}:
            detail += " - an attributable audit entry is written for every change"
        elif writes:
            detail += f" - writes to {', '.join(sorted(set(writes))[:3])} are complete and accurate"
        out.append(detail)
    return out[:12]


def build_component_plan(kg: KnowledgeGraph, cid: str) -> ComponentAssurance:
    node = kg.node(cid) or {}
    tier = str(node.get("gxpTier") or "LOW")
    spec = ASSURANCE_BY_TIER.get(tier, ASSURANCE_BY_TIER["LOW"])

    regulated: set[str] = set()
    for m in [cid, *kg.children(cid)]:
        for rel in ("READS", "WRITES"):
            for t in kg.out_neighbors(m, rel):
                td = kg.node(t) or {}
                if td.get("regulated"):
                    regulated.add(str(td.get("name")))

    return ComponentAssurance(
        node_id=cid,
        name=str(node.get("fqn") or node.get("name") or cid),
        tier=tier,
        tags=list(node.get("gxpTags") or []),
        intended_use=describe_intended_use(kg, cid),
        approach=str(spec["approach"]),
        activities=list(spec["activities"]),
        evidence=list(spec["evidence"]),
        reviewer=str(spec["reviewer"]),
        critical_functions=critical_functions(kg, cid),
        regulated_tables=sorted(regulated),
    )


def build_wave_plan(
    kg: KnowledgeGraph, wave: int, tasks: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The assurance plan for one migration wave."""
    components: list[ComponentAssurance] = []
    cluster_ids: list[str] = []

    for t in tasks:
        cid = str(t.get("cluster_id") or "")
        if not cid or not kg.has(cid):
            continue
        cluster_ids.append(cid)
        for member in kg.in_neighbors(cid, "IN_CLUSTER"):
            components.append(build_component_plan(kg, member))

    tier_counts = {k: sum(1 for c in components if c.tier == k)
                   for k in ("HIGH", "MEDIUM", "LOW")}
    # The effort story CSA is for: most components do not need scripted testing.
    scripted = tier_counts["HIGH"]
    total = max(1, len(components))

    return {
        "wave": wave,
        "clusters": [
            {"cluster_id": cid, "name": (kg.node(cid) or {}).get("name"),
             "gxp_max": (kg.node(cid) or {}).get("gxpMax"),
             "strategy": (decisions.get(cid) or {}).get("strategy")}
            for cid in cluster_ids
        ],
        "components": [c.as_dict() for c in sorted(
            components, key=lambda c: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[c.tier], c.name)
        )],
        "tier_counts": tier_counts,
        "scripted_share_pct": round(100.0 * scripted / total, 1),
        "approach_by_tier": ASSURANCE_BY_TIER,
        "summary": (
            f"{len(components)} component(s) in scope: {tier_counts['HIGH']} HIGH, "
            f"{tier_counts['MEDIUM']} MEDIUM, {tier_counts['LOW']} LOW. Under a "
            f"risk-based approach {scripted} of {len(components)} "
            f"({round(100.0 * scripted / total)}%) require scripted testing with "
            f"independent review; the remainder are covered by exploratory testing "
            f"with recorded results or by automated and vendor evidence."
        ),
    }


def differential_testing_plan(
    kg: KnowledgeGraph, cluster_ids: list[str]
) -> dict[str, Any]:
    """Shadow / differential testing (PRD §14.5)."""
    endpoints: list[dict[str, Any]] = []
    for cid in cluster_ids:
        for member in kg.in_neighbors(cid, "IN_CLUSTER"):
            for e in kg.out_neighbors(member, "EXPOSES"):
                ed = kg.node(e) or {}
                endpoints.append({
                    "node_id": e,
                    "endpoint": f"{ed.get('httpMethod')} {ed.get('path')}",
                    "handler": ed.get("handler"),
                    "gxp_tier": (kg.node(member) or {}).get("gxpTier"),
                })
    usecases = sorted(
        ({"name": u.get("name"),
          "hits": sum(
              d.get("hits", 0)
              for m in kg.in_neighbors(u["id"], "PART_OF_USECASE")
              for d in (kg.g.get_edge_data(m, u["id"]) or {}).values()
              if d.get("rel") == "PART_OF_USECASE"
          )}
         for u in kg.nodes("UseCase")),
        key=lambda r: -r["hits"],
    )
    return {
        "method": (
            "Run the legacy and modernized components side by side. Mirror a copy "
            "of each production request to the new service, compare the responses "
            "field by field, and report every mismatch. The legacy system remains "
            "the system of record throughout, so a mismatch is a finding rather "
            "than a deviation."
        ),
        "duration": (
            "Minimum two full business cycles per wave, and at least one "
            "month-end and one batch-release cycle for any HIGH-tier component."
        ),
        "endpoints": endpoints[:40],
        "use_cases": usecases[:15],
        "comparison_rules": [
            "Response payloads compared field by field; a differing field is a finding.",
            "Timestamps compared for ordering and timezone, not exact equality - "
            "clock source differences are expected and are themselves a finding to resolve.",
            "Generated identifiers excluded from equality but checked for uniqueness and format.",
            "Rounding of numeric results compared to the full stored precision: an "
            "OOS decision must not change because of a display rounding difference.",
            "Audit-trail entries compared for presence, attributability and content.",
        ],
        "exit_criteria": [
            "Zero unexplained mismatches on HIGH-tier endpoints over the full shadow period.",
            "Every mismatch either resolved or accepted with a documented justification approved by QA.",
            "Performance of the new service within the agreed envelope under production-equivalent load.",
        ],
    }


def data_migration_checks(kg: KnowledgeGraph, cluster_ids: list[str]) -> dict[str, Any]:
    """Row counts, checksums and audit-trail continuity (PRD §14.6)."""
    tables: dict[str, dict[str, Any]] = {}
    for cid in cluster_ids:
        for member in kg.in_neighbors(cid, "IN_CLUSTER"):
            for m in [member, *kg.children(member)]:
                for rel in ("READS", "WRITES"):
                    for t in kg.out_neighbors(m, rel):
                        td = kg.node(t) or {}
                        name = str(td.get("name"))
                        entry = tables.setdefault(name, {
                            "node_id": t, "regulated": bool(td.get("regulated")),
                            "columns": sorted(
                                str((kg.node(c) or {}).get("name"))
                                for c in kg.out_neighbors(t, "CONTAINS")
                            ),
                            "modes": set(),
                        })
                        entry["modes"].add("WRITE" if rel == "WRITES" else "READ")

    rows = []
    for name, entry in sorted(tables.items()):
        regulated = entry["regulated"]
        checks = [
            "Source and target row counts match exactly",
            "SHA-256 checksum over the sorted business key and all data columns matches",
        ]
        if regulated:
            checks += [
                "Referential integrity verified against parent and child tables",
                "No NULL introduced in any column that was NOT NULL in the source",
                "Numeric precision and scale preserved exactly (an OOS decision depends on it)",
                "Timestamps preserved with their original value and an explicit UTC offset",
            ]
        if "AUDIT" in name.upper() or "TRAIL" in name.upper():
            checks += [
                "Audit-trail continuity: no gap in the sequence across the cutover boundary",
                "Every pre-migration audit entry still resolves to its subject record",
                "Append-only behaviour verified on the target (UPDATE and DELETE rejected)",
            ]
        rows.append({
            "table": name, "regulated": regulated,
            "modes": "".join(sorted(entry["modes"])),
            "column_count": len(entry["columns"]),
            "checks": checks,
        })

    return {
        "tables": rows,
        "regulated_count": sum(1 for r in rows if r["regulated"]),
        "general_requirements": [
            "Run every check on a full-volume copy of production data before the live cutover.",
            "Record the verification output as system-generated evidence; a reported count is not evidence.",
            "Reconcile again immediately after cutover, before the system is released for use.",
            "Retain the reconciliation reports for the record retention period.",
        ],
    }


def rollback_plan(
    kg: KnowledgeGraph, wave: int, tasks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Per-cutover rollback (PRD §14.8).

    The question that matters is what happens to records written *after* the
    switch, because those cannot simply be discarded - they are GxP records.
    """
    high = [t for t in tasks if str(t.get("tier")) == "HIGH"]
    return {
        "wave": wave,
        "trigger_criteria": [
            "Any mismatch on a HIGH-tier function that cannot be explained within the cutover window",
            "Any GxP record written without a corresponding audit-trail entry",
            "Data-migration reconciliation failing after cutover",
            "Loss of attributability for any write (an actor cannot be resolved)",
            "Performance outside the agreed envelope such that operations cannot proceed",
        ],
        "procedure": [
            "Stop new work entering the modernized component; queue inbound requests.",
            "Re-point the facade or API gateway to the legacy implementation.",
            "Export every record created or modified in the modernized component "
            "since cutover, with its audit trail.",
            "Reconcile and replay those records into the legacy system under change "
            "control - they are GxP records and may not be discarded.",
            "Verify audit-trail continuity across both the cutover and the rollback.",
            "Raise a deviation, perform the investigation, and record the root cause.",
        ],
        "data_considerations": (
            "Records created in the modernized component between cutover and rollback "
            "are regulated records. They must be preserved, reconciled into the "
            "system of record, and their audit trail must remain continuous and "
            "attributable across both transitions. Plan the export path before "
            "cutover, not during the incident."
        ),
        "rollback_window": (
            "Rollback must remain possible for at least one full business cycle "
            "after cutover; keep the legacy path warm and tested for that period."
        ),
        "high_tier_cutovers": [{"id": t.get("id"), "name": t.get("name")} for t in high],
        "decision_authority": "System owner plus QA; for HIGH-tier components the "
                              "Qualified Person is informed before any rollback of a release path.",
    }


def traceability_matrix(
    kg: KnowledgeGraph, cluster_ids: list[str], decisions: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """requirement -> component -> test -> evidence (PRD §14.7).

    Requirements are derived from each component's GxP tags, so the matrix is
    generated from the same analysis as everything else rather than typed by
    hand and left to drift.
    """
    by_tag = {
        "PRODUCT_RELEASE": ("URS-REL", "Batch disposition shall be recorded only when all "
                                       "release preconditions are satisfied, by an authorised QP."),
        "E_SIGNATURE": ("URS-SIG", "Electronic signatures shall require credential re-entry, "
                                   "record their meaning, and be permanently linked to the record."),
        "AUDIT_TRAIL": ("URS-AUD", "All changes to GxP records shall produce a secure, "
                                   "computer-generated, time-stamped, attributable audit entry."),
        "ACCESS_CONTROL": ("URS-ACC", "System access shall be limited to authorised individuals "
                                      "with role-appropriate permissions."),
        "DATA_INTEGRITY": ("URS-INT", "GxP records shall be complete, accurate and attributable "
                                      "throughout their lifecycle."),
        "TIME_SOURCE": ("URS-TIM", "GxP records shall be time-stamped from a single "
                                   "authoritative, synchronised time source."),
        "REPORTING_ONLY": ("URS-RPT", "Reports shall faithfully represent the underlying "
                                      "GxP records without modifying them."),
    }

    rows: list[dict[str, Any]] = []
    seq = 0
    for cid in cluster_ids:
        decision = decisions.get(cid) or {}
        for member in kg.in_neighbors(cid, "IN_CLUSTER"):
            node = kg.node(member) or {}
            tier = str(node.get("gxpTier") or "LOW")
            for tag in (node.get("gxpTags") or []):
                if tag not in by_tag:
                    continue
                seq += 1
                code, text = by_tag[tag]
                spec = ASSURANCE_BY_TIER.get(tier, ASSURANCE_BY_TIER["LOW"])
                rows.append({
                    "id": f"{code}-{seq:03d}",
                    "requirement": text,
                    "tag": tag,
                    "component": node.get("fqn"),
                    "component_node_id": member,
                    "cluster": (kg.node(cid) or {}).get("name"),
                    "gxp_tier": tier,
                    "strategy": decision.get("strategy"),
                    "test_approach": spec["approach"],
                    "evidence": spec["evidence"][0] if spec["evidence"] else "",
                    "reviewer": spec["reviewer"],
                })
    return rows


def supplier_oversight_checklist(target_cloud: str) -> dict[str, Any]:
    """Cloud supplier oversight (PRD §14.9)."""
    return {
        "target_cloud": target_cloud,
        "basis": "EU GMP Annex 11 draft (July 2025) addresses cloud and service "
                 "providers explicitly; 21 CFR Part 11 expectations for records "
                 "held by a third party continue to apply to the regulated company.",
        "items": [
            {"item": "Supplier assessment completed and approved",
             "detail": f"Formal assessment of {target_cloud} covering quality system, "
                       f"certifications (ISO 27001, SOC 2), and relevant audit reports.",
             "owner": "QA / Procurement", "status": "Required before cutover"},
            {"item": "Quality or service agreement in place",
             "detail": "Written agreement defining GxP responsibilities, notification of "
                       "change, incident reporting, data-return and exit terms.",
             "owner": "QA / Legal", "status": "Required before cutover"},
            {"item": "Responsibility split documented (shared responsibility model)",
             "detail": "Explicit allocation for each control: infrastructure, platform "
                       "patching, backup, restore testing, access management, monitoring, "
                       "and qualification evidence.",
             "owner": "IT / QA", "status": "Required before cutover"},
            {"item": "Data residency confirmed and pinned",
             "detail": "Region pinned for primary, replica and backup copies of regulated "
                       "data; cross-border transfer assessed and documented.",
             "owner": "IT / Regulatory", "status": "Required before cutover"},
            {"item": "Backup and restore qualified",
             "detail": "Backup schedule, retention aligned to record retention, and a "
                       "documented restore test with evidence - a backup that has never "
                       "been restored is not a control.",
             "owner": "IT", "status": "Required before cutover"},
            {"item": "Access management and privileged access reviewed",
             "detail": "Named individual accounts, least privilege, MFA, periodic access "
                       "review, and logging of provider personnel access to regulated data.",
             "owner": "Security / QA", "status": "Required before cutover"},
            {"item": "Change notification and change control",
             "detail": "Process for assessing provider-initiated changes against validated "
                       "state, including deprecation notices.",
             "owner": "QA / IT", "status": "Ongoing"},
            {"item": "Business continuity and exit strategy",
             "detail": "Documented continuity plan, and an exit plan demonstrating regulated "
                       "records can be retrieved in a readable form for their full "
                       "retention period.",
             "owner": "IT / QA", "status": "Required before cutover"},
            {"item": "Periodic review scheduled",
             "detail": "Defined frequency for re-assessing the supplier and reviewing "
                       "performance, incidents and changes.",
             "owner": "QA", "status": "Ongoing"},
        ],
    }
