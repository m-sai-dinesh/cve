"""Roadmap, what-if, evidence packs, jobs and the audit log (PRD §17)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.audit import verify_chain
from ..db.models import AuditLog, EvidencePack, Project, Roadmap
from ..db.session import get_db
from ..jobs import get_job, list_jobs, run_in_background
from ..pipeline import run_evidence, run_roadmap, whatif
from .schemas import JobAccepted, RoadmapRequest, WhatIfRequest

router = APIRouter(tags=["roadmap"])


# =============================================================================
# Engine 6
# =============================================================================

@router.post("/projects/{project_id}/roadmap", status_code=202)
def start_roadmap(
    project_id: str, body: RoadmapRequest | None = None, db: Session = Depends(get_db)
) -> JobAccepted:
    from ..db.models import Decision

    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    opts = body or RoadmapRequest()
    q = db.query(Decision).filter(Decision.project_id == project_id)
    if opts.approved_only:
        q = q.filter(Decision.status == "Approved")
    if q.count() == 0:
        raise HTTPException(
            409,
            "no Council decisions"
            + (" with status Approved" if opts.approved_only else "")
            + " - run the Council first",
        )

    windows = ([w.model_dump() for w in opts.freeze_windows]
               if opts.freeze_windows is not None else None)
    job_id = run_in_background(
        project_id, "roadmap",
        lambda ctx: run_roadmap(
            ctx, squads=opts.squads, freeze_windows=windows,
            target_date=opts.target_date, start_date=opts.start_date,
            runs=opts.runs, approved_only=opts.approved_only,
            wave_weeks=opts.wave_weeks,
            max_high_cutovers_per_wave=opts.max_high_cutovers_per_wave,
        ),
    )
    return JobAccepted.of(job_id, project_id, "roadmap")


@router.get("/projects/{project_id}/roadmap")
def get_roadmap(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    r = db.execute(
        select(Roadmap).where(Roadmap.project_id == project_id)
        .order_by(Roadmap.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(409, "no roadmap yet - run POST /projects/{id}/roadmap")
    return {
        "id": r.id,
        "schedule": r.schedule_json or {},
        "montecarlo": r.montecarlo_json or {},
        "inputs": r.inputs_json or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/projects/{project_id}/roadmap/history")
def roadmap_history(project_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Roadmap).where(Roadmap.project_id == project_id)
        .order_by(Roadmap.created_at.desc()).limit(20)
    ).scalars().all()
    return [{
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "makespan_weeks": (r.schedule_json or {}).get("makespan_weeks"),
        "p80": ((r.montecarlo_json or {}).get("percentiles") or {}).get("p80"),
        "p80_date": ((r.montecarlo_json or {}).get("dates") or {}).get("p80"),
        "squads": (r.inputs_json or {}).get("squads"),
        "solver": (r.schedule_json or {}).get("solver"),
    } for r in rows]


@router.post("/projects/{project_id}/roadmap/whatif")
def roadmap_whatif(
    project_id: str, body: WhatIfRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Synchronous re-solve for the what-if sliders (PRD §13.2)."""
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    windows = ([w.model_dump() for w in body.freeze_windows]
               if body.freeze_windows is not None else None)
    try:
        return whatif(
            project_id, squads=body.squads, freeze_windows=windows,
            target_date=body.target_date, strategy_overrides=body.strategy_overrides,
            runs=body.runs, wave_weeks=body.wave_weeks,
            max_high_cutovers_per_wave=body.max_high_cutovers_per_wave,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


# =============================================================================
# Engine 7
# =============================================================================

@router.post("/projects/{project_id}/evidence/{wave}", status_code=202)
def start_evidence(project_id: str, wave: int, db: Session = Depends(get_db)) -> JobAccepted:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    r = db.execute(
        select(Roadmap).where(Roadmap.project_id == project_id)
        .order_by(Roadmap.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(409, "no roadmap yet - run the roadmap optimizer first")
    waves = {int(w["wave"]) for w in ((r.schedule_json or {}).get("waves") or [])}
    if wave not in waves:
        raise HTTPException(
            400, f"wave {wave} is not in the current roadmap. Available: {sorted(waves)}"
        )

    job_id = run_in_background(project_id, "evidence", lambda ctx: run_evidence(ctx, wave))
    return JobAccepted.of(job_id, project_id, "evidence")


@router.get("/projects/{project_id}/evidence")
def list_packs(project_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvidencePack).where(EvidencePack.project_id == project_id)
        .order_by(EvidencePack.created_at.desc())
    ).scalars().all()
    out = []
    for p in rows:
        pdf = Path(p.file_path)
        out.append({
            "id": p.id, "wave": p.wave,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "meta": p.meta_json or {},
            "exists": pdf.exists(),
            "size_kb": round(pdf.stat().st_size / 1024, 1) if pdf.exists() else None,
            "pdf_url": f"/projects/{project_id}/evidence/{p.id}/download",
            "preview_url": f"/projects/{project_id}/evidence/{p.id}/preview",
        })
    return out


@router.get("/projects/{project_id}/evidence/{pack_id}/download")
def download_pack(project_id: str, pack_id: str, db: Session = Depends(get_db)) -> FileResponse:
    p = db.get(EvidencePack, pack_id)
    if p is None or p.project_id != project_id:
        raise HTTPException(404, "evidence pack not found")
    path = Path(p.file_path)
    if not path.exists():
        raise HTTPException(410, "the generated file is no longer on disk - regenerate the pack")
    project = db.get(Project, project_id)
    name = f"{(project.name if project else 'project').replace(' ', '_')}_EvidencePack_Wave{p.wave}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=name)


@router.get("/projects/{project_id}/evidence/{pack_id}/preview", response_class=HTMLResponse)
def preview_pack(project_id: str, pack_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    p = db.get(EvidencePack, pack_id)
    if p is None or p.project_id != project_id:
        raise HTTPException(404, "evidence pack not found")
    path = Path(p.html_path or "")
    if not path.exists():
        raise HTTPException(410, "the HTML preview is no longer on disk - regenerate the pack")
    return HTMLResponse(path.read_text(encoding="utf-8"))


# =============================================================================
# Jobs
# =============================================================================

@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.get("/projects/{project_id}/jobs")
def project_jobs(project_id: str, limit: int = Query(25, ge=1, le=100)) -> list[dict[str, Any]]:
    return list_jobs(project_id, limit)


# =============================================================================
# Audit log (PRD §15, §18 screen 10)
# =============================================================================

@router.get("/audit")
def audit(
    actor: str | None = None,
    action: str | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    project_id: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    verify: bool = True,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if actor:
        q = q.where(AuditLog.actor == actor)
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    if entity:
        q = q.where(AuditLog.entity == entity)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    rows = db.execute(q.offset(offset).limit(limit)).scalars().all()

    if project_id:
        rows = [
            r for r in rows
            if r.entity_id == project_id
            or (r.payload_json or {}).get("project_id") == project_id
        ]

    chain = verify_chain(db) if verify else {"valid": None, "detail": "verification skipped"}
    return {
        "rows": [{
            "id": r.id, "ts": r.ts.isoformat() if r.ts else None,
            "actor": r.actor, "action": r.action, "entity": r.entity,
            "entity_id": r.entity_id, "payload": r.payload_json or {},
            "prev_hash": r.prev_hash, "hash": r.hash,
        } for r in rows],
        "total": db.query(AuditLog).count(),
        "chain": chain,
        "actions": sorted({a for (a,) in db.query(AuditLog.action).distinct().all()}),
    }


@router.post("/audit/verify")
def audit_verify(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Verify the hash chain end to end (the UI's "Verify chain" button)."""
    return verify_chain(db)
