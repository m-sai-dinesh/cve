"""Scheduler and Monte Carlo tests (PRD §13, §22)."""
from __future__ import annotations

import pytest
from app.engines.roadmap.scheduler import solve, Task
from app.engines.roadmap.montecarlo import simulate


def test_monte_carlo_percentiles_order():
    """PRD §22: Monte Carlo P50 <= P80 <= P95."""
    tasks = [
        Task(id="t1", name="Task 1", weeks=4.0, squad_weeks=4.0, pert=(2.0, 4.0, 7.0), tier="HIGH"),
        Task(id="t2", name="Task 2", weeks=3.0, squad_weeks=3.0, pert=(1.0, 3.0, 5.0), tier="LOW", depends_on=["t1"]),
        Task(id="t3", name="Task 3", weeks=5.0, squad_weeks=5.0, pert=(3.0, 5.0, 9.0), tier="MEDIUM", depends_on=["t2"]),
    ]
    sched = solve(tasks, squads=2, freeze_windows=[])
    mc = simulate(sched, runs=1000, seed=42)
    p = mc.percentiles
    assert p["p50"] <= p["p80"] <= p["p95"], f"Percentiles must satisfy P50 <= P80 <= P95: {p}"


def test_scheduler_respects_precedence():
    """PRD §22: scheduler never violates dependency constraints."""
    tasks = [
        Task(id="a", name="Task A", weeks=3.0, squad_weeks=3.0),
        Task(id="b", name="Task B", weeks=4.0, squad_weeks=4.0, depends_on=["a"]),
    ]
    sched = solve(tasks, squads=2, freeze_windows=[])
    by_id = sched.by_id()
    assert by_id["b"].start_week >= by_id["a"].end_week, "Task B must start after Task A finishes"
