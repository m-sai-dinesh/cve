"""Request/response models for the REST API (PRD §17)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    repo_url: str = ""
    source_path: str = ""
    target_cloud: Literal["AWS", "Azure", "GCP"] = "AWS"
    use_runtime_traces: bool = True
    created_by: str = ""


class AnalyzeOptions(BaseModel):
    use_runtime_traces: bool = True
    use_llm: bool = True
    use_git_mining: bool = True
    weights: list[float] | None = None
    gamma: float | None = None
    min_cluster_size: int | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class GxpOverride(BaseModel):
    new_tier: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str = Field(min_length=3, max_length=1000)
    user_id: str = ""


class DecomposeOptions(BaseModel):
    weights: list[float] | None = None
    gamma: float | None = None
    alpha: float | None = None
    beta: float | None = None
    min_cluster_size: int | None = None
    chosen: Literal["louvain", "hdbscan", "modernrx"] = "modernrx"


class CouncilRun(BaseModel):
    cluster_ids: list[str] | None = None


class ApprovalRequest(BaseModel):
    user_id: str = ""
    comment: str = ""


class FreezeWindowIn(BaseModel):
    name: str = "Freeze window"
    start_week: int | None = None
    end_week: int | None = None
    start_date: str | None = None
    end_date: str | None = None


class RoadmapRequest(BaseModel):
    squads: int | None = Field(default=None, ge=1, le=20)
    freeze_windows: list[FreezeWindowIn] | None = None
    target_date: str | None = None
    start_date: str | None = None
    runs: int | None = Field(default=None, ge=100, le=200000)
    approved_only: bool = False
    wave_weeks: int = Field(default=8, ge=2, le=26)
    max_high_cutovers_per_wave: int = Field(default=1, ge=0, le=10)


class WhatIfRequest(BaseModel):
    squads: int | None = Field(default=None, ge=1, le=20)
    freeze_windows: list[FreezeWindowIn] | None = None
    target_date: str | None = None
    strategy_overrides: dict[str, str] | None = None
    runs: int = Field(default=2000, ge=200, le=50000)
    wave_weeks: int = Field(default=8, ge=2, le=26)
    max_high_cutovers_per_wave: int = Field(default=1, ge=0, le=10)


class JobAccepted(BaseModel):
    job_id: str
    project_id: str
    type: str
    ws: str

    @staticmethod
    def of(job_id: str, project_id: str, job_type: str) -> JobAccepted:
        return JobAccepted(job_id=job_id, project_id=project_id, type=job_type,
                           ws=f"/ws/jobs/{job_id}")


class TemplateQuery(BaseModel):
    template_id: str
    params: dict[str, Any] = Field(default_factory=dict)
