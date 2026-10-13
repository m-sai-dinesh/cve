"""Engine 5 agents (PRD §12.1, §12.4).

Five specialists plus a Moderator. Each has a prompt file in ``prompts/``.

Two execution modes, and the mode is recorded on every decision:

* **gemini** — the prompt is sent to the pinned model with ``response_schema``.
* **deterministic** — with no API key, each agent's brief is evaluated by a
  rule set written from the same prompt. This is not a mock: the rules encode
  each role's actual priorities against real graph facts, and the resulting
  debate is a genuine (if less articulate) application of those briefs. It
  exists because a demo that dies without network access is not a product, and
  because it makes the Council's reasoning auditable.

Both modes produce the same ``AgentOpinion``/``CouncilDecision`` shapes, and
both are held to the same validation: evidence ids must exist in the graph.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from ...core.llm import get_llm
from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from . import tools as T
from .state import OPINION_SCHEMA, RESPONSE_SCHEMA, AgentOpinion

log = get_logger("council.agents")

PROMPT_DIR = Path(__file__).parent / "prompts"

AGENTS: dict[str, str] = {
    "Cloud Architect": "cloud_architect",
    "Validation & QA Lead": "validation_qa_lead",
    "Security Officer": "security_officer",
    "FinOps Analyst": "finops_analyst",
    "Regulatory Affairs": "regulatory_affairs",
}
MODERATOR = "Moderator"


@lru_cache(maxsize=16)
def load_prompt(slug: str) -> str:
    shared = (PROMPT_DIR / "_shared.md").read_text(encoding="utf-8")
    role = (PROMPT_DIR / f"{slug}.md").read_text(encoding="utf-8")
    return f"{shared}\n\n---\n\n{role}"


# =============================================================================
# LLM-backed opinions
# =============================================================================

def ask_agent(
    agent: str,
    context: dict[str, Any],
    *,
    others: list[AgentOpinion] | None = None,
    rnd: int = 1,
) -> AgentOpinion:
    """One specialist's opinion. Falls back to the rule set on any failure."""
    llm = get_llm()
    if not llm.available:
        return rule_opinion(agent, context, others=others, rnd=rnd)

    system = load_prompt(AGENTS[agent])
    if others:
        peer_text = "\n\n".join(
            f"### {o.agent} voted {o.position} (confidence {o.confidence:.2f})\n"
            f"{o.argument}\n"
            + (f"Concerns: {'; '.join(o.concerns)}\n" if o.concerns else "")
            + (f"Conditions: {'; '.join(o.conditions)}" if o.conditions else "")
            for o in others if o.agent != agent
        )
        task = (
            "This is the rebuttal round. You have already given your opening "
            "position. Below are the other specialists' positions.\n\n"
            "Respond to the arguments that actually challenge yours. You may "
            "change your position if they have convinced you - say so in your "
            "argument if you do. Do not simply repeat your opening.\n\n"
            f"{peer_text}\n\n---\n\nCLUSTER PROFILE:\n{_json(context)}"
        )
    else:
        task = (
            "Give your opening position on this cluster.\n\n"
            f"CLUSTER PROFILE:\n{_json(context)}"
        )

    res = llm.generate(task, system=system, input_payload=context, schema=OPINION_SCHEMA)
    if res.data is None:
        log.warning("agent_llm_failed", agent=agent, error=res.error)
        return rule_opinion(agent, context, others=others, rnd=rnd)

    d = res.data or {}
    return AgentOpinion(
        agent=agent,
        position=str(d.get("position") or "Retain"),
        patterns=[str(p) for p in (d.get("patterns") or [])],
        argument=str(d.get("argument") or "").strip(),
        concerns=[str(c) for c in (d.get("concerns") or [])][:6],
        conditions=[str(c) for c in (d.get("conditions") or [])][:6],
        confidence=_clamp01(d.get("confidence"), 0.6),
        evidence_node_ids=[str(e) for e in (d.get("evidence_node_ids") or [])][:12],
        round=rnd,
        generator="gemini",
    )


