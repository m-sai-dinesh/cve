"""Decomposition, Council and approvals (PRD §17)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.audit import record
from ..db.graph import KnowledgeGraph
from ..db.models import Approval, Decision, Project, User
from ..db.session import get_db
from ..jobs import run_in_background
from ..pipeline import run_council
from .schemas import ApprovalRequest, CouncilRun, DecomposeOptions, JobAccepted

router = APIRouter(tags=["council"])


def _kg(db: Session, project_id: str) -> KnowledgeGraph:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    kg = KnowledgeGraph.load(db, project_id)
    if kg.g.number_of_nodes() == 0:
        raise HTTPException(409, "no twin yet - run the analysis first")
    return kg


# =============================================================================
# Engine 4 results
# =============================================================================

@router.get("/projects/{project_id}/decomposition")
def decomposition(
    project_id: str,
    variant: str = Query("modernrx", pattern="^(louvain|hdbscan|modernrx)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    summary = (p.summary_json or {}).get("decomposition") or {}
    if not summary:
        raise HTTPException(409, "no decomposition yet - run the analysis first")

    kg = _kg(db, project_id)
    clusters = []
    for cl in sorted(kg.nodes("Cluster"), key=lambda c: -(c.get("size") or 0)):
        members = kg.in_neighbors(cl["id"], "IN_CLUSTER")
        clusters.append({
            "cluster_id": cl["id"], "name": cl.get("name"), "size": cl.get("size"),
            "gxp_max": cl.get("gxpMax"), "gxp_counts": cl.get("gxpCounts") or {},
            "readiness_avg": cl.get("readinessAvg"), "loc": cl.get("loc"),
            "runtime_hits": cl.get("runtimeHits") or 0,
            "has_endpoints": bool(cl.get("hasEndpoints")),
            "tables": cl.get("tables") or [],
            "regulated_tables": cl.get("regulatedTables") or [],
            "members": [
                {"node_id": m, "name": (kg.node(m) or {}).get("name"),
                 "fqn": (kg.node(m) or {}).get("fqn"),
                 "gxp_tier": (kg.node(m) or {}).get("gxpTier"),
                 "readiness": (kg.node(m) or {}).get("readiness"),
                 "loc": (kg.node(m) or {}).get("loc"),
                 "runtime_hits": (kg.node(m) or {}).get("runtimeHits") or 0}
                for m in sorted(members, key=lambda m: -(int((kg.node(m) or {}).get("loc") or 0)))
            ],
        })

    return {
        "variant": variant,
        "requested_variant": variant,
        "applied_variant": summary.get("chosen"),
        "note": (
            "The metrics table compares all three variants. The cluster list below "
            "is the decomposition written to the graph "
            f"({summary.get('chosen')}); re-run POST /projects/{{id}}/decompose "
            "with a different `chosen` to apply another variant."
        ) if variant != summary.get("chosen") else "",
        "clusters": clusters,
        "comparison": summary.get("comparison") or {},
        "table": summary.get("table") or {},
        "signals": summary.get("signals") or {},
    }


@router.post("/projects/{project_id}/decompose", status_code=202)
def redecompose(
    project_id: str, body: DecomposeOptions | None = None, db: Session = Depends(get_db)
) -> JobAccepted:
    """Re-run Engine 4 with different weights, gamma or chosen variant."""
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    opts = body or DecomposeOptions()
    if opts.weights is not None and len(opts.weights) != 5:
        raise HTTPException(400, "weights must have 5 entries")

    def body_fn(ctx) -> dict[str, Any]:
        from ..db.session import session_scope
        from ..engines.decompose import runner as decompose_runner
        from ..engines.twin.embeddings import build_embeddings

        with session_scope() as s:
            kg = KnowledgeGraph.load(s, project_id)
        if not kg.classes():
            raise RuntimeError("no twin found - run the analysis first")

        ctx.engine(4, "Blast-Radius-Aware Decomposition", "re-running with new parameters")
        emb = build_embeddings(kg, progress=ctx.stage("Embeddings", 0.02, 0.1))
        readiness = {c["id"]: float(c.get("readiness") or 0) for c in kg.classes()}
        decomp = decompose_runner.run(
            kg,
            weights=opts.weights or settings.weights,
            gamma=settings.decomp_gamma if opts.gamma is None else opts.gamma,
            alpha=settings.decomp_alpha if opts.alpha is None else opts.alpha,
            beta=settings.decomp_beta if opts.beta is None else opts.beta,
            min_cluster_size=(settings.hdbscan_min_cluster_size
                              if opts.min_cluster_size is None else opts.min_cluster_size),
            emb=emb, readiness=readiness, chosen=opts.chosen,
            progress=ctx.stage("Decomposition", 0.1, 0.95),
        )
        with session_scope() as s:
            kg.save(s)
            proj = s.get(Project, project_id)
            if proj is not None:
                merged = dict(proj.summary_json or {})
                merged["decomposition"] = {
                    "chosen": decomp.chosen,
                    "clusters": decomp.partitions[decomp.chosen].cluster_count(),
                    "comparison": decomp.comparison,
                    "table": decomp.table(),
                    "signals": {
                        "available": decomp.features.available if decomp.features else {},
                        "weights": ({k: round(v, 4) for k, v in decomp.features.weights.items()}
                                    if decomp.features else {}),
                    },
                }
                proj.summary_json = merged

        head = decomp.comparison.get("headline", {})
        ctx.note(
            f"{decomp.partitions[decomp.chosen].cluster_count()} services; "
            f"re-validation scope {head.get('reval_scope_after')}%."
        )
        return {"clusters": decomp.partitions[decomp.chosen].cluster_count(),
                "variant": decomp.chosen,
                "reval_scope_after": head.get("reval_scope_after")}

    job_id = run_in_background(project_id, "decompose", body_fn)
    return JobAccepted.of(job_id, project_id, "decompose")


# =============================================================================
# Engine 5
# =============================================================================

@router.post("/projects/{project_id}/council/run", status_code=202)
def start_council(
    project_id: str, body: CouncilRun | None = None, db: Session = Depends(get_db)
) -> JobAccepted:
    kg = _kg(db, project_id)
    if not kg.node_ids("Cluster"):
        raise HTTPException(409, "no decomposition yet - run the analysis first")
    ids = (body.cluster_ids if body else None) or None
    if ids:
        missing = [c for c in ids if not kg.has(c)]
        if missing:
            raise HTTPException(400, f"unknown cluster id(s): {', '.join(missing[:5])}")

    job_id = run_in_background(project_id, "council", lambda ctx: run_council(ctx, ids))
    return JobAccepted.of(job_id, project_id, "council")


@router.get("/projects/{project_id}/council/decisions")
def get_decisions(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    kg = KnowledgeGraph.load(db, project_id)
    rows = db.execute(
        select(Decision).where(Decision.project_id == project_id)
    ).scalars().all()

    users = {u.id: u.name for u in db.query(User).all()}
    approvals_by_decision: dict[str, list[dict[str, Any]]] = {}
    for a in db.execute(select(Approval)).scalars().all():
        approvals_by_decision.setdefault(a.decision_id, []).append({
            "id": a.id, "action": a.action, "comment": a.comment,
            "user": users.get(a.user_id, a.user_id), "user_id": a.user_id,
            "ts": a.ts.isoformat(),
        })

    out = []
    for d in rows:
        cluster = kg.node(d.cluster_id) or {}
        payload = d.payload_json or {}
        out.append({
            "id": d.id, "cluster_id": d.cluster_id,
            "cluster_name": cluster.get("name"),
            "cluster_size": cluster.get("size"),
            "cluster_gxp_max": cluster.get("gxpMax"),
            "cluster_readiness": cluster.get("readinessAvg"),
            "status": d.status,
            **payload,
            "evidence": [
                {"node_id": n, "name": (kg.node(n) or {}).get("fqn")
                 or (kg.node(n) or {}).get("name") or n,
                 "kind": (kg.node(n) or {}).get("label"),
                 "gxpTier": (kg.node(n) or {}).get("gxpTier")}
                for n in (payload.get("evidence_node_ids") or []) if kg.has(n)
            ],
            "provenance": {
                "model_id": d.model_id, "generator": d.generator,
                "prompt_hash": d.prompt_hash, "input_hash": d.input_hash,
                "temperature": d.temperature, "prompt_version": d.prompt_version,
            },
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "approvals": approvals_by_decision.get(d.id, []),
            "transcript_length": len(d.transcript_json or []),
        })

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    out.sort(key=lambda d: (order.get(str(d.get("cluster_gxp_max")), 3),
                            -(d.get("cluster_size") or 0)))

    counts = {"Proposed": 0, "Approved": 0, "Rejected": 0}
    for d in out:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    reviewed = counts["Approved"] + counts["Rejected"]
    return {
        "decisions": out,
        "counts": counts,
        # PRD §15: the override rate is shown openly.
        "override_rate": round(counts["Rejected"] / reviewed, 4) if reviewed else None,
        "strategies": _tally(out, "strategy"),
    }


def _tally(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        v = str(r.get(key) or "")
        if v:
            out[v] = out.get(v, 0) + 1
    return out


@router.get("/decisions/{decision_id}/transcript")
def get_transcript(decision_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The full debate, for replaying it after the job has finished."""
    d = db.get(Decision, decision_id)
    if d is None:
        raise HTTPException(404, "decision not found")
    return {
        "decision_id": d.id, "cluster_id": d.cluster_id, "status": d.status,
        "decision": d.payload_json or {},
        "transcript": d.transcript_json or [],
        "provenance": {
            "model_id": d.model_id, "generator": d.generator,
            "prompt_hash": d.prompt_hash, "input_hash": d.input_hash,
            "temperature": d.temperature, "prompt_version": d.prompt_version,
        },
    }


