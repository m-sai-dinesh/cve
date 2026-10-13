"""Projects, users and the analysis trigger (PRD §17)."""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.audit import record
from ..core.llm import get_llm
from ..db.graph import KnowledgeGraph
from ..db.models import Decision, EvidencePack, Job, Project, Roadmap, User
from ..db.session import get_db
from ..jobs import list_jobs, run_in_background
from ..pipeline import analyze
from .schemas import AnalyzeOptions, JobAccepted, ProjectCreate

router = APIRouter(tags=["projects"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def project_payload(p: Project, db: Session) -> dict[str, Any]:
    summary = p.summary_json or {}
    elapsed = None
    if p.analysis_started_at:
        end = p.analysis_finished_at or dt.datetime.now(dt.timezone.utc)
        start = p.analysis_started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt.timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=dt.timezone.utc)
        elapsed = round((end - start).total_seconds(), 2)

    counts = {
        "decisions": db.query(Decision).filter(Decision.project_id == p.id).count(),
        "approved": db.query(Decision).filter(
            Decision.project_id == p.id, Decision.status == "Approved").count(),
        "rejected": db.query(Decision).filter(
            Decision.project_id == p.id, Decision.status == "Rejected").count(),
        "roadmaps": db.query(Roadmap).filter(Roadmap.project_id == p.id).count(),
        "evidence_packs": db.query(EvidencePack).filter(
            EvidencePack.project_id == p.id).count(),
    }
    return {
        "id": p.id, "name": p.name, "repo_url": p.repo_url,
        "source_path": p.source_path, "target_cloud": p.target_cloud,
        "use_runtime_traces": p.use_runtime_traces,
        "status": p.status, "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "analysis_started_at": (p.analysis_started_at.isoformat()
                                if p.analysis_started_at else None),
        "analysis_finished_at": (p.analysis_finished_at.isoformat()
                                 if p.analysis_finished_at else None),
        "assessment_seconds": summary.get("assessment_seconds", elapsed),
        "elapsed_seconds": elapsed,
        "has_twin": KnowledgeGraph.exists(db, p.id),
        "counts": counts,
        "summary": summary,
    }


@router.get("/users")
def get_users(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Seeded demo users for the header switcher (PRD §18 - no login screen)."""
    rows = db.execute(select(User).order_by(User.name)).scalars().all()
    return [{"id": u.id, "name": u.name, "role": u.role} for u in rows]


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    llm = get_llm()
    return {
        "status": "ok",
        "projects": db.query(Project).count(),
        "llm": llm.status(),
        "graph_store": "embedded (NetworkX + SQLite)"
        + (f" mirrored to Neo4j at {settings.neo4j_uri}" if settings.neo4j_uri else ""),
        "data_dir": str(settings.data_dir),
        "engines": {
            "1": "Living Architecture Twin",
            "2": "GxP Criticality Scanner",
            "3": "Cloud Readiness Scorer",
            "4": "Blast-Radius-Aware Decomposition",
            "5": "AI Architecture Council",
            "6": "Roadmap Optimizer & Monte Carlo",
            "7": "Evidence Pack Generator",
        },
    }


@router.get("/projects")
def get_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    return [project_payload(p, db) for p in rows]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not (body.repo_url or body.source_path):
        raise HTTPException(
            400,
            "provide repo_url or source_path, or use POST /projects/upload for a zip archive",
        )
    if body.source_path and not Path(body.source_path).exists():
        raise HTTPException(400, f"source_path does not exist: {body.source_path}")

    p = Project(
        name=body.name, repo_url=body.repo_url, source_path=body.source_path,
        target_cloud=body.target_cloud, use_runtime_traces=body.use_runtime_traces,
        created_by=body.created_by,
    )
    db.add(p)
    db.commit()
    record("project.created", actor=body.created_by or "system", entity="project",
           entity_id=p.id, payload={"name": p.name, "target_cloud": p.target_cloud,
                                    "repo_url": p.repo_url, "source_path": p.source_path})
    return project_payload(p, db)


@router.post("/projects/upload", status_code=201)
async def create_project_from_upload(
    name: str = Form(...),
    target_cloud: str = Form("AWS"),
    use_runtime_traces: bool = Form(True),
    created_by: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a project from an uploaded zip archive (PRD §17 POST /projects)."""
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "upload a .zip archive of the repository")

    p = Project(name=name, target_cloud=target_cloud,
                use_runtime_traces=use_runtime_traces, created_by=created_by)
    db.add(p)
    db.commit()

    dest = settings.uploads_dir / p.id
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "upload.zip"
    size = 0
    with archive.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                shutil.rmtree(dest, ignore_errors=True)
                db.delete(p)
                db.commit()
                raise HTTPException(413, f"archive exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
            out.write(chunk)

    from ..engines.twin.ingest import prepare_source

    try:
        root, _notes = prepare_source(dest=dest, upload_zip=archive)
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        db.delete(p)
        db.commit()
        raise HTTPException(400, f"could not unpack the archive: {exc}") from exc

    p.source_path = str(root)
    db.commit()
    record("project.created", actor=created_by or "system", entity="project",
           entity_id=p.id, payload={"name": p.name, "upload": file.filename,
                                    "bytes": size, "target_cloud": target_cloud})
    return project_payload(p, db)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    payload = project_payload(p, db)
    payload["jobs"] = list_jobs(project_id, limit=12)
    return payload


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> None:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    name = p.name
    from ..db.models import Approval, Embedding, GraphBlob, GxpOverride

    for model, attr in ((Decision, "project_id"), (Roadmap, "project_id"),
                        (EvidencePack, "project_id"), (Job, "project_id"),
                        (Embedding, "project_id"), (GxpOverride, "project_id")):
        db.query(model).filter(getattr(model, attr) == project_id).delete()
    db.query(GraphBlob).filter(GraphBlob.project_id == project_id).delete()
    db.delete(p)
    db.commit()
    shutil.rmtree(settings.uploads_dir / project_id, ignore_errors=True)
    # The audit log is append-only: deleting a project records the deletion
    # rather than removing its history.
    record("project.deleted", entity="project", entity_id=project_id,
           payload={"name": name})


@router.post("/projects/{project_id}/analyze", status_code=202)
def start_analysis(
    project_id: str, body: AnalyzeOptions | None = None, db: Session = Depends(get_db)
) -> JobAccepted:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    opts = body or AnalyzeOptions()
    if opts.weights is not None and len(opts.weights) != 5:
        raise HTTPException(400, "weights must have 5 entries: "
                                 "structural, runtime, data, cochange, semantic")

    running = [j for j in list_jobs(project_id, 10)
               if j["type"] == "analyze" and j["status"] == "running"]
    if running:
        raise HTTPException(409, f"analysis already running (job {running[0]['id']})")

    use_traces = opts.use_runtime_traces and p.use_runtime_traces
    job_id = run_in_background(
        project_id, "analyze",
        lambda ctx: analyze(
            ctx,
            use_runtime_traces=use_traces,
            use_llm=opts.use_llm,
            use_git_mining=opts.use_git_mining,
            weights=opts.weights,
            gamma=opts.gamma,
            min_cluster_size=opts.min_cluster_size,
        ),
        actor=p.created_by or "system",
    )
    return JobAccepted.of(job_id, project_id, "analyze")