def ask_moderator(
    context: dict[str, Any],
    opinions: list[AgentOpinion],
    rebuttals: list[AgentOpinion],
    effort_options: dict[str, Any],
) -> tuple[dict[str, Any] | None, Any]:
    """The Moderator's synthesis. Returns (raw decision dict, LLMResult)."""
    llm = get_llm()
    if not llm.available:
        return None, None

    def render(items: list[AgentOpinion], title: str) -> str:
        if not items:
            return ""
        body = "\n\n".join(
            f"### {o.agent}: {o.position} (confidence {o.confidence:.2f})\n{o.argument}\n"
            + (f"Concerns: {'; '.join(o.concerns)}\n" if o.concerns else "")
            + (f"Conditions: {'; '.join(o.conditions)}\n" if o.conditions else "")
            + f"Cites: {', '.join(o.evidence_node_ids[:6])}"
            for o in items
        )
        return f"## {title}\n\n{body}"

    task = "\n\n".join(filter(None, [
        f"CLUSTER PROFILE:\n{_json(context)}",
        render(opinions, "Opening positions"),
        render(rebuttals, "Rebuttal round"),
        f"## Deterministic effort estimates (weeks, PERT)\n{_json(effort_options)}",
        f"Return the decision for cluster_id {context.get('cluster_id')!r}.",
    ]))
    res = llm.generate(task, system=load_prompt("moderator"),
                       input_payload={"context": context,
                                      "opinions": [o.as_dict() for o in opinions],
                                      "rebuttals": [o.as_dict() for o in rebuttals]},
                       schema=RESPONSE_SCHEMA)
    return (res.data if isinstance(res.data, dict) else None), res


# =============================================================================
# Deterministic reasoners — one per brief
# =============================================================================

def _facts(ctx: dict[str, Any]) -> dict[str, Any]:
    """The decision-relevant facts, extracted once so each brief reads the same."""
    classes = ctx.get("classes") or []
    gaps = set(ctx.get("compliance_gaps") or [])
    tags = set(ctx.get("gxp_tags") or [])
    blockers: dict[str, int] = {}
    for c in classes:
        for b in c.get("top_blockers") or []:
            if b:
                blockers[b] = blockers.get(b, 0) + 1
    return {
        "tier": str(ctx.get("gxp_max") or "LOW"),
        "size": int(ctx.get("size") or 0),
        "loc": int(ctx.get("loc") or 0),
        "readiness": float(ctx.get("readiness_avg") or 0),
        "hits": int(ctx.get("runtime_hits") or 0),
        "tags": tags,
        "gaps": gaps,
        "blockers": blockers,
        "regulated_tables": ctx.get("regulated_tables") or [],
        "external_writes": ctx.get("tables_written_from_outside") or [],
        "has_endpoints": bool(ctx.get("has_endpoints")),
        "scheduled": int(ctx.get("scheduled_jobs") or 0),
        "local_file": int(ctx.get("local_file_methods") or 0),
        "session": int(ctx.get("session_methods") or 0),
        "dependents": ctx.get("depended_on_by") or [],
        "depends_on": ctx.get("depends_on") or [],
        "cloud": str(ctx.get("target_cloud") or "AWS"),
        "ids": [c["node_id"] for c in classes][:8],
        "names": {c["node_id"]: c.get("name") for c in classes},
        "biggest": (classes[0] if classes else {}),
        "is_dead": all(int(c.get("runtime_hits") or 0) == 0 and int(c.get("fan_in") or 0) == 0
                       for c in classes) if classes else False,
    }


CLOUD_SERVICES: dict[str, dict[str, str]] = {
    "AWS": {"compute": "ECS Fargate", "k8s": "EKS", "db": "RDS for PostgreSQL",
            "store": "S3", "queue": "SQS", "events": "EventBridge",
            "secrets": "Secrets Manager", "gw": "API Gateway", "sched": "EventBridge Scheduler"},
    "Azure": {"compute": "Container Apps", "k8s": "AKS", "db": "Azure Database for PostgreSQL",
              "store": "Blob Storage", "queue": "Service Bus", "events": "Event Grid",
              "secrets": "Key Vault", "gw": "API Management", "sched": "Logic Apps"},
    "GCP": {"compute": "Cloud Run", "k8s": "GKE", "db": "Cloud SQL for PostgreSQL",
            "store": "Cloud Storage", "queue": "Pub/Sub", "events": "Eventarc",
            "secrets": "Secret Manager", "gw": "API Gateway", "sched": "Cloud Scheduler"},
}


def _svc(cloud: str, key: str) -> str:
    return CLOUD_SERVICES.get(cloud, CLOUD_SERVICES["AWS"]).get(key, key)


