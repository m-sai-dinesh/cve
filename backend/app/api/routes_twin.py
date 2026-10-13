"""Twin graph, node detail, GxP, readiness and "Ask the Twin" (PRD §17)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.audit import record
from ..core.llm import get_llm
from ..db.graph import KnowledgeGraph, describe_templates, run_template
from ..db.models import GxpOverride, Project, User
from ..db.session import get_db
from ..engines.gxp.scanner import apply_override
from .schemas import AskRequest, GxpOverride as GxpOverrideIn, TemplateQuery

router = APIRouter(tags=["twin"])

MAX_GRAPH_NODES = 1200


def _load(db: Session, project_id: str) -> KnowledgeGraph:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    kg = KnowledgeGraph.load(db, project_id)
    if kg.g.number_of_nodes() == 0:
        raise HTTPException(409, "no twin yet - run POST /projects/{id}/analyze first")
    return kg


@router.get("/projects/{project_id}/twin/graph")
def twin_graph(
    project_id: str,
    level: str = Query("class", pattern="^(module|class|cluster)$"),
    tier: str | None = Query(None, pattern="^(HIGH|MEDIUM|LOW)$"),
    cluster_id: str | None = None,
    search: str | None = None,
    include_tables: bool = True,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Nodes and edges for the Cytoscape view."""
    kg = _load(db, project_id)

    if level == "module":
        primary = kg.nodes("Module")
    elif level == "cluster":
        primary = kg.nodes("Cluster")
    else:
        primary = [c for c in kg.classes() if not c.get("isTest")]

    if tier:
        primary = [n for n in primary
                   if str(n.get("gxpTier") or n.get("gxpMax") or "LOW") == tier]
    if cluster_id:
        primary = [n for n in primary
                   if n.get("clusterId") == cluster_id or n["id"] == cluster_id]
    if search:
        q = search.lower()
        primary = [n for n in primary
                   if q in str(n.get("fqn") or n.get("name") or "").lower()]

    truncated = False
    if len(primary) > MAX_GRAPH_NODES:
        primary = sorted(primary, key=lambda n: -(
            int(n.get("fanIn") or 0) + int(n.get("fanOut") or 0)
            + int(n.get("runtimeHits") or 0) // 100
        ))[:MAX_GRAPH_NODES]
        truncated = True

    keep = {n["id"] for n in primary}
    nodes: list[dict[str, Any]] = []
    for n in primary:
        nodes.append({
            "id": n["id"], "label": n.get("name") or n["id"], "kind": n.get("label"),
            "fqn": n.get("fqn"), "package": n.get("package"),
            "gxpTier": n.get("gxpTier") or n.get("gxpMax") or "LOW",
            "gxpTags": n.get("gxpTags") or [],
            "readiness": n.get("readiness") if n.get("readiness") is not None
            else n.get("readinessAvg"),
            "loc": n.get("loc"), "complexity": n.get("complexity"),
            "fanIn": n.get("fanIn"), "fanOut": n.get("fanOut"),
            "runtimeHits": n.get("runtimeHits") or 0,
            "clusterId": n.get("clusterId"),
            "size": n.get("size"),
            "isController": n.get("isController"),
            "isEntity": n.get("isEntity"),
            "overridden": bool(n.get("gxpOverridden")),
            "gaps": n.get("complianceGaps") or [],
        })

    # Regulated tables are what make a boundary expensive, so they are drawn.
    if include_tables and level == "class":
        for t in kg.nodes("Table"):
            accessors = {kg.owner_class(m)
                         for rel in ("READS", "WRITES")
                         for m in kg.in_neighbors(t["id"], rel)}
            if not (accessors & keep):
                continue
            keep.add(t["id"])
            nodes.append({
                "id": t["id"], "label": t.get("name"), "kind": "Table",
                "gxpTier": t.get("gxpTier") or "LOW",
                "gxpTags": t.get("gxpTags") or [],
                "regulated": bool(t.get("regulated")),
                "gaps": t.get("complianceGaps") or [],
            })

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for u, v, data in kg.g.edges(data=True):
        rel = data.get("rel")
        if rel in ("CONTAINS", "IN_CLUSTER", "PART_OF_USECASE", "CONFIGURED_BY", "USES_LIB"):
            continue
        su = u if u in keep else kg._owner(u, "Class" if level == "class" else "Module")
        sv = v if v in keep else kg._owner(v, "Class" if level == "class" else "Module")
        if level == "cluster":
            su = (kg.node(kg.owner_class(u)) or {}).get("clusterId") if u not in keep else u
            sv = (kg.node(kg.owner_class(v)) or {}).get("clusterId") if v not in keep else v
        if not su or not sv or su == sv or su not in keep or sv not in keep:
            continue
        key = (su, sv, str(rel))
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "id": f"{su}->{sv}:{rel}", "source": su, "target": sv, "rel": rel,
            "count": data.get("count", 1),
            "runtimeCount": data.get("runtimeCount"),
            "confirmedAtRuntime": bool(data.get("confirmedAtRuntime")),
            "weight": data.get("weight"),
        })

    return {
        "level": level, "nodes": nodes, "edges": edges,
        "truncated": truncated,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "stats": kg.stats(),
        "legend": {
            "tiers": ["HIGH", "MEDIUM", "LOW"],
            "relationships": sorted({e["rel"] for e in edges}),
        },
    }


