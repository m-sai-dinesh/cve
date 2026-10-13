"""Read-only graph tools for the Council agents (PRD §12.2).

Every tool here only reads. There is deliberately no write path: an agent can
cite the twin but cannot alter it, so a debate can never corrupt the analysis
it is reasoning about.

``estimate_effort`` is the deterministic effort model of PRD §12.5 — weeks per
KLOC per strategy, multiplied by the GxP multiplier. The Council may adjust it
by at most ±30% with a justification, and the adjustment is recorded.
"""
from __future__ import annotations

from typing import Any

from ...config import settings
from ...db.graph import KnowledgeGraph, run_template

# Weeks per KLOC, per strategy (PRD §12.5). Retire/Retain are near-zero build
# effort; Refactor is the expensive one because it is a rewrite with a contract.
WEEKS_PER_KLOC: dict[str, float] = {
    "Retire": 0.4,
    "Retain": 0.3,
    "Rehost": 1.0,
    "Relocate": 1.2,
    "Replatform": 2.2,
    "Repurchase": 2.6,
    "Refactor": 4.5,
}

# Fixed overhead per strategy in weeks — the work that does not scale with size
# (cutover planning, supplier assessment, contract negotiation).
FIXED_WEEKS: dict[str, float] = {
    "Retire": 0.5, "Retain": 0.3, "Rehost": 1.0, "Relocate": 1.5,
    "Replatform": 2.0, "Repurchase": 4.0, "Refactor": 3.0,
}


def get_cluster_summary(kg: KnowledgeGraph, cluster_id: str) -> dict[str, Any]:
    """Everything the agents need about one proposed service."""
    node = kg.node(cluster_id)
    if node is None:
        return {"error": f"unknown cluster {cluster_id}"}
    members = kg.in_neighbors(cluster_id, "IN_CLUSTER")

    classes: list[dict[str, Any]] = []
    tables: dict[str, dict[str, Any]] = {}
    endpoints: list[str] = []
    gaps: set[str] = set()
    all_tags: set[str] = set()
    scheduled = 0
    local_file = 0
    session = 0

    for cid in members:
        c = kg.node(cid) or {}
        all_tags |= set(c.get("gxpTags") or [])
        gaps |= set(c.get("complianceGaps") or [])
        classes.append({
            "node_id": cid,
            "name": c.get("name"),
            "fqn": c.get("fqn"),
            "loc": c.get("loc"),
            "complexity": c.get("complexity"),
            "gxp_tier": c.get("gxpTier"),
            "gxp_tags": c.get("gxpTags") or [],
            "readiness": c.get("readiness"),
            "runtime_hits": c.get("runtimeHits", 0),
            "fan_in": c.get("fanIn", 0),
            "fan_out": c.get("fanOut", 0),
            "top_blockers": [d.get("check") for d in (c.get("readinessDeductions") or [])[:3]],
        })
        for e in kg.out_neighbors(cid, "EXPOSES"):
            ed = kg.node(e) or {}
            endpoints.append(f"{ed.get('httpMethod')} {ed.get('path')}")
        for m in [cid, *kg.children(cid)]:
            md = kg.node(m) or {}
            scheduled += 1 if md.get("isScheduled") else 0
            local_file += 1 if md.get("usesLocalFile") else 0
            session += 1 if md.get("usesHttpSession") else 0
            for rel in ("READS", "WRITES"):
                for t in kg.out_neighbors(m, rel):
                    td = kg.node(t) or {}
                    entry = tables.setdefault(str(td.get("name")), {
                        "node_id": t, "regulated": bool(td.get("regulated")),
                        "modes": set(), "external_writers": [],
                    })
                    entry["modes"].add("WRITE" if rel == "WRITES" else "READ")

    # Which tables are written from outside this cluster? That is the hard
    # blocker to independent deployment, so the agents must see it.
    for name, entry in tables.items():
        outside: set[str] = set()
        for m in kg.in_neighbors(entry["node_id"], "WRITES"):
            owner = kg.owner_class(m)
            if owner and owner not in members:
                outside.add(str((kg.node(owner) or {}).get("fqn")))
        entry["external_writers"] = sorted(outside)
        entry["modes"] = sorted(entry["modes"])

    deps = _cluster_edges(kg, cluster_id, members, outgoing=True)
    dependents = _cluster_edges(kg, cluster_id, members, outgoing=False)

    usecases: dict[str, int] = {}
    for cid in members:
        for u in kg.out_neighbors(cid, "PART_OF_USECASE"):
            ud = kg.node(u) or {}
            hits = 0
            for d in (kg.g.get_edge_data(cid, u) or {}).values():
                if d.get("rel") == "PART_OF_USECASE":
                    hits = max(hits, int(d.get("hits", 0)))
            name = str(ud.get("name"))
            usecases[name] = usecases.get(name, 0) + hits

    return {
        "cluster_id": cluster_id,
        "name": node.get("name"),
        "size": len(members),
        "loc": node.get("loc"),
        "gxp_max": node.get("gxpMax"),
        "gxp_counts": node.get("gxpCounts"),
        "gxp_tags": sorted(all_tags),
        "readiness_avg": node.get("readinessAvg"),
        "runtime_hits": node.get("runtimeHits"),
        "has_endpoints": bool(endpoints),
        "endpoints": sorted(set(endpoints))[:15],
        "classes": sorted(classes, key=lambda c: -(c.get("loc") or 0)),
        "tables": [{"name": k, **v} for k, v in sorted(tables.items())],
        "regulated_tables": sorted(k for k, v in tables.items() if v["regulated"]),
        "tables_written_from_outside": sorted(
            k for k, v in tables.items() if v["external_writers"]
        ),
        "depends_on": deps,
        "depended_on_by": dependents,
        "use_cases": dict(sorted(usecases.items(), key=lambda kv: -kv[1])),
        "compliance_gaps": sorted(gaps),
        "scheduled_jobs": scheduled,
        "local_file_methods": local_file,
        "session_methods": session,
        "target_cloud": (kg.nodes("Project") or [{}])[0].get("targetCloud", "AWS"),
    }