def rule_opinion(
    agent: str,
    ctx: dict[str, Any],
    *,
    others: list[AgentOpinion] | None = None,
    rnd: int = 1,
) -> AgentOpinion:
    f = _facts(ctx)
    # Unreachable code is decided before anything else. Every brief agrees that
    # you do not migrate, containerise or re-platform code nothing calls and
    # nothing ran - and checking this first matters: an earlier ordering had the
    # Cloud Architect proposing a replatform of a dead class because the runtime
    # it never runs on was end-of-life.
    if f["is_dead"]:
        op = _dead_code_opinion(agent, f)
    else:
        op = {
            "Cloud Architect": _cloud_architect,
            "Validation & QA Lead": _validation_lead,
            "Security Officer": _security_officer,
            "FinOps Analyst": _finops,
            "Regulatory Affairs": _regulatory,
        }[agent](ctx, f)
    op.agent = agent
    op.round = rnd
    op.generator = "deterministic"
    op.evidence_node_ids = [e for e in op.evidence_node_ids if e][:12]

    if others and rnd > 1:
        op = _rebut(op, others, f)
    return op


def _dead_code_opinion(agent: str, f: dict[str, Any]) -> AgentOpinion:
    """Every brief reaches Retire on unreachable code, for its own reasons.

    The agreement is not a shortcut - it is what each role would actually say.
    The Validation Lead still attaches the one condition that matters, because
    deleting code that turns out to be reachable by reflection would be a far
    worse outcome than carrying it.
    """
    names = ", ".join(n for n in list(f["names"].values())[:3] if n)
    loc = f["loc"]
    texts = {
        "Cloud Architect": (
            f"{names} has no inbound call, no type reference, no instantiation "
            f"and no runtime hit across the traced use cases. There is nothing "
            f"to containerise - it does not run. Retire it and the deployable "
            f"surface shrinks."
        ),
        "Validation & QA Lead": (
            f"{names} is unreachable, so deleting it changes no GxP function and "
            f"needs no functional re-validation - only an impact assessment "
            f"recording that it was unreachable. I want reflection and dynamic "
            f"loading ruled out first; static analysis cannot see those, and "
            f"deleting live code would be the worse error."
        ),
        "Security Officer": (
            f"{names} is unreachable code carrying its own dependencies and "
            f"attack surface for no benefit. Unused code is unpatched code. Retire it."
        ),
        "FinOps Analyst": (
            f"{loc} LOC with zero runtime hits and no inbound calls. Migrating it "
            f"costs twice - once to move, once to validate - and returns nothing. "
            f"This is the cheapest win on the roadmap."
        ),
        "Regulatory Affairs": (
            f"{names} creates and modifies no GxP record, so retiring it raises no "
            f"supplier-oversight or data-integrity obligation. Record the removal "
            f"under change control with the evidence of unreachability."
        ),
    }
    conditions = {
        "Validation & QA Lead": [
            "confirm no reflective or dynamically-loaded reference before deletion",
            "impact assessment recording the evidence of unreachability",
        ],
        "Regulatory Affairs": ["record the removal under change control"],
    }
    return AgentOpinion(
        agent=agent, position="Retire", patterns=[],
        argument=texts.get(agent, f"{names} is unreachable; retire it."),
        concerns=["paying to migrate and validate code that never executes"],
        conditions=conditions.get(agent, []),
        confidence=0.85 if agent in ("FinOps Analyst", "Cloud Architect") else 0.78,
        evidence_node_ids=f["ids"],
    )


