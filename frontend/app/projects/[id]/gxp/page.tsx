"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Check, ChevronDown, Database, Edit3, Filter,
  History, Info, Layers, RefreshCw, Search, ShieldAlert, ShieldCheck,
} from "lucide-react";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type Gap, type GxpComponent, type Tier } from "@/lib/api";
import { cn, num, pct, simple, TIER_HEX } from "@/lib/format";
import { useApp } from "@/lib/store";
import {
  Banner, Card, Drawer, Empty, ErrorNote, Kpi, Loading, Modal,
  PageHeader, Spinner, Tabs, TierBadge, Tip,
} from "@/components/ui";

export default function GxpPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { currentUser } = useApp();

  const [activeTab, setActiveTab] = React.useState<"components" | "gaps" | "tables" | "overrides">("components");
  const [tierFilter, setTierFilter] = React.useState<Tier | "ALL">("ALL");
  const [tagFilter, setTagFilter] = React.useState<string>("ALL");
  const [search, setSearch] = React.useState("");

  // Override Modal state
  const [overrideModal, setOverrideModal] = React.useState<GxpComponent | null>(null);
  const [newTier, setNewTier] = React.useState<Tier>("MEDIUM");
  const [overrideReason, setOverrideReason] = React.useState("");
  const [overrideError, setOverrideError] = React.useState("");

  // Inspect component detail
  const [selectedComp, setSelectedComp] = React.useState<GxpComponent | null>(null);

  const gxpQuery = useQuery({
    queryKey: ["gxp", id],
    queryFn: () => Api.gxp(id),
  });

  const overrideMutation = useMutation({
    mutationFn: (data: { nodeId: string; tier: Tier; reason: string; userId: string }) =>
      Api.overrideTier(id, data.nodeId, {
        new_tier: data.tier,
        reason: data.reason,
        user_id: data.userId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["gxp", id] });
      qc.invalidateQueries({ queryKey: ["project", id] });
      setOverrideModal(null);
      setOverrideReason("");
      setOverrideError("");
    },
    onError: (err) => {
      setOverrideError(apiError(err));
    },
  });

  if (gxpQuery.isLoading) return <Loading label="Loading GxP Criticality Scanner results" rows={5} />;
  if (gxpQuery.error) {
    return <ErrorNote error={apiError(gxpQuery.error)} retry={() => gxpQuery.refetch()} />;
  }

  const data = gxpQuery.data!;
  const s = data.summary;

  // Filter components
  const filteredComponents = data.components.filter((c) => {
    if (tierFilter !== "ALL" && c.tier !== tierFilter) return false;
    if (tagFilter !== "ALL" && !c.tags.includes(tagFilter)) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return c.name.toLowerCase().includes(q) || c.fqn.toLowerCase().includes(q);
    }
    return true;
  });

  const allTags = Object.keys(data.tag_definitions || {});

  const handleOpenOverride = (comp: GxpComponent) => {
    setOverrideModal(comp);
    setNewTier(comp.tier === "HIGH" ? "MEDIUM" : comp.tier === "MEDIUM" ? "LOW" : "HIGH");
    setOverrideReason("");
    setOverrideError("");
  };

  const handleSubmitOverride = () => {
    if (!overrideModal) return;
    if (!overrideReason.trim()) {
      setOverrideError("A regulatory reason is required for any GxP criticality override.");
      return;
    }
    const userId = currentUser?.id || "user-qa";
    overrideMutation.mutate({
      nodeId: overrideModal.node_id,
      tier: newTier,
      reason: overrideReason.trim(),
      userId,
    });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Engine 2 — Regulatory Classification"
        title="GxP Criticality & Compliance Gaps"
        subtitle="Every class and table evaluated against 21 CFR Part 11, EU GMP Annex 11, and FDA CSA risk scaling. Backed by deterministic rules and human review."
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Kpi
          label="HIGH Criticality"
          value={num(s.class_tier_counts?.HIGH)}
          tone="high"
          hint={`${pct(s.pct_high_classes, 1)} of classes require scripted CSA testing`}
          icon={<ShieldAlert className="h-4 w-4" />}
        />
        <Kpi
          label="MEDIUM Criticality"
          value={num(s.class_tier_counts?.MEDIUM)}
          tone="medium"
          hint="Read-only GxP or indirect 1-hop impact"
        />
        <Kpi
          label="LOW Criticality"
          value={num(s.class_tier_counts?.LOW)}
          tone="low"
          hint="UI/helpers — no GxP validation drag"
        />
        <Kpi
          label="Compliance Gaps"
          value={num(data.gaps.length)}
          tone={data.gaps.length > 0 ? "high" : "low"}
          hint={`${num(s.gaps_by_severity?.HIGH)} HIGH severity gaps planted`}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <Kpi
          label="Regulated Tables"
          value={num(data.tables.filter((t) => t.regulated).length)}
          hint={`${num(data.tables.length)} physical tables total`}
          icon={<Database className="h-4 w-4" />}
        />
        <Kpi
          label="Human Override Rate"
          value={pct(data.override_rate * 100, 1)}
          hint={`${num(data.overrides.length)} manual overrides recorded`}
          icon={<Edit3 className="h-4 w-4" />}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border bg-surface p-1 shadow-sm">
        <button
          onClick={() => setActiveTab("components")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "components" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <Layers className="mr-1.5 inline h-3.5 w-3.5" /> Components Heatmap ({filteredComponents.length})
        </button>
        <button
          onClick={() => setActiveTab("gaps")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "gaps" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5" /> Compliance Gaps ({data.gaps.length})
        </button>
        <button
          onClick={() => setActiveTab("tables")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "tables" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <Database className="mr-1.5 inline h-3.5 w-3.5" /> Tables ({data.tables.length})
        </button>
        <button
          onClick={() => setActiveTab("overrides")}
          className={cn("rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors",
            activeTab === "overrides" ? "bg-accent text-white" : "text-muted hover:text-ink")}
        >
          <History className="mr-1.5 inline h-3.5 w-3.5" /> Human Overrides ({data.overrides.length})
        </button>
      </div>

      {/* ---------------------------------------------------------------- TAB 1: COMPONENTS */}
      {activeTab === "components" && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-surface p-3 shadow-card">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-[220px]">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
                <input
                  type="text"
                  placeholder="Filter by class name..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="input py-1.5 pl-8 text-xs"
                />
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

              {/* Tag Filter */}
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-muted font-medium">Tag:</span>
                <select
                  value={tagFilter}
                  onChange={(e) => setTagFilter(e.target.value)}
                  className="input py-1 text-xs max-w-[160px]"
                >
                  <option value="ALL">All GxP Tags</option>
                  {allTags.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="text-2xs text-muted font-medium">
              Showing {filteredComponents.length} of {data.components.length} components
            </div>
          </div>

          {/* Component Heatmap Table */}
          <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-line bg-raised/75 text-2xs font-bold text-muted">
                  <tr>
                    <th className="px-4 py-3">Criticality Tier</th>
                    <th className="px-4 py-3">Component / Class</th>
                    <th className="px-4 py-3">Regulatory Tags</th>
                    <th className="px-4 py-3 text-right">LOC</th>
                    <th className="px-4 py-3 text-right">Runtime Hits</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40 text-2xs">
                  {filteredComponents.map((c) => (
                    <tr
                      key={c.node_id}
                      className={cn(
                        "transition-colors duration-150 hover:bg-raised/50",
                        c.overridden && "bg-accent-soft/20"
                      )}
                    >
                      <td className="px-4 py-3 font-semibold whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <TierBadge tier={c.tier} />
                          {c.overridden && (
                            <span className="rounded bg-accent/15 px-1 py-0.5 text-[0.5625rem] font-bold text-accent">
                              OVERRIDDEN
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => setSelectedComp(c)}
                          className="font-semibold text-ink hover:text-accent text-left truncate max-w-md block transition-colors focus-visible:outline-none focus-visible:underline"
                        >
                          {c.name}
                        </button>
                        <span className="text-faint text-3xs font-mono truncate max-w-md block">
                          {c.fqn}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1 max-w-sm">
                          {c.tags.length === 0 ? (
                            <span className="text-faint italic text-3xs">None</span>
                          ) : (
                            c.tags.map((t) => (
                              <span
                                key={t}
                                className="rounded bg-raised border border-line/40 px-1.5 py-0.5 text-3xs font-medium text-muted"
                              >
                                {t}
                              </span>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-muted">{num(c.loc)}</td>
                      <td className="px-4 py-3 text-right font-mono text-muted">{num(c.runtime_hits)}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setSelectedComp(c)}
                            className="btn-ghost py-1 px-2.5 text-2xs font-semibold text-muted hover:text-ink min-h-[32px]"
                            title="Inspect Evidence"
                          >
                            Evidence
                          </button>
                          <button
                            onClick={() => handleOpenOverride(c)}
                            className="btn-outline py-1 px-2.5 text-2xs font-semibold text-accent min-h-[32px] hover:border-accent/40"
                            title="Override GxP Criticality Tier"
                          >
                            <Edit3 className="h-3 w-3 inline mr-1" /> Override
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 2: COMPLIANCE GAPS */}
      {activeTab === "gaps" && (
        <div className="space-y-4">
          <Banner tone="danger" title="Regulatory Compliance Gaps Detected in Monolith">
            ModernRx identified {data.gaps.length} non-compliant data integrity or procedural controls that must be remediated during modernization to comply with 21 CFR Part 11 and EU GMP Annex 11.
          </Banner>

          <div className="grid grid-cols-1 gap-4">
            {data.gaps.map((gap) => (
              <Card
                key={gap.id}
                title={
                  <div className="flex items-center gap-2">
                    <TierBadge tier={gap.severity} />
                    <span className="font-bold text-sm text-ink">{gap.title}</span>
                  </div>
                }
                subtitle={<span className="font-mono text-xs text-accent">{gap.clause}</span>}
              >
                <div className="space-y-3 text-xs">
                  <div>
                    <h4 className="font-semibold text-muted text-2xs uppercase tracking-wider mb-1">
                      Observation & Regulatory Risk:
                    </h4>
                    <p className="text-ink leading-relaxed">{gap.detail}</p>
                  </div>

                  <div className="rounded-lg border border-low/30 bg-low-soft/30 p-3">
                    <h4 className="font-semibold text-low text-2xs uppercase tracking-wider mb-1">
                      Required Modernization Remediation:
                    </h4>
                    <p className="text-ink leading-relaxed">{gap.remediation}</p>
                  </div>

                  {gap.evidence_node_ids.length > 0 && (
                    <div className="pt-2 border-t">
                      <span className="text-2xs font-semibold text-muted">
                        Evidence Nodes ({gap.evidence_node_ids.length}):
                      </span>
                      <div className="mt-1 flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                        {gap.evidence_node_ids.map((nid) => (
                          <span key={nid} className="mono rounded bg-raised px-1.5 py-0.5 text-3xs text-muted">
                            {simple(nid)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 3: TABLES */}
      {activeTab === "tables" && (
        <div className="space-y-4">
          <Card
            title="Database Tables Regulatory Status"
            subtitle="Identifies which physical tables store regulated GxP records (requiring audit trail continuity and row-count reconciliation)."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b bg-raised font-semibold text-muted text-2xs">
                  <tr>
                    <th className="px-4 py-2.5">Table Name</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5">GxP Tier</th>
                    <th className="px-4 py-2.5">Tags</th>
                    <th className="px-4 py-2.5">Columns Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-2xs">
                  {data.tables.map((t) => (
                    <tr key={t.node_id} className="hover:bg-raised/40">
                      <td className="px-4 py-2.5 font-mono font-bold text-ink">{t.name}</td>
                      <td className="px-4 py-2.5">
                        {t.regulated ? (
                          <span className="chip text-high border-high/35 bg-high-soft text-3xs font-semibold">
                            REGULATED GxP
                          </span>
                        ) : (
                          <span className="chip text-muted border-line bg-raised text-3xs">
                            Standard
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <TierBadge tier={t.tier} size="xs" />
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {t.tags.map((tag) => (
                            <span key={tag} className="rounded bg-raised px-1.5 py-0.5 text-3xs text-muted">
                              {tag}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-muted">{t.columns?.length ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 4: OVERRIDES HISTORY */}
      {activeTab === "overrides" && (
        <div className="space-y-4">
          <Card
            title="Human Review & Tier Override History"
            subtitle="Under Annex 22, every human override of an automated AI or rule classification must be attributed and audit-logged."
          >
            {data.overrides.length === 0 ? (
              <Empty
                title="No Manual Overrides Recorded"
                hint="All components currently retain their automated GxP rule classification. You can override any tier using the Override button."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b bg-raised font-semibold text-muted text-2xs">
                    <tr>
                      <th className="px-4 py-2.5">Component</th>
                      <th className="px-4 py-2.5">Change</th>
                      <th className="px-4 py-2.5">Justification / Reason</th>
                      <th className="px-4 py-2.5">Reviewer</th>
                      <th className="px-4 py-2.5 text-right">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y text-2xs">
                    {data.overrides.map((ov) => (
                      <tr key={ov.id} className="hover:bg-raised/40">
                        <td className="px-4 py-2.5 font-mono font-semibold text-ink">
                          {simple(ov.node_id)}
                        </td>
                        <td className="px-4 py-2.5 whitespace-nowrap">
                          <span className="font-semibold text-muted">{ov.old_tier}</span> &rarr;{" "}
                          <span className="font-bold text-accent">{ov.new_tier}</span>
                        </td>
                        <td className="px-4 py-2.5 text-ink max-w-md">{ov.reason}</td>
                        <td className="px-4 py-2.5 font-medium text-muted">{ov.user}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-faint">{ov.ts}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ---------------------------------------------------------------- OVERRIDE MODAL */}
      <Modal
        open={Boolean(overrideModal)}
        onClose={() => setOverrideModal(null)}
        title={
          <div className="flex items-center gap-2">
            <Edit3 className="h-4 w-4 text-accent" />
            <span>Override GxP Criticality: {overrideModal?.name}</span>
          </div>
        }
        footer={
          <>
            <button onClick={() => setOverrideModal(null)} className="btn-outline text-xs">
              Cancel
            </button>
            <button
              onClick={handleSubmitOverride}
              disabled={overrideMutation.isPending || !overrideReason.trim()}
              className="btn-primary text-xs"
            >
              {overrideMutation.isPending ? <Spinner /> : <Check className="h-3.5 w-3.5" />}
              Save Override to Audit Log
            </button>
          </>
        }
      >
        <div className="space-y-4 text-xs">
          <p className="text-muted leading-relaxed">
            Changing the GxP tier alters the component&apos;s validation scope and whether it is kept
            inside the constrained microservice core. This action will be appended to the tamper-evident
            hash-chained audit log.
          </p>

          <div className="grid grid-cols-2 gap-3 p-3 bg-raised/50 rounded-lg">
            <div>
              <span className="text-2xs text-muted">Current Tier:</span>
              <div className="mt-1">
                <TierBadge tier={overrideModal?.tier || "LOW"} />
              </div>
            </div>
            <div>
              <span className="text-2xs text-muted">Acting Reviewer:</span>
              <p className="mt-1 font-semibold text-ink">
                {currentUser?.name || "Modernization Lead"}
              </p>
            </div>
          </div>

          <div>
            <label className="text-2xs font-semibold uppercase tracking-wider text-muted block mb-1.5">
              Select New Tier
            </label>
            <div className="flex gap-2">
              {(["HIGH", "MEDIUM", "LOW"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setNewTier(t)}
                  className={cn(
                    "flex-1 rounded-lg border py-2 text-xs font-semibold transition-colors",
                    newTier === t
                      ? "border-accent bg-accent-soft text-accent"
                      : "bg-surface text-muted hover:bg-raised hover:text-ink"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-2xs font-semibold uppercase tracking-wider text-muted block mb-1">
              Regulatory Justification / QA Reason <span className="text-high">*</span>
            </label>
            <textarea
              rows={3}
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="e.g. Verified by QA review that this service only renders read-only exports with no write path to GxP records..."
              className="input text-xs"
            />
          </div>

          {overrideError && <ErrorNote error={overrideError} />}
        </div>
      </Modal>

      {/* ---------------------------------------------------------------- COMPONENT EVIDENCE DRAWER */}
      <Drawer
        open={Boolean(selectedComp)}
        onClose={() => setSelectedComp(null)}
        width="max-w-xl"
        title={
          selectedComp ? (
            <div className="flex items-center gap-2">
              <TierBadge tier={selectedComp.tier} />
              <span className="truncate">{selectedComp.name}</span>
            </div>
          ) : "Component Evidence"
        }
        subtitle={selectedComp?.fqn}
      >
        {selectedComp && (
          <div className="space-y-4 p-5 text-xs">
            <div className="space-y-1">
              <h4 className="font-semibold text-muted text-2xs uppercase tracking-wider">
                Assigned GxP Tags:
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedComp.tags.map((t) => (
                  <span key={t} className="chip bg-accent/10 border-accent/30 text-accent text-xs">
                    {t}
                  </span>
                ))}
              </div>
            </div>

            <div className="space-y-2 pt-2 border-t">
              <h4 className="font-semibold text-ink text-sm">
                Rule Evidence Hits ({selectedComp.evidence.length}):
              </h4>
              <div className="space-y-2">
                {selectedComp.evidence.map((ev, i) => (
                  <div key={i} className="rounded-lg border bg-surface p-3 space-y-1.5 shadow-sm">
                    <div className="flex items-center justify-between text-2xs">
                      <span className="font-bold text-accent">{ev.tag}</span>
                      <span className="mono rounded bg-raised px-1.5 py-0.5 text-muted">
                        Confidence: {(ev.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-ink text-xs">{ev.rationale}</p>
                    {ev.clause && (
                      <p className="text-faint text-2xs font-mono">
                        Regulatory Clause: {ev.clause}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-4 border-t flex justify-end">
              <button
                onClick={() => {
                  handleOpenOverride(selectedComp);
                  setSelectedComp(null);
                }}
                className="btn-primary text-xs"
              >
                <Edit3 className="h-3.5 w-3.5 mr-1" /> Override Tier for this Component
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
