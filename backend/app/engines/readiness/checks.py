"""Engine 3 checks — the eleven cloud-readiness signals of PRD §10.

Each check returns a severity in [0, 1] plus the graph node ids that justify it.
``readiness = 100 - sum(weight_i * severity_i)``, so every point deducted is
clickable in the UI. A check that finds nothing returns severity 0 and says so:
a silent check and a passing check must not look the same to a reviewer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ...db.graph import KnowledgeGraph

# ---------------------------------------------------------------- weights
# PRD §10. Kept in one place so they can be surfaced and tuned from config.
WEIGHTS: dict[str, int] = {
    "statelessness": 15,
    "local_filesystem": 10,
    "hardcoded_config": 10,
    "framework_eol": 15,
    "db_coupling": 15,
    "complexity_size": 10,
    "test_coverage": 5,
    "scheduled_jobs": 5,
    "licensing_blockers": 5,
    "observability": 5,
    "gxp_tier_penalty": 5,
}

CHECK_TITLES: dict[str, str] = {
    "statelessness": "Statelessness",
    "local_filesystem": "Local filesystem dependence",
    "hardcoded_config": "Hard-coded config, hosts and secrets",
    "framework_eol": "Framework / runtime end-of-life",
    "db_coupling": "Database coupling (shared tables)",
    "complexity_size": "Complexity and size",
    "test_coverage": "Test coverage present",
    "scheduled_jobs": "Scheduled / batch jobs",
    "licensing_blockers": "Licensing and proprietary blockers",
    "observability": "Observability",
    "gxp_tier_penalty": "GxP tier penalty",
}


@dataclass
class Deduction:
    check: str
    title: str
    weight: int
    severity: float
    points: float
    detail: str
    evidence_node_ids: list[str] = field(default_factory=list)
    remediation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check, "title": self.title, "weight": self.weight,
            "severity": round(self.severity, 3), "points": round(self.points, 2),
            "detail": self.detail, "remediation": self.remediation,
            "evidence_node_ids": self.evidence_node_ids[:20],
            "evidence_count": len(self.evidence_node_ids),
        }


# A check receives (kg, class_node_id, context) and returns
# (severity, detail, evidence_ids, remediation).
CheckResult = tuple[float, str, list[str], str]
Check = Callable[[KnowledgeGraph, str, dict[str, Any]], CheckResult]


def _members(kg: KnowledgeGraph, cid: str) -> list[str]:
    """The class node plus its methods — the scope a class-level check sees."""
    return [cid, *kg.children(cid)]


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


# =============================================================================
# The checks
# =============================================================================

def check_statelessness(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    ev: list[str] = []
    reasons: list[str] = []
    node = kg.node(cid) or {}

    session = [m for m in _members(kg, cid) if (kg.node(m) or {}).get("usesHttpSession")]
    if session:
        ev += session
        reasons.append(f"{len(session)} method(s) read or write the servlet session")

    # Static mutable state: a static non-final field is shared process state and
    # silently diverges the moment a second instance starts.
    static_mutable = [f for f in (node.get("staticMutableFields") or [])]
    if static_mutable:
        ev.append(cid)
        reasons.append(f"static mutable field(s): {', '.join(static_mutable[:4])}")

    caches = [m for m in _members(kg, cid) if (kg.node(m) or {}).get("usesInMemoryCache")]
    static_collections = node.get("staticCollectionFields") or []
    if caches or static_collections:
        ev += caches
        if static_collections:
            ev.append(cid)
        reasons.append(
            "an in-process collection is used as a shared cache"
            + (f" ({', '.join(static_collections[:3])})" if static_collections else "")
        )

    threads = [m for m in _members(kg, cid) if (kg.node(m) or {}).get("usesThreads")]
    if threads:
        ev += threads
        reasons.append("threads are created inside the request path")

    if not reasons:
        return 0.0, "No session, static-mutable or in-process-cache state found.", [], ""
    severity = _clamp(0.45 * bool(session) + 0.4 * bool(static_mutable)
                      + 0.3 * bool(caches) + 0.15 * bool(threads))
    return (
        severity, "; ".join(reasons),
        sorted(set(ev)),
        "Move per-user state to a signed token or a shared cache, and replace "
        "static mutable fields with a request-scoped or externalised store.",
    )


def check_local_filesystem(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    ev = [m for m in _members(kg, cid) if (kg.node(m) or {}).get("usesLocalFile")]
    paths: list[str] = []
    if ev:
        # Absolute paths in config apply to the whole app; attribute them to the
        # class that actually touches the filesystem.
        paths = [c["id"] for c in kg.nodes("ConfigItem") if c.get("kind") == "path"]
    if not ev:
        return 0.0, "No direct filesystem access.", [], ""
    severity = _clamp(0.55 + 0.1 * len(ev) + (0.2 if paths else 0.0))
    detail = f"{len(ev)} method(s) use java.io file APIs directly"
    if paths:
        detail += f"; {len(paths)} absolute host path(s) in configuration"
    return (
        severity, detail, sorted(set(ev + paths[:6])),
        "Replace filesystem I/O with object storage or a managed transfer "
        "service, and add a verified-transfer check (checksum and row count).",
    )


def check_hardcoded_config(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    """Config findings are application-wide; classes that read config carry them."""
    items = ctx.get("config_items", [])
    if not items:
        return 0.0, "No hard-coded hosts, connection strings or secrets found.", [], ""
    node = kg.node(cid) or {}
    reads_config = bool(node.get("readsConfig")) or any(
        (kg.node(m) or {}).get("readsConfig") for m in kg.children(cid)
    )
    if not reads_config:
        return 0.0, "This class does not read configuration directly.", [], ""

    secrets = [c for c in items if c.get("isSecret")]
    hosts = [c for c in items if c.get("kind") in ("host", "url", "jdbc")]
    paths = [c for c in items if c.get("kind") == "path"]
    severity = _clamp(0.5 * bool(secrets) + 0.3 * bool(hosts) + 0.2 * bool(paths))
    parts = []
    if secrets:
        parts.append(f"{len(secrets)} credential(s) in configuration")
    if hosts:
        parts.append(f"{len(hosts)} hard-coded endpoint(s)")
    if paths:
        parts.append(f"{len(paths)} absolute path(s)")
    return (
        severity, "; ".join(parts),
        [c["id"] for c in (secrets + hosts + paths)][:12],
        "Externalise all configuration, inject secrets from a managed secrets "
        "service at runtime, and rotate anything that has been in version control.",
    )


FRAMEWORK_ANNOTATIONS = {
    "Service", "Repository", "Component", "Controller", "RestController",
    "Configuration", "SpringBootApplication", "Entity", "Transactional",
    "Autowired", "Scheduled", "Value", "PreAuthorize", "EnableWebSecurity",
    "EnableGlobalMethodSecurity", "RequestMapping", "GetMapping", "PostMapping",
}


def check_framework_eol(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    """End-of-life runtime and framework exposure, attributed per class.

    The EOL *runtime* affects everything equally, so it contributes a floor.
    The EOL *framework* only burdens classes actually coupled to it: a plain
    POJO helper recompiles on a modern JDK and moves, while a class wired
    through Spring annotations carries the whole upgrade with it. Charging both
    the same 15 points would make every score identical and tell a reviewer
    nothing about where the work is.
    """
    eol = ctx.get("eol_libraries", [])
    if not eol:
        return 0.0, "No end-of-life frameworks or runtimes detected.", [], ""

    node = kg.node(cid) or {}
    runtime_eol = [l for l in eol if l.get("group") == "runtime" or l.get("name") == "jdk"]
    framework_eol = [l for l in eol if l.get("group") != "runtime" and l.get("name") != "jdk"]

    own_anns = set(node.get("annotations") or [])
    for mid in kg.children(cid):
        own_anns |= set((kg.node(mid) or {}).get("annotations") or [])
    framework_bound = bool(own_anns & FRAMEWORK_ANNOTATIONS) or bool(node.get("extends"))

    severity = 0.0
    reasons: list[str] = []
    evidence: list[str] = []

    if runtime_eol:
        severity += 0.35
        names = ", ".join(f"{l['name']} {l.get('version')}" for l in runtime_eol)
        reasons.append(f"runtime out of support ({names})")
        evidence += [l["id"] for l in runtime_eol]

    if framework_eol and framework_bound:
        severity += _clamp(0.35 + 0.08 * len(framework_eol))
        bound = ", ".join(sorted(own_anns & FRAMEWORK_ANNOTATIONS)[:3])
        reasons.append(
            f"coupled to {len(framework_eol)} end-of-life framework/library "
            f"version(s) via {bound}"
        )
        evidence += [l["id"] for l in framework_eol][:8]
    elif framework_eol:
        severity += 0.1
        reasons.append(
            f"{len(framework_eol)} end-of-life library/libraries in the build, but "
            f"this class has no framework coupling of its own"
        )
        evidence += [l["id"] for l in framework_eol][:3]

    return (
        _clamp(severity), "; ".join(reasons), evidence,
        "Upgrade the runtime and framework to a supported release before "
        "migrating; an unsupported runtime cannot be patched in a managed service.",
    )


def check_db_coupling(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    """How entangled this class is with tables other classes also use."""
    shared: list[str] = []
    co_writers: set[str] = set()
    writers_by_table: dict[str, set[str]] = ctx.get("writers_by_table", {})
    accessors_by_table: dict[str, set[str]] = ctx.get("accessors_by_table", {})

    own_tables: set[str] = set()
    for m in _members(kg, cid):
        for rel in ("READS", "WRITES"):
            own_tables |= set(kg.out_neighbors(m, rel))

    for t in own_tables:
        others = accessors_by_table.get(t, set()) - {cid}
        if others:
            shared.append(t)
            co_writers |= writers_by_table.get(t, set()) - {cid}

    if not shared:
        return (0.0, f"Owns its data: {len(own_tables)} table(s), none shared.", [], "")
    ratio = len(shared) / max(1, len(own_tables))
    severity = _clamp(0.35 * ratio + 0.12 * len(co_writers))
    names = ", ".join(sorted((kg.node(t) or {}).get("name", t) for t in shared)[:5])
    return (
        severity,
        f"{len(shared)} of {len(own_tables)} table(s) shared with "
        f"{len(co_writers)} other writing class(es): {names}",
        sorted(shared)[:12],
        "Decide a single owner per table. Give other consumers an API or a "
        "read model; a shared write is what makes two services one service.",
    )


def check_complexity_size(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    node = kg.node(cid) or {}
    loc = int(node.get("loc") or 0)
    methods = max(1, int(node.get("methodCount") or 1))
    total_cc = int(node.get("complexity") or 0)
    worst = int(node.get("maxMethodComplexity") or 0)
    avg_cc = total_cc / methods

    # Thresholds: average McCabe above 5 is hard to test; a single method above
    # 15 is where defect density climbs sharply.
    severity = _clamp(max(0.0, (avg_cc - 3.0) / 12.0)
                      + max(0.0, (worst - 10) / 30.0)
                      + max(0.0, (loc - 250) / 1500.0))
    if severity <= 0.02:
        return (0.0, f"{loc} LOC, average complexity {avg_cc:.1f} - comfortably testable.", [], "")
    hot = sorted(
        (m for m in kg.children(cid)),
        key=lambda m: -(int((kg.node(m) or {}).get("complexity") or 0)),
    )[:5]
    return (
        severity,
        f"{loc} LOC across {methods} method(s); average complexity {avg_cc:.1f}, "
        f"worst method {worst}",
        [cid, *hot],
        "Break the most complex methods out before migrating - characterisation "
        "tests are only trustworthy on code you can reach every branch of.",
    )


def check_test_coverage(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    ratio = float(ctx.get("test_ratio", 0.0))
    has_own = bool(ctx.get("tested_classes", set()) & {cid})
    if has_own:
        return 0.0, "A test class targets this component.", [], ""
    severity = _clamp(1.0 - min(1.0, ratio * 4.0))
    return (
        severity,
        f"No test targets this class; project test-file ratio is {ratio:.0%}",
        [cid],
        "Generate characterisation tests that record current behaviour before "
        "changing anything - that record is the evidence the behaviour survived.",
    )


def check_scheduled_jobs(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    scheduled = [m for m in kg.children(cid) if (kg.node(m) or {}).get("isScheduled")]
    if not scheduled:
        return 0.0, "No scheduled or batch entry points.", [], ""
    severity = _clamp(0.5 + 0.15 * len(scheduled))
    return (
        severity,
        f"{len(scheduled)} scheduled job(s) on a singleton - every replica would "
        f"run them, and there is no lock or leader election",
        scheduled,
        "Move to an external scheduler that invokes an idempotent endpoint, or "
        "add a distributed lock, before running more than one instance.",
    )


PROPRIETARY_HINTS = [
    (re.compile(r"(?i)\bojdbc|oracle\.jdbc|oracle\.sql"), "Oracle-specific JDBC"),
    (re.compile(r"(?i)\bsysdate\b|\bnvl\s*\(|\bdecode\s*\(|connect\s+by|rownum"), "Oracle-specific SQL"),
    (re.compile(r"(?i)\bcom4j|jacob|\bCOM\b\.|ActiveX"), "COM / ActiveX interop"),
    (re.compile(r"(?i)sqlserver|mssql|T-SQL|nvarchar"), "SQL Server-specific SQL"),
    (re.compile(r"(?i)\bsap\b|jco3|\bsapjco"), "SAP proprietary connector"),
]


def check_licensing_blockers(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    hits: list[str] = []
    reasons: set[str] = set()
    for m in _members(kg, cid):
        d = kg.node(m) or {}
        blob = " ".join([
            *(d.get("sqlLiterals") or []),
            *(d.get("externalCalls") or []),
            *(d.get("annotations") or []),
        ])
        for rx, label in PROPRIETARY_HINTS:
            if rx.search(blob):
                hits.append(m)
                reasons.add(label)
    lib_hits = [l["id"] for l in ctx.get("proprietary_libraries", [])]
    if not hits and not lib_hits:
        return 0.0, "No vendor-specific SQL, interop or licensed SDK found.", [], ""
    severity = _clamp(0.3 * bool(hits) + 0.3 * bool(lib_hits) + 0.1 * len(reasons))
    detail = ", ".join(sorted(reasons)) or "proprietary dependency"
    if lib_hits:
        detail += f"; {len(lib_hits)} licensed/vendor library/libraries"
    return (
        severity, detail, sorted(set(hits))[:8] + lib_hits[:4],
        "Replace vendor-specific SQL with portable equivalents and confirm the "
        "licence permits running in a cloud region before committing to a target.",
    )


def check_observability(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    has_logging = bool(ctx.get("has_logging_framework"))
    has_health = bool(ctx.get("has_health_endpoint"))
    has_metrics = bool(ctx.get("has_metrics"))
    swallows = [m for m in kg.children(cid) if (kg.node(m) or {}).get("catchesAndSwallows")]

    severity = _clamp(
        (0.0 if has_logging else 0.35)
        + (0.0 if has_health else 0.3)
        + (0.0 if has_metrics else 0.2)
        + (0.25 if swallows else 0.0)
    )
    if severity <= 0.02:
        return 0.0, "Logging, health and metrics are all present.", [], ""
    missing = [n for n, ok in (("structured logging", has_logging),
                               ("a health endpoint", has_health),
                               ("metrics", has_metrics)) if not ok]
    detail = ("missing " + ", ".join(missing)) if missing else ""
    if swallows:
        detail += f"{'; ' if detail else ''}{len(swallows)} empty catch block(s) hide failures"
    return (
        severity, detail, swallows[:8] or [cid],
        "Add a health endpoint, structured logs with a correlation id, and "
        "metrics. A managed platform cannot operate what it cannot observe.",
    )


def check_gxp_tier_penalty(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any]) -> CheckResult:
    """A HIGH-tier component is not less migratable — it is less safe to rush.

    This deduction is deliberately the smallest (weight 5). It expresses
    "move this later, with more assurance", not "this is bad code".
    """
    node = kg.node(cid) or {}
    tier = node.get("gxpTier", "LOW")
    sev = {"HIGH": 1.0, "MEDIUM": 0.5}.get(tier, 0.0)
    if sev == 0.0:
        return 0.0, "LOW GxP tier - no re-validation drag on moving fast.", [], ""
    tags = ", ".join(node.get("gxpTags", [])[:3])
    return (
        sev,
        f"{tier} GxP tier ({tags}) - a cutover needs scripted testing and "
        f"QA approval, so this cannot be a fast first move",
        [cid],
        "Keep this in a later wave, behind a facade, once the team has proven "
        "the migration pattern on lower-tier components.",
    )


CHECKS: dict[str, Check] = {
    "statelessness": check_statelessness,
    "local_filesystem": check_local_filesystem,
    "hardcoded_config": check_hardcoded_config,
    "framework_eol": check_framework_eol,
    "db_coupling": check_db_coupling,
    "complexity_size": check_complexity_size,
    "test_coverage": check_test_coverage,
    "scheduled_jobs": check_scheduled_jobs,
    "licensing_blockers": check_licensing_blockers,
    "observability": check_observability,
    "gxp_tier_penalty": check_gxp_tier_penalty,
}