def _cloud_architect(ctx: dict[str, Any], f: dict[str, Any]) -> AgentOpinion:
    cloud = f["cloud"]
    blockers: list[str] = []
    if f["session"]:
        blockers.append(f"{f['session']} method(s) hold servlet session state")
    if f["scheduled"]:
        blockers.append(f"{f['scheduled']} @Scheduled job(s) on a singleton with no lock")
    if f["local_file"]:
        blockers.append(f"{f['local_file']} method(s) read the host filesystem")
    if "statelessness" in f["blockers"]:
        blockers.append("static mutable state or an in-process cache")
    eol = f["blockers"].get("framework_eol", 0)

    patterns: list[str] = ["Containerized"]
    services = [_svc(cloud, "compute")]
    if f["regulated_tables"]:
        patterns.append("ManagedDB")
        services.append(_svc(cloud, "db"))
    if f["local_file"]:
        services.append(_svc(cloud, "store"))
    if f["scheduled"]:
        services.append(_svc(cloud, "sched"))
    if f["has_endpoints"]:
        patterns.append("APIGateway")
        services.append(_svc(cloud, "gw"))

    # Replatform removes the blockers without a functional change; Refactor is
    # only justified when the boundary itself is broken.
    if f["external_writes"] and f["size"] >= 4:
        position = "Refactor"
        patterns.append("StranglerFig")
        arg = (
            f"The boundary is not deployable as it stands: "
            f"{', '.join(f['external_writes'][:3])} is written from outside this "
            f"cluster, so extracting it yields a distributed monolith. That needs "
            f"a real re-architecture behind a Strangler Fig facade, with one owner "
            f"per table. "
        )
    elif blockers or eol:
        position = "Replatform"
        arg = (
            f"Containerising onto {_svc(cloud, 'compute')} with "
            f"{_svc(cloud, 'db')} removes the scaling and patching blockers "
            f"without changing behaviour. "
        )
    elif f["is_dead"]:
        position = "Retire"
        arg = "Nothing calls this and nothing ran it in the traces. There is no operational case for moving it. "
    else:
        position = "Rehost"
        arg = ("No scaling blocker in this cluster, so a lift-and-shift exits "
               "the data centre at the lowest cost and risk. ")

    if blockers:
        arg += "Blockers: " + "; ".join(blockers) + ". "
    if eol:
        arg += (f"{eol} class(es) are coupled to an end-of-life framework that "
                f"cannot be patched in place. ")
    if position == "Replatform":
        arg += "I considered a full rewrite and rejected it: the blockers here are runtime, not design."

    return AgentOpinion(
        agent="Cloud Architect", position=position, patterns=sorted(set(patterns)),
        argument=arg.strip(),
        concerns=blockers[:4],
        conditions=([f"one owner per table for {', '.join(f['external_writes'][:2])}"]
                    if f["external_writes"] else []),
        confidence=0.82 if (blockers or eol) else 0.6,
        evidence_node_ids=f["ids"],
    )


def _validation_lead(ctx: dict[str, Any], f: dict[str, Any]) -> AgentOpinion:
    tier = f["tier"]
    critical = f["tags"] & {"PRODUCT_RELEASE", "E_SIGNATURE", "AUDIT_TRAIL"}
    no_tests = f["blockers"].get("test_coverage", 0)
    conditions: list[str] = []
    concerns: list[str] = []

    if no_tests:
        conditions.append(
            f"characterisation tests for {no_tests} untested class(es) before any change"
        )
        concerns.append("no test currently proves the behaviour we must preserve")
    if f["regulated_tables"]:
        conditions.append(
            f"data-migration checks (row counts and checksums) on "
            f"{', '.join(f['regulated_tables'][:3])}"
        )
    if f["dependents"]:
        concerns.append(
            f"{len(f['dependents'])} other cluster(s) call into this one, so a "
            f"cutover re-tests their integrations too"
        )

    if tier == "HIGH" and critical:
        position = "Replatform"
        conditions.insert(0, "scripted testing of the critical functions plus independent review")
        conditions.append("staged Strangler Fig cutover with a tested rollback")
        arg = (
            f"This cluster carries {', '.join(sorted(critical))}. Under CSA that "
            f"means scripted testing of critical functions and independent review "
            f"for any change. A replatform with no functional change is validatable "
            f"as an infrastructure qualification; a rewrite puts the whole Part 11 "
            f"surface back through full validation. I will support the replatform, "
            f"not a refactor. If we do nothing, the unsupported runtime becomes its "
            f"own data-integrity risk within a year, so Retain is not acceptable "
            f"beyond the next annual review."
        )
        confidence = 0.88
        patterns = ["Containerized", "StranglerFig"]
    elif tier == "HIGH":
        position = "Replatform"
        arg = (
            f"HIGH tier via {', '.join(sorted(f['tags'])[:3])}, writing "
            f"{', '.join(f['regulated_tables'][:3]) or 'regulated data'}. Keep the "
            f"functional behaviour identical and the validation stays an "
            f"infrastructure qualification."
        )
        confidence = 0.8
        patterns = ["Containerized", "ManagedDB"]
    elif tier == "MEDIUM":
        position = "Replatform"
        arg = (
            f"MEDIUM tier - reads GxP data without writing it. CSA scales this to "
            f"unscripted testing with recorded results, so the validation cost is "
            f"modest. This is a sensible early move that builds the team's evidence "
            f"pattern before we touch the core."
        )
        confidence = 0.72
        patterns = ["Containerized", "CQRS"] if "REPORTING_ONLY" in f["tags"] else ["Containerized"]
    else:
        position = "Rehost"
        arg = (
            "LOW tier with no GxP data path. Vendor and automated evidence is "
            "sufficient here, so this is exactly where the programme should start "
            "and learn."
        )
        confidence = 0.75
        patterns = ["Containerized"]

    return AgentOpinion(
        agent="Validation & QA Lead", position=position, patterns=patterns,
        argument=arg, concerns=concerns[:4], conditions=conditions[:5],
        confidence=confidence, evidence_node_ids=f["ids"],
    )


