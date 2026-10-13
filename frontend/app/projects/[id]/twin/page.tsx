"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity, ArrowRight, Code2, Database, Eye, FileCode2, GitFork,
  Layers, Network, Play, Search, ShieldAlert, Sparkles, Terminal, X,
} from "lucide-react";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type NodeDetail, type Tier } from "@/lib/api";
import { cn, duration, num, simple } from "@/lib/format";
import { useApp } from "@/lib/store";
import { MermaidViewer } from "@/components/MermaidViewer";
import { TwinCytoscape } from "@/components/TwinCytoscape";
import {
  Banner, Card, Drawer, Empty, ErrorNote, Kpi, Loading, PageHeader,
  Spinner, Tabs, TierBadge,
} from "@/components/ui";

export default function TwinPage() {
  const { id } = useParams<{ id: string }>();
  const [level, setLevel] = React.useState<"class" | "module">("class");
  const [tier, setTier] = React.useState<Tier | "ALL">("ALL");
  const [search, setSearch] = React.useState("");
  const [viewTab, setViewTab] = React.useState<"graph" | "c4" | "queries">("graph");
  const [c4Tab, setC4Tab] = React.useState<"context" | "containers" | "components" | "sequence">("containers");
  const [selectedUseCase, setSelectedUseCase] = React.useState<string>("");
  const [selectedTemplateId, setSelectedTemplateId] = React.useState<string>("");
  const [templateParams, setTemplateParams] = React.useState<Record<string, string>>({});

  const { selectedNode, selectNode, setChatOpen } = useApp();

  const graphQuery = useQuery({
    queryKey: ["twinGraph", id, level, tier],
    queryFn: () => Api.twinGraph(id, { level, tier: tier === "ALL" ? undefined : tier }),
  });

  const nodeQuery = useQuery({
    queryKey: ["nodeDetail", id, selectedNode],
    queryFn: () => (selectedNode ? Api.nodeDetail(id, selectedNode) : null),
    enabled: Boolean(selectedNode),
  });

  const diagramsQuery = useQuery({
    queryKey: ["diagrams", id],
    queryFn: () => Api.diagrams(id),
  });

  const templatesQuery = useQuery({
    queryKey: ["templates", id],
    queryFn: () => Api.templates(id),
  });

  const runQueryMutation = useMutation({
    mutationFn: () => Api.runQuery(id, selectedTemplateId, templateParams),
  });

  // Set default usecase when diagrams load
  React.useEffect(() => {
    if (diagramsQuery.data?.usecases && !selectedUseCase) {
      const keys = Object.keys(diagramsQuery.data.usecases);
      if (keys.length > 0) setSelectedUseCase(keys[0]);
    }
  }, [diagramsQuery.data, selectedUseCase]);

  // Set default template
  React.useEffect(() => {
    if (templatesQuery.data?.templates?.length && !selectedTemplateId) {
      setSelectedTemplateId(templatesQuery.data.templates[0].id);
    }
  }, [templatesQuery.data, selectedTemplateId]);

  if (graphQuery.isLoading) return <Loading label="Loading living architecture twin" rows={5} />;
  if (graphQuery.error) {
    return <ErrorNote error={apiError(graphQuery.error)} retry={() => graphQuery.refetch()} />;
  }

  const rawGraph = graphQuery.data;
  const filteredNodes = (rawGraph?.nodes || []).filter((n) => {
    if (tier !== "ALL" && n.gxpTier !== tier) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      const matchFqn = n.fqn?.toLowerCase().includes(q);
      const matchLabel = n.label?.toLowerCase().includes(q);
      const matchId = n.id.toLowerCase().includes(q);
      return matchFqn || matchLabel || matchId;
    }
    return true;
  });

  const nodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = (rawGraph?.edges || []).filter(
    (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
  );

  const selectedTemplate = templatesQuery.data?.templates?.find((t) => t.id === selectedTemplateId);

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Engine 1 — Knowledge Graph"
        title="Living Architecture Twin"
        subtitle="Source code AST, SQL read/write access, runtime OTel spans, and configuration unified into an interactive dependency graph."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setChatOpen(true)}
              className="btn-outline text-xs min-h-[38px] shadow-sm"
            >
              <Sparkles className="h-3.5 w-3.5 text-accent" /> Ask the Twin
            </button>
            <div className="flex rounded-lg border border-line bg-surface p-1 shadow-sm">
              <button
                onClick={() => setViewTab("graph")}
                className={cn("rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
                  viewTab === "graph" ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink")}
              >
                <Network className="mr-1.5 inline h-3.5 w-3.5" /> Graph
              </button>
              <button
                onClick={() => setViewTab("c4")}
                className={cn("rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
                  viewTab === "c4" ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink")}
              >
                <Code2 className="mr-1.5 inline h-3.5 w-3.5" /> C4 Diagrams
              </button>
              <button
                onClick={() => setViewTab("queries")}
                className={cn("rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:ring-2 focus-visible:ring-accent/40",
                  viewTab === "queries" ? "bg-accent text-white shadow-xs" : "text-muted hover:text-ink")}
              >
                <Terminal className="mr-1.5 inline h-3.5 w-3.5" /> Query Templates
              </button>
            </div>
          </div>
        }
      />

      {/* Stats bar */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Kpi label="Total Graph Nodes" value={num(rawGraph?.counts?.nodes)} icon={<Network className="h-4 w-4" />} />
        <Kpi label="Total Graph Edges" value={num(rawGraph?.counts?.edges)} icon={<GitFork className="h-4 w-4" />} />
        <Kpi label="Visible Nodes" value={num(filteredNodes.length)} hint={`Filtered by ${tier} tier`} />
        <Kpi label="Visible Edges" value={num(filteredEdges.length)} />
        <Kpi label="High GxP Classes" value={num(rawGraph?.nodes.filter((n) => n.gxpTier === "HIGH").length)} tone="high" />
        <Kpi label="Database Tables" value={num(rawGraph?.nodes.filter((n) => n.kind === "Table" || n.label === "Table").length)} />
      </div>

      {/* ---------------------------------------------------------------- TAB 1: GRAPH VIEW */}
      {viewTab === "graph" && (
        <div className="space-y-4">
          {/* Controls Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-surface p-3 shadow-card">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-[200px]">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
                <input
                  type="text"
                  placeholder="Search class or table..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="input py-1.5 pl-8 text-xs"
                />
              </div>

              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-muted">Tier:</span>
                {(["ALL", "HIGH", "MEDIUM", "LOW"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTier(t)}
                    className={cn(
                      "rounded px-2 py-1 text-2xs font-semibold transition-colors",
                      tier === t ? "bg-accent text-white" : "bg-raised text-muted hover:text-ink"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-muted">Level:</span>
                <button
                  onClick={() => setLevel("class")}
                  className={cn(
                    "rounded px-2 py-1 text-2xs font-semibold transition-colors",
                    level === "class" ? "bg-accent text-white" : "bg-raised text-muted hover:text-ink"
                  )}
                >
                  Classes
                </button>
                <button
                  onClick={() => setLevel("module")}
                  className={cn(
                    "rounded px-2 py-1 text-2xs font-semibold transition-colors",
                    level === "module" ? "bg-accent text-white" : "bg-raised text-muted hover:text-ink"
                  )}
                >
                  Modules
                </button>
              </div>
            </div>

            <div className="text-2xs text-muted">
              Click any node on the graph to inspect methods, tables, latency and blast radius.
            </div>
          </div>

          {/* Cytoscape Canvas */}
          <div className="h-[620px] w-full">
            <TwinCytoscape
              nodes={filteredNodes}
              edges={filteredEdges}
              selectedNodeId={selectedNode}
              onSelectNode={(nodeId) => selectNode(nodeId)}
              className="h-full w-full"
            />
          </div>
        </div>
      )}

      {/* ---------------------------------------------------------------- TAB 2: C4 DIAGRAMS */}
      {viewTab === "c4" && (
        <Card
          title="Auto-Generated C4 Architecture Diagrams"
          subtitle="Mermaid diagrams generated deterministically from the Living Architecture Twin graph."
          actions={
            <div className="flex gap-1 rounded-lg border bg-raised p-1">
              <button
                onClick={() => setC4Tab("context")}
                className={cn("rounded-md px-3 py-1 text-xs font-semibold",
                  c4Tab === "context" ? "bg-surface shadow-sm text-ink" : "text-muted hover:text-ink")}
              >
                C4 L1 Context
              </button>
              <button
                onClick={() => setC4Tab("containers")}
                className={cn("rounded-md px-3 py-1 text-xs font-semibold",
                  c4Tab === "containers" ? "bg-surface shadow-sm text-ink" : "text-muted hover:text-ink")}
              >
                C4 L2 Containers
              </button>
              <button
                onClick={() => setC4Tab("components")}
                className={cn("rounded-md px-3 py-1 text-xs font-semibold",
                  c4Tab === "components" ? "bg-surface shadow-sm text-ink" : "text-muted hover:text-ink")}
              >
                C4 L3 Components
              </button>
              <button
                onClick={() => setC4Tab("sequence")}
                className={cn("rounded-md px-3 py-1 text-xs font-semibold",
                  c4Tab === "sequence" ? "bg-surface shadow-sm text-ink" : "text-muted hover:text-ink")}
              >
                Use-Case Sequence
              </button>
            </div>
          }
        >
          {diagramsQuery.isLoading ? (
            <Loading label="Rendering architecture diagrams" />
          ) : (
            <div className="space-y-4">
              {c4Tab === "context" && diagramsQuery.data?.context && (
                <MermaidViewer chart={diagramsQuery.data.context} />
              )}
              {c4Tab === "containers" && diagramsQuery.data?.containers && (
                <MermaidViewer chart={diagramsQuery.data.containers} />
              )}
              {c4Tab === "components" && diagramsQuery.data?.components && (
                <MermaidViewer chart={diagramsQuery.data.components} />
              )}
              {c4Tab === "sequence" && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <label className="text-xs font-semibold text-muted">Select Observed Use Case:</label>
                    <select
                      value={selectedUseCase}
                      onChange={(e) => setSelectedUseCase(e.target.value)}
                      className="input max-w-sm py-1 text-xs font-medium"
                    >
                      {Object.keys(diagramsQuery.data?.usecases || {}).map((uc) => (
                        <option key={uc} value={uc}>{uc}</option>
                      ))}
                    </select>
                  </div>
                  {selectedUseCase && diagramsQuery.data?.usecases?.[selectedUseCase] && (
                    <MermaidViewer chart={diagramsQuery.data.usecases[selectedUseCase]} />
                  )}
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* ---------------------------------------------------------------- TAB 3: QUERY TEMPLATES */}
      {viewTab === "queries" && (
        <Card
          title="Whitelisted Cypher Query Templates"
          subtitle="Deterministic, injection-safe graph traversals used by both human architects and AI agents."
        >
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Template Selector */}
            <div className="space-y-2 lg:col-span-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted">
                Available Templates
              </label>
              <div className="space-y-1.5 max-h-[500px] overflow-y-auto pr-1">
                {templatesQuery.data?.templates.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => {
                      setSelectedTemplateId(t.id);
                      setTemplateParams({});
                    }}
                    className={cn(
                      "w-full rounded-lg border p-3 text-left text-xs transition-colors",
                      selectedTemplateId === t.id
                        ? "border-accent bg-accent-soft/50 text-accent font-semibold"
                        : "bg-surface text-muted hover:bg-raised hover:text-ink"
                    )}
                  >
                    <div className="font-mono text-2xs uppercase tracking-wider text-ink">
                      {t.id}
                    </div>
                    <div className="mt-1 line-clamp-2 text-2xs text-muted">
                      {t.description}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Template Form & Results */}
            <div className="space-y-4 lg:col-span-2">
              {selectedTemplate && (
                <div className="rounded-xl border bg-raised/40 p-4 space-y-3">
                  <div>
                    <h3 className="font-semibold text-sm text-ink">{selectedTemplate.id}</h3>
                    <p className="text-xs text-muted mt-0.5">{selectedTemplate.description}</p>
                  </div>

                  <div className="rounded bg-surface p-2.5 font-mono text-2xs text-muted border">
                    {selectedTemplate.cypher}
                  </div>

                  {/* Dynamic Parameters */}
                  {Object.keys(selectedTemplate.params || {}).length > 0 && (
                    <div className="space-y-2 pt-2 border-t">
                      <p className="text-2xs font-semibold uppercase tracking-wider text-muted">
                        Template Parameters
                      </p>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {Object.entries(selectedTemplate.params).map(([key, desc]) => (
                          <div key={key}>
                            <label className="text-2xs font-medium text-ink">
                              {key} <span className="text-faint">({desc})</span>
                            </label>
                            <input
                              type="text"
                              value={templateParams[key] || ""}
                              placeholder={`e.g. ${desc}`}
                              onChange={(e) =>
                                setTemplateParams({ ...templateParams, [key]: e.target.value })
                              }
                              className="input py-1 text-xs mt-1"
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <button
                    onClick={() => runQueryMutation.mutate()}
                    disabled={runQueryMutation.isPending}
                    className="btn-primary py-1.5 text-xs"
                  >
                    {runQueryMutation.isPending ? <Spinner /> : <Play className="h-3.5 w-3.5" />}
                    Execute Template
                  </button>
                </div>
              )}

              {/* Execution Results */}
              {runQueryMutation.data && (
                <div className="rounded-xl border bg-surface p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold">
                      Query Results ({runQueryMutation.data.row_count} rows)
                    </span>
                    <span className="text-2xs font-mono text-muted">Status: Success</span>
                  </div>

                  {runQueryMutation.data.rows.length === 0 ? (
                    <div className="p-4 text-center text-xs text-muted">No rows returned.</div>
                  ) : (
                    <div className="max-h-[360px] overflow-x-auto overflow-y-auto rounded border">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b bg-raised font-semibold text-muted text-2xs">
                          <tr>
                            {Object.keys(runQueryMutation.data.rows[0]).map((col) => (
                              <th key={col} className="px-3 py-2">{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y text-2xs">
                          {runQueryMutation.data.rows.map((row, i) => (
                            <tr key={i} className="hover:bg-raised/50">
                              {Object.values(row).map((val, j) => (
                                <td key={j} className="px-3 py-2 font-mono truncate max-w-xs">
                                  {typeof val === "object" ? JSON.stringify(val) : String(val ?? "-")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {runQueryMutation.error && (
                <ErrorNote error={apiError(runQueryMutation.error)} />
              )}
            </div>
          </div>
        </Card>
      )}

      {/* ---------------------------------------------------------------- NODE DETAIL DRAWER */}
      <Drawer
        open={Boolean(selectedNode)}
        onClose={() => selectNode(null)}
        width="max-w-2xl"
        title={
          nodeQuery.data ? (
            <div className="flex items-center gap-2">
              <TierBadge tier={nodeQuery.data.node.gxpTier as Tier} />
              <span className="truncate">{simple(nodeQuery.data.node.fqn as string) || (nodeQuery.data.node.name as string)}</span>
            </div>
          ) : "Node Details"
        }
        subtitle={nodeQuery.data?.node.fqn as string || selectedNode || ""}
      >
        {nodeQuery.isLoading && <Loading label="Loading component details" rows={4} />}
        {nodeQuery.error && <ErrorNote error={apiError(nodeQuery.error)} />}

        {nodeQuery.data && (
          <div className="space-y-5 p-5">
            {/* Quick KPIs */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Kpi label="Lines of Code" value={num(nodeQuery.data.node.loc as number)} icon={<Code2 className="h-3.5 w-3.5" />} />
              <Kpi label="Complexity" value={num(nodeQuery.data.node.complexity as number)} />
              <Kpi label="Runtime Hits" value={num(nodeQuery.data.node.runtimeHits as number)} icon={<Activity className="h-3.5 w-3.5" />} />
              <Kpi label="Readiness" value={num(nodeQuery.data.node.readiness as number)} unit="/100" />
            </div>

            {/* GxP Evidence Rationale */}
            {nodeQuery.data.gxp_evidence.length > 0 && (
              <div className="rounded-xl border bg-raised/40 p-3.5 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                  <ShieldAlert className="h-4 w-4 text-high" /> GxP Regulatory Rationale
                </div>
                <div className="space-y-1.5">
                  {nodeQuery.data.gxp_evidence.map((ev, i) => (
                    <div key={i} className="rounded-lg border bg-surface p-2.5 text-2xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-accent">{ev.tag}</span>
                        <span className="mono text-muted">{ev.clause || ev.rule_id}</span>
                      </div>
                      <p className="text-ink">{ev.rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Database Tables Access */}
            {(nodeQuery.data.tables.writes.length > 0 || nodeQuery.data.tables.reads.length > 0) && (
              <div className="rounded-xl border border-line bg-surface p-3.5 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                  <Database className="h-4 w-4 text-accent" /> Database Access
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-2xs">
                  <div>
                    <span className="font-semibold text-high">Writes ({nodeQuery.data.tables.writes.length}):</span>
                    <ul className="mt-1 space-y-1">
                      {nodeQuery.data.tables.writes.map((t) => (
                        <li key={t.id} className="mono rounded bg-raised px-2 py-1">
                          {t.name} {t.regulated && <span className="text-high font-bold">(GxP Regulated)</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <span className="font-semibold text-accent">Reads ({nodeQuery.data.tables.reads.length}):</span>
                    <ul className="mt-1 space-y-1">
                      {nodeQuery.data.tables.reads.map((t) => (
                        <li key={t.id} className="mono rounded bg-raised px-2 py-1">
                          {t.name}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* Methods Table */}
            {nodeQuery.data.methods.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Declared Methods ({nodeQuery.data.methods.length})
                </h4>
                <div className="max-h-60 overflow-y-auto rounded-lg border divide-y text-2xs">
                  {nodeQuery.data.methods.map((m) => (
                    <div key={m.id} className="p-2.5 hover:bg-raised/50 space-y-1">
                      <div className="flex items-center justify-between font-mono font-semibold">
                        <span className="text-ink truncate">{m.name}</span>
                        <TierBadge tier={m.gxpTier} size="xs" />
                      </div>
                      <div className="text-muted flex items-center gap-3">
                        <span>Lines: {m.startLine}–{m.endLine}</span>
                        <span>Complexity: {m.complexity}</span>
                        <span>Hits: {m.runtimeHits}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Downstream Blast Radius */}
            {nodeQuery.data.blast_radius.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Blast Radius — Affected Dependents ({nodeQuery.data.blast_radius.length})
                </h4>
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
                  {nodeQuery.data.blast_radius.map((b) => (
                    <span
                      key={b.id}
                      onClick={() => selectNode(b.id)}
                      className="chip cursor-pointer hover:border-accent text-2xs"
                    >
                      <TierBadge tier={b.gxpTier} size="xs" showLabel={false} />
                      {simple(b.fqn)} ({b.hops} hop)
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