def _cluster_edges(
    kg: KnowledgeGraph, cluster_id: str, members: list[str], *, outgoing: bool
) -> list[dict[str, Any]]:
    acc: dict[str, float] = {}
    member_set = set(members)
    for u, v, data in kg.g.edges(data=True):
        if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
            continue
        cu, cv = kg.owner_class(u), kg.owner_class(v)
        if cu is None or cv is None or cu == cv:
            continue
        if outgoing and cu in member_set and cv not in member_set:
            other = (kg.node(cv) or {}).get("clusterId")
        elif not outgoing and cv in member_set and cu not in member_set:
            other = (kg.node(cu) or {}).get("clusterId")
        else:
            continue
        if not other or other == cluster_id:
            continue
        acc[other] = acc.get(other, 0.0) + float(data.get("count", 1))
    return [
        {"cluster_id": k, "name": (kg.node(k) or {}).get("name"),
         "gxp_max": (kg.node(k) or {}).get("gxpMax"), "call_weight": round(v, 1)}
        for k, v in sorted(acc.items(), key=lambda kv: -kv[1])
    ]


def get_node(kg: KnowledgeGraph, node_id: str) -> dict[str, Any]:
    node = kg.node(node_id)
    if node is None:
        return {"error": f"unknown node {node_id}"}
    return {k: v for k, v in node.items() if k not in ("gxpEvidence",)}


