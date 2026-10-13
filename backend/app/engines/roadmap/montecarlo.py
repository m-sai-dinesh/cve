"""Engine 6, part 2 — Monte Carlo schedule simulation (PRD §13.2).

Each task duration is drawn from a PERT (scaled Beta) distribution fitted to its
(optimistic, likely, pessimistic) triple, then propagated through the dependency
graph and squad capacity that CP-SAT produced. 10,000 runs by default.

Outputs: P50 / P80 / P95 completion dates, probability of hitting a target
date, and a tornado chart of which tasks actually drive the variance.

Why PERT rather than triangular: the Beta form puts less mass in the extreme
tails, which matches how software estimates actually miss - usually a little,
occasionally a lot - and it is the distribution the PERT triple was designed for.
A fixed seed makes every reported percentile reproducible, which Annex 22 asks
of us for any number we put in front of a reviewer.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ...core.logging import get_logger
from .scheduler import Schedule, Task

log = get_logger("roadmap.montecarlo")

# PERT shape parameter. 4 is the classical weighting of the mode in the
# PERT mean (o + 4m + p) / 6.
PERT_LAMBDA = 4.0


@dataclass
class SimulationResult:
    runs: int = 0
    seed: int = 0
    percentiles: dict[str, float] = field(default_factory=dict)
    dates: dict[str, str] = field(default_factory=dict)
    histogram: list[dict[str, Any]] = field(default_factory=list)
    tornado: list[dict[str, Any]] = field(default_factory=list)
    target_date: str | None = None
    probability_by_target: float | None = None
    deterministic_weeks: int = 0
    mean_weeks: float = 0.0
    std_weeks: float = 0.0
    task_stats: list[dict[str, Any]] = field(default_factory=list)
    start_date: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs, "seed": self.seed,
            "percentiles": {k: round(v, 2) for k, v in self.percentiles.items()},
            "dates": self.dates,
            "histogram": self.histogram,
            "tornado": self.tornado,
            "target_date": self.target_date,
            "probability_by_target": (round(self.probability_by_target, 4)
                                      if self.probability_by_target is not None else None),
            "deterministic_weeks": self.deterministic_weeks,
            "mean_weeks": round(self.mean_weeks, 2),
            "std_weeks": round(self.std_weeks, 2),
            "task_stats": self.task_stats,
            "start_date": self.start_date,
            "distribution": "PERT (scaled Beta, lambda=4)",
        }


def pert_samples(
    rng: np.random.Generator, o: float, m: float, p: float, n: int
) -> np.ndarray:
    """Draw n samples from a PERT distribution on [o, p] with mode m."""
    o, m, p = float(o), float(m), float(p)
    if p <= o:
        return np.full(n, max(0.1, m if m > 0 else o))
    m = min(max(m, o), p)
    span = p - o
    # Standard PERT -> Beta parameterisation.
    alpha = 1.0 + PERT_LAMBDA * (m - o) / span
    beta = 1.0 + PERT_LAMBDA * (p - m) / span
    return o + span * rng.beta(alpha, beta, size=n)


def simulate(
    schedule: Schedule,
    *,
    runs: int = 10000,
    seed: int = 20260413,
    target_date: dt.date | None = None,
    progress=None,
) -> SimulationResult:
    """Propagate sampled durations through the solved schedule's structure."""
    tasks = schedule.tasks
    res = SimulationResult(
        runs=runs, seed=seed,
        deterministic_weeks=schedule.makespan_weeks,
        start_date=schedule.start_date.isoformat(),
    )
    if not tasks:
        return res

    rng = np.random.default_rng(seed)
    n = len(tasks)
    index = {t.id: i for i, t in enumerate(tasks)}

    # Sample every task's duration once, for all runs: shape (n, runs).
    durations = np.empty((n, runs), dtype=np.float64)
    for t in tasks:
        o, m, p = t.pert
        durations[index[t.id]] = pert_samples(rng, o, m, p, runs)

    if progress:
        progress(0.3, f"propagating {runs:,} runs through the schedule")

    # Topological order so a predecessor's finish is known before its successor.
    order = _topological(tasks)
    finish = np.zeros((n, runs), dtype=np.float64)

    # Squad capacity: each task was solved onto a lane, so a lane's tasks run in
    # sequence. Modelling that keeps the simulation consistent with the schedule
    # CP-SAT actually produced rather than assuming infinite parallelism.
    lane_free: dict[int, np.ndarray] = {}

    for tid in order:
        t = tasks[index[tid]]
        i = index[tid]
        ready = np.zeros(runs, dtype=np.float64)
        for dep in t.depends_on:
            if dep in index:
                ready = np.maximum(ready, finish[index[dep]])
        lane = lane_free.get(t.squad)
        if lane is not None:
            ready = np.maximum(ready, lane)
        finish[i] = ready + durations[i]
        lane_free[t.squad] = finish[i]

    makespan = finish.max(axis=0)

    if progress:
        progress(0.7, "computing percentiles and variance drivers")

    for label, q in (("p10", 10), ("p50", 50), ("p80", 80), ("p90", 90), ("p95", 95)):
        res.percentiles[label] = float(np.percentile(makespan, q))
    res.mean_weeks = float(makespan.mean())
    res.std_weeks = float(makespan.std())

    sd = schedule.start_date
    res.dates = {
        k: (sd + dt.timedelta(weeks=float(v))).isoformat()
        for k, v in res.percentiles.items()
    }
    res.dates["mean"] = (sd + dt.timedelta(weeks=res.mean_weeks)).isoformat()
    res.dates["deterministic"] = (
        sd + dt.timedelta(weeks=schedule.makespan_weeks)
    ).isoformat()

    if target_date is not None:
        target_weeks = (target_date - sd).days / 7.0
        res.target_date = target_date.isoformat()
        res.probability_by_target = float((makespan <= target_weeks).mean())

    res.histogram = _histogram(makespan, res.percentiles)
    res.tornado = _tornado(tasks, durations, makespan, index)
    res.task_stats = [
        {
            "id": t.id, "name": t.name, "tier": t.tier,
            "pert": list(t.pert),
            "mean_weeks": round(float(durations[index[t.id]].mean()), 2),
            "p80_weeks": round(float(np.percentile(durations[index[t.id]], 80)), 2),
            "finish_p50": round(float(np.percentile(finish[index[t.id]], 50)), 2),
            "finish_p80": round(float(np.percentile(finish[index[t.id]], 80)), 2),
            "on_critical_path": t.id in schedule.critical_path,
        }
        for t in sorted(tasks, key=lambda t: -(t.pert[2] - t.pert[0]))
    ]

    if progress:
        progress(1.0, f"P50 {res.percentiles['p50']:.0f}w / "
                      f"P80 {res.percentiles['p80']:.0f}w / "
                      f"P95 {res.percentiles['p95']:.0f}w")
    log.info("montecarlo_done", runs=runs,
             p50=round(res.percentiles["p50"], 1),
             p80=round(res.percentiles["p80"], 1),
             p95=round(res.percentiles["p95"], 1),
             deterministic=schedule.makespan_weeks)
    return res