def _security_officer(ctx: dict[str, Any], f: dict[str, Any]) -> AgentOpinion:
    cloud = f["cloud"]
    gaps = f["gaps"]
    concerns: list[str] = []
    conditions: list[str] = []
    blocking: str | None = None

    if "H2_CONSOLE_ENABLED" in gaps:
        blocking = ("an interactive database console is exposed - GxP data can be "
                    "edited with no audit row at all")
        conditions.append("disable the database console and prove it in installation qualification")
    if "SHARED_ADMIN_ACCOUNT" in gaps:
        concerns.append("a shared admin credential sits in configuration, destroying attributability")
        conditions.append("replace the shared admin account with named individual accounts")
        blocking = blocking or "a shared administrator credential in configuration"
    if "SECRETS_IN_CONFIG" in gaps:
        concerns.append("credentials are committed in configuration and cannot be rotated")
        conditions.append(f"move every credential to {_svc(cloud, 'secrets')} and rotate it")
    if "STATEFUL_SESSION" in gaps or f["session"]:
        concerns.append("identity is carried in a server-side session, so a failover loses the actor")
        conditions.append("resolve the acting user from a signed token at the point of write")
    if "AUDIT_TRAIL" in f["tags"]:
        conditions.append("append-only or WORM storage for the audit trail, with access logging")
    if "AUTO_SCHEMA_UPDATE" in gaps:
        concerns.append("the schema holding GxP records can change at startup with no change control")

    patterns = ["Containerized"]
    services = [_svc(cloud, "secrets")]
    if f["has_endpoints"]:
        patterns.append("APIGateway")
        services.append(_svc(cloud, "gw"))
    if f["regulated_tables"]:
        patterns.append("ManagedDB")
        services.append(_svc(cloud, "db"))

    arg = (
        (f"Must be fixed before any migration: {blocking}. " if blocking else "")
        + (f"Then, during the wave: {'; '.join(concerns[:2])}. " if concerns else "")
        + (f"Moving to {_svc(cloud, 'db')} gives managed encryption, backup and "
           f"access logging, which is a net control improvement over the current "
           f"file-mode database. " if f["regulated_tables"] else "")
        + ("I am not opposing the strategy - these are the conditions attached to it."
           if concerns or blocking else
           "No blocking security finding in this cluster.")
    )

    return AgentOpinion(
        agent="Security Officer",
        position="Replatform" if (concerns or blocking) else "Rehost",
        patterns=sorted(set(patterns)), argument=arg.strip(),
        concerns=concerns[:4], conditions=conditions[:5],
        confidence=0.85 if blocking else 0.65,
        evidence_node_ids=f["ids"],
    )


