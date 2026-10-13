"""The seven-engine pipeline (PRD §3), wired as job bodies.

    analyze   -> Engine 1 (twin) + 2 (GxP) + 3 (readiness) + 4 (decomposition)
    council   -> Engine 5
    roadmap   -> Engine 6
    evidence  -> Engine 7

Analysis is one job because the four stages share one in-memory graph and the
demo is timed end to end (PRD §23 "assessment time"); the later engines are
separate jobs because each has a human gate in front of it.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .config import settings
from .core.audit import record
from .core.logging import get_logger
from .db.graph import KnowledgeGraph
from .db.models import Decision, EvidencePack, Job, Project, Roadmap
from .db.session import session_scope
from .engines.council.graph import deliberate_many
from .engines.decompose import runner as decompose_runner
from .engines.evidence import report as evidence_report
from .engines.gxp.scanner import scan as gxp_scan
from .engines.readiness.scorer import score as readiness_score
from .engines.roadmap import montecarlo as mc
from .engines.roadmap import scheduler as sched
from .engines.twin import c4
from .engines.twin.embeddings import build_embeddings
from .engines.twin.gitmining import apply_cochange, mine_cochange
from .engines.twin.graph_builder import build_graph
from .engines.twin.ingest import enrich_with_lizard, ingest, prepare_source
from .engines.twin.runtime import ingest_traces
from .jobs import JobContext

log = get_logger("pipeline")


def _project(project_id: str) -> dict[str, Any]:
    with session_scope() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise KeyError(f"unknown project {project_id}")
        return {
            "id": p.id, "name": p.name, "repo_url": p.repo_url,
            "source_path": p.source_path, "target_cloud": p.target_cloud,
            "use_runtime_traces": p.use_runtime_traces,
            "summary": p.summary_json or {},
        }


def _save_summary(project_id: str, patch: dict[str, Any], *, status: str | None = None) -> None:
    with session_scope() as s:
        p = s.get(Project, project_id)
        if p is None:
            return
        merged = dict(p.summary_json or {})
        merged.update(patch)
        p.summary_json = merged
        if status:
            p.status = status


# =============================================================================
# Engines 1-4: analysis
# =============================================================================

def analyze(
    ctx: JobContext,
    *,
    use_runtime_traces: bool = True,
    use_llm: bool = True,
    use_git_mining: bool = True,
    weights: list[float] | None = None,
    gamma: float | None = None,
    min_cluster_size: int | None = None,
) -> dict[str, Any]:
    project = _project(ctx.project_id)
    started = dt.datetime.now(dt.timezone.utc)
    with session_scope() as s:
        p = s.get(Project, ctx.project_id)
        if p is not None:
            p.analysis_started_at = started
            p.analysis_finished_at = None
            p.status = "analyzing"

    # ---------------------------------------------------------- Engine 1
    ctx.engine(1, "Living Architecture Twin", "parsing source, data and config")
    ctx.progress(0.01, "preparing source")
    root, notes = prepare_source(
        dest=settings.uploads_dir / ctx.project_id,
        repo_url=project["repo_url"],
        local_path=Path(project["source_path"]) if project["source_path"] else None,
    )
    for n in notes:
        ctx.note(n)

    res = ingest(root, name=project["name"], progress=ctx.stage("Parsing", 0.02, 0.18))
    ctx.note(
        f"Parsed {res.total_files} files, {res.total_loc:,} lines across "
        f"{len(res.loc_by_language)} language(s). "
        f"{sum(len(f.types) for f in res.code_files)} types, "
        f"{len(res.libraries)} dependencies, {len(res.sql_schema.tables())} tables from DDL.",
        languages=res.loc_by_language,
    )
    if not res.code_files and not res.sql_files:
        raise RuntimeError(
            f"no analysable source found under {root}. Supported: Java, C#, Kotlin, "
            f"Scala, SQL, plus build and configuration files."
        )

    ctx.progress(0.19, "measuring complexity")
    lz = enrich_with_lizard(res, root)
    if lz.get("replaced"):
        ctx.note(f"Cyclomatic complexity measured by lizard for {lz['replaced']} functions.")

    kg, graph_info = build_graph(
        res, project_id=ctx.project_id, project_name=project["name"],
        target_cloud=project["target_cloud"],
        progress=ctx.stage("Graph", 0.20, 0.34),
    )
    ctx.note(
        f"Knowledge graph: {graph_info['graph']['nodes']} nodes, "
        f"{graph_info['graph']['edges']} relationships. "
        f"{graph_info['links']['resolved']} internal calls resolved, "
        f"{graph_info['links']['instantiations']} instantiations, "
        f"{graph_info['links']['type_refs']} type references.",
        by_label=graph_info["graph"]["by_label"],
    )

    trace_summary = None
    if use_runtime_traces:
        ctx.progress(0.35, "ingesting runtime traces")
        trace_summary = ingest_traces(kg, root, progress=ctx.stage("Traces", 0.35, 0.44))
        if trace_summary:
            ctx.note(
                f"Runtime traces: {trace_summary.total_hits:,} method calls across "
                f"{trace_summary.traces:,} traces and {len(trace_summary.use_cases)} "
                f"use cases. {trace_summary.observed_edges} call edge(s) found that "
                f"static analysis had missed.",
                use_cases=trace_summary.use_cases,
            )
        else:
            ctx.note("No runtime trace export found; the runtime similarity signal "
                     "will be redistributed over the other signals.")

    cochange = None
    if use_git_mining:
        ctx.progress(0.45, "mining git history for co-change coupling")
        cochange = mine_cochange(root)
        if cochange.available and cochange.pairs:
            written = apply_cochange(kg, cochange)
            ctx.note(
                f"Co-change mining: {cochange.commits_used} of "
                f"{cochange.commits_scanned} commits usable, "
                f"{len(cochange.pairs)} coupled file pairs, {written} graph edges."
            )
        else:
            ctx.note(f"Co-change mining unavailable ({cochange.reason or 'no usable history'}); "
                     "its weight is redistributed over the other signals.")

    ctx.progress(0.48, "embedding identifiers")
    emb = build_embeddings(kg, progress=ctx.stage("Embeddings", 0.48, 0.53))

    # ---------------------------------------------------------- Engine 2
    ctx.engine(2, "GxP Criticality Scanner", "tagging regulatory criticality")
    gxp = gxp_scan(kg, use_llm=use_llm, progress=ctx.stage("GxP", 0.54, 0.68))
    gxp_sum = gxp.summary()
    ctx.note(
        f"GxP scan: {gxp_sum['class_tier_counts']['HIGH']} HIGH, "
        f"{gxp_sum['class_tier_counts']['MEDIUM']} MEDIUM, "
        f"{gxp_sum['class_tier_counts']['LOW']} LOW "
        f"({gxp_sum['pct_high_classes']}% of components are HIGH tier). "
        f"{len(gxp.gaps)} compliance gap(s) found.",
        tier_counts=gxp_sum["class_tier_counts"],
        gaps=[{"id": g.id, "severity": g.severity, "title": g.title} for g in gxp.gaps],
    )

    # ---------------------------------------------------------- Engine 3
    ctx.engine(3, "Cloud Readiness Scorer", "scoring components 0-100")
    readiness = readiness_score(kg, emb=emb, progress=ctx.stage("Readiness", 0.69, 0.78))
    r_sum = readiness.summary()
    ctx.note(
        f"Readiness: average {r_sum['average']}/100 "
        f"({r_sum['loc_weighted_average']}/100 weighted by size). "
        f"Top blocker: {r_sum['top_blockers'][0]['title'] if r_sum['top_blockers'] else 'none'}. "
        f"{r_sum['quick_wins']} quick win(s) identified.",
        distribution=r_sum["distribution"],
    )

    # ---------------------------------------------------------- Engine 4
    ctx.engine(4, "Blast-Radius-Aware Decomposition", "clustering with the GxP constraint")
    decomp = decompose_runner.run(
        kg,
        weights=weights or settings.weights,
        gamma=settings.decomp_gamma if gamma is None else gamma,
        alpha=settings.decomp_alpha, beta=settings.decomp_beta,
        min_cluster_size=(settings.hdbscan_min_cluster_size
                          if min_cluster_size is None else min_cluster_size),
        emb=emb,
        readiness={s.node_id: s.readiness for s in readiness.scores},
        progress=ctx.stage("Decomposition", 0.79, 0.93),
    )
    head = decomp.comparison.get("headline", {})
    if head.get("reval_scope_reduction_pp") is not None:
        ctx.note(
            f"Decomposition: {decomp.partitions['modernrx'].cluster_count()} services "
            f"proposed. Re-validation scope {head['reval_scope_before']:.1f}% "
            f"(GxP-blind HDBSCAN) -> {head['reval_scope_after']:.1f}% (ModernRx), "
            f"a reduction of {head['reval_scope_reduction_pp']} percentage points "
            f"({head['reval_scope_reduction_pct']}%).",
            headline=head,
        )

    ctx.progress(0.94, "generating C4 diagrams")
    diagrams = c4.generate_all(kg)

    ctx.progress(0.96, "persisting the twin")
    with session_scope() as s:
        kg.save(s)
        _persist_embeddings(s, ctx.project_id, emb)

    finished = dt.datetime.now(dt.timezone.utc)
    elapsed = (finished - started).total_seconds()
    summary = {
        "graph": kg.stats(),
        "loc": res.total_loc,
        "files": res.total_files,
        "languages": res.loc_by_language,
        "primary_language": res.primary_language(),
        "components": len(kg.classes()),
        "tables": len(kg.nodes("Table")),
        "regulated_tables": sum(1 for t in kg.nodes("Table") if t.get("regulated")),
        "endpoints": len(kg.nodes("Endpoint")),
        "use_cases": len(kg.nodes("UseCase")),
        "test_files": res.test_files,
        "gxp": gxp_sum,
        "gxp_gaps": [g.as_dict() for g in gxp.gaps],
        "readiness": r_sum,
        "decomposition": {
            "chosen": decomp.chosen,
            "clusters": decomp.partitions["modernrx"].cluster_count()
            if "modernrx" in decomp.partitions else 0,
            "comparison": decomp.comparison,
            "table": decomp.table(),
            "signals": {"available": decomp.features.available if decomp.features else {},
                        "weights": {k: round(v, 4) for k, v in decomp.features.weights.items()}
                        if decomp.features else {}},
        },
        "diagrams": diagrams,
        "trace_summary": {
            "spans": trace_summary.spans, "traces": trace_summary.traces,
            "total_hits": trace_summary.total_hits,
            "use_cases": trace_summary.use_cases,
            "observed_edges": trace_summary.observed_edges,
            "unmapped_spans": trace_summary.unmapped_spans,
        } if trace_summary else None,
        "cochange": {
            "available": cochange.available, "reason": cochange.reason,
            "commits_scanned": cochange.commits_scanned,
            "commits_used": cochange.commits_used,
            "pairs": len(cochange.pairs), "authors": cochange.authors,
        } if cochange else None,
        "embeddings": {"model": emb.model, "dim": emb.dim, "count": len(emb.node_ids)},
        "assessment_seconds": round(elapsed, 2),
        "analysed_at": finished.isoformat(),
    }

    with session_scope() as s:
        p = s.get(Project, ctx.project_id)
        if p is not None:
            p.analysis_finished_at = finished
            p.status = "analyzed"
            merged = dict(p.summary_json or {})
            merged.update(summary)
            p.summary_json = merged

    record("project.analyzed", actor="system", entity="project", entity_id=ctx.project_id,
           payload={"assessment_seconds": round(elapsed, 2),
                    "components": summary["components"],
                    "gxp_high": gxp_sum["class_tier_counts"]["HIGH"],
                    "reval_scope": head.get("reval_scope_after")})

    ctx.progress(1.0, f"assessment complete in {elapsed:.1f}s")
    ctx.note(f"Full assessment completed in {elapsed:.1f} seconds.")
    return {
        "assessment_seconds": round(elapsed, 2),
        "components": summary["components"],
        "clusters": summary["decomposition"]["clusters"],
        "gxp_high": gxp_sum["class_tier_counts"]["HIGH"],
        "gaps": len(gxp.gaps),
        "readiness_average": r_sum["average"],
        "reval_scope_reduction_pp": head.get("reval_scope_reduction_pp"),
    }


def _persist_embeddings(s: Any, project_id: str, emb: Any) -> None:
    """Store embeddings in SQLite (PRD §16.3 embeddings table)."""
    from .db.models import Embedding

    s.query(Embedding).filter(Embedding.project_id == project_id).delete()
    for node_id, blob in emb.to_blobs().items():
        s.add(Embedding(project_id=project_id, node_id=node_id, dim=emb.dim, vector=blob))


# =============================================================================
# Engine 5: Council
# =============================================================================

def run_council(ctx: JobContext, cluster_ids: list[str] | None = None) -> dict[str, Any]:
    with session_scope() as s:
        kg = KnowledgeGraph.load(s, ctx.project_id)
    if not kg.node_ids("Cluster"):
        raise RuntimeError("no decomposition found - run the analysis first")

    targets = cluster_ids or [c["id"] for c in sorted(
        kg.nodes("Cluster"), key=lambda c: -(c.get("size") or 0)
    )]
    targets = [t for t in targets if kg.has(t)]
    if not targets:
        raise RuntimeError("none of the requested cluster ids exist in this project")

    ctx.engine(5, "AI Architecture Council", f"{len(targets)} cluster(s) under review")

    states = deliberate_many(
        kg, ctx.project_id, targets,
        on_event=ctx.event,
        progress=ctx.stage("Council", 0.02, 0.95),
    )

    stored = 0
    needs_review = 0
    with session_scope() as s:
        for st in states:
            if st.decision is None:
                needs_review += 1
                continue
            payload = st.decision.model_dump()
            prov = st.provenance or {}
            existing = s.execute(
                select(Decision).where(
                    Decision.project_id == ctx.project_id,
                    Decision.cluster_id == st.cluster_id,
                )
            ).scalar_one_or_none()
            transcript = [e.model_dump() for e in st.transcript]
            if existing is None:
                s.add(Decision(
                    project_id=ctx.project_id, cluster_id=st.cluster_id,
                    payload_json=payload, transcript_json=transcript,
                    status="Proposed",
                    model_id=str(prov.get("model_id") or ""),
                    prompt_hash=str(prov.get("prompt_hash") or ""),
                    input_hash=str(prov.get("input_hash") or ""),
                    temperature=float(prov.get("temperature") or 0.0),
                    prompt_version=str(prov.get("prompt_version") or ""),
                    generator=str(prov.get("generator") or ""),
                ))
            else:
                # Re-running the Council supersedes the proposal but never an
                # approval: an approved decision is a human record.
                if existing.status == "Approved":
                    continue
                existing.payload_json = payload
                existing.transcript_json = transcript
                existing.status = "Proposed"
                existing.model_id = str(prov.get("model_id") or "")
                existing.prompt_hash = str(prov.get("prompt_hash") or "")
                existing.input_hash = str(prov.get("input_hash") or "")
                existing.temperature = float(prov.get("temperature") or 0.0)
                existing.prompt_version = str(prov.get("prompt_version") or "")
                existing.generator = str(prov.get("generator") or "")
            stored += 1
            if st.needs_human_review:
                needs_review += 1

            record("council.decision_proposed", actor="system", entity="decision",
                   entity_id=st.cluster_id,
                   payload={"project_id": ctx.project_id,
                            "strategy": payload["strategy"],
                            "confidence": payload["confidence"],
                            "model_id": prov.get("model_id"),
                            "generator": prov.get("generator"),
                            "prompt_hash": prov.get("prompt_hash"),
                            "input_hash": prov.get("input_hash"),
                            "evidence_count": len(payload.get("evidence_node_ids") or [])})

    strategies: dict[str, int] = {}
    for st in states:
        if st.decision:
            strategies[st.decision.strategy] = strategies.get(st.decision.strategy, 0) + 1

    _save_summary(ctx.project_id, {"council": {
        "decisions": stored, "needs_review": needs_review, "strategies": strategies,
        "generator": states[0].provenance.get("generator") if states else None,
        "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }})
    ctx.progress(1.0, f"{stored} decision(s) proposed")
    return {"decisions": stored, "needs_human_review": needs_review,
            "strategies": strategies}


# =============================================================================
# Engine 6: Roadmap
# =============================================================================

def run_roadmap(
    ctx: JobContext,
    *,
    squads: int | None = None,
    freeze_windows: list[dict[str, Any]] | None = None,
    target_date: str | None = None,
    start_date: str | None = None,
    runs: int | None = None,
    approved_only: bool = False,
    wave_weeks: int = 8,
    max_high_cutovers_per_wave: int = 1,
) -> dict[str, Any]:
    with session_scope() as s:
        kg = KnowledgeGraph.load(s, ctx.project_id)
        rows = s.execute(
            select(Decision).where(Decision.project_id == ctx.project_id)
        ).scalars().all()
        decisions = [
            {**(d.payload_json or {}), "status": d.status}
            for d in rows
            if not approved_only or d.status == "Approved"
        ]

    if not decisions:
        raise RuntimeError(
            "no Council decisions found"
            + (" with status Approved" if approved_only else "")
            + " - run the Council first"
        )

    ctx.engine(6, "Roadmap Optimizer & Monte Carlo", f"{len(decisions)} decision(s)")

    from .engines.decompose.metrics import cluster_profiles
    from .engines.decompose.cluster import Partition

    labels: dict[str, int] = {}
    for cl in kg.nodes("Cluster"):
        label = int(str(cl["id"]).split(":")[-1]) if str(cl["id"]).split(":")[-1].isdigit() else 0
        for m in kg.in_neighbors(cl["id"], "IN_CLUSTER"):
            labels[m] = label
    part = Partition(variant="modernrx", labels=labels,
                     names={int(str(c["id"]).split(":")[-1]): str(c.get("name"))
                            for c in kg.nodes("Cluster")
                            if str(c["id"]).split(":")[-1].isdigit()})
    index = {c["cluster_id"]: c for c in cluster_profiles(kg, part)}
    # Fall back to the Cluster nodes themselves for anything cluster_profiles missed.
    for cl in kg.nodes("Cluster"):
        index.setdefault(cl["id"], {
            "cluster_id": cl["id"], "name": cl.get("name"),
            "gxp_max": cl.get("gxpMax"), "depends_on": [],
        })

    sd = dt.date.fromisoformat(start_date) if start_date else dt.date.today()
    fw = (sched.parse_freeze_windows(freeze_windows, sd)
          if freeze_windows is not None else sched.default_freeze_windows(sd))

    ctx.progress(0.1, "building tasks")
    tasks = sched.build_tasks(decisions, index)
    ctx.note(f"{len(tasks)} task(s): {sum(1 for t in tasks if t.is_foundation)} foundation, "
             f"{sum(1 for t in tasks if t.is_cutover)} HIGH-tier cutover(s).")

    ctx.progress(0.2, "solving the schedule with CP-SAT")
    schedule = sched.solve(
        tasks,
        squads=squads or settings.squad_count,
        freeze_windows=fw,
        wave_weeks=wave_weeks,
        max_high_cutovers_per_wave=max_high_cutovers_per_wave,
        time_limit=settings.roadmap_solver_seconds,
        start_date=sd,
    )
    ctx.note(
        f"{schedule.solver}: {schedule.status}, makespan {schedule.makespan_weeks} weeks "
        f"({schedule.makespan_weeks / 4.345:.1f} months) across {len(schedule.waves)} wave(s). "
        + (f"Constraint check found {len(schedule.violations)} violation(s)."
           if schedule.violations else "All constraints verified on the produced schedule."),
        waves=[{k: w[k] for k in ("wave", "title", "task_count", "high_cutovers")}
               for w in schedule.waves],
    )

    ctx.progress(0.6, "running the Monte Carlo simulation")
    td = dt.date.fromisoformat(target_date) if target_date else None
    sim = mc.simulate(
        schedule, runs=runs or settings.montecarlo_runs,
        seed=settings.montecarlo_seed, target_date=td,
        progress=ctx.stage("Monte Carlo", 0.6, 0.95),
    )
    ctx.note(
        f"{sim.runs:,} simulations: P50 {sim.percentiles['p50']:.0f} weeks "
        f"({sim.dates['p50']}), P80 {sim.percentiles['p80']:.0f} weeks "
        f"({sim.dates['p80']}), P95 {sim.percentiles['p95']:.0f} weeks "
        f"({sim.dates['p95']})."
        + (f" Probability of finishing by {sim.target_date}: "
           f"{sim.probability_by_target:.0%}." if sim.probability_by_target is not None else ""),
        percentiles=sim.percentiles,
    )

    schedule_json = schedule.as_dict()
    sim_json = sim.as_dict()
    inputs = {
        "squads": squads or settings.squad_count,
        "freeze_windows": [f.as_dict() for f in fw],
        "target_date": target_date, "start_date": sd.isoformat(),
        "runs": runs or settings.montecarlo_runs,
        "approved_only": approved_only,
        "wave_weeks": wave_weeks,
        "max_high_cutovers_per_wave": max_high_cutovers_per_wave,
    }

    with session_scope() as s:
        s.add(Roadmap(project_id=ctx.project_id, schedule_json=schedule_json,
                      montecarlo_json=sim_json, inputs_json=inputs))

    _save_summary(ctx.project_id, {"roadmap": {
        "makespan_weeks": schedule.makespan_weeks,
        "solver": schedule.solver, "status": schedule.status,
        "waves": len(schedule.waves),
        "p50": sim.percentiles.get("p50"), "p80": sim.percentiles.get("p80"),
        "p95": sim.percentiles.get("p95"),
        "p80_date": sim.dates.get("p80"),
        "violations": len(schedule.violations),
        "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }})
    ctx.progress(1.0, f"P80 {sim.percentiles['p80']:.0f} weeks ({sim.dates['p80']})")
    return {
        "makespan_weeks": schedule.makespan_weeks,
        "waves": len(schedule.waves),
        "p50_weeks": round(sim.percentiles["p50"], 1),
        "p80_weeks": round(sim.percentiles["p80"], 1),
        "p95_weeks": round(sim.percentiles["p95"], 1),
        "p80_date": sim.dates["p80"],
        "solver": schedule.solver,
        "violations": len(schedule.violations),
    }


def whatif(
    project_id: str,
    *,
    squads: int | None = None,
    freeze_windows: list[dict[str, Any]] | None = None,
    target_date: str | None = None,
    strategy_overrides: dict[str, str] | None = None,
    runs: int = 2000,
    wave_weeks: int = 8,
    max_high_cutovers_per_wave: int = 1,
) -> dict[str, Any]:
    """Re-solve and re-simulate synchronously for the what-if sliders (PRD §13.2).

    Fewer runs than the stored simulation (2,000 rather than 10,000) so the UI
    answers in well under a second; the percentile error at 2,000 runs is a
    fraction of a week, which is far below the resolution anyone plans at.
    """
    with session_scope() as s:
        kg = KnowledgeGraph.load(s, project_id)
        rows = s.execute(
            select(Decision).where(Decision.project_id == project_id)
        ).scalars().all()
        decisions = [dict(d.payload_json or {}) for d in rows]
        latest = s.execute(
            select(Roadmap).where(Roadmap.project_id == project_id)
            .order_by(Roadmap.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        baseline = dict(latest.inputs_json or {}) if latest else {}
        baseline_sched = dict(latest.schedule_json or {}) if latest else {}
        baseline_sim = dict(latest.montecarlo_json or {}) if latest else {}

    if not decisions:
        raise RuntimeError("no Council decisions found - run the Council first")

    if strategy_overrides:
        from .engines.council.tools import estimate_effort

        for d in decisions:
            cid = str(d.get("cluster_id"))
            if cid in strategy_overrides:
                new_strategy = strategy_overrides[cid]
                d["strategy"] = new_strategy
                # Re-price from the deterministic model: keeping the old effort
                # with a new strategy would make the slider lie.
                d["effort_weeks"] = estimate_effort(kg, cid, new_strategy)["effort_weeks"]

    from .engines.decompose.cluster import Partition
    from .engines.decompose.metrics import cluster_profiles

    labels: dict[str, int] = {}
    for cl in kg.nodes("Cluster"):
        tail = str(cl["id"]).split(":")[-1]
        label = int(tail) if tail.isdigit() else 0
        for m in kg.in_neighbors(cl["id"], "IN_CLUSTER"):
            labels[m] = label
    part = Partition(variant="modernrx", labels=labels)
    index = {c["cluster_id"]: c for c in cluster_profiles(kg, part)}
    for cl in kg.nodes("Cluster"):
        index.setdefault(cl["id"], {"cluster_id": cl["id"], "name": cl.get("name"),
                                    "gxp_max": cl.get("gxpMax"), "depends_on": []})

    sd = dt.date.fromisoformat(baseline.get("start_date") or dt.date.today().isoformat())
    fw = (sched.parse_freeze_windows(freeze_windows, sd) if freeze_windows is not None
          else sched.parse_freeze_windows(baseline.get("freeze_windows"), sd))
    tasks = sched.build_tasks(decisions, index)
    schedule = sched.solve(
        tasks,
        squads=squads or baseline.get("squads") or settings.squad_count,
        freeze_windows=fw, wave_weeks=wave_weeks,
        max_high_cutovers_per_wave=max_high_cutovers_per_wave,
        time_limit=min(5.0, settings.roadmap_solver_seconds), start_date=sd,
    )
    td = dt.date.fromisoformat(target_date) if target_date else None
    sim = mc.simulate(schedule, runs=runs, seed=settings.montecarlo_seed, target_date=td)

    return {
        "schedule": schedule.as_dict(),
        "montecarlo": sim.as_dict(),
        "baseline": {
            "makespan_weeks": baseline_sched.get("makespan_weeks"),
            "p50": (baseline_sim.get("percentiles") or {}).get("p50"),
            "p80": (baseline_sim.get("percentiles") or {}).get("p80"),
            "p95": (baseline_sim.get("percentiles") or {}).get("p95"),
            "p80_date": (baseline_sim.get("dates") or {}).get("p80"),
            "squads": baseline.get("squads"),
        },
        "delta": {
            "makespan_weeks": (schedule.makespan_weeks
                               - (baseline_sched.get("makespan_weeks") or 0)),
            "p80_weeks": round(
                sim.percentiles["p80"] - ((baseline_sim.get("percentiles") or {}).get("p80") or 0), 2
            ),
        },
        "inputs": {
            "squads": squads or baseline.get("squads") or settings.squad_count,
            "freeze_windows": [f.as_dict() for f in fw],
            "target_date": target_date,
            "strategy_overrides": strategy_overrides or {},
            "runs": runs,
        },
    }


# =============================================================================
# Engine 7: Evidence
# =============================================================================

def run_evidence(ctx: JobContext, wave: int) -> dict[str, Any]:
    project = _project(ctx.project_id)
    with session_scope() as s:
        kg = KnowledgeGraph.load(s, ctx.project_id)
        rows = s.execute(
            select(Decision).where(Decision.project_id == ctx.project_id)
        ).scalars().all()
        decisions = [dict(d.payload_json or {}) for d in rows]
        latest = s.execute(
            select(Roadmap).where(Roadmap.project_id == ctx.project_id)
            .order_by(Roadmap.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if latest is None:
            raise RuntimeError("no roadmap found - run the roadmap optimizer first")
        schedule = dict(latest.schedule_json or {})
        montecarlo = dict(latest.montecarlo_json or {})

        from .db.models import Approval, User

        approvals = []
        for a, u in s.execute(
            select(Approval, User).join(User, User.id == Approval.user_id, isouter=True)
        ).all():
            approvals.append({"decision_id": a.decision_id, "action": a.action,
                              "comment": a.comment, "ts": a.ts.isoformat(),
                              "user": (u.name if u else a.user_id)})

    ctx.engine(7, "Evidence Pack Generator", f"wave {wave}")
    ctx.progress(0.2, "assembling the assurance plan")

    summary = project.get("summary") or {}
    pack = evidence_report.generate_pack(
        kg,
        project={"id": ctx.project_id, "name": project["name"],
                 "target_cloud": project["target_cloud"]},
        wave=wave,
        schedule=schedule,
        decisions=decisions,
        gxp_summary={**(summary.get("gxp") or {}), "gaps": summary.get("gxp_gaps") or []},
        readiness_summary=summary.get("readiness") or {},
        decomposition=summary.get("decomposition") or {},
        montecarlo=montecarlo,
        approvals=approvals,
    )
    ctx.progress(0.9, "writing the PDF")

    with session_scope() as s:
        s.add(EvidencePack(
            project_id=ctx.project_id, wave=wave,
            file_path=str(pack.pdf_path), html_path=str(pack.html_path),
            meta_json={
                "renderer": pack.renderer,
                "components": len((pack.data.get("assurance") or {}).get("components") or []),
                "tier_counts": (pack.data.get("assurance") or {}).get("tier_counts") or {},
                "traceability_rows": len(pack.data.get("traceability") or []),
                "tests": len((pack.data.get("tests") or {}).get("tests") or []),
                "gaps": len((pack.data.get("gxp") or {}).get("gaps") or []),
                "size_kb": round(Path(pack.pdf_path).stat().st_size / 1024, 1)
                if pack.pdf_path else None,
            },
        ))

    record("evidence.generated", actor="system", entity="evidence_pack",
           entity_id=f"{ctx.project_id}:wave{wave}",
           payload={"wave": wave, "renderer": pack.renderer})

    meta = (pack.data.get("assurance") or {}).get("tier_counts") or {}
    ctx.progress(1.0, f"evidence pack for wave {wave} generated")
    return {
        "wave": wave,
        "pdf_path": str(pack.pdf_path),
        "html_path": str(pack.html_path),
        "renderer": pack.renderer,
        "tier_counts": meta,
        "traceability_rows": len(pack.data.get("traceability") or []),
        "tests_generated": len((pack.data.get("tests") or {}).get("tests") or []),
    }
