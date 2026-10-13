"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle, AlertTriangle, ArrowRight, CheckCircle2, ChevronDown,
  Gauge, Info, Layers, RefreshCw, Search, ShieldAlert,
} from "lucide-react";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type Deduction, type Opportunity, type ReadinessScore, type Tier } from "@/lib/api";
import { cn, num, pct, simple } from "@/lib/format";
import {
  Banner, Card, Drawer, Empty, ErrorNote, Kpi, Loading, Meter,
  PageHeader, Tabs, TierBadge, Tip,
} from "@/components/ui";

export default function ReadinessPage() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = React.useState<"scores" | "blockers" | "opportunities">("scores");
  const [tierFilter, setTierFilter] = React.useState<Tier | "ALL">("ALL");
  const [bucketFilter, setBucketFilter] = React.useState<string>("ALL");
  const [search, setSearch] = React.useState("");
  const [selectedScore, setSelectedScore] = React.useState<ReadinessScore | null>(null);

  const readinessQuery = useQuery({
    queryKey: ["readiness", id],
    queryFn: () => Api.readiness(id),
  });

  if (readinessQuery.isLoading) {
    return <Loading label="Evaluating 11-factor cloud readiness metrics" rows={5} />;
  }
  if (readinessQuery.error) {
    return <ErrorNote error={apiError(readinessQuery.error)} retry={() => readinessQuery.refetch()} />;
  }

  const data = readinessQuery.data!;
  const s = data.summary;

  // Filter components
  const filteredScores = data.scores.filter((sc) => {
    if (tierFilter !== "ALL" && sc.gxp_tier !== tierFilter) return false;
    if (bucketFilter !== "ALL") {
      const r = sc.readiness;
      if (bucketFilter === "ready" && r < 80) return false;
      if (bucketFilter === "moderate" && (r < 60 || r >= 80)) return false;
      if (bucketFilter === "difficult" && (r < 40 || r >= 60)) return false;
      if (bucketFilter === "blocked" && r >= 40) return false;
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      return sc.fqn.toLowerCase().includes(q) || (sc.name && sc.name.toLowerCase().includes(q));
    }
    return true;
  });

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Engine 3 — Cloud Readiness Scorer"
        title="12-Factor & Cloud Readiness"
        subtitle="Evaluates statelessness, local filesystem coupling, shared database access, runtime EOL, and complexity with explainable deductions down to the exact line."
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Kpi
          label="Average Readiness"
          value={num(s.average, 1)}
          unit="/100"
          hint="Unweighted mean across components"
          tone={s.average >= 75 ? "low" : s.average >= 55 ? "medium" : "high"}
          icon={<Gauge className="h-4 w-4" />}
        />
        <Kpi
          label="LOC-Weighted Avg"
          value={num(s.loc_weighted_average, 1)}
          unit="/100"
          hint="Weighted by LOC (core monolith penalised)"
          tone={s.loc_weighted_average >= 70 ? "low" : "medium"}
        />
        <Kpi
          label="Ready (80-100)"
          value={num(s.distribution?.["ready (80-100)"] ?? 0)}
          hint="Safe for immediate rehost/replatform"
          tone="low"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <Kpi
          label="Moderate (60-79)"
          value={num(s.distribution?.["moderate (60-79)"] ?? 0)}
          hint="Needs config/session refactoring"
          tone="medium"
        />
        <Kpi
          label="Difficult / Blocked"
          value={num((s.distribution?.["difficult (40-59)"] ?? 0) + (s.distribution?.["blocked (0-39)"] ?? 0))}
          hint="Severe coupling or filesystem ties"
          tone="high"
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <Kpi
          label="Opportunities"
          value={num(data.opportunities.length)}
          hint={`${num(s.quick_wins)} quick wins identified`}
          icon={<Layers className="h-4 w-4" />}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border bg-surface p-1 shadow-sm">
        <button
          onClick={() => setActiveTab("scores")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "scores" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <Gauge className="mr-1.5 inline h-3.5 w-3.5" /> Component Scores ({filteredScores.length})
        </button>
        <button
          onClick={() => setActiveTab("blockers")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "blockers" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <AlertCircle className="mr-1.5 inline h-3.5 w-3.5" /> Top Migration Blockers ({s.top_blockers.length})
        </button>
        <button
          onClick={() => setActiveTab("opportunities")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "opportunities" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <Layers className="mr-1.5 inline h-3.5 w-3.5" /> Modernization Opportunities ({data.opportunities.length})
        </button>
      </div>

      {/* ---------------------------------------------------------------- TAB 1: SCORES */}
      {activeTab === "scores" && (
        <div className="space-y-4">
          {/* Controls Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-3.5 shadow-card">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-[220px]">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
                <input
                  type="text"
                  placeholder="Filter by class name..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="input py-1.5 pl-8 text-xs min-h-[36px]"
                />
              </div>

              {/* Bucket Filter */}
              <div className="flex items-center gap-1 text-xs">
                <span className="text-muted mr-1 font-medium">Readiness:</span>
                {(["ALL", "ready", "moderate", "difficult", "blocked"] as const).map((b) => (
                  <button
                    key={b}
                    onClick={() => setBucketFilter(b)}
                    className={cn(
                      "rounded px-2.5 py-1 text-2xs font-semibold capitalize transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
                      bucketFilter === b ? "bg-accent text-white shadow-xs" : "bg-raised text-muted hover:text-ink"
                    )}
                  >
                    {b}
                  </button>
                ))}
              </div>

              {/* Tier Filter */}
              <div className="flex items-center gap-1 text-xs">
                <span className="text-muted mr-1 font-medium">Tier:</span>
                {(["ALL", "HIGH", "MEDIUM", "LOW"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTierFilter(t)}
                    className={cn(
                      "rounded px-2.5 py-1 text-2xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
                      tierFilter === t ? "bg-accent text-white shadow-xs" : "bg-raised text-muted hover:text-ink"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div className="text-2xs text-muted font-medium">
              Click any row to inspect explainable point deductions.
            </div>
          </div>

          {/* Scores Table */}
          <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-line bg-raised/75 text-2xs font-bold text-muted">
                  <tr>
                    <th className="px-4 py-3">Readiness Score</th>
                    <th className="px-4 py-3">Component / Class</th>
                    <th className="px-4 py-3">GxP Tier</th>
                    <th className="px-4 py-3 text-right">LOC</th>
                    <th className="px-4 py-3 text-right">Penalties Deducted</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40 text-2xs">
                  {filteredScores.map((sc) => (
                    <tr
                      key={sc.node_id}
                      onClick={() => setSelectedScore(sc)}
                      className="cursor-pointer transition-colors duration-150 hover:bg-raised/50"
                    >
                      <td className="px-4 py-3 w-48">
                        <Meter value={sc.readiness} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-semibold text-ink block">{simple(sc.fqn)}</span>
                        <span className="text-faint text-3xs font-mono block truncate max-w-md">
                          {sc.fqn}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <TierBadge tier={sc.gxp_tier} />
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-muted">{num(sc.loc)}</td>
                      <td className="px-4 py-3 text-right font-mono text-high font-semibold">
                        -{sc.total_deducted.toFixed(1)} pts ({sc.deductions.length} smells)
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedScore(sc);
                          }}
                          className="btn-outline py-1 px-2.5 text-2xs font-semibold text-accent min-h-[30px] hover:border-accent/40"
                        >
                          Deductions &rarr;
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 2: TOP BLOCKERS */}
      {activeTab === "blockers" && (
        <div className="space-y-4">
          <Card
            title="Top 5 Cloud Modernization Blockers"
            subtitle="The primary architectural anti-patterns driving down cloud readiness across this codebase."
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {s.top_blockers.map((b, i) => (
                <div key={b.check} className="rounded-xl border bg-raised/30 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-2xs font-bold uppercase tracking-wider text-muted">
                      Rank #{i + 1}
                    </span>
                    <span className="font-mono text-xs font-bold text-high">
                      -{b.total_points.toFixed(1)} pts impact
                    </span>
                  </div>
                  <h4 className="font-bold text-sm text-ink">{b.title}</h4>
                  <p className="text-2xs text-muted leading-relaxed">
                    Check weight: {data.weights[b.check] ?? 10} pts. Deductions occur when components depend on stateful session data, shared database tables, or host filesystem paths.
                  </p>
                </div>
              ))}
            </div>
          </Card>

          <Card
            title="Scoring Formula & Check Weights"
            subtitle="PRD §10 explainable scoring model: each check evaluates severity in [0, 1]."
          >
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 text-xs">
              {Object.entries(data.weights).map(([check, w]) => (
                <div key={check} className="rounded-lg border bg-surface p-2.5 flex items-center justify-between">
                  <span className="text-muted truncate mr-2">{data.check_titles[check] || check}</span>
                  <span className="font-mono font-bold text-accent shrink-0">{w} pts</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 3: OPPORTUNITIES */}
      {activeTab === "opportunities" && (
        <div className="space-y-4">
          <Banner tone="info" title="High-Impact Modernization Quick Wins">
            PRD §10 identifies code that can be retired, consolidated, or moved immediately to demonstrate modernization progress at minimal regulatory risk.
          </Banner>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {data.opportunities.map((opp, i) => (
              <Card
                key={i}
                title={
                  <div className="flex items-center gap-2">
                    {opp.kind === "dead_code" && (
                      <span className="chip border-high/35 bg-high-soft text-high text-2xs font-semibold">
                        <AlertTriangle className="h-3 w-3 mr-1 inline" /> Dead Code
                      </span>
                    )}
                    {opp.kind === "duplicate_logic" && (
                      <span className="chip border-medium/35 bg-medium-soft text-medium text-2xs font-semibold">
                        <Layers className="h-3 w-3 mr-1 inline" /> Duplicate Logic
                      </span>
                    )}
                    {opp.kind === "quick_win" && (
                      <span className="chip border-low/35 bg-low-soft text-low text-2xs font-semibold">
                        <CheckCircle2 className="h-3 w-3 mr-1 inline" /> Quick Win
                      </span>
                    )}
                    <span className="font-bold text-sm text-ink truncate">{opp.title}</span>
                  </div>
                }
              >
                <div className="space-y-3 text-xs">
                  <p className="text-ink leading-relaxed">{opp.detail}</p>
                  {opp.node_ids.length > 0 && (
                    <div className="pt-2 border-t text-2xs text-muted flex flex-wrap gap-1">
                      <span className="font-semibold text-muted mr-1">Target Nodes:</span>
                      {opp.node_ids.map((nid) => (
                        <span key={nid} className="mono rounded bg-raised px-1.5 py-0.5 text-3xs text-ink">
                          {simple(nid)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- DEDUCTION DRAWER */}
      <Drawer
        open={Boolean(selectedScore)}
        onClose={() => setSelectedScore(null)}
        width="max-w-xl"
        title={
          selectedScore ? (
            <div className="flex items-center gap-2">
              <TierBadge tier={selectedScore.gxp_tier} />
              <span className="truncate">{simple(selectedScore.fqn)}</span>
            </div>
          ) : "Readiness Deductions"
        }
        subtitle={selectedScore?.fqn}
      >
        {selectedScore && (
          <div className="space-y-5 p-5 text-xs">
            <div className="rounded-xl border bg-raised/40 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-2xs font-semibold uppercase tracking-wider text-muted">
                  Overall Cloud Readiness:
                </span>
                <span className="font-mono text-sm font-bold text-ink">
                  {selectedScore.readiness.toFixed(1)} / 100
                </span>
              </div>
              <Meter value={selectedScore.readiness} />
              <p className="text-2xs text-muted pt-1">
                Total penalty deducted: -{selectedScore.total_deducted.toFixed(1)} points across {selectedScore.deductions.length} checks.
              </p>
            </div>

            <div className="space-y-3">
              <h4 className="font-semibold text-sm text-ink">
                Itemized Point Deductions ({selectedScore.deductions.length})
              </h4>

              {selectedScore.deductions.map((d, i) => (
                <div key={i} className="rounded-lg border bg-surface p-3.5 space-y-2 shadow-sm">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-ink">{d.title}</span>
                    <span className="font-mono font-bold text-high text-xs">
                      -{d.points.toFixed(1)} pts
                    </span>
                  </div>

                  <p className="text-xs text-ink leading-relaxed">{d.detail}</p>

                  <div className="rounded border border-low/30 bg-low-soft/20 p-2 text-2xs text-ink">
                    <span className="font-semibold text-low block mb-0.5">Remediation:</span>
                    {d.remediation}
                  </div>

                  {d.evidence_node_ids.length > 0 && (
                    <div className="text-3xs font-mono text-muted flex flex-wrap gap-1 pt-1">
                      <span className="font-semibold">Evidence:</span>
                      {d.evidence_node_ids.map((nid) => (
                        <span key={nid} className="rounded bg-raised px-1 py-0.5">
                          {simple(nid)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