def _finops(ctx: dict[str, Any], f: dict[str, Any]) -> AgentOpinion:
    hits, loc, tier = f["hits"], f["loc"], f["tier"]
    kloc = loc / 1000.0
    refactor_weeks = kloc * 4.5
    replatform_weeks = kloc * 2.2

    if f["is_dead"]:
        return AgentOpinion(
            agent="FinOps Analyst", position="Retire", patterns=[],
            argument=(
                f"{loc} LOC with zero runtime hits and no inbound calls. Migrating "
                f"it costs twice - once to move, once to validate - and returns "
                f"nothing. Delete it and the migration and validation scope both shrink."
            ),
            concerns=["paying to migrate code nothing executes"],
            confidence=0.85, evidence_node_ids=f["ids"],
        )

    if hits < 50 and tier != "HIGH":
        return AgentOpinion(
            agent="FinOps Analyst", position="Retain", patterns=[],
            argument=(
                f"Only {hits:,} runtime hits across the traced period. There is no "
                f"cost of delay here. Spend the wave-1 budget on the high-traffic "
                f"paths and revisit this when something forces the issue."
            ),
            concerns=["no measurable cost of delay"],
            conditions=["revisit once the runtime platform reaches end of support"],
            confidence=0.7, evidence_node_ids=f["ids"],
        )

    arg = (
        f"{hits:,} runtime hits over {loc} LOC, so this is carrying real load and "
        f"is worth spending on. At roughly 4.5 weeks per KLOC a rewrite is about "
        f"{refactor_weeks:.1f} weeks against {replatform_weeks:.1f} for a "
        f"replatform - the rewrite has to buy something specific to justify "
        f"{refactor_weeks - replatform_weeks:.1f} extra weeks, and I have not heard what."
    )
    conditions = []
    if tier == "HIGH":
        arg += (" I accept the Validation Lead's conditions and I am pricing them "
                "in rather than arguing them away - a cheap migration that fails "
                "an inspection costs more than every option we rejected.")
        conditions.append("validation effort costed into the wave, not treated as overhead")
    if "licensing_blockers" in f["blockers"]:
        arg += " There is also a proprietary dependency here whose licence may be a large line item."
        conditions.append("confirm licence terms permit running in the target region")

    return AgentOpinion(
        agent="FinOps Analyst", position="Replatform",
        patterns=["Containerized", "ManagedDB"] if f["regulated_tables"] else ["Containerized"],
        argument=arg, concerns=["rewrite cost without a stated return"],
        conditions=conditions, confidence=0.75, evidence_node_ids=f["ids"],
    )


def _regulatory(ctx: dict[str, Any], f: dict[str, Any]) -> AgentOpinion:
    obligations: list[str] = []
    concerns: list[str] = []

    if f["regulated_tables"]:
        obligations.append(
            "supplier assessment and a quality agreement with the cloud provider "
            "before cutover (Annex 11 draft, July 2025)"
        )
        obligations.append(
            f"pin the region and document where {', '.join(f['regulated_tables'][:2])} "
            f"and their backups reside"
        )
        obligations.append("retention and readability strategy for the full record retention period")
    if "AUDIT_NO_REASON" in f["gaps"]:
        concerns.append(
            "the audit trail cannot record a reason for change - a direct "
            "21 CFR 11.10(e) finding and a common inspection observation"
        )
    if "AUTO_SCHEMA_UPDATE" in f["gaps"]:
        concerns.append(
            "the schema holding GxP records updates automatically at startup, so "
            "structural change happens with no change-control record"
        )
    if "LOCAL_TIME_SOURCE" in f["gaps"]:
        concerns.append(
            "GxP timestamps come from the application server clock; across "
            "multiple instances contemporaneousness cannot be demonstrated"
        )
    if "PRODUCT_RELEASE" in f["tags"]:
        concerns.append(
            "this cluster carries the QP release decision, so it is in scope for "
            "Annex 16 certification evidence"
        )

    arg = (
        (f"Prerequisites, not blockers: {obligations[0]}. " if obligations else "")
        + (f"Genuine findings to fix: {concerns[0]}. " if concerns else "")
        + (f"Concurrent activity: {obligations[1]}. " if len(obligations) > 1 else "")
        + ("None of this changes the strategy; it changes what must be in place "
           "before cutover." if obligations or concerns else
           "No GxP records in this cluster, so no supplier-oversight obligation arises.")
    )

    return AgentOpinion(
        agent="Regulatory Affairs",
        position="Replatform" if f["regulated_tables"] else "Rehost",
        patterns=["Containerized"], argument=arg.strip(),
        concerns=concerns[:4], conditions=obligations[:4],
        confidence=0.7 if f["regulated_tables"] else 0.55,
        evidence_node_ids=f["ids"],
    )


