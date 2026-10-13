"""Engine 5 schemas — the Council's output contract (PRD §12.3).

``CouncilDecision`` is handed to Gemini as ``response_schema``, so the API
returns conforming JSON. It is then re-validated with Pydantic *and* every
``evidence_node_ids`` entry is checked to exist in the graph before the decision
is accepted. A decision that cannot cite the graph is rejected, not stored.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Strategy = Literal["Retire", "Retain", "Rehost", "Relocate", "Replatform", "Repurchase", "Refactor"]
TargetPattern = Literal[
    "StranglerFig", "EventDriven", "CQRS", "Serverless",
    "Containerized", "ManagedDB", "APIGateway", "SaaS",
]

STRATEGIES: tuple[str, ...] = (
    "Retire", "Retain", "Rehost", "Relocate", "Replatform", "Repurchase", "Refactor",
)
PATTERNS: tuple[str, ...] = (
    "StranglerFig", "EventDriven", "CQRS", "Serverless",
    "Containerized", "ManagedDB", "APIGateway", "SaaS",
)

AGENT_NAMES: tuple[str, ...] = (
    "Cloud Architect", "Validation & QA Lead", "Security Officer",
    "FinOps Analyst", "Regulatory Affairs", "Moderator",
)


class Dissent(BaseModel):
    agent: str
    position: str
    reason: str


class CouncilDecision(BaseModel):
    """The Moderator's synthesis for one cluster."""

    cluster_id: str
    strategy: Strategy
    target_pattern: list[TargetPattern] = Field(default_factory=list)
    target_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    risks: list[str] = Field(default_factory=list)
    dissent: list[Dissent] = Field(default_factory=list)
    evidence_node_ids: list[str] = Field(default_factory=list)
    effort_weeks: tuple[float, float, float]   # (optimistic, likely, pessimistic)

    @field_validator("effort_weeks")
    @classmethod
    def _ordered(cls, v: tuple[float, float, float]) -> tuple[float, float, float]:
        o, l, p = (max(0.1, float(x)) for x in v)
        # A PERT triple that is not ordered is a bug, not an opinion: sort it
        # rather than feeding an impossible distribution to the simulator.
        o, l, p = sorted((o, l, p))
        return (round(o, 2), round(l, 2), round(p, 2))

    @field_validator("rationale")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rationale is required")
        return v.strip()


# The JSON Schema handed to Gemini. Written out rather than derived from the
# Pydantic model because the API rejects some of the constructs Pydantic emits
# ($defs/$ref, prefixItems for tuples).
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cluster_id": {"type": "string"},
        "strategy": {"type": "string", "enum": list(STRATEGIES)},
        "target_pattern": {"type": "array", "items": {"type": "string", "enum": list(PATTERNS)}},
        "target_services": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "dissent": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "position": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["agent", "position", "reason"],
            },
        },
        "evidence_node_ids": {"type": "array", "items": {"type": "string"}},
        "effort_weeks_optimistic": {"type": "number"},
        "effort_weeks_likely": {"type": "number"},
        "effort_weeks_pessimistic": {"type": "number"},
    },
    "required": [
        "cluster_id", "strategy", "target_pattern", "confidence", "rationale",
        "risks", "evidence_node_ids",
        "effort_weeks_optimistic", "effort_weeks_likely", "effort_weeks_pessimistic",
    ],
}

OPINION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "position": {"type": "string", "enum": list(STRATEGIES)},
        "patterns": {"type": "array", "items": {"type": "string", "enum": list(PATTERNS)}},
        "argument": {"type": "string"},
        "concerns": {"type": "array", "items": {"type": "string"}},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "evidence_node_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["position", "argument", "confidence", "evidence_node_ids"],
}


class AgentOpinion(BaseModel):
    agent: str
    position: str = "Retain"
    patterns: list[str] = Field(default_factory=list)
    argument: str = ""
    concerns: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    evidence_node_ids: list[str] = Field(default_factory=list)
    round: int = 1
    generator: str = "deterministic"

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


class TranscriptEntry(BaseModel):
    """One streamed message in the debate (what the UI renders as a bubble)."""

    seq: int
    stage: str                     # context | opinion | rebuttal | synthesis | validation
    agent: str
    text: str
    position: str = ""
    confidence: float | None = None
    evidence_node_ids: list[str] = Field(default_factory=list)
    round: int = 0
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())


class CouncilState(BaseModel):
    """State threaded through the Council state machine (PRD §12.2)."""

    project_id: str
    cluster_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    opinions: list[AgentOpinion] = Field(default_factory=list)
    rebuttals: list[AgentOpinion] = Field(default_factory=list)
    decision: CouncilDecision | None = None
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    needs_human_review: bool = False
    retries: int = 0
    provenance: dict[str, Any] = Field(default_factory=dict)

    def say(
        self,
        stage: str,
        agent: str,
        text: str,
        *,
        position: str = "",
        confidence: float | None = None,
        evidence: list[str] | None = None,
        rnd: int = 0,
    ) -> TranscriptEntry:
        entry = TranscriptEntry(
            seq=len(self.transcript) + 1, stage=stage, agent=agent, text=text,
            position=position, confidence=confidence,
            evidence_node_ids=evidence or [], round=rnd,
        )
        self.transcript.append(entry)
        return entry