def _topological(tasks: list[Task]) -> list[str]:
    by_id = {t.id: t for t in tasks}
    seen: set[str] = set()
    order: list[str] = []

    def visit(tid: str, stack: set[str]) -> None:
        if tid in seen or tid not in by_id:
            return
        if tid in stack:
            return          # cycles were cut at build time; guard anyway
        stack.add(tid)
        for dep in by_id[tid].depends_on:
            visit(dep, stack)
        stack.discard(tid)
        seen.add(tid)
        order.append(tid)

    # Deterministic iteration order so the simulation is reproducible.
    for t in sorted(tasks, key=lambda t: (t.start_week, t.id)):
        visit(t.id, set())
    return order


def _histogram(makespan: np.ndarray, percentiles: dict[str, float], bins: int = 36) -> list[dict[str, Any]]:
    counts, edges = np.histogram(makespan, bins=bins)
    total = max(1, counts.sum())
    cumulative = np.cumsum(counts) / total
    return [
        {
            "week_from": round(float(edges[i]), 2),
            "week_to": round(float(edges[i + 1]), 2),
            "week_mid": round(float((edges[i] + edges[i + 1]) / 2), 2),
            "count": int(counts[i]),
            "share": round(float(counts[i] / total), 5),
            "cumulative": round(float(cumulative[i]), 5),
        }
        for i in range(len(counts))
    ]


def _tornado(
    tasks: list[Task], durations: np.ndarray, makespan: np.ndarray,
    index: dict[str, int], top: int = 12,
) -> list[dict[str, Any]]:
    """Which tasks drive the variance in the completion date.

    Correlation between a task's sampled duration and the overall makespan.
    A task with a wide estimate that is never on the critical path correlates
    near zero and is therefore *not* a schedule risk, however uncertain it is -
    which is exactly the distinction a planner needs and a Gantt chart hides.
    """
    out: list[dict[str, Any]] = []
    m_centred = makespan - makespan.mean()
    m_std = makespan.std()
    if m_std <= 0:
        return out
    for t in tasks:
        d = durations[index[t.id]]
        d_std = d.std()
        if d_std <= 0:
            continue
        corr = float(np.mean(m_centred * (d - d.mean())) / (m_std * d_std))
        # Weeks the makespan shifts between this task's own P10 and P90.
        lo, hi = np.percentile(d, 10), np.percentile(d, 90)
        mask_lo, mask_hi = d <= lo, d >= hi
        swing = 0.0
        if mask_lo.any() and mask_hi.any():
            swing = float(makespan[mask_hi].mean() - makespan[mask_lo].mean())
        out.append({
            "id": t.id, "name": t.name, "tier": t.tier,
            "correlation": round(corr, 4),
            "swing_weeks": round(swing, 2),
            "spread_weeks": round(float(t.pert[2] - t.pert[0]), 2),
        })
    out.sort(key=lambda r: -abs(r["correlation"]))
    return out[:top]


def probability_by(res: SimulationResult, schedule: Schedule, target: dt.date) -> float | None:
    """Re-answer 'what is the chance we make this date?' without re-simulating.

    Interpolated from the stored cumulative histogram, so the what-if sliders
    stay instant.
    """
    if not res.histogram:
        return None
    weeks = (target - schedule.start_date).days / 7.0
    prev = 0.0
    for b in res.histogram:
        if weeks < b["week_from"]:
            return round(prev, 4)
        if b["week_from"] <= weeks <= b["week_to"]:
            span = max(1e-9, b["week_to"] - b["week_from"])
            frac = (weeks - b["week_from"]) / span
            return round(prev + frac * b["share"], 4)
        prev = b["cumulative"]
    return 1.0