def _rebut(op: AgentOpinion, others: list[AgentOpinion], f: dict[str, Any]) -> AgentOpinion:
    """Second round: respond to the specific positions that conflict."""
    peers = [o for o in others if o.agent != op.agent]
    opposed = [o for o in peers if o.position != op.position]
    if not opposed:
        agree = ", ".join(sorted({o.agent for o in peers}))
        op.argument = (
            f"I hold my position. {agree} reached the same conclusion from "
            f"different briefs, which strengthens it. " + op.argument
        )
        op.confidence = min(0.95, op.confidence + 0.08)
        return op

    names = ", ".join(f"{o.agent} ({o.position})" for o in opposed[:3])
    rebuttal = ""

    if op.agent == "Validation & QA Lead" and any(o.position == "Refactor" for o in opposed):
        rebuttal = (
            f"{names} want a rewrite. On a {f['tier']}-tier cluster writing "
            f"{', '.join(f['regulated_tables'][:2]) or 'GxP data'} that means full "
            f"re-validation of every critical function, not an infrastructure "
            f"qualification. I will support it only with characterisation tests and "
            f"differential testing in place first, and I am not willing to call that "
            f"wave 1."
        )
        op.confidence = min(0.95, op.confidence + 0.05)
    elif op.agent == "Cloud Architect" and any(o.position in ("Retain", "Rehost") for o in opposed):
        rebuttal = (
            f"{names} would leave this where it is. That keeps an unpatchable "
            f"runtime in production and keeps the scaling blockers, so the problem "
            f"is still here next year and larger. I have moved to the smallest "
            f"change that fixes it rather than the one I would prefer."
        )
    elif op.agent == "FinOps Analyst" and any(o.position == "Refactor" for o in opposed):
        rebuttal = (
            f"{names} propose a rewrite at roughly twice the weeks per KLOC. I will "
            f"fund it if someone states the return in numbers. Otherwise the "
            f"replatform captures the operational benefit at a fraction of the cost."
        )
    elif op.agent == "Security Officer":
        rebuttal = (
            f"{names} differ on strategy, which does not affect my position: my "
            f"conditions attach to whichever option is chosen. I will rank them - "
            f"{(op.conditions or ['no blocking finding'])[0]} is the one that must "
            f"precede any migration."
        )
    elif op.agent == "Regulatory Affairs":
        rebuttal = (
            f"{names} differ on strategy. My obligations are sequenced, not "
            f"blocking: the supplier assessment must exist before cutover, the "
            f"residency documentation can run concurrently."
        )
    else:
        rebuttal = f"{names} disagree. I have weighed their arguments and hold my position."

    op.argument = rebuttal + " " + op.argument
    op.argument = op.argument[:1200]
    return op


# =============================================================================
# Deterministic moderator
# =============================================================================

STRATEGY_WEIGHT_BY_AGENT: dict[str, float] = {
    # The Validation Lead and Regulatory Affairs carry more weight on HIGH-tier
    # clusters; the Cloud Architect and FinOps carry more on LOW-tier ones. This
    # encodes PRD 12.2's "weight by criticality, not by volume".
    "Validation & QA Lead": 1.0,
    "Regulatory Affairs": 0.8,
    "Security Officer": 0.8,
    "Cloud Architect": 1.0,
    "FinOps Analyst": 0.9,
}


