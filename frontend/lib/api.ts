/**
 * Typed client for the ModernRx API.
 *
 * Requests go to /api/* on this origin; next.config.mjs rewrites that to the
 * FastAPI backend, so there is no CORS preflight and no backend host baked into
 * the client bundle.
 */
import axios, { AxiosError } from "axios";

export const api = axios.create({ baseURL: "/api", timeout: 300_000 });

/** Turn an axios failure into the message the API actually sent. */
export function apiError(e: unknown): string {
  const err = e as AxiosError<{ detail?: string | { msg?: string }[] }>;
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg ?? JSON.stringify(d)).join("; ");
  }
  if (err?.code === "ECONNABORTED") return "The request timed out.";
  if (err?.message?.includes("Network Error")) {
    return "Cannot reach the ModernRx API. Is the backend running on port 8000?";
  }
  return err?.message ?? "Unexpected error";
}

// =============================================================================
// Types
// =============================================================================

export type Tier = "HIGH" | "MEDIUM" | "LOW";
export type Strategy =
  | "Retire" | "Retain" | "Rehost" | "Relocate"
  | "Replatform" | "Repurchase" | "Refactor";

export interface User { id: string; name: string; role: string }

export interface Health {
  status: string;
  projects: number;
  llm: { available: boolean; model_id: string; mode: string; error?: string };
  graph_store: string;
  engines: Record<string, string>;
}

export interface Project {
  id: string;
  name: string;
  repo_url: string;
  source_path: string;
  target_cloud: "AWS" | "Azure" | "GCP";
  use_runtime_traces: boolean;
  status: string;
  created_at: string | null;
  analysis_started_at: string | null;
  analysis_finished_at: string | null;
  assessment_seconds: number | null;
  elapsed_seconds: number | null;
  has_twin: boolean;
  counts: {
    decisions: number; approved: number; rejected: number;
    roadmaps: number; evidence_packs: number;
  };
  summary: ProjectSummary;
  jobs?: JobBrief[];
}

export interface ProjectSummary {
  loc?: number;
  files?: number;
  components?: number;
  tables?: number;
  regulated_tables?: number;
  endpoints?: number;
  use_cases?: number;
  test_files?: number;
  primary_language?: string;
  languages?: Record<string, number>;
  assessment_seconds?: number;
  graph?: { nodes: number; edges: number; by_label: Record<string, number> };
  gxp?: {
    class_tier_counts: Record<Tier, number>;
    pct_high_classes: number;
    tag_counts: Record<string, number>;
    gaps: number;
    gaps_by_severity: Record<string, number>;
    rules_version: string;
    llm_classified?: number;
    propagated?: number;
  };
  gxp_gaps?: Gap[];
  readiness?: {
    components: number; average: number; loc_weighted_average: number;
    distribution: Record<string, number>;
    top_blockers: { check: string; title: string; total_points: number }[];
    quick_wins: number;
  };
  decomposition?: {
    chosen: string;
    clusters: number;
    comparison: { headline: Headline; deltas: Record<string, Delta> };
    table: MetricTable;
    signals: { available: Record<string, boolean>; weights: Record<string, number> };
  };
  diagrams?: Diagrams;
  trace_summary?: {
    spans: number; traces: number; total_hits: number;
    use_cases: Record<string, number>; observed_edges: number; unmapped_spans: number;
  } | null;
  cochange?: {
    available: boolean; reason: string; commits_scanned: number;
    commits_used: number; pairs: number; authors: number;
  } | null;
  embeddings?: { model: string; dim: number; count: number };
  council?: {
    decisions: number; needs_review: number;
    strategies: Record<string, number>; generator: string | null;
  };
  roadmap?: {
    makespan_weeks: number; solver: string; status: string; waves: number;
    p50: number; p80: number; p95: number; p80_date: string; violations: number;
  };
}

export interface Diagrams {
  context: string;
  containers: string;
  components: string;
  usecases: Record<string, string>;
  modules: string[];
}

export interface Headline {
  baseline_variant: string;
  champion_variant: string;
  reval_scope_before: number;
  reval_scope_after: number;
  reval_scope_reduction_pp: number | null;
  reval_scope_reduction_pct: number | null;
  blast_radius_before: number;
  blast_radius_after: number;
  blast_radius_reduction_pct: number | null;
  mixed_tier_before: number;
  mixed_tier_after: number;
  core_clusters_before: number;
  core_clusters_after: number;
  coupling_before: number;
  coupling_after: number;
  tradeoff: string;
}

