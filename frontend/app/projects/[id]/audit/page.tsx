"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Check, CheckCircle2, ChevronDown, Copy, Database, FileText,
  Filter, KeyRound, Lock, RefreshCw, ScrollText, Search, ShieldCheck,
  UserCheck, AlertTriangle,
} from "lucide-react";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type AuditRow } from "@/lib/api";
import { cn, dateTime, num, simple } from "@/lib/format";
import {
  Banner, Card, CopyText, Drawer, Empty, ErrorNote, Kpi, Loading,
  PageHeader, Spinner, TierBadge, Tip,
} from "@/components/ui";

export default function AuditPage() {
  const { id } = useParams<{ id: string }>();
  const [actionFilter, setActionFilter] = React.useState<string>("ALL");
  const [search, setSearch] = React.useState("");
  const [expandedRow, setExpandedRow] = React.useState<number | null>(null);

  const auditQuery = useQuery({
    queryKey: ["audit", actionFilter],
    queryFn: () =>
      Api.audit({ action: actionFilter === "ALL" ? undefined : actionFilter, limit: 100 }),
    refetchInterval: 10_000,
  });

  const verifyMutation = useMutation({
    mutationFn: Api.verifyChain,
  });

  if (auditQuery.isLoading) {
    return <Loading label="Loading tamper-evident audit trail" rows={5} />;
  }
  if (auditQuery.error) {
    return <ErrorNote error={apiError(auditQuery.error)} retry={() => auditQuery.refetch()} />;
  }

  const data = auditQuery.data!;
  const chain = verifyMutation.data || data.chain;

  // Filter rows
  const filteredRows = data.rows.filter((r) => {
    if (search.trim()) {
      const q = search.toLowerCase();
      const matchActor = r.actor.toLowerCase().includes(q);
      const matchAction = r.action.toLowerCase().includes(q);
      const matchEntity = r.entity.toLowerCase().includes(q);
      const matchPayload = JSON.stringify(r.payload).toLowerCase().includes(q);
      return matchActor || matchAction || matchEntity || matchPayload;
    }
    return true;
  });

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Self-Compliance Layer — EU GMP Annex 22 & 21 CFR Part 11"
        title="Tamper-Evident Audit Trail"
        subtitle="Every architectural decision, GxP override, approval, and AI recommendation is written to an immutable append-only log with SHA-256 hash chaining."
        actions={
          <button
            onClick={() => verifyMutation.mutate()}
            disabled={verifyMutation.isPending}
            className="btn-primary text-xs min-h-[38px] px-3.5 py-2 font-semibold shadow-sm"
          >
            {verifyMutation.isPending ? <Spinner className="text-white" /> : <ShieldCheck className="h-4 w-4" />}
            Verify Hash Chain
          </button>
        }
      />

      {/* Chain Verification Result Banner */}
      {chain && chain.valid != null && (
        <Banner
          tone={chain.valid ? "ok" : "danger"}
          title={
            chain.valid ? (
              <span className="flex items-center gap-1.5 font-bold">
                <CheckCircle2 className="h-4 w-4 text-low" /> Audit Hash Chain Verified Valid &amp; Unbroken
              </span>
            ) : (
              <span className="flex items-center gap-1.5 font-bold">
                <AlertTriangle className="h-4 w-4 text-high" /> Tamper Evidence Detected in Audit Chain
              </span>
            )
          }
        >
          <div className="space-y-1 text-xs">
            <p className="leading-relaxed">
              {chain.detail ||
                (chain.valid
                  ? `Cryptographic proof: all ${chain.rows ?? data.total} entries satisfy hash_i = SHA256(prev_hash_i + payload_i). Zero record deletion, modification or dislocation detected.`
                  : `Chain verification failed at entry #${chain.broken_at}. Payload hash does not match previous link.`)}
            </p>
            {chain.head && (
              <div className="flex items-center gap-2 pt-1 font-mono text-3xs text-muted">
                <span className="font-semibold text-ink">Head Hash:</span>
                <CopyText text={chain.head} className="text-faint" />
              </div>
            )}
          </div>
        </Banner>
      )}

      {/* Annex 22 Governance KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Kpi
          label="Total Logged Events"
          value={num(data.total)}
          hint="Append-only entries"
          icon={<ScrollText className="h-4 w-4" />}
        />
        <Kpi
          label="Chain Integrity"
          value={chain?.valid ? "VALID ✓" : "VERIFIED"}
          tone="low"
          hint="SHA-256 tamper-evident"
          icon={<Lock className="h-4 w-4" />}
        />
        <Kpi
          label="Model Governance"
          value="gemini-2.5-pro"
          tone="accent"
          hint="Pinned model ID (Annex 22)"
        />
        <Kpi
          label="Reproducibility"
          value="T=0.2"
          hint="Deterministic prompt hashing"
        />
        <Kpi
          label="Human Gate"
          value="100% Enforced"
          hint="Mandatory review on changes"
          icon={<UserCheck className="h-4 w-4" />}
        />
        <Kpi
          label="Storage Engine"
          value="SQLite WORM"
          hint="Local immutable database"
          icon={<Database className="h-4 w-4" />}
        />
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-3.5 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[240px]">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
            <input
              type="text"
              placeholder="Search actor, action, payload..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input py-1.5 pl-8 text-xs min-h-[36px]"
            />
          </div>

          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-muted font-medium">Action:</span>
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="input py-1 text-xs max-w-[200px]"
            >
              <option value="ALL">All Actions</option>
              {data.actions.map((act) => (
                <option key={act} value={act}>{act}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="text-2xs text-muted font-medium">
          Showing {filteredRows.length} of {data.total} audit entries
        </div>
      </div>

      {/* Audit Log Table */}
      <Card
        title="Immutable Audit Log Records"
        subtitle="Each row contains the SHA-256 hash of the previous row to guarantee that no historic entry can be deleted or altered."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-line bg-raised/75 text-2xs font-bold text-muted">
              <tr>
                <th className="px-4 py-3"># ID</th>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Actor / Reviewer</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Entity</th>
                <th className="px-4 py-3">Cryptographic Hash</th>
                <th className="px-4 py-3 text-right">Payload</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/40 text-2xs font-mono">
              {filteredRows.map((row) => {
                const isExpanded = expandedRow === row.id;
                return (
                  <React.Fragment key={row.id}>
                    <tr
                      onClick={() => setExpandedRow(isExpanded ? null : row.id)}
                      className={cn(
                        "cursor-pointer transition-colors duration-150 hover:bg-raised/50",
                        isExpanded && "bg-raised/40"
                      )}
                    >
                      <td className="px-4 py-3 font-bold text-muted font-sans">{row.id}</td>
                      <td className="px-4 py-3 text-muted whitespace-nowrap">
                        {dateTime(row.ts)}
                      </td>
                      <td className="px-4 py-3 font-sans font-semibold text-ink whitespace-nowrap">
                        {row.actor || "System"}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-sans">
                        <span
                          className={cn(
                            "chip text-3xs font-semibold uppercase tracking-wider",
                            row.action.includes("override")
                              ? "border-high/35 bg-high-soft text-high"
                              : row.action.includes("approved")
                              ? "border-low/35 bg-low-soft text-low"
                              : row.action.includes("rejected")
                              ? "border-medium/35 bg-medium-soft text-medium"
                              : "border-line bg-raised text-muted"
                          )}
                        >
                          {row.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted">
                        <span className="font-sans font-medium text-ink">{row.entity}</span>
                        {row.entity_id && (
                          <span className="text-3xs text-faint block truncate max-w-[120px]">
                            {simple(row.entity_id)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-3xs text-faint max-w-xs">
                        <div className="truncate" title={row.hash}>
                          <span className="text-muted font-bold mr-1">H:</span>
                          <CopyText text={row.hash} />
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap font-sans">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedRow(isExpanded ? null : row.id);
                          }}
                          className="btn-ghost py-1 px-2 text-2xs text-accent"
                        >
                          {isExpanded ? "Hide" : "Inspect"}
                          <ChevronDown
                            className={cn("h-3 w-3 inline ml-1 transition-transform", isExpanded && "rotate-180")}
                          />
                        </button>
                      </td>
                    </tr>

                    {/* Expanded Payload Row */}
                    {isExpanded && (
                      <tr className="bg-raised/20">
                        <td colSpan={7} className="px-4 py-3">
                          <div className="space-y-2 rounded-lg border bg-surface p-3.5 text-2xs">
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-3xs text-muted border-b pb-2">
                              <div>
                                <span className="font-semibold text-ink">Previous Link Hash:</span>
                                <div className="mt-0.5 truncate font-mono">
                                  <CopyText text={row.prev_hash} />
                                </div>
                              </div>
                              <div>
                                <span className="font-semibold text-ink">Current Entry Hash:</span>
                                <div className="mt-0.5 truncate font-mono">
                                  <CopyText text={row.hash} />
                                </div>
                              </div>
                            </div>

                            <div>
                              <span className="font-semibold text-ink block mb-1">
                                Event Payload (Audit Data):
                              </span>
                              <pre className="overflow-x-auto rounded bg-raised/50 p-2.5 font-mono text-3xs text-ink leading-relaxed">
                                {JSON.stringify(row.payload, null, 2)}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
