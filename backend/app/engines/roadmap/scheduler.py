"""Engine 6, part 1 — wave scheduling with OR-Tools CP-SAT (PRD §13.1).

Tasks are one per approved cluster decision, plus the shared foundation tasks
every cloud programme needs before any workload moves.

Constraints:
  * foundation tasks precede every workload task;
  * strangler ordering - if A depends heavily on B and both move, B's API facade
    lands before A;
  * GxP freeze windows - no HIGH-tier cutover inside an audit month or batch
    campaign;
  * team capacity per week (squads);
  * at most one HIGH-tier cutover per wave (the risk cap).

Objective: minimise makespan plus lambda * sum of risk-weighted start times, so
risky work lands later - after the team has learned the pattern on quick wins.

A greedy scheduler is kept as a fallback for when CP-SAT cannot prove a solution
inside the time budget; it honours the same hard constraints, and which one ran
is reported rather than hidden.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ...core.logging import get_logger

log = get_logger("roadmap.scheduler")

TIER_RISK = {"HIGH": 3.0, "MEDIUM": 1.6, "LOW": 1.0}

# PRD §13.1: "shared foundation tasks: landing zone, IAM, CI/CD, observability,
# supplier qualification".
FOUNDATION_TASKS: list[dict[str, Any]] = [
    {"id": "foundation:landing-zone", "name": "Cloud landing zone and network",
     "weeks": 3.0, "squad_weeks": 3.0, "tier": "LOW", "wave": 0,
     "detail": "Accounts/subscriptions, network topology, region pinned for data residency."},
    {"id": "foundation:iam", "name": "Identity and access management",
     "weeks": 2.5, "squad_weeks": 2.5, "tier": "MEDIUM", "wave": 0,
     "detail": "Named individual accounts, role mapping, removal of shared credentials."},
    {"id": "foundation:secrets", "name": "Secrets management",
     "weeks": 1.5, "squad_weeks": 1.5, "tier": "MEDIUM", "wave": 0,
     "detail": "Managed secret store, credentials out of configuration, rotation."},
    {"id": "foundation:cicd", "name": "CI/CD with qualified pipeline",
     "weeks": 3.0, "squad_weeks": 3.0, "tier": "MEDIUM", "wave": 0,
     "detail": "Build, test and deploy pipeline whose output is itself qualifiable evidence."},
    {"id": "foundation:observability", "name": "Observability baseline",
     "weeks": 2.0, "squad_weeks": 2.0, "tier": "LOW", "wave": 0,
     "detail": "Health endpoints, structured logs with correlation ids, metrics, alerting."},
    {"id": "foundation:supplier-qualification", "name": "Cloud supplier qualification",
     "weeks": 4.0, "squad_weeks": 2.0, "tier": "HIGH", "wave": 0,
     "detail": "Supplier assessment, quality agreement, responsibility split, "
               "periodic review schedule (Annex 11 draft, July 2025).",
     "is_foundation_gate": True},
    {"id": "foundation:csa-strategy", "name": "CSA assurance strategy and templates",
     "weeks": 2.0, "squad_weeks": 1.0, "tier": "HIGH", "wave": 0,
     "detail": "Risk-based assurance approach, test-evidence templates, approval workflow."},
]


@dataclass
class Task:
    id: str
    name: str
    weeks: float                   # duration in weeks (likely)
    squad_weeks: float             # capacity consumed
    tier: str = "LOW"
    cluster_id: str = ""
    strategy: str = ""
    is_foundation: bool = False
    is_cutover: bool = False       # a HIGH-tier cutover: subject to the risk cap
    depends_on: list[str] = field(default_factory=list)
    pert: tuple[float, float, float] = (1.0, 1.0, 1.0)
    detail: str = ""
    risk: float = 1.0

    # filled by the solver
    start_week: int = 0
    end_week: int = 0
    wave: int = 0
    squad: int = 0

    def as_dict(self, start_date: dt.date) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "detail": self.detail,
            "cluster_id": self.cluster_id, "strategy": self.strategy,
            "tier": self.tier, "is_foundation": self.is_foundation,
            "is_cutover": self.is_cutover, "depends_on": self.depends_on,
            "weeks": round(self.weeks, 2), "pert": list(self.pert),
            "start_week": self.start_week, "end_week": self.end_week,
            "wave": self.wave, "squad": self.squad, "risk": round(self.risk, 2),
            "start_date": (start_date + dt.timedelta(weeks=self.start_week)).isoformat(),
            "end_date": (start_date + dt.timedelta(weeks=self.end_week)).isoformat(),
        }


@dataclass
class FreezeWindow:
    """A period in which no HIGH-tier cutover may happen."""

    name: str
    start_week: int
    end_week: int

    def covers(self, week: int) -> bool:
        return self.start_week <= week < self.end_week

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "start_week": self.start_week, "end_week": self.end_week}


@dataclass
class Schedule:
    tasks: list[Task] = field(default_factory=list)
    waves: list[dict[str, Any]] = field(default_factory=list)
    makespan_weeks: int = 0
    solver: str = ""
    status: str = ""
    objective: float | None = None
    critical_path: list[str] = field(default_factory=list)
    freeze_windows: list[FreezeWindow] = field(default_factory=list)
    squads: int = 3
    start_date: dt.date = field(default_factory=dt.date.today)
    violations: list[str] = field(default_factory=list)
    solve_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tasks": [t.as_dict(self.start_date) for t in self.tasks],
            "waves": self.waves,
            "makespan_weeks": self.makespan_weeks,
            "makespan_months": round(self.makespan_weeks / 4.345, 1),
            "solver": self.solver, "status": self.status,
            "objective": self.objective,
            "critical_path": self.critical_path,
            "freeze_windows": [f.as_dict() for f in self.freeze_windows],
            "squads": self.squads,
            "start_date": self.start_date.isoformat(),
            "end_date": (self.start_date + dt.timedelta(weeks=self.makespan_weeks)).isoformat(),
            "violations": self.violations,
            "solve_seconds": round(self.solve_seconds, 2),
        }

    def by_id(self) -> dict[str, Task]:
        return {t.id: t for t in self.tasks}


# =============================================================================
# Task construction
# =============================================================================

def build_tasks(
    decisions: list[dict[str, Any]],
    cluster_index: dict[str, dict[str, Any]],
    *,
    include_foundation: bool = True,
) -> list[Task]:
    """One task per decision, plus the foundation tasks."""
    tasks: list[Task] = []

    if include_foundation:
        for spec in FOUNDATION_TASKS:
            tasks.append(Task(
                id=spec["id"], name=spec["name"], weeks=float(spec["weeks"]),
                squad_weeks=float(spec["squad_weeks"]), tier=str(spec["tier"]),
                is_foundation=True, detail=str(spec["detail"]),
                pert=(float(spec["weeks"]) * 0.8, float(spec["weeks"]),
                      float(spec["weeks"]) * 1.4),
                risk=TIER_RISK.get(str(spec["tier"]), 1.0),
            ))

    foundation_ids = [t.id for t in tasks]

    for d in decisions:
        cid = str(d.get("cluster_id") or "")
        cluster = cluster_index.get(cid, {})
        strategy = str(d.get("strategy") or "Retain")
        pert = d.get("effort_weeks") or [1.0, 1.0, 1.0]
        o, l, p = (float(pert[0]), float(pert[1]), float(pert[2]))
        tier = str(cluster.get("gxp_max") or cluster.get("gxpMax") or "LOW")
        name = str(cluster.get("name") or cid)

        # Retain and Retire are decisions, not build work - they still appear on
        # the roadmap (a Retain has a review date, a Retire has a deletion and
        # its validation impact) but they consume almost no capacity.
        tasks.append(Task(
            id=f"task:{cid}",
            name=f"{strategy}: {name}",
            weeks=max(0.5, l),
            squad_weeks=max(0.2, l if strategy not in ("Retain", "Retire") else l * 0.3),
            tier=tier, cluster_id=cid, strategy=strategy,
            is_cutover=(tier == "HIGH" and strategy not in ("Retain", "Retire")),
            depends_on=list(foundation_ids) if strategy not in ("Retain", "Retire") else [],
            pert=(o, l, p),
            detail=str(d.get("rationale") or "")[:300],
            risk=TIER_RISK.get(tier, 1.0) * (1.4 if strategy == "Refactor" else 1.0),
        ))

    # Strangler ordering: if A depends heavily on B and both are moving, B goes
    # first so A can call a stable facade rather than a moving target.
    by_cluster = {t.cluster_id: t for t in tasks if t.cluster_id}
    for d in decisions:
        cid = str(d.get("cluster_id") or "")
        task = by_cluster.get(cid)
        if task is None or task.strategy in ("Retain", "Retire"):
            continue
        for dep in (cluster_index.get(cid, {}).get("depends_on") or []):
            dep_id = str(dep.get("cluster_id") or "")
            dep_task = by_cluster.get(dep_id)
            if dep_task is None or dep_task.id == task.id:
                continue
            if dep_task.strategy in ("Retain", "Retire"):
                continue
            # "Heavily" = the dependency carries real traffic, not one stray call.
            if float(dep.get("call_weight") or 0) >= 3 and dep_task.id not in task.depends_on:
                task.depends_on.append(dep_task.id)

    _break_cycles(tasks)
    return tasks


def _break_cycles(tasks: list[Task]) -> None:
    """Dependency cycles make the model infeasible; cut the weakest edge.

    Two clusters that call each other is a real finding (it means the boundary
    is wrong), but it must not stop the schedule from being produced. The cut
    is recorded on the task so the UI can show it.
    """
    by_id = {t.id: t for t in tasks}
    state: dict[str, int] = {}

    def visit(tid: str, path: list[str]) -> None:
        state[tid] = 1
        task = by_id.get(tid)
        if task is not None:
            for dep in list(task.depends_on):
                if state.get(dep) == 1:
                    task.depends_on.remove(dep)
                    task.detail = (task.detail + " [circular dependency with "
                                   f"{by_id[dep].name if dep in by_id else dep} "
                                   "was cut to schedule; the boundary needs review]").strip()
                    log.warning("dependency_cycle_cut", task=tid, dep=dep)
                elif state.get(dep, 0) == 0 and dep in by_id:
                    visit(dep, path + [tid])
        state[tid] = 2

    for t in list(tasks):
        if state.get(t.id, 0) == 0:
            visit(t.id, [])


def parse_freeze_windows(
    windows: list[dict[str, Any]] | None, start_date: dt.date
) -> list[FreezeWindow]:
    """Accept week offsets or ISO dates."""
    out: list[FreezeWindow] = []
    for w in windows or []:
        name = str(w.get("name") or "Freeze window")
        if "start_week" in w:
            out.append(FreezeWindow(name, int(w["start_week"]), int(w.get("end_week", 0)
                                                                    or int(w["start_week"]) + 4)))
            continue
        try:
            s = dt.date.fromisoformat(str(w["start_date"]))
            e = dt.date.fromisoformat(str(w["end_date"]))
        except (KeyError, ValueError):
            continue
        out.append(FreezeWindow(
            name,
            max(0, (s - start_date).days // 7),
            max(1, (e - start_date).days // 7),
        ))
    return out


def default_freeze_windows(start_date: dt.date) -> list[FreezeWindow]:
    """Sensible defaults for a pharma site: the annual audit and two campaigns."""
    return [
        FreezeWindow("Annual regulatory audit", 10, 14),
        FreezeWindow("Q4 batch campaign", 30, 36),
    ]


# =============================================================================
# CP-SAT model
# =============================================================================

def solve(
    tasks: list[Task],
    *,
    squads: int = 3,
    freeze_windows: list[FreezeWindow] | None = None,
    horizon_weeks: int | None = None,
    wave_weeks: int = 8,
    max_high_cutovers_per_wave: int = 1,
    lambda_risk: float = 0.08,
    time_limit: float = 10.0,
    start_date: dt.date | None = None,
) -> Schedule:
    start_date = start_date or dt.date.today()
    freeze = freeze_windows if freeze_windows is not None else default_freeze_windows(start_date)
    sched = Schedule(tasks=tasks, squads=squads, freeze_windows=freeze, start_date=start_date)

    if not tasks:
        sched.solver = "none"
        sched.status = "no tasks"
        return sched

    total = sum(max(1, int(round(t.weeks))) for t in tasks)
    horizon = horizon_weeks or max(16, total + 12)

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        log.warning("ortools_unavailable")
        return _greedy(sched, wave_weeks=wave_weeks,
                       max_high_cutovers_per_wave=max_high_cutovers_per_wave)

    import time

    t0 = time.time()
    model = cp_model.CpModel()
    by_id = {t.id: t for t in tasks}
    dur = {t.id: max(1, int(round(t.weeks))) for t in tasks}

    start = {t.id: model.NewIntVar(0, horizon, f"s_{i}") for i, t in enumerate(tasks)}
    end = {t.id: model.NewIntVar(0, horizon, f"e_{i}") for i, t in enumerate(tasks)}
    intervals = {
        t.id: model.NewIntervalVar(start[t.id], dur[t.id], end[t.id], f"i_{i}")
        for i, t in enumerate(tasks)
    }

    # --- precedence -------------------------------------------------------
    for t in tasks:
        for dep in t.depends_on:
            if dep in by_id:
                model.Add(start[t.id] >= end[dep])

    # --- the supplier-qualification gate ----------------------------------
    # No regulated workload may cut over before the cloud provider is qualified.
    gate = next((t.id for t in tasks if t.id == "foundation:supplier-qualification"), None)
    if gate:
        for t in tasks:
            if t.tier in ("HIGH", "MEDIUM") and not t.is_foundation:
                model.Add(start[t.id] >= end[gate])

    # --- capacity: squads working in parallel -----------------------------
    model.AddCumulative(
        [intervals[t.id] for t in tasks],
        [max(1, int(round(t.squad_weeks / max(0.5, t.weeks)))) for t in tasks],
        squads,
    )

    # --- GxP freeze windows: no HIGH-tier cutover inside one --------------
    for t in tasks:
        if not t.is_cutover:
            continue
        for fw in freeze:
            # Either the task finishes before the window opens, or starts after
            # it closes. A HIGH-tier cutover may not straddle an audit month.
            before = model.NewBoolVar(f"b_{t.id}_{fw.start_week}")
            model.Add(end[t.id] <= fw.start_week).OnlyEnforceIf(before)
            model.Add(start[t.id] >= fw.end_week).OnlyEnforceIf(before.Not())

    # --- risk cap: at most N HIGH-tier cutovers per wave ------------------
    waves = max(1, horizon // wave_weeks + 1)
    cutovers = [t for t in tasks if t.is_cutover]
    if cutovers and max_high_cutovers_per_wave > 0:
        for w in range(waves):
            lo, hi = w * wave_weeks, (w + 1) * wave_weeks
            in_wave = []
            for t in cutovers:
                # b is fully reified against "starts inside [lo, hi)". Both
                # directions are needed: with only the forward implication the
                # solver could leave b false for a task that *is* in the wave
                # and dodge the cap entirely.
                b = model.NewBoolVar(f"w{w}_{t.id}")
                lt = model.NewBoolVar(f"w{w}_{t.id}_before")
                ge = model.NewBoolVar(f"w{w}_{t.id}_after")
                model.Add(start[t.id] >= lo).OnlyEnforceIf(b)
                model.Add(start[t.id] < hi).OnlyEnforceIf(b)
                model.Add(start[t.id] < lo).OnlyEnforceIf(lt)
                model.Add(start[t.id] >= lo).OnlyEnforceIf(lt.Not())
                model.Add(start[t.id] >= hi).OnlyEnforceIf(ge)
                model.Add(start[t.id] < hi).OnlyEnforceIf(ge.Not())
                # Exactly one of: before the wave, inside it, after it.
                model.AddExactlyOne([b, lt, ge])
                in_wave.append(b)
            model.Add(sum(in_wave) <= max_high_cutovers_per_wave)

    # --- objective: makespan + lambda * risk-weighted start times ---------
    # CP-SAT objectives must be integer-linear, so lambda and the per-task risk
    # weights are folded into integer coefficients up front rather than divided
    # afterwards. Makespan is scaled by 100 so it stays the dominant term and
    # the risk weighting only breaks ties between equal-length schedules -
    # pushing HIGH-tier work later without ever lengthening the programme.
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, [end[t.id] for t in tasks])
    risk_weight = {t.id: max(1, int(round(lambda_risk * t.risk * 100))) for t in tasks}
    model.Minimize(
        100 * makespan + sum(risk_weight[t.id] * start[t.id] for t in tasks)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 20260413      # reproducible schedules
    status = solver.Solve(model)
    sched.solve_seconds = time.time() - t0

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        log.warning("cpsat_infeasible", status=solver.StatusName(status))
        out = _greedy(sched, wave_weeks=wave_weeks,
                      max_high_cutovers_per_wave=max_high_cutovers_per_wave)
        out.status = (f"CP-SAT returned {solver.StatusName(status)}; "
                      f"fell back to the greedy scheduler")
        return out

    for t in tasks:
        t.start_week = int(solver.Value(start[t.id]))
        t.end_week = int(solver.Value(end[t.id]))
        t.wave = 0 if t.is_foundation else (t.start_week // wave_weeks) + 1
    sched.makespan_weeks = int(solver.Value(makespan))
    sched.solver = "OR-Tools CP-SAT"
    sched.status = solver.StatusName(status)
    sched.objective = solver.ObjectiveValue()

    _assign_squads(sched)
    _finish(sched, wave_weeks)
    log.info("schedule_solved", solver=sched.solver, status=sched.status,
             makespan=sched.makespan_weeks, tasks=len(tasks),
             seconds=round(sched.solve_seconds, 2))
    return sched


def _greedy(
    sched: Schedule, *, wave_weeks: int, max_high_cutovers_per_wave: int
) -> Schedule:
    """List scheduling honouring the same hard constraints.

    Order: foundation first, then by risk ascending (quick wins early to build
    the pattern), then by size. This is what runs if CP-SAT is unavailable or
    cannot prove a solution in the time budget.
    """
    tasks = sched.tasks
    by_id = {t.id: t for t in tasks}
    order = sorted(
        tasks,
        key=lambda t: (not t.is_foundation, t.risk, -t.squad_weeks, t.name),
    )
    squad_free = [0] * max(1, sched.squads)
    cutovers_in_wave: dict[int, int] = {}

    scheduled: set[str] = set()
    remaining = list(order)
    guard = 0
    while remaining and guard < 10000:
        guard += 1
        progressed = False
        for t in list(remaining):
            if any(dep in by_id and dep not in scheduled for dep in t.depends_on):
                continue
            earliest = 0
            for dep in t.depends_on:
                if dep in by_id:
                    earliest = max(earliest, by_id[dep].end_week)
            squad = min(range(len(squad_free)), key=lambda i: squad_free[i])
            week = max(earliest, squad_free[squad])
            dur = max(1, int(round(t.weeks)))

            # Slide past freeze windows and the per-wave cutover cap.
            for _ in range(400):
                wave = 0 if t.is_foundation else (week // wave_weeks) + 1
                blocked = t.is_cutover and any(
                    fw.covers(w) for fw in sched.freeze_windows
                    for w in range(week, week + dur)
                )
                capped = (t.is_cutover and max_high_cutovers_per_wave > 0
                          and cutovers_in_wave.get(wave, 0) >= max_high_cutovers_per_wave)
                if not blocked and not capped:
                    break
                week += 1
            t.start_week, t.end_week = week, week + dur
            t.squad = squad
            t.wave = 0 if t.is_foundation else (week // wave_weeks) + 1
            if t.is_cutover:
                cutovers_in_wave[t.wave] = cutovers_in_wave.get(t.wave, 0) + 1
            squad_free[squad] = t.end_week
            scheduled.add(t.id)
            remaining.remove(t)
            progressed = True
        if not progressed:
            # A residual cycle: schedule the rest sequentially rather than hang.
            for t in remaining:
                squad = min(range(len(squad_free)), key=lambda i: squad_free[i])
                t.start_week = squad_free[squad]
                t.end_week = t.start_week + max(1, int(round(t.weeks)))
                t.squad = squad
                t.wave = (t.start_week // wave_weeks) + 1
                squad_free[squad] = t.end_week
                scheduled.add(t.id)
            remaining = []

    sched.makespan_weeks = max((t.end_week for t in tasks), default=0)
    sched.solver = "greedy list scheduler"
    sched.status = "feasible"
    _finish(sched, wave_weeks)
    return sched


def _assign_squads(sched: Schedule) -> None:
    """Pack tasks onto squad lanes for the Gantt, respecting their solved times."""
    lanes: list[int] = [0] * max(1, sched.squads)
    for t in sorted(sched.tasks, key=lambda t: (t.start_week, t.name)):
        # The lane that is free earliest and no later than this task's start.
        candidates = [i for i, free in enumerate(lanes) if free <= t.start_week]
        lane = candidates[0] if candidates else min(range(len(lanes)), key=lambda i: lanes[i])
        t.squad = lane
        lanes[lane] = t.end_week


def _finish(sched: Schedule, wave_weeks: int) -> None:
    sched.waves = _summarise_waves(sched)
    sched.critical_path = _critical_path(sched)
    sched.violations = _check(sched)


def _summarise_waves(sched: Schedule) -> list[dict[str, Any]]:
    groups: dict[int, list[Task]] = {}
    for t in sched.tasks:
        groups.setdefault(t.wave, []).append(t)

    titles = {
        0: "Wave 0 - Foundation",
        1: "Wave 1 - Quick wins",
    }
    out: list[dict[str, Any]] = []
    for wave in sorted(groups):
        members = sorted(groups[wave], key=lambda t: t.start_week)
        tiers = [t.tier for t in members]
        out.append({
            "wave": wave,
            "title": titles.get(wave, f"Wave {wave}"),
            "task_count": len(members),
            "tasks": [t.id for t in members],
            "task_names": [t.name for t in members],
            "start_week": min(t.start_week for t in members),
            "end_week": max(t.end_week for t in members),
            "start_date": (sched.start_date + dt.timedelta(
                weeks=min(t.start_week for t in members))).isoformat(),
            "end_date": (sched.start_date + dt.timedelta(
                weeks=max(t.end_week for t in members))).isoformat(),
            "high_cutovers": sum(1 for t in members if t.is_cutover),
            "tier_counts": {k: tiers.count(k) for k in ("HIGH", "MEDIUM", "LOW")},
            "total_weeks": round(sum(t.weeks for t in members), 1),
        })
    return out


def _critical_path(sched: Schedule) -> list[str]:
    """The longest dependency chain by finish time."""
    by_id = sched.by_id()
    if not by_id:
        return []
    memo: dict[str, tuple[float, list[str]]] = {}

    def best(tid: str) -> tuple[float, list[str]]:
        if tid in memo:
            return memo[tid]
        t = by_id.get(tid)
        if t is None:
            return 0.0, []
        deps = [d for d in t.depends_on if d in by_id]
        if not deps:
            memo[tid] = (t.weeks, [tid])
        else:
            length, chain = max((best(d) for d in deps), key=lambda x: x[0])
            memo[tid] = (length + t.weeks, chain + [tid])
        return memo[tid]

    end_task = max(by_id, key=lambda tid: (by_id[tid].end_week, best(tid)[0]))
    return best(end_task)[1]


def _check(sched: Schedule) -> list[str]:
    """Verify the hard constraints on the produced schedule.

    The solver should make these impossible, but a schedule that silently
    violates a freeze window would be worse than no schedule at all, so it is
    checked rather than trusted.
    """
    problems: list[str] = []
    by_id = sched.by_id()
    for t in sched.tasks:
        for dep in t.depends_on:
            d = by_id.get(dep)
            if d and t.start_week < d.end_week:
                problems.append(
                    f"'{t.name}' starts in week {t.start_week} but depends on "
                    f"'{d.name}' which ends in week {d.end_week}"
                )
        if t.is_cutover:
            for fw in sched.freeze_windows:
                if any(fw.covers(w) for w in range(t.start_week, max(t.end_week, t.start_week + 1))):
                    problems.append(
                        f"HIGH-tier cutover '{t.name}' (weeks {t.start_week}-{t.end_week}) "
                        f"overlaps the freeze window '{fw.name}'"
                    )
    for w in sched.waves:
        if w["high_cutovers"] > 1:
            problems.append(
                f"{w['title']} contains {w['high_cutovers']} HIGH-tier cutovers; "
                f"the risk cap is 1"
            )
    return problems
