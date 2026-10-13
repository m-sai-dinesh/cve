"""Engine 3 — Cloud Readiness Scorer (PRD §10).

    readiness = 100 - sum(weight_i * severity_i),  severity_i in [0, 1]

Every deduction carries its evidence node ids, so a score is never a bare
number: the UI can walk from "67" to the exact method that cost the points.

Also detects the *opportunities* of §10: dead code, duplicate logic (high
embedding similarity) and quick-win rehost candidates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from .checks import CHECK_TITLES, CHECKS, WEIGHTS, Deduction

log = get_logger("readiness")

PROPRIETARY_LIB_RE = re.compile(r"(?i)\b(ojdbc|oracle|sqlserver|mssql|sapjco|jacob|com4j|crystal|informix|db2)")
LOGGING_LIB_RE = re.compile(r"(?i)(slf4j|logback|log4j|logging|serilog|nlog)")
METRICS_LIB_RE = re.compile(r"(?i)(micrometer|prometheus|actuator|opentelemetry|dropwizard-metrics)")
HEALTH_KEY_RE = re.compile(r"(?i)(actuator|health|management\.endpoint)")


@dataclass
class ComponentScore:
    node_id: str
    fqn: str
    readiness: float
    gxp_tier: str
    loc: int
    deductions: list[Deduction] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "fqn": self.fqn,
            "readiness": round(self.readiness, 1), "gxp_tier": self.gxp_tier,
            "loc": self.loc,
            "deductions": [d.as_dict() for d in self.deductions if d.points > 0],
            "passed_checks": [d.check for d in self.deductions if d.points == 0],
            "total_deducted": round(sum(d.points for d in self.deductions), 1),
        }


@dataclass
class Opportunity:
    kind: str                     # dead_code | duplicate_logic | quick_win
    title: str
    detail: str
    node_ids: list[str] = field(default_factory=list)
    value: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "title": self.title, "detail": self.detail,
                "node_ids": self.node_ids, "value": round(self.value, 2)}


@dataclass
class ReadinessResult:
    scores: list[ComponentScore] = field(default_factory=list)
    opportunities: list[Opportunity] = field(default_factory=list)
    weights: dict[str, int] = field(default_factory=lambda: dict(WEIGHTS))
    context: dict[str, Any] = field(default_factory=dict)

    def by_node(self) -> dict[str, ComponentScore]:
        return {s.node_id: s for s in self.scores}

    def average(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.readiness for s in self.scores) / len(self.scores), 1)

    def weighted_average(self) -> float:
        """LOC-weighted: a 2000-line monolith core should not be averaged away
        by a dozen tiny DTOs."""
        total_loc = sum(max(1, s.loc) for s in self.scores)
        if not total_loc:
            return self.average()
        return round(sum(s.readiness * max(1, s.loc) for s in self.scores) / total_loc, 1)

    def summary(self) -> dict[str, Any]:
        buckets = {"ready (80-100)": 0, "moderate (60-79)": 0,
                   "difficult (40-59)": 0, "blocked (0-39)": 0}
        for s in self.scores:
            r = s.readiness
            key = ("ready (80-100)" if r >= 80 else "moderate (60-79)" if r >= 60
                   else "difficult (40-59)" if r >= 40 else "blocked (0-39)")
            buckets[key] += 1
        worst_checks: dict[str, float] = {}
        for s in self.scores:
            for d in s.deductions:
                worst_checks[d.check] = worst_checks.get(d.check, 0.0) + d.points
        return {
            "components": len(self.scores),
            "average": self.average(),
            "loc_weighted_average": self.weighted_average(),
            "distribution": buckets,
            "top_blockers": [
                {"check": k, "title": CHECK_TITLES.get(k, k), "total_points": round(v, 1)}
                for k, v in sorted(worst_checks.items(), key=lambda kv: -kv[1])[:5]
            ],
            "opportunities": len(self.opportunities),
            "quick_wins": sum(1 for o in self.opportunities if o.kind == "quick_win"),
        }


def build_context(kg: KnowledgeGraph) -> dict[str, Any]:
    """Project-wide facts the per-class checks need, computed once."""
    config_items = [c for c in kg.nodes("ConfigItem")]
    libraries = kg.nodes("Library")

    writers_by_table: dict[str, set[str]] = {}
    accessors_by_table: dict[str, set[str]] = {}
    for t in kg.nodes("Table"):
        w = {kg.owner_class(m) for m in kg.in_neighbors(t["id"], "WRITES")}
        r = {kg.owner_class(m) for m in kg.in_neighbors(t["id"], "READS")}
        w.discard(None)
        r.discard(None)
        writers_by_table[t["id"]] = w
        accessors_by_table[t["id"]] = w | r

    classes = [c for c in kg.classes() if not c.get("isTest")]
    test_classes = [c for c in kg.classes() if c.get("isTest")]
    # A test class named FooTest is taken to cover Foo.
    tested: set[str] = set()
    by_name = {c.get("name"): c["id"] for c in classes}
    for tc in test_classes:
        base = re.sub(r"(Test|Tests|IT|Spec)$", "", str(tc.get("name") or ""))
        if base in by_name:
            tested.add(by_name[base])

    lib_blob = " ".join(f"{l.get('name')} {l.get('version')}" for l in libraries)
    cfg_blob = " ".join(f"{c.get('key')} {c.get('valueMasked')}" for c in config_items)

    return {
        "config_items": config_items,
        "eol_libraries": [l for l in libraries if l.get("eol")],
        "proprietary_libraries": [l for l in libraries
                                  if PROPRIETARY_LIB_RE.search(str(l.get("name", "")))],
        "writers_by_table": writers_by_table,
        "accessors_by_table": accessors_by_table,
        "test_ratio": (len(test_classes) / max(1, len(classes))),
        "tested_classes": tested,
        "has_logging_framework": bool(LOGGING_LIB_RE.search(lib_blob)),
        "has_metrics": bool(METRICS_LIB_RE.search(lib_blob)),
        "has_health_endpoint": bool(HEALTH_KEY_RE.search(cfg_blob)
                                    or METRICS_LIB_RE.search(lib_blob)),
    }


def score_component(kg: KnowledgeGraph, cid: str, ctx: dict[str, Any],
                    weights: dict[str, int] | None = None) -> ComponentScore:
    w = weights or WEIGHTS
    node = kg.node(cid) or {}
    deductions: list[Deduction] = []
    total = 0.0

    for name, fn in CHECKS.items():
        weight = w.get(name, 0)
        try:
            severity, detail, evidence, remediation = fn(kg, cid, ctx)
        except Exception as exc:  # a broken check must not void the whole score
            log.warning("check_failed", check=name, node=cid, error=str(exc))
            continue
        severity = max(0.0, min(1.0, float(severity)))
        points = weight * severity
        total += points
        deductions.append(Deduction(
            check=name, title=CHECK_TITLES.get(name, name), weight=weight,
            severity=severity, points=points, detail=detail,
            evidence_node_ids=[e for e in evidence if kg.has(e)],
            remediation=remediation,
        ))

    deductions.sort(key=lambda d: -d.points)
    return ComponentScore(
        node_id=cid, fqn=str(node.get("fqn") or cid),
        readiness=max(0.0, 100.0 - total),
        gxp_tier=str(node.get("gxpTier") or "LOW"),
        loc=int(node.get("loc") or 0),
        deductions=deductions,
    )


def detect_opportunities(
    kg: KnowledgeGraph, scores: list[ComponentScore], emb=None
) -> list[Opportunity]:
    """PRD §10: dead code, duplicate logic, quick-win rehost candidates."""
    out: list[Opportunity] = []
    from ...db.graph import run_template

    # --- dead code ---------------------------------------------------------
    dead = run_template(kg, "dead_code")["rows"]
    if dead:
        total_loc = sum(int(r.get("loc") or 0) for r in dead)
        out.append(Opportunity(
            kind="dead_code",
            title=f"Retire {len(dead)} unreachable class(es)",
            detail=(f"{total_loc} LOC with no inbound call, no runtime hit, no "
                    f"instantiation and no type reference. Deleting these shrinks "
                    f"the migration and the validation scope at no functional risk."),
            node_ids=[r["node_id"] for r in dead], value=float(total_loc),
        ))

    # --- duplicate logic (embedding similarity) ---------------------------
    if emb is not None and len(emb.node_ids) > 2:
        sim = emb.similarity_matrix()
        pairs: list[tuple[float, str, str]] = []
        for i in range(len(emb.node_ids)):
            for j in range(i + 1, len(emb.node_ids)):
                s = float(sim[i, j])
                if s >= 0.93:
                    a, b = emb.node_ids[i], emb.node_ids[j]
                    # Different packages doing the same thing is the real smell;
                    # a DTO and its mapper are *supposed* to look alike.
                    na, nb = kg.node(a) or {}, kg.node(b) or {}
                    if na.get("package") == nb.get("package"):
                        continue
                    pairs.append((s, a, b))
        pairs.sort(reverse=True)
        for s, a, b in pairs[:6]:
            na, nb = kg.node(a) or {}, kg.node(b) or {}
            out.append(Opportunity(
                kind="duplicate_logic",
                title="Near-duplicate logic across packages",
                detail=(f"{na.get('name')} and {nb.get('name')} have "
                        f"{s:.0%} identifier/data similarity but live in different "
                        f"packages - consolidate before migrating both."),
                node_ids=[a, b], value=s,
            ))

    # --- quick wins --------------------------------------------------------
    # A quick win has to be something you can actually deploy and point at. A
    # DTO or a row mapper scores well because it has no dependencies, not
    # because it is a migration candidate - and dead code is a deletion, not a
    # rehost. Requiring real behaviour (an endpoint or data access) keeps the
    # wave-1 list honest.
    dead_ids = {r["node_id"] for r in dead}

    def is_deployable(cid: str) -> bool:
        if cid in dead_ids:
            return False
        node = kg.node(cid) or {}
        if node.get("isEntity"):
            return False
        if kg.out_neighbors(cid, "EXPOSES"):
            return True
        for m in [cid, *kg.children(cid)]:
            if kg.out_neighbors(m, "READS") or kg.out_neighbors(m, "WRITES"):
                return True
        # A utility with real inbound use is still a legitimate shared-library win.
        return int(node.get("fanIn") or 0) >= 3 and int(node.get("methodCount") or 0) >= 3

    quick = [s for s in scores
             if s.readiness >= 70 and s.gxp_tier == "LOW" and s.loc >= 10
             and is_deployable(s.node_id)]
    quick.sort(key=lambda s: -s.readiness)
    for s in quick[:12]:
        out.append(Opportunity(
            kind="quick_win",
            title=f"Rehost candidate: {s.fqn.rsplit('.', 1)[-1]}",
            detail=(f"Readiness {s.readiness:.0f}/100 at LOW GxP tier - no "
                    f"re-validation of a regulated function, so this can move in "
                    f"wave 1 and prove the pattern."),
            node_ids=[s.node_id], value=s.readiness,
        ))

    # Also surface MEDIUM-tier read-only components: these are the genuinely
    # valuable early wins in a GxP system, because reporting load is what hurts.
    # The test is "writes no *regulated* table", not "writes nothing". A
    # reporting service that logs which certificates it produced still changes
    # no GxP record, so it remains safe to extract behind a read model.
    read_only = []
    for s in scores:
        node = kg.node(s.node_id) or {}
        tags = set(node.get("gxpTags") or [])
        if "REPORTING_ONLY" not in tags or s.readiness < 50:
            continue
        writes_regulated = any(
            (kg.node(t) or {}).get("regulated")
            for m in [s.node_id, *kg.children(s.node_id)]
            for t in kg.out_neighbors(m, "WRITES")
        )
        if not writes_regulated:
            read_only.append(s)
    for s in sorted(read_only, key=lambda s: -s.readiness)[:6]:
        out.append(Opportunity(
            kind="quick_win",
            title=f"Read-only extraction: {s.fqn.rsplit('.', 1)[-1]}",
            detail=(f"Reads GxP data but writes none, readiness {s.readiness:.0f}. "
                    f"Extracting it behind a read model removes reporting load from "
                    f"the validated core without touching a single GxP write path."),
            node_ids=[s.node_id], value=s.readiness,
        ))
    return out


def score(
    kg: KnowledgeGraph,
    *,
    weights: dict[str, int] | None = None,
    emb=None,
    progress=None,
) -> ReadinessResult:
    ctx = build_context(kg)
    classes = [c["id"] for c in kg.classes() if not c.get("isTest")]
    res = ReadinessResult(weights=dict(weights or WEIGHTS), context={
        k: v for k, v in ctx.items()
        if k in ("test_ratio", "has_logging_framework", "has_metrics", "has_health_endpoint")
    })
    total = max(1, len(classes))
    for i, cid in enumerate(classes):
        if progress and i % 10 == 0:
            progress(0.1 + 0.8 * i / total, f"scoring {cid.split('.')[-1]}")
        s = score_component(kg, cid, ctx, res.weights)
        res.scores.append(s)
        kg.set_prop(cid, "readiness", round(s.readiness, 1))
        kg.set_prop(cid, "readinessDeductions",
                    [d.as_dict() for d in s.deductions if d.points > 0][:8])

    res.scores.sort(key=lambda s: s.readiness)
    if progress:
        progress(0.92, "detecting opportunities")
    res.opportunities = detect_opportunities(kg, res.scores, emb)
    if progress:
        progress(1.0, f"average readiness {res.average()}/100")
    log.info("readiness_done", **res.summary())
    return res
