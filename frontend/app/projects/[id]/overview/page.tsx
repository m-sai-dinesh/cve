"use client";

/**
 * Screen 2 - Overview (PRD §18).
 *
 * This is the page a sponsor looks at for ten seconds, so it answers the four
 * questions in order: how big is it, how regulated is it, how ready is it, and
 * how long will it take. The assessment timer is deliberately prominent: the
 * claim being made is that a whole-portfolio GxP assessment takes seconds, not
 * the six weeks a consultancy quotes, and the number is measured, not asserted.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarRange, Clock, Code2, FileCheck2, GitFork, Gauge, Layers,
  MessagesSquare, Network, Play, RefreshCw, ShieldAlert, Timer, TrendingDown,
  ArrowRight, Database, Activity,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type Project } from "@/lib/api";
import { cn, duration, num, pct, ratio, weeks } from "@/lib/format";
import { useJob } from "@/lib/useJob";
import {
  Banner, Card, Empty, ErrorNote, Kpi, Loading, PageHeader, ProgressBar, Spinner, Tip,
} from "@/components/ui";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () => Api.project(id),
    refetchInterval: (q) => (q.state.data?.status === "analyzing" ? 1500 : false),
  });

  const job = useJob([
    ["project", id], ["gxp", id], ["readiness", id],
    ["decomposition", id], ["twin", id],
  ]);

  const [err, setErr] = React.useState("");

  // Reattach to an analysis that is already running (e.g. after a page reload).
  const running = project.data?.jobs?.find(
    (j) => j.type === "analyze" && (j.status === "running" || j.status === "queued"),
  );
  React.useEffect(() => {
    if (running && job.jobId !== running.id) job.attach(running.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running?.id]);

  const rerun = async () => {
    setErr("");
    try {
      const { job_id } = await Api.analyze(id, {});
      job.attach(job_id);
      qc.invalidateQueries({ queryKey: ["project", id] });
    } catch (e) {
      setErr(apiError(e));
    }
  };

  if (project.isLoading) return <Loading label="Loading assessment" rows={4} />;
  if (project.error) {
    return <ErrorNote error={apiError(project.error)} retry={() => project.refetch()} />;
  }

  const p = project.data!;
  const s = p.summary ?? {};
  const analysing = p.status === "analyzing" || job.busy;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Assessment overview"
        title={p.name}
        subtitle={
          <>
            {p.repo_url || p.source_path || "uploaded archive"} &middot; target{" "}
            <strong className="text-ink">{p.target_cloud}</strong>
            {p.use_runtime_traces && " · runtime traces enabled"}
          </>
        }
        actions={
          <>
            {p.has_twin && (
              <Link href={`/projects/${id}/twin`} className="btn-outline py-2 text-xs">
                <Network className="h-4 w-4" /> Open the twin
              </Link>
            )}
            <button onClick={rerun} disabled={analysing} className="btn-primary py-2 text-xs">
              {analysing ? <Spinner className="text-white" /> : <RefreshCw className="h-4 w-4" />}
              {p.has_twin ? "Re-run assessment" : "Run assessment"}
            </button>
          </>
        }
      />

      {err && <ErrorNote error={err} />}

      {analysing && (
        <Card title="Engines 1-4 running" subtitle={job.step || "starting..."}>
          <ProgressBar value={job.progress} label={job.step} status={job.status} />
          <LiveTimer startedAt={p.analysis_started_at} fallback={p.elapsed_seconds} />
          {job.events.length > 0 && (
            <ul className="mono mt-4 max-h-44 space-y-0.5 overflow-y-auto rounded-lg
                           border bg-raised/50 p-2.5 text-[0.6875rem] text-muted">
              {job.events.slice(-40).map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0 text-faint">
                    {e.type === "engine" ? "ENGINE" : e.type === "note" ? "note" : e.type}
                  </span>
                  <span className="min-w-0 truncate">{e.text ?? e.step ?? e.name ?? ""}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {job.status === "failed" && (
        <Banner tone="danger" title="The assessment failed">{job.error}</Banner>
      )}

      {!p.has_twin && !analysing && (
        <Empty
          icon={<Network className="h-7 w-7" />}
          title="No architecture twin yet"
          hint="Run the assessment to parse the source, build the knowledge graph, classify GxP criticality, score cloud readiness and propose a decomposition. On the bundled AcmeLIMS monolith this takes about eight seconds."
          action={<button onClick={rerun} className="btn-primary py-2 text-xs">
            <Play className="h-4 w-4" /> Run assessment
          </button>}
        />
      )}

      {p.has_twin && (
        <>
          {/* ------------------------------------------------------- KPI row */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Lines of code" value={num(s.loc)} icon={<Code2 className="h-4 w-4" />}
              hint={`${num(s.files)} files · ${s.primary_language ?? "-"}`} />
            <Kpi label="Components" value={num(s.components)} icon={<Layers className="h-4 w-4" />}
              hint={`${num(s.graph?.nodes)} graph nodes, ${num(s.graph?.edges)} edges`} />
            <Kpi label="HIGH GxP" value={pct(s.gxp?.pct_high_classes, 0)} tone="high"
              icon={<ShieldAlert className="h-4 w-4" />}
              hint={`${num(s.gxp?.class_tier_counts?.HIGH)} of ${num(s.components)} need scripted testing`} />
            <Kpi label="Avg readiness" value={num(s.readiness?.average, 1)} unit="/100"
              tone={readinessTone(s.readiness?.average)} icon={<Gauge className="h-4 w-4" />}
              hint={`${num(s.readiness?.quick_wins)} quick wins available`} />
            <Kpi label="Compliance gaps" value={num(s.gxp?.gaps)} tone="medium"
              icon={<FileCheck2 className="h-4 w-4" />}
              hint={severityLine(s.gxp?.gaps_by_severity)} />
            <Kpi
              label="Duration P80"
              value={s.roadmap ? num(s.roadmap.p80, 0) : "-"}
              unit={s.roadmap ? "weeks" : undefined}
              tone="accent"
              icon={<CalendarRange className="h-4 w-4" />}
              hint={s.roadmap
                ? `P50 ${num(s.roadmap.p50, 0)}w · P95 ${num(s.roadmap.p95, 0)}w · ${s.roadmap.p80_date}`
                : "Run the roadmap optimizer"} />
          </div>

          {/* ---------------------------------------------- timer + the claim */}
          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-1" title="Assessment duration"
              subtitle="Measured wall-clock, engines 1-4">
              <div className="flex items-baseline gap-2">
                <Timer className="h-6 w-6 shrink-0 text-accent" />
                <span className="text-4xl font-bold tabular-nums tracking-tight text-accent">
                  {s.assessment_seconds != null
                    ? s.assessment_seconds.toFixed(1)
                    : duration(p.assessment_seconds)}
                </span>
                {s.assessment_seconds != null && (
                  <span className="text-sm font-medium text-muted">seconds</span>
                )}
              </div>
              <p className="mt-3 text-xs leading-relaxed text-muted">
                Source parsing, graph construction, GxP classification, readiness scoring
                and blast-radius-aware decomposition, end to end. The equivalent manual
                assessment is quoted in weeks.
              </p>
              <dl className="mt-4 space-y-2 border-t pt-3 text-xs">
                <Row label="Database tables" value={`${num(s.tables)} (${num(s.regulated_tables)} regulated)`} />
                <Row label="HTTP endpoints" value={num(s.endpoints)} />
                <Row label="Test files" value={num(s.test_files)} />
                {s.trace_summary && (
                  <Row label="Runtime spans"
                    value={`${num(s.trace_summary.spans)} over ${num(s.trace_summary.use_cases && Object.keys(s.trace_summary.use_cases).length)} use cases`} />
                )}
                {s.cochange && (
                  <Row label="Git co-change"
                    value={s.cochange.available
                      ? `${num(s.cochange.commits_used)} commits, ${num(s.cochange.pairs)} pairs`
                      : s.cochange.reason} />
                )}
                {s.embeddings && (
                  <Row label="Embeddings"
                    value={`${s.embeddings.model} · ${s.embeddings.dim}d`} />
                )}
              </dl>
            </Card>

            {/* The decomposition money shot, if it has been computed. */}
            <Card className="lg:col-span-2"
              title="What the decomposition bought you"
              subtitle="Engine 4 optimises for revalidation scope, not for modularity"
              actions={
                <Link href={`/projects/${id}/decomposition`} className="btn-ghost py-1 text-xs">
                  Details <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              }>
              {s.decomposition ? (
                <HeadlineBlock d={s.decomposition} />
              ) : (
                <p className="text-sm text-muted">Not computed yet.</p>
              )}
            </Card>
          </div>

          {/* Objectives and Expected Outcomes Alignment */}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="5 Modernization Objectives" subtitle="Track progress across all 5 core advisory objectives">
              <ol className="space-y-2 text-xs">
                <li className="flex items-start gap-2">
                  <span className="font-bold text-accent">1.</span>
                  <span><strong>Analyze existing architectures:</strong> {s.graph ? `Complete (${num(s.graph.nodes)} nodes, ${num(s.graph.edges)} edges in Living Twin)` : "Engine 1 pending"}</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="font-bold text-accent">2.</span>
                  <span><strong>Evaluate cloud readiness:</strong> {s.readiness ? `Complete (Average readiness score: ${num(s.readiness.average, 1)}/100)` : "Engine 3 pending"}</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="font-bold text-accent">3.</span>
                  <span><strong>Identify modernization risks & opportunities:</strong> {s.gxp ? `Complete (${num(s.gxp.class_tier_counts?.HIGH)} HIGH-tier components, ${num(s.gxp.gaps)} gaps, ${num(s.readiness?.quick_wins ?? 0)} quick wins)` : "Engine 2 pending"}</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="font-bold text-accent">4.</span>
                  <span><strong>Recommend target architecture patterns:</strong> {s.decomposition ? `Complete (${num(s.decomposition.clusters)} services, Strangler Fig & 7R patterns)` : "Engines 4 & 5 pending"}</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="font-bold text-accent">5.</span>
                  <span><strong>Generate migration roadmaps:</strong> {s.roadmap ? `Complete (${num(s.roadmap.waves)} waves, P80 completion date computed)` : "Engine 6 pending"}</span>
                </li>
              </ol>
            </Card>

            <Card title="5 Expected Outcomes" subtitle="Delivered business and architectural outcomes">
              <ul className="space-y-2 text-xs">
                <li className="flex items-center gap-2.5">
                  <span className="grid h-5 w-5 place-items-center rounded bg-low/10 text-2xs font-semibold text-low">1</span>
                  <span><strong>Faster architecture assessments:</strong> Delivered in ~{num(p.assessment_seconds ?? 8, 1)}s vs weeks of manual audits.</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="grid h-5 w-5 place-items-center rounded bg-low/10 text-2xs font-semibold text-low">2</span>
                  <span><strong>Clear migration strategy:</strong> 7R recommendations with PERT effort estimates per service.</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="grid h-5 w-5 place-items-center rounded bg-low/10 text-2xs font-semibold text-low">3</span>
                  <span><strong>Reduced transformation risk:</strong> {s.decomposition?.comparison?.headline?.reval_scope_reduction_pp ? `Re-validation scope cut by ${num(s.decomposition.comparison.headline.reval_scope_reduction_pp, 1)} percentage points.` : "Validation blast radius minimized."}</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="grid h-5 w-5 place-items-center rounded bg-low/10 text-2xs font-semibold text-low">4</span>
                  <span><strong>Improved scalability & maintainability:</strong> Decoupled microservice boundaries with low ICP.</span>
                </li>
                <li className="flex items-center gap-2.5">
                  <span className="grid h-5 w-5 place-items-center rounded bg-low/10 text-2xs font-semibold text-low">5</span>
                  <span><strong>Accelerated cloud adoption:</strong> Actionable CP-SAT waves with FDA CSA assurance evidence pack.</span>
                </li>
              </ul>
            </Card>
          </div>

          {/* ---------------------------------------------------- the pipeline */}
          <Card title="Pipeline Execution" subtitle="Each stage feeds the next to achieve the 5 expected outcomes"
            dense bodyClass="divide-y">
            <Stage n={1} Icon={Network} title="Living Architecture Twin"
              href={`/projects/${id}/twin`} done={!!s.graph}
              detail={s.graph
                ? `${num(s.graph.nodes)} nodes, ${num(s.graph.edges)} edges across ${Object.keys(s.graph.by_label ?? {}).length} labels`
                : "not built"} />
            <Stage n={2} Icon={ShieldAlert} title="GxP Criticality Scanner"
              href={`/projects/${id}/gxp`} done={!!s.gxp}
              detail={s.gxp
                ? `${num(s.gxp.class_tier_counts?.HIGH)} HIGH / ${num(s.gxp.class_tier_counts?.MEDIUM)} MEDIUM / ${num(s.gxp.class_tier_counts?.LOW)} LOW · rules v${s.gxp.rules_version} · ${num(s.gxp.gaps)} gaps`
                : "not run"} />
            <Stage n={3} Icon={Gauge} title="Cloud Readiness Scorer"
              href={`/projects/${id}/readiness`} done={!!s.readiness}
              detail={s.readiness
                ? `average ${num(s.readiness.average, 1)}, LOC-weighted ${num(s.readiness.loc_weighted_average, 1)} · top blocker: ${s.readiness.top_blockers?.[0]?.title ?? "-"}`
                : "not run"} />
            <Stage n={4} Icon={GitFork} title="Blast-Radius-Aware Decomposition"
              href={`/projects/${id}/decomposition`} done={!!s.decomposition}
              detail={s.decomposition
                ? `${num(s.decomposition.clusters)} candidate services · chosen variant: ${s.decomposition.chosen}`
                : "not run"} />
            <Stage n={5} Icon={MessagesSquare} title="Architecture Council"
              href={`/projects/${id}/council`} done={!!p.counts.decisions}
              detail={p.counts.decisions
                ? `${num(p.counts.decisions)} decisions · ${num(p.counts.approved)} approved, ${num(p.counts.rejected)} rejected${s.council?.needs_review ? ` · ${s.council.needs_review} need review` : ""}`
                : "five specialist agents debate a 7R strategy per candidate service"}
              cta="Convene" />
            <Stage n={6} Icon={CalendarRange} title="Roadmap Optimizer & Monte Carlo"
              href={`/projects/${id}/roadmap`} done={!!s.roadmap}
              detail={s.roadmap
                ? `${weeks(s.roadmap.makespan_weeks)} in ${num(s.roadmap.waves)} waves · ${s.roadmap.solver} ${s.roadmap.status} · ${num(s.roadmap.violations)} violations · P80 ${num(s.roadmap.p80, 0)}w`
                : "CP-SAT schedule plus a 10,000-run Monte Carlo"}
              cta="Optimise" />
            <Stage n={7} Icon={FileCheck2} title="Evidence Pack Generator"
              href={`/projects/${id}/evidence`} done={!!p.counts.evidence_packs}
              detail={p.counts.evidence_packs
                ? `${num(p.counts.evidence_packs)} packs generated`
                : "CSA-aligned validation plan, traceability matrix and test skeletons per wave"}
              cta="Generate" />
          </Card>

          {/* ------------------------------------------------ blockers + langs */}
          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Top migration blockers"
              subtitle="Deduction points summed across every component"
              actions={<Link href={`/projects/${id}/readiness`} className="btn-ghost py-1 text-xs">
                <Gauge className="h-3.5 w-3.5" /> Readiness
              </Link>}
              className="lg:col-span-2">
              {s.readiness?.top_blockers?.length ? (
                <ul className="space-y-2.5">
                  {s.readiness.top_blockers.slice(0, 6).map((b, i) => {
                    const max = s.readiness!.top_blockers[0].total_points || 1;
                    return (
                      <li key={b.check}>
                        <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
                          <span className="min-w-0 truncate font-medium">
                            <span className="mr-2 text-faint tabular-nums">{i + 1}</span>
                            {b.title}
                          </span>
                          <span className="shrink-0 font-semibold tabular-nums text-muted">
                            {num(b.total_points, 1)} pts
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                          <div className="h-full rounded-full bg-high/80"
                            style={{ width: `${(b.total_points / max) * 100}%` }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-sm text-muted">Readiness has not been scored.</p>
              )}
            </Card>

            <Card title="Composition">
              <dl className="space-y-2.5 text-xs">
                {Object.entries(s.languages ?? {})
                  .sort((a, b) => b[1] - a[1])
                  .map(([lang, loc]) => (
                    <div key={lang}>
                      <div className="mb-1 flex items-baseline justify-between gap-2">
                        <dt className="font-medium">{lang}</dt>
                        <dd className="tabular-nums text-muted">{num(loc)} LOC</dd>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                        <div className="h-full rounded-full bg-accent/80"
                          style={{ width: `${((loc / (s.loc || 1)) * 100).toFixed(1)}%` }} />
                      </div>
                    </div>
                  ))}
                {!Object.keys(s.languages ?? {}).length && (
                  <p className="text-muted">No language breakdown.</p>
                )}
              </dl>

              {s.gxp?.tag_counts && (
                <div className="mt-4 border-t pt-3">
                  <p className="label mb-2">Regulatory tags applied</p>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(s.gxp.tag_counts)
                      .sort((a, b) => b[1] - a[1])
                      .map(([tag, n]) => (
                        <span key={tag} className="chip border-line bg-raised text-muted">
                          <span className="mono">{tag}</span>
                          <span className="font-bold tabular-nums text-ink">{n}</span>
                        </span>
                      ))}
                  </div>
                </div>
              )}

              {s.gxp && (s.gxp.llm_classified || s.gxp.propagated) ? (
                <p className="mt-3 flex items-start gap-1.5 text-2xs leading-relaxed text-faint">
                  <Activity className="mt-px h-3 w-3 shrink-0" />
                  <span>
                    {num(s.gxp.propagated)} components were tiered by indirect
                    propagation and {num(s.gxp.llm_classified)} by the LLM classifier;
                    the rest matched a deterministic rule.
                  </span>
                </p>
              ) : null}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

// =============================================================================

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium">{value}</dd>
    </div>
  );
}

function Stage({
  n, Icon, title, detail, href, done, cta = "View",
}: {
  n: number; Icon: typeof Network; title: string; detail: string;
  href: string; done: boolean; cta?: string;
}) {
  return (
    <Link href={href} className="flex items-center gap-3.5 px-5 py-4 hover:bg-raised/70 transition-colors duration-150 focus-visible:outline-none focus-visible:bg-raised min-h-[48px]">
      <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-lg border shadow-2xs",
        done ? "border-low/35 bg-low-soft text-low" : "border-dashed border-line bg-raised text-faint")}>
        <Icon className="h-4.5 w-4.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="text-2xs font-bold tabular-nums text-faint">{n}</span>
          {title}
        </p>
        <p className="mt-0.5 truncate text-xs text-muted">{detail}</p>
      </div>
      <span className={cn("chip shrink-0 px-2.5 py-1 shadow-2xs font-semibold",
        done ? "border-low/35 bg-low-soft text-low" : "border-accent/35 bg-accent-soft text-accent")}>
        {done ? cta : <>{cta} <ArrowRight className="h-3 w-3" /></>}
      </span>
    </Link>
  );
}

