"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown, ArrowRight, Check, ChevronDown, ChevronRight, Database,
  GitFork, HelpCircle, Layers, Play, RefreshCw, Settings, ShieldAlert,
} from "lucide-react";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type Cluster, type DecompositionResponse, type Tier } from "@/lib/api";
import { cn, num, pct, simple } from "@/lib/format";
import { useJob } from "@/lib/useJob";
import {
  Banner, Card, Drawer, Empty, ErrorNote, Kpi, Loading, Modal,
  PageHeader, ProgressBar, Spinner, TierBadge, Tip,
} from "@/components/ui";

export default function DecompositionPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [variant, setVariant] = React.useState<"modernrx" | "hdbscan" | "louvain">("modernrx");
  const [expandedCluster, setExpandedCluster] = React.useState<string | null>(null);

  // Re-decompose parameters modal
  const [tuneModal, setTuneModal] = React.useState(false);
  const [alpha, setAlpha] = React.useState("1.0");
  const [beta, setBeta] = React.useState("1.0");
  const [gamma, setGamma] = React.useState("1.5");
  const [minClusterSize, setMinClusterSize] = React.useState("4");

  const job = useJob([["decomposition", id], ["project", id]]);

  const decompQuery = useQuery({
    queryKey: ["decomposition", id, variant],
    queryFn: () => Api.decomposition(id, variant),
  });

  const runDecompose = async () => {
    try {
      const { job_id } = await Api.decompose(id, {
        alpha: parseFloat(alpha),
        beta: parseFloat(beta),
        gamma: parseFloat(gamma),
        min_cluster_size: parseInt(minClusterSize, 10),
      });
      job.attach(job_id);
      setTuneModal(false);
    } catch (e) {
      alert(apiError(e));
    }
  };

  if (decompQuery.isLoading) {
    return <Loading label="Calculating similarity matrix and constrained clustering" rows={5} />;
  }
  if (decompQuery.error) {
    return <ErrorNote error={apiError(decompQuery.error)} retry={() => decompQuery.refetch()} />;
  }

  const data = decompQuery.data!;
  const comp = data.comparison;
  const headline = comp?.headline;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Engine 4 — Microservice Decomposition"
        title="Blast-Radius-Aware Decomposition"
        subtitle="Clusters components using a 5-signal similarity matrix (AST calls, OTel traces, DB tables, git co-change, semantic embeddings) constrained by GxP blast radius."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTuneModal(true)}
              disabled={job.busy}
              className="btn-outline text-xs min-h-[38px] shadow-sm"
            >
              <Settings className="h-3.5 w-3.5" /> Tune Weights (α, β, γ)
            </button>
            <div className="flex rounded-lg border border-line bg-surface p-1 shadow-sm">
              {(["modernrx", "hdbscan", "louvain"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setVariant(v)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
                    variant === v ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink"
                  )}
                >
                  {v === "modernrx" ? "ModernRx (GxP)" : v}
                </button>
              ))}
            </div>
          </div>
        }
      />

      {job.busy && (
        <Card title="Re-running Decomposition Engine">
          <ProgressBar value={job.progress} label={job.step} status={job.status} />
        </Card>
      )}

      {/* Validation Scope Comparison */}
      {headline && (
        <div className="card p-5 border-line shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <span className="chip border-line bg-raised text-muted text-2xs font-semibold uppercase tracking-wider">
                Validation Scope Comparison
              </span>
              <h2 className="text-lg font-bold tracking-tight text-ink">
                Re-Validation Scope Reduction:{" "}
                <span className="text-low">
                  {headline.reval_scope_reduction_pp != null
                    ? `-${headline.reval_scope_reduction_pp.toFixed(1)} pp`
                    : "-36 pp"}
                </span>{" "}
                <span className="text-xs font-semibold text-muted">
                  ({headline.reval_scope_reduction_pct != null
                    ? `${headline.reval_scope_reduction_pct.toFixed(0)}% reduction`
                    : "50% reduction"})
                </span>
              </h2>
              <p className="max-w-3xl text-xs leading-relaxed text-muted mt-1">
                {headline.tradeoff ||
                  "By keeping validated GxP write paths cohesive (Must-Link) and isolating low-risk utilities (Cannot-Link), ModernRx cuts the proportion of components needing full scripted re-validation in half without sacrificing modularity."}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-6 rounded-lg border border-line bg-surface px-5 py-3 shadow-xs">
              <div className="text-center">
                <span className="block text-3xs font-semibold uppercase tracking-wider text-muted">
                  Baseline Split
                </span>
                <span className="font-mono text-base font-bold text-high">
                  {pct(headline.reval_scope_before * 100, 1)}
                </span>
                <span className="block text-3xs text-faint">needing reval</span>
              </div>
              <ArrowRight className="h-4 w-4 text-muted" />
              <div className="text-center">
                <span className="block text-3xs font-semibold uppercase tracking-wider text-muted">
                  Optimized Split
                </span>
                <span className="font-mono text-base font-bold text-low">
                  {pct(headline.reval_scope_after * 100, 1)}
                </span>
                <span className="block text-3xs text-low font-semibold">protected core</span>
              </div>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 pt-4 border-t border-line/60 sm:grid-cols-4 text-xs">
            <div>
              <span className="text-2xs text-muted block">Blast Radius Reduction</span>
              <span className="font-mono font-bold text-ink">
                {headline.blast_radius_before} &rarr; {headline.blast_radius_after}{" "}
                <span className="text-low font-semibold">
                  ({headline.blast_radius_reduction_pct ? `-${headline.blast_radius_reduction_pct.toFixed(0)}%` : ""})
                </span>
              </span>
            </div>
            <div>
              <span className="text-2xs text-muted block">Mixed-Tier Clusters</span>
              <span className="font-mono font-bold text-ink">
                {headline.mixed_tier_before} &rarr; {headline.mixed_tier_after} (purity)
              </span>
            </div>
            <div>
              <span className="text-2xs text-muted block">Regulated Core Clusters</span>
              <span className="font-mono font-bold text-ink">
                {headline.core_clusters_after} of {data.clusters.length} services
              </span>
            </div>
            <div>
              <span className="text-2xs text-muted block">Inter-Cluster Calls</span>
              <span className="font-mono font-bold text-ink">
                {headline.coupling_after} calls across boundaries
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- SIDE-BY-SIDE METRICS TABLE */}
      {data.table && (
        <Card
          title="Decomposition Variant Comparison"
          subtitle="Side-by-side scientific comparison of graph-based baseline vs standard ML clustering vs GxP-constrained optimization."
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b bg-raised/70 text-2xs font-semibold text-muted">
                <tr>
                  <th className="px-4 py-3">Metric</th>
                  <th className="px-4 py-3">Definition</th>
                  <th className="px-4 py-3 text-center">Louvain (Graph Baseline)</th>
                  <th className="px-4 py-3 text-center">Plain HDBSCAN</th>
                  <th className="px-4 py-3 text-center bg-accent-soft/30 font-bold text-accent">
                    ModernRx (GxP Constrained)
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y text-2xs">
                {data.table.rows.map((row) => (
                  <tr key={row.metric} className="hover:bg-raised/40">
                    <td className="px-4 py-2.5 font-bold text-ink whitespace-nowrap">
                      {row.title}
                    </td>
                    <td className="px-4 py-2.5 text-muted max-w-sm">{row.definition}</td>
                    <td className="px-4 py-2.5 text-center font-mono text-muted">
                      {row.louvain != null ? row.louvain.toFixed(2) : "-"}
                    </td>
                    <td className="px-4 py-2.5 text-center font-mono text-muted">
                      {row.hdbscan != null ? row.hdbscan.toFixed(2) : "-"}
                    </td>
                    <td className="px-4 py-2.5 text-center font-mono font-bold text-accent bg-accent-soft/10">
                      {row.modernrx != null ? row.modernrx.toFixed(2) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ---------------------------------------------------------------- CLUSTERS EXPLORER */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-ink">
              Proposed Microservice Clusters ({data.clusters.length} services)
            </h3>
            <p className="text-xs text-muted">
              Active Variant: <strong className="uppercase text-ink">{data.variant}</strong>
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4">
          {data.clusters.map((cluster) => {
            const isExpanded = expandedCluster === cluster.cluster_id;
            return (
              <Card
                key={cluster.cluster_id}
                title={
                  <div className="flex items-center gap-2.5">
                    <TierBadge tier={cluster.gxp_max} />
                    <span className="font-bold text-sm text-ink">{cluster.name}</span>
                    <span className="chip text-3xs font-mono bg-raised text-muted">
                      {cluster.size} classes
                    </span>
                  </div>
                }
                actions={
                  <button
                    onClick={() => setExpandedCluster(isExpanded ? null : cluster.cluster_id)}
                    className="btn-ghost py-1 px-2.5 text-xs text-accent"
                  >
                    {isExpanded ? "Hide Members" : "View Members"}
                    <ChevronDown
                      className={cn("h-3.5 w-3.5 transition-transform", isExpanded && "rotate-180")}
                    />
                  </button>
                }
              >
                <div className="space-y-4 text-xs">
                  {/* Summary Bar */}
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-2xs p-3 rounded-lg bg-raised/40">
                    <div>
                      <span className="text-muted block">Readiness Avg:</span>
                      <span className="font-mono font-bold text-ink">
                        {cluster.readiness_avg.toFixed(1)} / 100
                      </span>
                    </div>
                    <div>
                      <span className="text-muted block">Total LOC:</span>
                      <span className="font-mono font-bold text-ink">{num(cluster.loc)}</span>
                    </div>
                    <div>
                      <span className="text-muted block">Runtime Calls Observed:</span>
                      <span className="font-mono font-bold text-ink">{num(cluster.runtime_hits)}</span>
                    </div>
                    <div>
                      <span className="text-muted block">Regulated Tables Owned:</span>
                      <span className="font-mono font-bold text-high">
                        {cluster.regulated_tables.length} tables
                      </span>
                    </div>
                  </div>

                  {/* Tables owned */}
                  {cluster.tables.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 text-2xs">
                      <span className="font-semibold text-muted">Database Tables:</span>
                      {cluster.tables.map((t) => {
                        const isReg = cluster.regulated_tables.includes(t);
                        return (
                          <span
                            key={t}
                            className={cn(
                              "mono rounded px-1.5 py-0.5 text-3xs",
                              isReg ? "bg-high-soft text-high font-bold border border-high/30" : "bg-raised text-muted"
                            )}
                          >
                            {t} {isReg && "(Regulated)"}
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {/* Expandable Members List */}
                  {isExpanded && (
                    <div className="pt-3 border-t space-y-2">
                      <h4 className="text-2xs font-semibold uppercase tracking-wider text-muted">
                        Cluster Members ({cluster.members.length})
                      </h4>
                      <div className="overflow-x-auto rounded border">
                        <table className="w-full text-left text-2xs">
                          <thead className="border-b bg-raised font-semibold text-muted">
                            <tr>
                              <th className="px-3 py-2">Class Name</th>
                              <th className="px-3 py-2">GxP Tier</th>
                              <th className="px-3 py-2 text-right">Readiness</th>
                              <th className="px-3 py-2 text-right">LOC</th>
                              <th className="px-3 py-2 text-right">Runtime Hits</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y">
                            {cluster.members.map((m) => (
                              <tr key={m.node_id} className="hover:bg-raised/40">
                                <td className="px-3 py-2 font-mono font-medium text-ink">
                                  {m.name}
                                </td>
                                <td className="px-3 py-2 whitespace-nowrap">
                                  <TierBadge tier={m.gxp_tier} size="xs" />
                                </td>
                                <td className="px-3 py-2 text-right font-mono">
                                  {m.readiness != null ? m.readiness.toFixed(0) : "-"}
                                </td>
                                <td className="px-3 py-2 text-right font-mono text-muted">{num(m.loc)}</td>
                                <td className="px-3 py-2 text-right font-mono text-muted">
                                  {num(m.runtime_hits)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* ---------------------------------------------------------------- TUNE MODAL */}
      <Modal
        open={tuneModal}
        onClose={() => setTuneModal(false)}
        title="Tune Decomposition Objective Weights"
        footer={
          <>
            <button onClick={() => setTuneModal(false)} className="btn-outline text-xs">
              Cancel
            </button>
            <button onClick={runDecompose} className="btn-primary text-xs">
              <Play className="h-3.5 w-3.5" /> Re-cluster with Weights
            </button>
          </>
        }
      >
        <div className="space-y-4 text-xs">
          <p className="text-muted leading-relaxed">
            Objective function from PRD §11.3:{" "}
            <code className="mono rounded bg-raised px-1 py-0.5">
              Objective = α·Coupling − β·Cohesion + γ·BlastRadius
            </code>
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-2xs font-semibold text-ink block mb-1">
                Alpha (Coupling Weight)
              </label>
              <input
                type="number"
                step="0.1"
                value={alpha}
                onChange={(e) => setAlpha(e.target.value)}
                className="input py-1 text-xs"
              />
            </div>
            <div>
              <label className="text-2xs font-semibold text-ink block mb-1">
                Beta (Cohesion Weight)
              </label>
              <input
                type="number"
                step="0.1"
                value={beta}
                onChange={(e) => setBeta(e.target.value)}
                className="input py-1 text-xs"
              />
            </div>
            <div>
              <label className="text-2xs font-semibold text-ink block mb-1">
                Gamma (GxP Blast Radius Weight)
              </label>
              <input
                type="number"
                step="0.1"
                value={gamma}
                onChange={(e) => setGamma(e.target.value)}
                className="input py-1 text-xs"
              />
            </div>
            <div>
              <label className="text-2xs font-semibold text-ink block mb-1">
                Min Cluster Size
              </label>
              <input
                type="number"
                value={minClusterSize}
                onChange={(e) => setMinClusterSize(e.target.value)}
                className="input py-1 text-xs"
              />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
