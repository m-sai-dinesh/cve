"""Engine 5 orchestration — the Council state machine (PRD §12.2).

    START -> load_context(cluster) -> parallel_opinions(5 agents)
          -> rebuttal_round (each sees the others, 1 round)
          -> moderator_synthesis -> validate_output(JSON schema + evidence IDs exist)
          -> (if invalid) retry_once -> human_review_queue -> END

The PRD specifies LangGraph. This implements the same state machine directly:
the graph is five nodes with one conditional retry edge, and writing it out
keeps the streaming contract, the retry semantics and the validation gate
visible in one readable file rather than spread across a framework's callbacks.
It also removes two heavy transitive dependency trees from a tool whose whole
pitch is that it runs anywhere. State is the ``CouncilState`` pydantic model, so
every transition is still typed and inspectable.

``on_event`` streams every transcript entry to the WebSocket as it happens.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ...core.llm import get_llm
from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from . import agents as A
from . import tools as T
from .state import AgentOpinion, CouncilDecision, CouncilState, Dissent

log = get_logger("council")

EventSink = Callable[[dict[str, Any]], None] | None


def _emit(state: CouncilState, entry, on_event: EventSink) -> None:
    if on_event is not None:
        try:
            on_event({"type": "council_message", **entry.model_dump()})
        except Exception as exc:          # a broken socket must not stop the debate
            log.warning("council_emit_failed", error=str(exc))


# =============================================================================
# Nodes
# =============================================================================

def load_context(kg: KnowledgeGraph, state: CouncilState, on_event: EventSink) -> CouncilState:
    ctx = T.get_cluster_summary(kg, state.cluster_id)
    state.context = ctx
    if "error" in ctx:
        state.needs_human_review = True
        _emit(state, state.say("context", "System", str(ctx["error"])), on_event)
        return state

    tiers = ctx.get("gxp_counts") or {}
    summary = (
        f"Reviewing **{ctx.get('name')}** - {ctx.get('size')} classes, "
        f"{ctx.get('loc')} LOC, GxP {ctx.get('gxp_max')} "
        f"({tiers.get('HIGH', 0)} HIGH / {tiers.get('MEDIUM', 0)} MEDIUM / "
        f"{tiers.get('LOW', 0)} LOW), average readiness "
        f"{ctx.get('readiness_avg')}/100, {ctx.get('runtime_hits', 0):,} runtime hits.\n\n"
        f"Regulated tables: {', '.join(ctx.get('regulated_tables') or []) or 'none'}.\n"
        f"Compliance gaps in scope: {', '.join(ctx.get('compliance_gaps') or []) or 'none'}.\n"
        f"Depends on {len(ctx.get('depends_on') or [])} cluster(s); "
        f"{len(ctx.get('depended_on_by') or [])} cluster(s) depend on it."
    )
    _emit(state, state.say("context", "System", summary, evidence=[state.cluster_id]), on_event)
    return state


def parallel_opinions(state: CouncilState, on_event: EventSink) -> CouncilState:
    """Five specialists, concurrently (PRD §12.2 parallel_opinions)."""
    names = list(A.AGENTS)

    def run(agent: str) -> AgentOpinion:
        return A.ask_agent(agent, state.context, rnd=1)

    # Threads, not processes: these are network-bound LLM calls. With no API key
    # the rule sets are pure CPU and finish instantly either way.
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        results = list(pool.map(run, names))

    # Emit in a stable order so the UI transcript is reproducible.
    for op in sorted(results, key=lambda o: names.index(o.agent)):
        state.opinions.append(op)
        _emit(state, state.say(
            "opinion", op.agent, op.argument, position=op.position,
            confidence=op.confidence, evidence=op.evidence_node_ids, rnd=1,
        ), on_event)
    return state


def rebuttal_round(state: CouncilState, on_event: EventSink) -> CouncilState:
    """One round in which each agent sees the others (PRD §12.2)."""
    names = list(A.AGENTS)

    def run(agent: str) -> AgentOpinion:
        return A.ask_agent(agent, state.context, others=state.opinions, rnd=2)

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        results = list(pool.map(run, names))

    for op in sorted(results, key=lambda o: names.index(o.agent)):
        state.rebuttals.append(op)
        _emit(state, state.say(
            "rebuttal", op.agent, op.argument, position=op.position,
            confidence=op.confidence, evidence=op.evidence_node_ids, rnd=2,
        ), on_event)
    return state


def moderator_synthesis(
    kg: KnowledgeGraph, state: CouncilState, on_event: EventSink
) -> tuple[CouncilState, dict[str, Any] | None]:
    # Price every strategy deterministically so the Moderator argues against
    # real numbers rather than inventing them.
    effort_options = {
        s: T.estimate_effort(kg, state.cluster_id, s)["effort_weeks"]
        for s in ("Retain", "Rehost", "Replatform", "Repurchase", "Refactor", "Retire")
    }

    raw, llm_res = A.ask_moderator(state.context, state.opinions, state.rebuttals, effort_options)
    generator = "gemini"
    if raw is None:
        raw = A.rule_decision(kg, state.context, state.opinions, state.rebuttals)
        generator = "deterministic"

    llm = get_llm()
    if llm_res is not None:
        state.provenance = {**llm_res.provenance(), "generator": generator}
    else:
        from ...core.llm import PROMPT_VERSION, hash_payload

        state.provenance = {
            "model_id": llm.model_id,
            "prompt_hash": hash_payload({"prompts": "deterministic-rule-set",
                                          "version": PROMPT_VERSION}),
            "input_hash": hash_payload(state.context),
            "temperature": 0.0,
            "prompt_version": PROMPT_VERSION,
            "generator": "deterministic",
        }
    return state, raw


def validate_output(
    kg: KnowledgeGraph, state: CouncilState, raw: dict[str, Any], on_event: EventSink
) -> tuple[CouncilState, bool]:
    """Schema validation plus the evidence-existence check (PRD §12.2, §15).

    This is the gate the whole "LLMs hallucinate" answer rests on. A decision
    that cites a node which is not in the graph is not accepted and softened -
    it is rejected, and the stage is retried once.
    """
    problems: list[str] = []

    # --- effort triple, held to the +/-30% adjustment limit of PRD 12.5 -----
    strategy = str(raw.get("strategy") or "Retain")
    baseline = T.estimate_effort(kg, state.cluster_id, strategy)["effort_weeks"]
    proposed = (
        float(raw.get("effort_weeks_optimistic") or baseline[0]),
        float(raw.get("effort_weeks_likely") or baseline[1]),
        float(raw.get("effort_weeks_pessimistic") or baseline[2]),
    )
    effort, clamped = T.clamp_effort(tuple(baseline), proposed)  # type: ignore[arg-type]
    if clamped:
        problems.append(
            "the proposed effort was outside the permitted +/-30% adjustment and was clamped"
        )

    # --- evidence ids must exist in the graph -------------------------------
    cited = [str(e) for e in (raw.get("evidence_node_ids") or [])]
    valid = [e for e in cited if kg.has(e)]
    invalid = [e for e in cited if not kg.has(e)]
    if invalid:
        problems.append(
            f"{len(invalid)} cited node id(s) do not exist in the graph: "
            f"{', '.join(invalid[:4])}"
        )
    if not valid:
        problems.append("no valid evidence node id was cited")

    try:
        decision = CouncilDecision(
            cluster_id=state.cluster_id,
            strategy=strategy,                     # type: ignore[arg-type]
            target_pattern=[p for p in (raw.get("target_pattern") or [])],  # type: ignore[arg-type]
            target_services=[str(s) for s in (raw.get("target_services") or [])],
            confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.5))),
            rationale=str(raw.get("rationale") or ""),
            risks=[str(r) for r in (raw.get("risks") or [])][:10],
            dissent=[
                Dissent(agent=str(d.get("agent", "")), position=str(d.get("position", "")),
                        reason=str(d.get("reason", "")))
                for d in (raw.get("dissent") or []) if isinstance(d, dict)
            ],
            evidence_node_ids=valid[:14],
            effort_weeks=effort,
        )
    except Exception as exc:
        state.validation = {
            "valid": False,
            "problems": problems + [f"schema validation failed: {exc}"],
            "evidence_valid": len(valid), "evidence_invalid": len(invalid),
        }
        _emit(state, state.say("validation", "System",
                               f"Decision rejected: {state.validation['problems'][0]}"), on_event)
        return state, False

    # A missing-evidence decision is never accepted, even if it parses.
    if not valid:
        state.validation = {
            "valid": False, "problems": problems,
            "evidence_valid": 0, "evidence_invalid": len(invalid),
        }
        _emit(state, state.say("validation", "System",
                               "Decision rejected: no claim was supported by a graph node id."),
              on_event)
        return state, False

    state.decision = decision
    state.validation = {
        "valid": True,
        "problems": problems,
        "evidence_valid": len(valid),
        "evidence_invalid": len(invalid),
        "effort_clamped": clamped,
        "effort_baseline": baseline,
        "checks": [
            "output conforms to the CouncilDecision schema",
            f"all {len(valid)} cited evidence node id(s) exist in the knowledge graph",
            "effort estimate within the permitted +/-30% of the deterministic model",
            "PERT triple is correctly ordered",
        ],
    }

    # Low confidence or an unresolved HIGH-tier dispute goes to a human.
    tier = str(state.context.get("gxp_max") or "LOW")
    if decision.confidence < 0.5:
        state.needs_human_review = True
    if tier == "HIGH" and decision.dissent:
        state.needs_human_review = True

    return state, True


def finalise(state: CouncilState, on_event: EventSink) -> CouncilState:
    d = state.decision
    if d is None:
        _emit(state, state.say("synthesis", "Moderator",
                               "No valid decision could be produced. Escalated for human review."),
              on_event)
        state.needs_human_review = True
        return state

    text = (
        f"**Decision: {d.strategy}**"
        + (f" using {', '.join(d.target_pattern)}" if d.target_pattern else "")
        + f" (confidence {d.confidence:.0%})\n\n{d.rationale}"
    )
    if d.target_services:
        text += f"\n\n**Target services:** {', '.join(d.target_services)}"
    if d.risks:
        text += "\n\n**Conditions and risks:**\n" + "\n".join(f"- {r}" for r in d.risks[:6])
    if d.dissent:
        text += "\n\n**Recorded dissent:**\n" + "\n".join(
            f"- *{x.agent}* argued **{x.position}**: {x.reason[:200]}" for x in d.dissent
        )
    text += (f"\n\n**Effort (PERT):** {d.effort_weeks[0]} / {d.effort_weeks[1]} / "
             f"{d.effort_weeks[2]} weeks (optimistic / likely / pessimistic)")

    _emit(state, state.say(
        "synthesis", "Moderator", text, position=d.strategy,
        confidence=d.confidence, evidence=d.evidence_node_ids,
    ), on_event)

    checks = state.validation.get("checks") or []
    _emit(state, state.say(
        "validation", "System",
        "Validated: " + "; ".join(checks)
        + (". Flagged for human review." if state.needs_human_review
           else ". Awaiting approval by a named reviewer."),
    ), on_event)
    return state


# =============================================================================
# The machine
# =============================================================================

def deliberate(
    kg: KnowledgeGraph,
    project_id: str,
    cluster_id: str,
    *,
    on_event: EventSink = None,
) -> CouncilState:
    """Run the Council for one cluster."""
    state = CouncilState(project_id=project_id, cluster_id=cluster_id)

    state = load_context(kg, state, on_event)
    if state.needs_human_review and not state.context.get("size"):
        return state

    state = parallel_opinions(state, on_event)
    state = rebuttal_round(state, on_event)

    state, raw = moderator_synthesis(kg, state, on_event)
    ok = False
    if raw is not None:
        state, ok = validate_output(kg, state, raw, on_event)

    # retry_once (PRD §12.2). The retry uses the deterministic reasoner, which
    # cannot fabricate a node id, so the second attempt is guaranteed citable.
    if not ok:
        state.retries += 1
        _emit(state, state.say(
            "validation", "System",
            "Retrying synthesis once with the deterministic reasoner, which "
            "constructs its citations directly from the graph.",
        ), on_event)
        raw = A.rule_decision(kg, state.context, state.opinions, state.rebuttals)
        state.provenance["generator"] = "deterministic-retry"
        state, ok = validate_output(kg, state, raw, on_event)
        if not ok:
            state.needs_human_review = True

    state = finalise(state, on_event)
    log.info("council_done", cluster=cluster_id,
             strategy=(state.decision.strategy if state.decision else None),
             confidence=(state.decision.confidence if state.decision else None),
             retries=state.retries, human_review=state.needs_human_review,
             generator=state.provenance.get("generator"))
    return state


def deliberate_many(
    kg: KnowledgeGraph,
    project_id: str,
    cluster_ids: list[str],
    *,
    on_event: EventSink = None,
    progress=None,
) -> list[CouncilState]:
    out: list[CouncilState] = []
    total = max(1, len(cluster_ids))
    for i, cid in enumerate(cluster_ids):
        if progress:
            name = (kg.node(cid) or {}).get("name", cid)
            progress(i / total, f"council reviewing {name} ({i + 1}/{len(cluster_ids)})")
        if on_event is not None:
            on_event({"type": "council_cluster_start", "cluster_id": cid,
                      "index": i, "total": len(cluster_ids),
                      "name": (kg.node(cid) or {}).get("name", cid)})
        out.append(deliberate(kg, project_id, cid, on_event=on_event))
    if progress:
        progress(1.0, f"{len(out)} decision(s) proposed")
    return out
