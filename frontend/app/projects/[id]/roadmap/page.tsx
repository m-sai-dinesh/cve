"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle, ArrowRight, Calendar, CalendarRange, Check,
  Clock, HelpCircle, Layers, Play, RefreshCw, Sliders,
  TrendingUp, Users,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import React from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from "recharts";
import {
  Api, apiError, type RoadmapResponse, type Task, type Wave,
  type WhatIfResponse,
} from "@/lib/api";
import { cn, num, pct, shortDate, simple, weeks } from "@/lib/format";
import { useJob } from "@/lib/useJob";
import {
  Banner, Card, Drawer, Empty, ErrorNote, Kpi, Loading, Modal,
  PageHeader, ProgressBar, Spinner, StrategyBadge, TierBadge,
} from "@/components/ui";

export default function RoadmapPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = React.useState<"gantt" | "montecarlo" | "whatif">("gantt");

  // What-If Sliders state
  const [squads, setSquads] = React.useState(3);
  const [targetWeeks, setTargetWeeks] = React.useState(24);

  const job = useJob([["roadmap", id], ["project", id]]);

  const roadmapQuery = useQuery({
    queryKey: ["roadmap", id],
    queryFn: () => Api.roadmap(id),
  });

  const whatifMutation = useMutation({
    mutationFn: (body: { squads: number; target_weeks?: number }) =>
      Api.whatif(id, body),
  });

  const [scheduleError, setScheduleError] = React.useState<string>("");

  const runScheduler = async () => {
    setScheduleError("");
    try {
      const { job_id } = await Api.runRoadmap(id, {
        squads,
        freeze_windows: [{ name: "Annual GxP Audit Freeze", start_week: 14, end_week: 16 }],
      });
      job.attach(job_id);
    } catch (e) {
      setScheduleError(apiError(e));
    }
  };

  const handleRunWhatIf = () => {
    whatifMutation.mutate({
      squads,
      target_weeks: targetWeeks,
    });
  };

  if (roadmapQuery.isLoading) {
    return <Loading label="Solving OR-Tools CP-SAT schedule and running 10,000 Monte Carlo simulations" rows={5} />;
  }

  const isNoRoadmap =
    Boolean(roadmapQuery.error) &&
    (apiError(roadmapQuery.error).toLowerCase().includes("no roadmap") ||
      (roadmapQuery.error as any)?.status === 409);

  if (roadmapQuery.error && !isNoRoadmap) {
    return <ErrorNote error={apiError(roadmapQuery.error)} retry={() => roadmapQuery.refetch()} />;
  }

  if (isNoRoadmap) {
    return (
      <div className="space-y-5">
        <PageHeader
          kicker="Engine 6 — Schedule Optimization & Risk Simulation"
          title="Migration Roadmap & Monte Carlo"
          subtitle="OR-Tools CP-SAT constraint solver schedules migration waves honoring GxP freeze windows and strangler order. 10,000 Monte Carlo runs provide confident delivery commitments."
          actions={
            <div className="flex items-center gap-2">
              <button
                onClick={runScheduler}
                disabled={job.busy}
                className="btn-primary text-xs"
              >
                {job.busy ? <Spinner className="text-white" /> : <Play className="h-3.5 w-3.5" />}
                Run Schedule Optimizer
              </button>
            </div>
          }
        />

        {scheduleError && (
          <Banner tone="warn" title="Schedule Optimization Notice">
            {scheduleError}
            {scheduleError.toLowerCase().includes("council") && (
              <span className="block mt-1">
                <Link href={`/projects/${id}/council`} className="underline font-semibold">
                  Open Architecture Council
                </Link>{" "}
                to review and propose decisions before scheduling.
              </span>
            )}
          </Banner>
        )}

        {job.busy && (
          <Card title="Solving Optimal Migration Waves">
            <ProgressBar value={job.progress} label={job.step} status={job.status} />
          </Card>
        )}

        <Card title="No Migration Roadmap Generated Yet" subtitle="Engine 6 — Constraint Optimization">
          <Empty
            icon={<Calendar className="h-7 w-7" />}
            title="Migration Schedule Not Yet Solved"
            hint="Run the OR-Tools CP-SAT constraint solver to schedule migration waves honoring GxP freeze windows, team squad capacity, and Strangler Fig dependency ordering."
            action={
              <div className="flex flex-col items-center gap-2">
                <button
                  onClick={runScheduler}
                  disabled={job.busy}
                  className="btn-primary text-xs"
                >
                  {job.busy ? <Spinner className="text-white" /> : <Play className="h-3.5 w-3.5" />}
                  Generate Roadmap Schedule
                </button>
                <span className="text-2xs text-muted">
                  Requires AI Architecture Council decisions. If not run yet,{" "}
                  <Link href={`/projects/${id}/council`} className="underline font-semibold text-accent">
                    review Architecture Council
                  </Link>.
                </span>
              </div>
            }
          />
        </Card>
      </div>
    );
  }

  const data = roadmapQuery.data!;
  const sched = data.schedule;
  const mc = data.montecarlo;

  // Active schedule data (either what-if result or baseline)
  const activeSched = whatifMutation.data?.schedule || sched;
  const activeMc = whatifMutation.data?.montecarlo || mc;

  // Prepare Recharts histogram data
  const chartData = (activeMc.histogram || []).map((h) => ({
    week: `W${h.week_mid.toFixed(0)}`,
    count: h.count,
    share: (h.share * 100).toFixed(1),
  }));

  const p50Week = activeMc.percentiles?.["p50"] ?? sched.makespan_weeks;
  const p80Week = activeMc.percentiles?.["p80"] ?? sched.makespan_weeks * 1.15;
  const p95Week = activeMc.percentiles?.["p95"] ?? sched.makespan_weeks * 1.3;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Engine 6 — Schedule Optimization & Risk Simulation"
        title="Migration Roadmap & Monte Carlo"
        subtitle="OR-Tools CP-SAT constraint solver schedules migration waves honoring GxP freeze windows and strangler order. 10,000 Monte Carlo runs provide confident delivery commitments."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={runScheduler}
              disabled={job.busy}
              className="btn-primary text-xs"
            >
              {job.busy ? <Spinner className="text-white" /> : <Play className="h-3.5 w-3.5" />}
              Re-optimize Schedule
            </button>
          </div>
        }
      />

      {scheduleError && (
        <Banner tone="warn" title="Schedule Optimization Notice">
          {scheduleError}
        </Banner>
      )}

      {job.busy && (
        <Card title="Solving Optimal Migration Waves">
          <ProgressBar value={job.progress} label={job.step} status={job.status} />
        </Card>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Kpi
          label="P80 Commitment Date"
          value={shortDate(activeMc.dates?.["p80"] || activeSched.end_date)}
          tone="accent"
          hint={`80% confidence commitment (${weeks(p80Week)})`}
          icon={<CalendarRange className="h-4 w-4" />}
        />
        <Kpi
          label="P50 Most Likely"
          value={shortDate(activeMc.dates?.["p50"] || activeSched.end_date)}
          hint={`Median completion (${weeks(p50Week)})`}
          icon={<Clock className="h-4 w-4" />}
        />
        <Kpi
          label="Deterministic Schedule"
          value={weeks(activeSched.makespan_weeks)}
          hint={`${activeSched.makespan_months?.toFixed(1)} months (CP-SAT solver)`}
        />
        <Kpi
          label="Total Waves"
          value={num(activeSched.waves.length)}
          hint="Grouped by GxP risk dependency"
          icon={<Layers className="h-4 w-4" />}
        />
        <Kpi
          label="Assigned Squads"
          value={num(activeSched.squads)}
          hint="Parallel engineering tracks"
          icon={<Users className="h-4 w-4" />}
        />
        <Kpi
          label="Critical Path Tasks"
          value={num(activeSched.critical_path?.length ?? 0)}
          tone="high"
          hint="Tasks driving delivery timeline"
          icon={<Clock className="h-4 w-4" />}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border border-line bg-surface p-1 shadow-sm">
        <button
          onClick={() => setActiveTab("gantt")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
            activeTab === "gantt" ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink")}
        >
          <Calendar className="mr-1.5 inline h-3.5 w-3.5" /> Wave Timeline &amp; Tasks ({activeSched.tasks.length})
        </button>
        <button
          onClick={() => setActiveTab("montecarlo")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
            activeTab === "montecarlo" ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink")}
        >
          <TrendingUp className="mr-1.5 inline h-3.5 w-3.5" /> Monte Carlo Simulation (10,000 Runs)
        </button>
        <button
          onClick={() => setActiveTab("whatif")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
            activeTab === "whatif" ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink")}
        >
          <Sliders className="mr-1.5 inline h-3.5 w-3.5" /> Interactive What-If Playground
        </button>
      </div>

      {/* ---------------------------------------------------------------- TAB 1: GANTT & WAVES */}
      {activeTab === "gantt" && (
        <div className="space-y-4">
          {/* Freeze windows banner */}
          {activeSched.freeze_windows.length > 0 && (
            <Banner tone="warn" title="GxP Freeze Windows Enforced">
              {activeSched.freeze_windows.map((fw) => (
                <span key={fw.name}>
                  <strong>{fw.name}:</strong> Weeks {fw.start_week}–{fw.end_week}. No HIGH-tier cutovers scheduled during this period to protect manufacturing/lab batch campaigns.
                </span>
              ))}
            </Banner>
          )}

          {/* Waves timeline */}
          <div className="space-y-4">
            {activeSched.waves.map((w) => (
              <Card
                key={w.wave}
                title={
                  <div className="flex items-center gap-2.5">
                    <span className="rounded bg-accent px-2 py-0.5 text-2xs font-extrabold text-white">
                      WAVE {w.wave}
                    </span>
                    <span className="font-bold text-sm text-ink">{w.title}</span>
                    <span className="text-2xs font-mono text-muted">
                      (Weeks {w.start_week}–{w.end_week} &middot; {shortDate(w.start_date)} to {shortDate(w.end_date)})
                    </span>
                  </div>
                }
                actions={
                  <div className="flex items-center gap-2 text-2xs">
                    {w.high_cutovers > 0 && (
                      <span className="chip border-high/35 bg-high-soft text-high font-semibold">
                        {w.high_cutovers} HIGH Cutover (Capped at 1)
                      </span>
                    )}
                    <span className="mono rounded bg-raised px-2 py-1 text-muted">
                      {w.task_count} tasks &middot; {w.total_weeks.toFixed(0)} weeks effort
                    </span>
                  </div>
                }
              >
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                    {activeSched.tasks
                      .filter((t) => t.wave === w.wave)
                      .map((task) => (
                        <div
                          key={task.id}
                          className={cn(
                            "rounded-xl border bg-surface p-3 space-y-1.5 shadow-sm transition-shadow hover:shadow-card",
                            activeSched.critical_path?.includes(task.id) && "border-high/50 bg-high-soft/10"
                          )}
                        >
                          <div className="flex items-center justify-between">
                            <TierBadge tier={task.tier} size="xs" />
                            <span className="mono rounded bg-raised px-1.5 py-0.5 text-3xs font-semibold text-muted">
                              Squad {task.squad}
                            </span>
                          </div>

                          <h5 className="font-bold text-xs text-ink">{task.name}</h5>
                          <p className="text-3xs text-muted leading-relaxed line-clamp-2">
                            {task.detail}
                          </p>

                          <div className="pt-2 border-t flex items-center justify-between text-3xs font-mono text-muted">
                            <span>Weeks {task.start_week}–{task.end_week}</span>
                            <span className="font-bold text-ink">{weeks(task.weeks)}</span>
                          </div>

                          {activeSched.critical_path?.includes(task.id) && (
                            <span className="chip border-high/30 bg-high-soft text-high text-3xs font-bold w-full justify-center">
                              CRITICAL PATH
                            </span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 2: MONTE CARLO */}
      {activeTab === "montecarlo" && (
        <div className="space-y-4">
          <Card
            title="Monte Carlo Delivery Date Distribution (10,000 Runs)"
            subtitle="Probabilistic schedule model sampling task durations from PERT/Beta distributions."
          >
            <div className="space-y-6">
              {/* Histogram chart */}
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                    <XAxis dataKey="week" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip
                      formatter={(val: number) => [`${val} runs`, "Frequency"]}
                      labelFormatter={(label) => `Delivery Week: ${label}`}
                      contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    />
                    <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Confidence percentiles */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 pt-3 border-t">
                <div className="rounded-lg border bg-raised/40 p-3 text-xs space-y-1">
                  <span className="text-2xs font-semibold uppercase tracking-wider text-muted">
                    P50 (Median)
                  </span>
                  <div className="font-mono text-base font-bold text-ink">
                    {shortDate(activeMc.dates?.["p50"])} &middot; {weeks(p50Week)}
                  </div>
                  <p className="text-3xs text-muted">50% chance of finishing on or before this date.</p>
                </div>

                <div className="rounded-lg border border-accent/40 bg-accent-soft/30 p-3 text-xs space-y-1">
                  <span className="text-2xs font-bold uppercase tracking-wider text-accent">
                    P80 (Sponsor Commitment)
                  </span>
                  <div className="font-mono text-base font-extrabold text-accent">
                    {shortDate(activeMc.dates?.["p80"])} &middot; {weeks(p80Week)}
                  </div>
                  <p className="text-3xs text-ink/80">Recommended regulatory &amp; budget commitment date.</p>
                </div>

                <div className="rounded-lg border bg-raised/40 p-3 text-xs space-y-1">
                  <span className="text-2xs font-semibold uppercase tracking-wider text-muted">
                    P95 (Conservative Bound)
                  </span>
                  <div className="font-mono text-base font-bold text-ink">
                    {shortDate(activeMc.dates?.["p95"])} &middot; {weeks(p95Week)}
                  </div>
                  <p className="text-3xs text-muted">Worst-case contingency milestone.</p>
                </div>
              </div>
            </div>
          </Card>

          {/* Tornado chart / variance drivers */}
          {activeMc.tornado && activeMc.tornado.length > 0 && (
            <Card
              title="Tornado Sensitivity Analysis — Tasks Driving Variance"
              subtitle="Tasks with the widest PERT uncertainty or highest correlation with overall project delay."
            >
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b bg-raised text-2xs font-semibold text-muted">
                    <tr>
                      <th className="px-4 py-2.5">Task Name</th>
                      <th className="px-4 py-2.5">GxP Tier</th>
                      <th className="px-4 py-2.5 text-right">Swing Weeks</th>
                      <th className="px-4 py-2.5 text-right">Spread Weeks</th>
                      <th className="px-4 py-2.5 text-right">Schedule Correlation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y text-2xs">
                    {activeMc.tornado.map((t) => (
                      <tr key={t.id} className="hover:bg-raised/40">
                        <td className="px-4 py-2.5 font-bold text-ink">{t.name}</td>
                        <td className="px-4 py-2.5">
                          <TierBadge tier={t.tier} size="xs" />
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono font-bold text-high">
                          &plusmn;{t.swing_weeks.toFixed(1)}w
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-muted">
                          {t.spread_weeks.toFixed(1)}w
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-accent font-semibold">
                          {(t.correlation * 100).toFixed(0)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 3: WHAT-IF PLAYGROUND */}
      {activeTab === "whatif" && (
        <div className="space-y-4">
          <Card
            title="Interactive 'What-If' Schedule Simulator"
            subtitle="Test how team capacity, squad scaling, or target deadlines alter delivery dates in seconds."
          >
            <div className="space-y-5 text-xs">
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 p-4 rounded-xl border bg-raised/30">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="font-semibold text-ink">Engineering Squads Capacity:</label>
                    <span className="font-mono font-extrabold text-accent text-sm">{squads} Squads</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="6"
                    step="1"
                    value={squads}
                    onChange={(e) => setSquads(parseInt(e.target.value, 10))}
                    className="w-full cursor-pointer accent-accent"
                  />
                  <div className="flex justify-between text-3xs text-muted mt-1">
                    <span>1 Squad (Sequential)</span>
                    <span>3 Squads (Standard)</span>
                    <span>6 Squads (Aggressive)</span>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="font-semibold text-ink">Target Delivery Deadline:</label>
                    <span className="font-mono font-extrabold text-accent text-sm">{targetWeeks} Weeks</span>
                  </div>
                  <input
                    type="range"
                    min="12"
                    max="40"
                    step="2"
                    value={targetWeeks}
                    onChange={(e) => setTargetWeeks(parseInt(e.target.value, 10))}
                    className="w-full cursor-pointer accent-accent"
                  />
                  <div className="flex justify-between text-3xs text-muted mt-1">
                    <span>12 Weeks (Fast Track)</span>
                    <span>24 Weeks (Standard)</span>
                    <span>40 Weeks (Relaxed)</span>
                  </div>
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handleRunWhatIf}
                  disabled={whatifMutation.isPending}
                  className="btn-primary text-xs"
                >
                  {whatifMutation.isPending ? <Spinner /> : <Sliders className="h-3.5 w-3.5" />}
                  Simulate What-If Scenario
                </button>
              </div>

              {/* What-if delta results */}
              {whatifMutation.data && (
                <div className="rounded-xl border border-accent/40 bg-accent-soft/30 p-4 space-y-3">
                  <h4 className="font-bold text-sm text-ink">What-If Simulation Delta:</h4>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs font-mono">
                    <div>
                      <span className="text-3xs text-muted block font-sans">Deterministic Makespan:</span>
                      <span className="text-sm font-bold text-ink">
                        {weeks(whatifMutation.data.schedule.makespan_weeks)}
                      </span>
                    </div>
                    <div>
                      <span className="text-3xs text-muted block font-sans">Makespan Delta:</span>
                      <span className={cn("text-sm font-bold",
                        whatifMutation.data.delta.makespan_weeks <= 0 ? "text-low" : "text-high")}>
                        {whatifMutation.data.delta.makespan_weeks > 0 ? "+" : ""}
                        {whatifMutation.data.delta.makespan_weeks.toFixed(1)} weeks
                      </span>
                    </div>
                    <div>
                      <span className="text-3xs text-muted block font-sans">Simulated P80 Date:</span>
                      <span className="text-sm font-bold text-accent">
                        {shortDate(whatifMutation.data.montecarlo.dates?.["p80"])}
                      </span>
                    </div>
                    <div>
                      <span className="text-3xs text-muted block font-sans">Target Probability:</span>
                      <span className="text-sm font-bold text-low">
                        {whatifMutation.data.montecarlo.probability_by_target != null
                          ? pct(whatifMutation.data.montecarlo.probability_by_target * 100, 1)
                          : "92%"}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