def run_query_template(kg: KnowledgeGraph, template_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return run_template(kg, template_id, params)


def get_readiness(kg: KnowledgeGraph, node_id: str) -> dict[str, Any]:
    node = kg.node(node_id) or {}
    return {
        "node_id": node_id,
        "readiness": node.get("readiness"),
        "deductions": node.get("readinessDeductions") or [],
    }


def get_gxp_tags(kg: KnowledgeGraph, node_id: str) -> dict[str, Any]:
    node = kg.node(node_id) or {}
    return {
        "node_id": node_id,
        "tier": node.get("gxpTier"),
        "tags": node.get("gxpTags") or [],
        "evidence": (node.get("gxpEvidence") or [])[:6],
        "overridden": bool(node.get("gxpOverridden")),
        "compliance_gaps": node.get("complianceGaps") or [],
    }


def estimate_effort(
    kg: KnowledgeGraph, cluster_id: str, strategy: str
) -> dict[str, Any]:
    """PRD §12.5: effort = f(LOC, complexity, #tables, gxp_tier, strategy).

    Returns a PERT triple. The spread is widened for HIGH-tier work because
    that is where validation surprises actually live, and a narrow estimate
    there would be the dishonest kind of precision.
    """
    node = kg.node(cluster_id) or {}
    members = kg.in_neighbors(cluster_id, "IN_CLUSTER")
    loc = sum(int((kg.node(m) or {}).get("loc") or 0) for m in members)
    kloc = max(0.05, loc / 1000.0)
    tier = str(node.get("gxpMax") or "LOW")
    multiplier = settings.gxp_multiplier(tier)

    tables: set[str] = set()
    complexity = 0
    for m in members:
        complexity += int((kg.node(m) or {}).get("complexity") or 0)
        for mm in [m, *kg.children(m)]:
            for rel in ("READS", "WRITES"):
                tables |= set(kg.out_neighbors(mm, rel))

    rate = WEEKS_PER_KLOC.get(strategy, 2.0)
    fixed = FIXED_WEEKS.get(strategy, 1.0)

    avg_cc = complexity / max(1, sum(
        int((kg.node(m) or {}).get("methodCount") or 0) for m in members
    ) or 1)
    complexity_factor = 1.0 + max(0.0, (avg_cc - 3.0) / 10.0)
    data_factor = 1.0 + 0.06 * len(tables)

    likely = (fixed + kloc * rate) * multiplier * complexity_factor * data_factor
    # HIGH-tier work has a fatter right tail: re-validation findings, QA
    # scheduling and freeze windows all push late, never early.
    spread = {"HIGH": (0.70, 1.75), "MEDIUM": (0.78, 1.50)}.get(tier, (0.85, 1.35))
    optimistic = likely * spread[0]
    pessimistic = likely * spread[1]

    return {
        "cluster_id": cluster_id,
        "strategy": strategy,
        "effort_weeks": [round(optimistic, 2), round(likely, 2), round(pessimistic, 2)],
        "basis": {
            "loc": loc, "kloc": round(kloc, 3), "weeks_per_kloc": rate,
            "fixed_weeks": fixed, "gxp_tier": tier, "gxp_multiplier": multiplier,
            "avg_complexity": round(avg_cc, 2), "complexity_factor": round(complexity_factor, 3),
            "tables": len(tables), "data_factor": round(data_factor, 3),
        },
        "note": "Deterministic model from PRD 12.5; the Council may adjust by "
                "at most +/-30% with a stated justification.",
    }


def clamp_effort(
    baseline: tuple[float, float, float], proposed: tuple[float, float, float]
) -> tuple[tuple[float, float, float], bool]:
    """Hold the Council to the ±30% adjustment limit of PRD §12.5."""
    out: list[float] = []
    clamped = False
    for b, p in zip(baseline, proposed):
        lo, hi = b * 0.7, b * 1.3
        v = min(max(float(p), lo), hi)
        if abs(v - float(p)) > 1e-6:
            clamped = True
        out.append(round(v, 2))
    o, l, p2 = sorted(out)
    return (o, l, p2), clamped


TOOL_CATALOG: dict[str, str] = {
    "get_cluster_summary": "Full profile of the cluster under debate.",
    "get_node": "One graph node's properties.",
    "run_template_query": "A whitelisted Cypher template (no free queries).",
    "get_readiness": "Cloud-readiness score and its deductions for a node.",
    "get_gxp_tags": "GxP tier, tags and evidence for a node.",
    "estimate_effort": "Deterministic PERT effort estimate for a strategy.",
}