def rule_decision(
    kg: KnowledgeGraph,
    ctx: dict[str, Any],
    opinions: list[AgentOpinion],
    rebuttals: list[AgentOpinion],
) -> dict[str, Any]:
    """Synthesise a decision from the agents' positions, without an LLM."""
    f = _facts(ctx)
    tier = f["tier"]
    final = {o.agent: o for o in opinions}
    for o in rebuttals:
        final[o.agent] = o
    votes = list(final.values())

    # Weight each vote by role relevance to this cluster's criticality.
    scores: dict[str, float] = {}
    for o in votes:
        w = STRATEGY_WEIGHT_BY_AGENT.get(o.agent, 0.8)
        if tier == "HIGH" and o.agent in ("Validation & QA Lead", "Regulatory Affairs"):
            w *= 1.6
        if tier == "LOW" and o.agent in ("Cloud Architect", "FinOps Analyst"):
            w *= 1.4
        scores[o.position] = scores.get(o.position, 0.0) + w * max(0.1, o.confidence)

    # A unanimous Retire is the one case that overrides weighting: if every
    # brief says the code is dead, it is dead.
    if all(o.position == "Retire" for o in votes):
        strategy = "Retire"
    else:
        strategy = max(scores.items(), key=lambda kv: (kv[1], kv[0]))[0]

    # Never let the deterministic path recommend a rewrite of the validated core
    # when the Validation Lead opposed it - that is the exact failure mode the
    # tool exists to prevent.
    val = final.get("Validation & QA Lead")
    if strategy == "Refactor" and tier == "HIGH" and val and val.position != "Refactor":
        strategy = "Replatform"

    patterns: list[str] = []
    for o in votes:
        for p in o.patterns:
            if p not in patterns:
                patterns.append(p)
    if strategy == "Retire":
        patterns = []
    if tier == "HIGH" and "StranglerFig" not in patterns and strategy in ("Refactor", "Replatform"):
        patterns.append("StranglerFig")

    cloud = f["cloud"]
    services: list[str] = []
    if strategy != "Retire" and strategy != "Retain":
        services.append(_svc(cloud, "compute"))
        if f["regulated_tables"]:
            services.append(_svc(cloud, "db"))
        if f["local_file"]:
            services.append(_svc(cloud, "store"))
        if f["has_endpoints"]:
            services.append(_svc(cloud, "gw"))
        if any("SECRETS_IN_CONFIG" in f["gaps"] or "SHARED_ADMIN_ACCOUNT" in f["gaps"]
               for _ in [0]):
            services.append(_svc(cloud, "secrets"))

    risks: list[str] = []
    for o in votes:
        for c in o.conditions:
            if c not in risks:
                risks.append(c)
    for o in votes:
        for c in o.concerns:
            if c not in risks:
                risks.append(c)

    dissent = [
        {"agent": o.agent, "position": o.position,
         "reason": (o.argument or "")[:300]}
        for o in votes if o.position != strategy
    ]

    effort = T.estimate_effort(kg, ctx["cluster_id"], strategy)

    decisive = _decisive_sentence(f, strategy, final)
    rationale = decisive
    if dissent:
        d = dissent[0]
        rationale += f" {d['agent']} argued for {d['position']}; that position is recorded as dissent."
    if tier == "HIGH":
        rationale += (" Because this cluster is HIGH GxP tier, the cutover requires "
                      "scripted testing of its critical functions and QA approval.")

    agreement = sum(1 for o in votes if o.position == strategy) / max(1, len(votes))
    confidence = round(min(0.9, 0.35 + 0.45 * agreement
                           + (0.1 if tier != "HIGH" else 0.0)), 2)
    if tier == "HIGH" and agreement < 0.5:
        confidence = min(confidence, 0.45)   # force the human-review flag

    evidence = []
    for o in votes:
        for e in o.evidence_node_ids:
            if e not in evidence and kg.has(e):
                evidence.append(e)
    if ctx["cluster_id"] not in evidence:
        evidence.insert(0, ctx["cluster_id"])

    o_, l_, p_ = effort["effort_weeks"]
    return {
        "cluster_id": ctx["cluster_id"],
        "strategy": strategy,
        "target_pattern": patterns[:5],
        "target_services": sorted(set(services)),
        "confidence": confidence,
        "rationale": rationale,
        "risks": risks[:8],
        "dissent": dissent,
        "evidence_node_ids": evidence[:14],
        "effort_weeks_optimistic": o_,
        "effort_weeks_likely": l_,
        "effort_weeks_pessimistic": p_,
        "_effort_basis": effort,
    }


def _decisive_sentence(f: dict[str, Any], strategy: str, final: dict[str, AgentOpinion]) -> str:
    names = list(f["names"].values())[:3]
    members = ", ".join(n for n in names if n)
    tables = ", ".join(f["regulated_tables"][:3])

    if strategy == "Retire":
        return (f"{members} has no inbound calls and no runtime hits across the "
                f"traced use cases, so it is retired rather than migrated.")
    if strategy == "Retain":
        return (f"{members} carries only {f['hits']:,} runtime hits and no scaling "
                f"blocker, so there is no cost of delay that justifies spending a "
                f"wave on it now.")
    if strategy == "Refactor":
        return (f"{members} cannot be deployed independently as it stands - "
                f"{', '.join(f['external_writes'][:2])} is written from outside the "
                f"cluster - so the boundary itself has to be rebuilt behind a facade.")
    if strategy == "Replatform":
        if tables:
            lead = (f"{members} holds the write path to {tables} and is coupled to "
                    f"an end-of-life runtime.")
        else:
            lead = f"{members} is coupled to an end-of-life runtime."
        return (
            f"{lead} Replatforming onto containers with a managed database removes "
            f"the operational risk with no functional change, which is validatable "
            f"as an infrastructure qualification rather than a full re-validation."
        )
    if strategy == "Rehost":
        return (f"{members} is {f['tier']} tier with readiness "
                f"{f['readiness']:.0f}/100 and no scaling blocker, so a lift and "
                f"shift exits the data centre at the lowest cost and risk and proves "
                f"the migration pattern early.")
    return f"{members} is assigned {strategy}."


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=1, default=str)


def _clamp01(v: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default