export interface Delta {
  title: string; baseline: number; champion: number;
  delta: number; delta_pct: number | null;
  lower_is_better: boolean | null; improved: boolean | null;
}

export interface MetricTable {
  variants: string[];
  rows: {
    metric: string; title: string; definition: string;
    lower_is_better: boolean | null;
    louvain?: number; hdbscan?: number; modernrx?: number;
  }[];
}

export interface JobBrief {
  id: string; type: string; status: string; progress: number;
  step: string; error: string;
  started_at: string | null; finished_at: string | null;
}

export interface Job extends JobBrief {
  project_id: string;
  events: JobEvent[];
  result: Record<string, unknown>;
}

export interface JobEvent {
  type: string;
  ts?: string;
  text?: string;
  step?: string;
  progress?: number;
  status?: string;
  error?: string;
  index?: number;
  name?: string;
  detail?: string;
  // council_message
  seq?: number;
  stage?: string;
  agent?: string;
  position?: string;
  confidence?: number | null;
  evidence_node_ids?: string[];
  round?: number;
  cluster_id?: string;
  total?: number;
  [k: string]: unknown;
}

export interface JobAccepted {
  job_id: string; project_id: string; type: string; ws: string;
}

export interface GraphNode {
  id: string; label: string; kind: string;
  fqn?: string; package?: string;
  gxpTier: Tier; gxpTags: string[];
  readiness?: number | null;
  loc?: number; complexity?: number;
  fanIn?: number; fanOut?: number; runtimeHits: number;
  clusterId?: string | null; size?: number;
  isController?: boolean; isEntity?: boolean;
  regulated?: boolean; overridden?: boolean; gaps?: string[];
}

export interface GraphEdge {
  id: string; source: string; target: string; rel: string;
  count?: number; runtimeCount?: number | null;
  confirmedAtRuntime?: boolean; weight?: number | null;
}

export interface TwinGraph {
  level: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  counts: { nodes: number; edges: number };
  stats: { nodes: number; edges: number; by_label: Record<string, number>; by_rel: Record<string, number> };
  legend: { tiers: Tier[]; relationships: string[] };
}

export interface GxpEvidence {
  node_id: string; tag: string; rule_id: string;
  confidence: number; rationale: string; clause: string; source: string;
}

export interface Gap {
  id: string; severity: Tier; title: string; clause: string;
  detail: string; remediation: string;
  evidence_node_ids: string[]; evidence_count: number; evidence_note: string;
}

export interface GxpComponent {
  node_id: string; fqn: string; name: string; package: string;
  tier: Tier; tags: string[]; evidence: GxpEvidence[];
  overridden: boolean; override_reason?: string; override_by?: string;
  readiness: number | null; runtime_hits: number; loc: number;
  gaps: string[]; cluster_id: string | null;
}

export interface GxpResponse {
  summary: NonNullable<ProjectSummary["gxp"]>;
  components: GxpComponent[];
  tables: {
    node_id: string; name: string; regulated: boolean;
    tier: Tier; tags: string[]; gaps: string[]; columns: string[];
  }[];
  gaps: Gap[];
  tag_definitions: Record<string, { title: string; clause: string; meaning: string }>;
  rules_version: string;
  overrides: {
    id: string; node_id: string; old_tier: Tier; new_tier: Tier;
    reason: string; user: string; ts: string;
  }[];
  override_rate: number;
}

export interface Deduction {
  check: string; title: string; weight: number; severity: number;
  points: number; detail: string; remediation: string;
  evidence_node_ids: string[]; evidence_count: number;
}

export interface ReadinessScore {
  node_id: string; fqn: string; name?: string;
  readiness: number; gxp_tier: Tier; loc: number;
  cluster_id?: string | null; runtime_hits?: number;
  deductions: Deduction[]; total_deducted: number;
}

export interface Opportunity {
  kind: "dead_code" | "duplicate_logic" | "quick_win";
  title: string; detail: string; node_ids: string[]; value: number;
}

export interface ReadinessResponse {
  summary: NonNullable<ProjectSummary["readiness"]>;
  scores: ReadinessScore[];
  weights: Record<string, number>;
  check_titles: Record<string, string>;
  context: Record<string, unknown>;
  opportunities: Opportunity[];
  formula: string;
}