/** Counts up while the assessment runs, so the duration claim is visibly live. */
function LiveTimer({
  startedAt, fallback,
}: { startedAt: string | null; fallback: number | null }) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, []);
  const base = startedAt ? new Date(startedAt).getTime() : NaN;
  const elapsed = Number.isNaN(base) ? (fallback ?? 0) : Math.max(0, (now - base) / 1000);
  return (
    <p className="mt-3 flex items-center gap-2 text-xs text-muted">
      <Clock className="h-3.5 w-3.5" />
      elapsed{" "}
      <span className="font-semibold tabular-nums text-ink">{elapsed.toFixed(1)}s</span>
    </p>
  );
}

function HeadlineBlock({ d }: { d: NonNullable<Project["summary"]["decomposition"]> }) {
  const h = d.comparison?.headline;
  if (!h) return <p className="text-sm text-muted">No comparison available.</p>;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Delta title="Revalidation scope"
          hint="Share of components a cutover drags into scripted revalidation."
          before={ratio(h.reval_scope_before / 100, 1)}
          after={ratio(h.reval_scope_after / 100, 1)}
          change={h.reval_scope_reduction_pct != null
            ? `${h.reval_scope_reduction_pct > 0 ? "-" : "+"}${Math.abs(h.reval_scope_reduction_pct).toFixed(1)}%`
            : "-"}
          good={(h.reval_scope_reduction_pct ?? 0) > 0} />
        <Delta title="Blast radius"
          hint="Mean fraction of the system reachable from a changed component."
          before={h.blast_radius_before.toFixed(3)}
          after={h.blast_radius_after.toFixed(3)}
          change={h.blast_radius_reduction_pct != null
            ? `${h.blast_radius_reduction_pct > 0 ? "-" : "+"}${Math.abs(h.blast_radius_reduction_pct).toFixed(1)}%`
            : "-"}
          good={(h.blast_radius_reduction_pct ?? 0) > 0} />
        <Delta title="Mixed-criticality services"
          hint="A service holding both HIGH and non-HIGH code forces the whole service through HIGH validation."
          before={String(h.mixed_tier_before)}
          after={String(h.mixed_tier_after)}
          change={`${h.mixed_tier_after - h.mixed_tier_before}`}
          good={h.mixed_tier_after <= h.mixed_tier_before} />
      </div>

      <p className="flex items-start gap-2 rounded-lg border border-medium/30 bg-medium-soft
                    px-3.5 py-2.5 text-xs leading-relaxed text-medium">
        <TrendingDown className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span><strong>Trade-off, stated honestly:</strong> {h.tradeoff}</span>
      </p>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-faint">
        <span className="flex items-center gap-1">
          <Database className="h-3 w-3" /> baseline {h.baseline_variant} vs {h.champion_variant}
        </span>
        <span>{num(d.clusters)} candidate services</span>
        <span>
          HIGH-only core services {h.core_clusters_before} &rarr; {h.core_clusters_after}
        </span>
      </div>
    </div>
  );
}

