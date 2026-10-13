"""SQLAlchemy models — exactly the tables in PRD §16.3, plus the graph blob store."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Seeded demo users — no login, a header switcher picks one (PRD §18)."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(default=_now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(200))
    repo_url: Mapped[str] = mapped_column(String(500), default="")
    source_path: Mapped[str] = mapped_column(String(1000), default="")
    target_cloud: Mapped[str] = mapped_column(String(20), default="AWS")
    use_runtime_traces: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(40), default="created")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(default=_now)
    # Wall-clock assessment timer (PRD §23 "Assessment time")
    analysis_started_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    analysis_finished_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    step: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    events_json: Mapped[list] = mapped_column(JSON, default=list)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)


class GraphBlob(Base):
    """The embedded knowledge graph, serialised per project (replaces the Neo4j server)."""

    __tablename__ = "graph_blobs"
    project_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(default=_now, onupdate=_now)


class GxpOverride(Base):
    __tablename__ = "gxp_overrides"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    node_id: Mapped[str] = mapped_column(String(400), index=True)
    old_tier: Mapped[str] = mapped_column(String(20))
    new_tier: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(String(32))
    ts: Mapped[dt.datetime] = mapped_column(default=_now)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    cluster_id: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    transcript_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="Proposed")
    # ---- Annex 22 reproducibility record (PRD §15) ----
    model_id: Mapped[str] = mapped_column(String(80), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    prompt_version: Mapped[str] = mapped_column(String(40), default="")
    generator: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[dt.datetime] = mapped_column(default=_now)
    __table_args__ = (UniqueConstraint("project_id", "cluster_id", name="uq_decision_cluster"),)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[dt.datetime] = mapped_column(default=_now)


class Roadmap(Base):
    __tablename__ = "roadmaps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    schedule_json: Mapped[dict] = mapped_column(JSON, default=dict)
    montecarlo_json: Mapped[dict] = mapped_column(JSON, default=dict)
    inputs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(default=_now)


class EvidencePack(Base):
    __tablename__ = "evidence_packs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    wave: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(1000))
    html_path: Mapped[str] = mapped_column(String(1000), default="")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(default=_now)


class AuditLog(Base):
    """Append-only, hash-chained. Never UPDATE or DELETE a row here."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(default=_now)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[str] = mapped_column(String(200), default="")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")


class Embedding(Base):
    __tablename__ = "embeddings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    node_id: Mapped[str] = mapped_column(String(400), index=True)
    dim: Mapped[int] = mapped_column(Integer, default=384)
    vector: Mapped[bytes] = mapped_column(LargeBinary)