export interface ClusterMember {
  node_id: string; name: string; fqn: string;
  gxp_tier: Tier; readiness: number | null; loc: number; runtime_hits: number;
}

export interface Cluster {
  cluster_id: string; name: string; size: number;
  gxp_max: Tier; gxp_counts: Record<Tier, number>;
  readiness_avg: number; loc: number; runtime_hits: number;
  has_endpoints: boolean; tables: string[]; regulated_tables: string[];
  members: ClusterMember[];
}

export interface DecompositionResponse {
  variant: string; applied_variant: string; note: string;
  clusters: Cluster[];
  comparison: { headline: Headline; deltas: Record<string, Delta> };
  table: MetricTable;
  signals: { available: Record<string, boolean>; weights: Record<string, number> };
}

export interface Decision {
  id: string; cluster_id: string;
  cluster_name: string; cluster_size: number;
  cluster_gxp_max: Tier; cluster_readiness: number;
  status: "Proposed" | "Approved" | "Rejected";
  strategy: Strategy;
  target_pattern: string[]; target_services: string[];
  confidence: number; rationale: string; risks: string[];
  dissent: { agent: string; position: string; reason: string }[];
  evidence_node_ids: string[];
  evidence: { node_id: string; name: string; kind: string; gxpTier: Tier }[];
  effort_weeks: [number, number, number];
  provenance: {
    model_id: string; generator: string; prompt_hash: string;
    input_hash: string; temperature: number; prompt_version: string;
  };
  created_at: string | null;
  approvals: { id: string; action: string; comment: string; user: string; ts: string }[];
  transcript_length: number;
}

export interface DecisionsResponse {
  decisions: Decision[];
  counts: Record<string, number>;
  override_rate: number | null;
  strategies: Record<string, number>;
}

export interface Task {
  id: string; name: string; detail: string;
  cluster_id: string; strategy: string; tier: Tier;
  is_foundation: boolean; is_cutover: boolean; depends_on: string[];
  weeks: number; pert: [number, number, number];
  start_week: number; end_week: number; wave: number; squad: number;
  risk: number; start_date: string; end_date: string;
}

export interface Wave {
  wave: number; title: string; task_count: number;
  tasks: string[]; task_names: string[];
  start_week: number; end_week: number;
  start_date: string; end_date: string;
  high_cutovers: number; tier_counts: Record<Tier, number>;
  total_weeks: number;
}

export interface Schedule {
  tasks: Task[]; waves: Wave[];
  makespan_weeks: number; makespan_months: number;
  solver: string; status: string; objective: number | null;
  critical_path: string[];
  freeze_windows: { name: string; start_week: number; end_week: number }[];
  squads: number; start_date: string; end_date: string;
  violations: string[]; solve_seconds: number;
}

export interface MonteCarlo {
  runs: number; seed: number;
  percentiles: Record<string, number>;
  dates: Record<string, string>;
  histogram: {
    week_from: number; week_to: number; week_mid: number;
    count: number; share: number; cumulative: number;
  }[];
  tornado: {
    id: string; name: string; tier: Tier;
    correlation: number; swing_weeks: number; spread_weeks: number;
  }[];
  target_date: string | null;
  probability_by_target: number | null;
  deterministic_weeks: number;
  mean_weeks: number; std_weeks: number;
  task_stats: {
    id: string; name: string; tier: Tier; pert: number[];
    mean_weeks: number; p80_weeks: number;
    finish_p50: number; finish_p80: number; on_critical_path: boolean;
  }[];
  start_date: string;
  distribution: string;
}

export interface RoadmapResponse {
  id: string; schedule: Schedule; montecarlo: MonteCarlo;
  inputs: Record<string, unknown>; created_at: string | null;
}

export interface WhatIfResponse {
  schedule: Schedule;
  montecarlo: MonteCarlo;
  baseline: {
    makespan_weeks: number | null; p50: number | null;
    p80: number | null; p95: number | null;
    p80_date: string | null; squads: number | null;
  };
  delta: { makespan_weeks: number; p80_weeks: number };
  inputs: Record<string, unknown>;
}

export interface EvidencePackRow {
  id: string; wave: number; created_at: string | null;
  meta: Record<string, unknown>;
  exists: boolean; size_kb: number | null;
  pdf_url: string; preview_url: string;
}