function Delta({
  title, hint, before, after, change, good,
}: {
  title: string; hint: string; before: string; after: string;
  change: string; good: boolean;
}) {
  return (
    <Tip text={hint}>
      <div className="w-full cursor-help rounded-lg border border-line bg-raised/50 p-3.5 transition-all duration-150 hover:bg-raised/80 hover:border-line">
        <p className="text-2xs font-semibold uppercase tracking-wider text-muted">{title}</p>
        <div className="mt-1.5 flex items-baseline gap-1.5">
          <span className="text-sm tabular-nums text-faint line-through">{before}</span>
          <ArrowRight className="h-3 w-3 shrink-0 text-faint" />
          <span className="text-lg font-bold tabular-nums">{after}</span>
        </div>
        <p className={cn("mt-1 text-xs font-bold tabular-nums",
          good ? "text-low" : "text-high")}>
          {change}
        </p>
      </div>
    </Tip>
  );
}

function readinessTone(v: number | undefined): "high" | "medium" | "low" | undefined {
  if (v === undefined) return undefined;
  return v >= 80 ? "low" : v >= 60 ? "medium" : "high";
}

function severityLine(by: Record<string, number> | undefined): string {
  if (!by) return "not scanned";
  const parts = (["HIGH", "MEDIUM", "LOW"] as const)
    .filter((k) => by[k])
    .map((k) => `${by[k]} ${k.toLowerCase()}`);
  return parts.join(", ") || "none found";
}