# =============================================================================
# Human approval gate (PRD §15)
# =============================================================================

def _decide(
    decision_id: str, action: str, body: ApprovalRequest, db: Session
) -> dict[str, Any]:
    d = db.get(Decision, decision_id)
    if d is None:
        raise HTTPException(404, "decision not found")
    if action == "reject" and not body.comment.strip():
        raise HTTPException(400, "a comment is required when rejecting a decision")

    user = db.get(User, body.user_id) if body.user_id else None
    if user is None:
        raise HTTPException(
            400,
            "user_id is required: an approval must be attributable to a named "
            "person (21 CFR 11.10(d)). Pick a user in the header switcher.",
        )

    d.status = "Approved" if action == "approve" else "Rejected"
    approval = Approval(decision_id=d.id, user_id=user.id, action=action,
                        comment=body.comment)
    db.add(approval)
    db.commit()

    entry = record(
        f"decision.{action}d", actor=user.name, entity="decision", entity_id=d.id,
        payload={"project_id": d.project_id, "cluster_id": d.cluster_id,
                 "strategy": (d.payload_json or {}).get("strategy"),
                 "comment": body.comment, "role": user.role,
                 "model_id": d.model_id, "generator": d.generator},
        db=db,
    )
    return {
        "decision_id": d.id, "cluster_id": d.cluster_id, "status": d.status,
        "action": action, "by": user.name, "role": user.role,
        "comment": body.comment, "ts": approval.ts.isoformat(),
        "audit_entry": entry,
    }


@router.post("/decisions/{decision_id}/approve")
def approve(decision_id: str, body: ApprovalRequest,
            db: Session = Depends(get_db)) -> dict[str, Any]:
    return _decide(decision_id, "approve", body, db)


@router.post("/decisions/{decision_id}/reject")
def reject(decision_id: str, body: ApprovalRequest,
           db: Session = Depends(get_db)) -> dict[str, Any]:
    return _decide(decision_id, "reject", body, db)