export interface AuditRow {
  id: number; ts: string; actor: string; action: string;
  entity: string; entity_id: string;
  payload: Record<string, unknown>;
  prev_hash: string; hash: string;
}

export interface AuditResponse {
  rows: AuditRow[];
  total: number;
  chain: {
    valid: boolean | null; rows?: number;
    broken_at: number | null; detail: string; head?: string;
  };
  actions: string[];
}

export interface AskResponse {
  question: string; answer: string;
  evidence_node_ids: string[];
  evidence: { node_id: string; kind: string; name: string; gxpTier: Tier; readiness: number | null }[];
  templates_used: string[];
  queries: { template_id: string; cypher: string; params: Record<string, unknown>; row_count: number }[];
  confidence: number; missing: string; reasoning: string;
  generator: string; model_id: string;
}

export interface NodeDetail {
  node: Record<string, unknown>;
  methods: {
    id: string; name: string; signature: string; returnType: string;
    loc: number; complexity: number; gxpTier: Tier; gxpTags: string[];
    runtimeHits: number; meanLatencyMs?: number; annotations: string[];
    isScheduled?: boolean; isTransactional?: boolean; isSecured?: boolean;
    usesLocalFile?: boolean; usesNewDate?: boolean; usesHttpSession?: boolean;
    sql: string[]; reads: string[]; writes: string[];
    startLine: number; endLine: number;
  }[];
  tables: {
    writes: { id: string; name: string; regulated: boolean }[];
    reads: { id: string; name: string; regulated: boolean }[];
  };
  endpoints: Record<string, unknown>[];
  depends_on: { id: string; name: string; gxpTier: Tier; readiness: number | null }[];
  depended_on_by: { id: string; name: string; gxpTier: Tier; readiness: number | null }[];
  co_changes: { id: string; name: string; weight: number }[];
  use_cases: { name: string; hits: number }[];
  blast_radius: { id: string; fqn: string; gxpTier: Tier; hops: number }[];
  gxp_evidence: GxpEvidence[];
  readiness_deductions: Deduction[];
  cluster: Record<string, unknown> | null;
}

export interface QueryTemplate {
  id: string; description: string;
  params: Record<string, string>; cypher: string;
}

// =============================================================================
// Calls
// =============================================================================