@router.get("/projects/{project_id}/twin/node/{node_id:path}")
def node_detail(project_id: str, node_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Side-panel detail: metrics, GxP evidence, tables, callers, code location."""
    kg = _load(db, project_id)
    node = kg.node(node_id)
    if node is None:
        raise HTTPException(404, f"node not found: {node_id}")

    def brief(nid: str) -> dict[str, Any]:
        n = kg.node(nid) or {}
        return {"id": nid, "label": n.get("label"),
                "name": n.get("fqn") or n.get("name") or nid,
                "gxpTier": n.get("gxpTier"), "readiness": n.get("readiness")}

    methods = []
    for mid in kg.children(node_id):
        m = kg.node(mid) or {}
        if m.get("label") != "Method":
            continue
        methods.append({
            "id": mid, "name": m.get("name"), "signature": m.get("signature"),
            "returnType": m.get("returnType"), "loc": m.get("loc"),
            "complexity": m.get("complexity"), "gxpTier": m.get("gxpTier"),
            "gxpTags": m.get("gxpTags") or [], "runtimeHits": m.get("runtimeHits") or 0,
            "meanLatencyMs": m.get("meanLatencyMs"),
            "annotations": m.get("annotations") or [],
            "isScheduled": m.get("isScheduled"), "isTransactional": m.get("isTransactional"),
            "isSecured": m.get("isSecured"),
            "usesLocalFile": m.get("usesLocalFile"), "usesNewDate": m.get("usesNewDate"),
            "usesHttpSession": m.get("usesHttpSession"),
            "sql": m.get("sqlLiterals") or [],
            "reads": [str((kg.node(t) or {}).get("name")) for t in kg.out_neighbors(mid, "READS")],
            "writes": [str((kg.node(t) or {}).get("name")) for t in kg.out_neighbors(mid, "WRITES")],
            "startLine": m.get("startLine"), "endLine": m.get("endLine"),
        })
    methods.sort(key=lambda m: -(m["runtimeHits"] or 0))

    reads: set[str] = set()
    writes: set[str] = set()
    for m in [node_id, *kg.children(node_id)]:
        for t in kg.out_neighbors(m, "WRITES"):
            writes.add(t)
        for t in kg.out_neighbors(m, "READS"):
            reads.add(t)

    usecases = []
    for u in kg.out_neighbors(node_id, "PART_OF_USECASE"):
        hits = 0
        for d in (kg.g.get_edge_data(node_id, u) or {}).values():
            if d.get("rel") == "PART_OF_USECASE":
                hits = max(hits, int(d.get("hits", 0)))
        usecases.append({"name": (kg.node(u) or {}).get("name"), "hits": hits})
    usecases.sort(key=lambda r: -r["hits"])

    return {
        "node": node,
        "methods": methods,
        "tables": {
            "writes": [{"id": t, "name": (kg.node(t) or {}).get("name"),
                        "regulated": bool((kg.node(t) or {}).get("regulated"))}
                       for t in sorted(writes)],
            "reads": [{"id": t, "name": (kg.node(t) or {}).get("name"),
                       "regulated": bool((kg.node(t) or {}).get("regulated"))}
                      for t in sorted(reads - writes)],
        },
        "endpoints": [
            {"id": e, **{k: v for k, v in (kg.node(e) or {}).items() if k != "label"}}
            for e in kg.out_neighbors(node_id, "EXPOSES")
        ],
        "depends_on": [brief(n) for n in kg.out_neighbors(node_id, "DEPENDS_ON")],
        "depended_on_by": [brief(n) for n in kg.in_neighbors(node_id, "DEPENDS_ON")],
        "co_changes": [
            {**brief(n), "weight": max(
                (d.get("weight", 0) for d in (kg.g.get_edge_data(node_id, n) or {}).values()
                 if d.get("rel") == "CO_CHANGES"), default=0)}
            for n in kg.out_neighbors(node_id, "CO_CHANGES")
        ],
        "use_cases": usecases,
        "blast_radius": kg.blast_radius(node_id, 3),
        "gxp_evidence": node.get("gxpEvidence") or [],
        "readiness_deductions": node.get("readinessDeductions") or [],
        "cluster": (kg.node(node.get("clusterId")) if node.get("clusterId") else None),
    }


@router.get("/projects/{project_id}/twin/diagrams")
def diagrams(project_id: str, module: str | None = None,
             db: Session = Depends(get_db)) -> dict[str, Any]:
    kg = _load(db, project_id)
    from ..engines.twin import c4

    if module:
        return {"components": c4.component_diagram(kg, module)}
    return c4.generate_all(kg)


@router.get("/projects/{project_id}/twin/templates")
def templates(project_id: str) -> dict[str, Any]:
    """The whitelisted Cypher templates agents and the chat may run (PRD §8.2)."""
    return {
        "templates": describe_templates(),
        "note": "Only these parameterised templates can be executed. Free-form "
                "Cypher is never accepted from a model or from the UI.",
    }


@router.post("/projects/{project_id}/twin/query")
def run_query(project_id: str, body: TemplateQuery,
              db: Session = Depends(get_db)) -> dict[str, Any]:
    kg = _load(db, project_id)
    return run_template(kg, body.template_id, body.params)


@router.post("/projects/{project_id}/twin/ask")
def ask_twin(project_id: str, body: AskRequest,
             db: Session = Depends(get_db)) -> dict[str, Any]:
    """Ask the Twin (PRD §8.2). Answers cite the node ids they used."""
    kg = _load(db, project_id)
    from ..engines.twin.ask import answer

    result = answer(kg, body.question)
    record("twin.asked", entity="project", entity_id=project_id,
           payload={"question": body.question[:300],
                    "templates": result.get("templates_used"),
                    "generator": result.get("generator")})
    return result


# =============================================================================
# GxP
# =============================================================================

@router.get("/projects/{project_id}/gxp")
def gxp(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    kg = _load(db, project_id)
    summary = (p.summary_json or {}).get("gxp") or {}
    gaps = (p.summary_json or {}).get("gxp_gaps") or []

    components = []
    for c in kg.classes():
        if c.get("isTest"):
            continue
        components.append({
            "node_id": c["id"], "fqn": c.get("fqn"), "name": c.get("name"),
            "package": c.get("package"),
            "tier": c.get("gxpTier") or "LOW", "tags": c.get("gxpTags") or [],
            "evidence": (c.get("gxpEvidence") or [])[:6],
            "overridden": bool(c.get("gxpOverridden")),
            "override_reason": c.get("gxpOverrideReason"),
            "override_by": c.get("gxpOverrideBy"),
            "readiness": c.get("readiness"),
            "runtime_hits": c.get("runtimeHits") or 0,
            "loc": c.get("loc"),
            "gaps": c.get("complianceGaps") or [],
            "cluster_id": c.get("clusterId"),
        })
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    components.sort(key=lambda c: (order.get(c["tier"], 3), -(c["runtime_hits"] or 0)))

    overrides = db.query(GxpOverride).filter(GxpOverride.project_id == project_id).all()
    users = {u.id: u.name for u in db.query(User).all()}

    from ..engines.gxp.scanner import load_rules

    rules = load_rules()
    return {
        "summary": summary,
        "components": components,
        "tables": [
            {"node_id": t["id"], "name": t.get("name"),
             "regulated": bool(t.get("regulated")),
             "tier": t.get("gxpTier") or "LOW", "tags": t.get("gxpTags") or [],
             "gaps": t.get("complianceGaps") or [],
             "columns": sorted(str((kg.node(c) or {}).get("name"))
                               for c in kg.out_neighbors(t["id"], "CONTAINS"))}
            for t in sorted(kg.nodes("Table"), key=lambda n: str(n.get("name")))
        ],
        "gaps": gaps,
        "tag_definitions": rules.get("tags", {}),
        "rules_version": rules.get("version"),
        "overrides": [
            {"id": o.id, "node_id": o.node_id, "old_tier": o.old_tier,
             "new_tier": o.new_tier, "reason": o.reason,
             "user": users.get(o.user_id, o.user_id), "ts": o.ts.isoformat()}
            for o in sorted(overrides, key=lambda o: o.ts, reverse=True)
        ],
        "override_rate": round(len(overrides) / max(1, len(components)), 4),
    }


@router.patch("/projects/{project_id}/gxp/{node_id:path}")
def override_tier(project_id: str, node_id: str, body: GxpOverrideIn,
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    """A QA reviewer overrides a tier. Audit-logged (PRD §9.2, §17)."""
    kg = _load(db, project_id)
    if not kg.has(node_id):
        raise HTTPException(404, f"node not found: {node_id}")

    user = db.get(User, body.user_id) if body.user_id else None
    actor = user.name if user else (body.user_id or "unknown")

    result = apply_override(kg, node_id, body.new_tier, body.reason, actor)
    kg.save(db)

    db.add(GxpOverride(
        project_id=project_id, node_id=node_id,
        old_tier=result["old_tier"], new_tier=result["new_tier"],
        reason=body.reason, user_id=body.user_id or "",
    ))
    db.commit()

    record("gxp.override", actor=actor, entity="node", entity_id=node_id,
           payload={"project_id": project_id, "old_tier": result["old_tier"],
                    "new_tier": result["new_tier"], "reason": body.reason},
           db=db)
    return {**result, "reason": body.reason, "by": actor,
            "node": kg.node(node_id)}


# =============================================================================
# Readiness
# =============================================================================

@router.get("/projects/{project_id}/readiness")
def readiness(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    kg = _load(db, project_id)
    summary = (p.summary_json or {}).get("readiness") or {}

    from ..engines.readiness.checks import CHECK_TITLES, WEIGHTS
    from ..engines.readiness.scorer import build_context, detect_opportunities, score_component

    ctx = build_context(kg)
    scores = []
    for c in kg.classes():
        if c.get("isTest"):
            continue
        if c.get("readiness") is None:
            scores.append(score_component(kg, c["id"], ctx).as_dict())
        else:
            scores.append({
                "node_id": c["id"], "fqn": c.get("fqn"), "name": c.get("name"),
                "readiness": c.get("readiness"), "gxp_tier": c.get("gxpTier") or "LOW",
                "loc": c.get("loc"), "cluster_id": c.get("clusterId"),
                "runtime_hits": c.get("runtimeHits") or 0,
                "deductions": c.get("readinessDeductions") or [],
                "total_deducted": round(100 - float(c.get("readiness") or 0), 1),
            })
    scores.sort(key=lambda s: s["readiness"])

    opportunities = [o.as_dict() for o in detect_opportunities(
        kg, [type("S", (), {
            "node_id": s["node_id"], "fqn": s["fqn"], "readiness": s["readiness"],
            "gxp_tier": s["gxp_tier"], "loc": s["loc"] or 0, "deductions": [],
        })() for s in scores]
    )]

    return {
        "summary": summary,
        "scores": scores,
        "weights": WEIGHTS,
        "check_titles": CHECK_TITLES,
        "context": {k: v for k, v in ctx.items()
                    if k in ("test_ratio", "has_logging_framework",
                             "has_metrics", "has_health_endpoint")},
        "opportunities": opportunities,
        "formula": "readiness = 100 - sum(weight_i * severity_i), severity_i in [0,1]",
    }