export const Api = {
  health: () => api.get<Health>("/health").then((r) => r.data),
  users: () => api.get<User[]>("/users").then((r) => r.data),

  projects: () => api.get<Project[]>("/projects").then((r) => r.data),
  project: (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data),
  createProject: (body: {
    name: string; repo_url?: string; source_path?: string;
    target_cloud: string; use_runtime_traces: boolean; created_by?: string;
  }) => api.post<Project>("/projects", body).then((r) => r.data),
  uploadProject: (form: FormData) =>
    api.post<Project>("/projects/upload", form).then((r) => r.data),
  deleteProject: (id: string) => api.delete(`/projects/${id}`),

  analyze: (id: string, body?: Record<string, unknown>) =>
    api.post<JobAccepted>(`/projects/${id}/analyze`, body ?? {}).then((r) => r.data),

  job: (jobId: string) => api.get<Job>(`/jobs/${jobId}`).then((r) => r.data),
  jobs: (id: string) => api.get<JobBrief[]>(`/projects/${id}/jobs`).then((r) => r.data),

  twinGraph: (id: string, params: Record<string, string | boolean | undefined>) =>
    api.get<TwinGraph>(`/projects/${id}/twin/graph`, { params }).then((r) => r.data),
  nodeDetail: (id: string, nodeId: string) =>
    api.get<NodeDetail>(`/projects/${id}/twin/node/${encodeURIComponent(nodeId)}`)
      .then((r) => r.data),
  diagrams: (id: string, module?: string) =>
    api.get<Partial<Diagrams>>(`/projects/${id}/twin/diagrams`, { params: { module } })
      .then((r) => r.data),
  templates: (id: string) =>
    api.get<{ templates: QueryTemplate[]; note: string }>(`/projects/${id}/twin/templates`)
      .then((r) => r.data),
  runQuery: (id: string, template_id: string, params: Record<string, unknown>) =>
    api.post<{ rows: Record<string, unknown>[]; cypher: string; row_count: number; error?: string }>(
      `/projects/${id}/twin/query`, { template_id, params }).then((r) => r.data),
  ask: (id: string, question: string) =>
    api.post<AskResponse>(`/projects/${id}/twin/ask`, { question }).then((r) => r.data),

  gxp: (id: string) => api.get<GxpResponse>(`/projects/${id}/gxp`).then((r) => r.data),
  overrideTier: (id: string, nodeId: string, body: { new_tier: Tier; reason: string; user_id: string }) =>
    api.patch(`/projects/${id}/gxp/${encodeURIComponent(nodeId)}`, body).then((r) => r.data),

  readiness: (id: string) =>
    api.get<ReadinessResponse>(`/projects/${id}/readiness`).then((r) => r.data),

  decomposition: (id: string, variant = "modernrx") =>
    api.get<DecompositionResponse>(`/projects/${id}/decomposition`, { params: { variant } })
      .then((r) => r.data),
  decompose: (id: string, body: Record<string, unknown>) =>
    api.post<JobAccepted>(`/projects/${id}/decompose`, body).then((r) => r.data),

  runCouncil: (id: string, cluster_ids?: string[]) =>
    api.post<JobAccepted>(`/projects/${id}/council/run`, { cluster_ids }).then((r) => r.data),
  decisions: (id: string) =>
    api.get<DecisionsResponse>(`/projects/${id}/council/decisions`).then((r) => r.data),
  transcript: (decisionId: string) =>
    api.get<{ transcript: JobEvent[]; decision: Decision; provenance: Record<string, unknown> }>(
      `/decisions/${decisionId}/transcript`).then((r) => r.data),
  approve: (decisionId: string, body: { user_id: string; comment: string }) =>
    api.post(`/decisions/${decisionId}/approve`, body).then((r) => r.data),
  reject: (decisionId: string, body: { user_id: string; comment: string }) =>
    api.post(`/decisions/${decisionId}/reject`, body).then((r) => r.data),

  runRoadmap: (id: string, body: Record<string, unknown>) =>
    api.post<JobAccepted>(`/projects/${id}/roadmap`, body).then((r) => r.data),
  roadmap: (id: string) =>
    api.get<RoadmapResponse>(`/projects/${id}/roadmap`).then((r) => r.data),
  whatif: (id: string, body: Record<string, unknown>) =>
    api.post<WhatIfResponse>(`/projects/${id}/roadmap/whatif`, body).then((r) => r.data),

  runEvidence: (id: string, wave: number) =>
    api.post<JobAccepted>(`/projects/${id}/evidence/${wave}`, {}).then((r) => r.data),
  evidencePacks: (id: string) =>
    api.get<EvidencePackRow[]>(`/projects/${id}/evidence`).then((r) => r.data),

  audit: (params: Record<string, string | number | boolean | undefined>) =>
    api.get<AuditResponse>("/audit", { params }).then((r) => r.data),
  verifyChain: () => api.post<AuditResponse["chain"]>("/audit/verify").then((r) => r.data),
};

/** Open the job WebSocket. Falls back to polling if the socket cannot connect. */
export function openJobSocket(
  jobId: string,
  onEvent: (e: JobEvent) => void,
  onClose?: () => void,
): () => void {
  let closed = false;
  let poll: ReturnType<typeof setInterval> | null = null;

  const startPolling = () => {
    if (poll || closed) return;
    poll = setInterval(async () => {
      try {
        const job = await Api.job(jobId);
        onEvent({ type: "snapshot", status: job.status, progress: job.progress, step: job.step });
        if (job.status === "succeeded" || job.status === "failed") {
          onEvent({ type: "status", status: job.status, error: job.error, final: true });
          stop();
        }
      } catch {
        /* keep trying: the backend may be restarting */
      }
    }, 1200);
  };

  const stop = () => {
    closed = true;
    if (poll) clearInterval(poll);
    poll = null;
    onClose?.();
  };

  let ws: WebSocket | null = null;
  try {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${window.location.host}/api/ws/jobs/${jobId}`);
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data) as JobEvent);
      } catch {
        /* ignore a malformed frame rather than tearing down the stream */
      }
    };
    ws.onerror = () => startPolling();
    ws.onclose = () => {
      if (!closed) startPolling();
    };
  } catch {
    startPolling();
  }

  return () => {
    closed = true;
    if (poll) clearInterval(poll);
    try {
      ws?.close();
    } catch {
      /* already closed */
    }
  };
}
