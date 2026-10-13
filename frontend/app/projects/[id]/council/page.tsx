"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Bot, Check, CheckCircle2, ChevronDown, Clock,
  FileCheck2, GitBranch, Layers, MessageSquare, MessagesSquare, Play,
  RefreshCw, ShieldAlert, UserCheck, UserRound, Users, X, XCircle,
} from "lucide-react";
import { useParams } from "next/navigation";
import React from "react";
import { Api, apiError, type Decision, type DecisionsResponse, type JobEvent, type Tier } from "@/lib/api";
import { cn, num, pct, simple, weeks } from "@/lib/format";
import { useApp } from "@/lib/store";
import { useJob } from "@/lib/useJob";
import {
  Banner, Card, Drawer, Empty, ErrorNote, Kpi, Loading, Modal,
  PageHeader, ProgressBar, Spinner, StrategyBadge, TierBadge,
} from "@/components/ui";

const AGENT_ROLES = [
  {
    name: "Cloud Architect",
    role: "Scalability & Managed Services",
    code: "ARCH",
    focus: "Containerization, event-driven queues, serverless, Strangler Fig facades",
  },
  {
    name: "QA & Validation Lead",
    role: "Data Integrity & CSA Assurance",
    code: "QA",
    focus: "Minimizing re-validation scope, Part 11 electronic records, risk scaling",
  },
  {
    name: "Security Officer",
    role: "Zero Trust & IAM Compliance",
    code: "SEC",
    focus: "Secret rotation, RBAC role tables, encrypted audit trails, network isolation",
  },
  {
    name: "FinOps Analyst",
    role: "Cloud Cost & Modernization ROI",
    code: "FIN",
    focus: "Rehosting quick wins, eliminating dead code licensing, managed DB TCO",
  },
  {
    name: "Regulatory Affairs",
    role: "Part 11 / Annex 11 Oversight",
    code: "REG",
    focus: "Cloud vendor qualification, data residency, software assurance traceability",
  },
  {
    name: "Moderator (Chair)",
    role: "Consensus Synthesis & Dissent Record",
    code: "MOD",
    focus: "Forces evidence citation, synthesizes majority verdict, records dissent",
  },
];

export default function CouncilPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { currentUser } = useApp();

  const [transcriptDecision, setTranscriptDecision] = React.useState<Decision | null>(null);

  // Approval/Rejection action state
  const [approvalModal, setApprovalModal] = React.useState<{
    decision: Decision;
    action: "approve" | "reject";
  } | null>(null);
  const [actionComment, setActionComment] = React.useState("");

  const job = useJob([["decisions", id], ["project", id]]);

  const decisionsQuery = useQuery({
    queryKey: ["decisions", id],
    queryFn: () => Api.decisions(id),
  });

  const transcriptQuery = useQuery({
    queryKey: ["transcript", transcriptDecision?.id],
    queryFn: () => (transcriptDecision ? Api.transcript(transcriptDecision.id) : null),
    enabled: Boolean(transcriptDecision),
  });

  const startCouncil = async () => {
    try {
      const { job_id } = await Api.runCouncil(id);
      job.attach(job_id);
    } catch (e) {
      alert(apiError(e));
    }
  };

  const approveMutation = useMutation({
    mutationFn: (data: { decisionId: string; comment: string }) =>
      Api.approve(data.decisionId, {
        user_id: currentUser?.id || "user-architect",
        comment: data.comment,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["decisions", id] });
      setApprovalModal(null);
      setActionComment("");
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (data: { decisionId: string; comment: string }) =>
      Api.reject(data.decisionId, {
        user_id: currentUser?.id || "user-architect",
        comment: data.comment,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["decisions", id] });
      setApprovalModal(null);
      setActionComment("");
    },
  });

  if (decisionsQuery.isLoading) {
    return <Loading label="Loading AI Architecture Council decisions" rows={5} />;
  }
  if (decisionsQuery.error) {
    return <ErrorNote error={apiError(decisionsQuery.error)} retry={() => decisionsQuery.refetch()} />;
  }

  const data = decisionsQuery.data!;
  const counts = data.counts || {};
  const isRunning = job.busy;

  return (
    <div className="space-y-5">
      <PageHeader
        kicker="Engine 5 — Multi-Agent Deliberation"
        title="AI Architecture Council"
        subtitle="A committee of 5 specialized agents debate cloud-native patterns vs. GxP validation drag. Decisions remain 'Proposed' until approved by an authorized human reviewer."
        actions={
          <button
            onClick={startCouncil}
            disabled={isRunning}
            className="btn-primary text-xs"
          >
            {isRunning ? <Spinner className="text-white" /> : <Play className="h-3.5 w-3.5" />}
            {data.decisions.length > 0 ? "Re-Run Architecture Council" : "Run Architecture Council"}
          </button>
        }
      />

      {/* Live Debate Progress */}
      {isRunning && (
        <Card title="Architecture Council Deliberation in Progress" subtitle={job.step || "debating..."}>
          <ProgressBar value={job.progress} label={job.step} status={job.status} />

          {job.events.length > 0 && (
            <div className="mt-4 max-h-56 space-y-2 overflow-y-auto rounded-lg border bg-raised/40 p-3 text-xs">
              {job.events.slice(-20).map((e, idx) => (
                <div key={idx} className="flex items-start gap-2 text-2xs">
                  <span className="mono font-bold text-accent shrink-0">
                    {e.agent || e.type?.toUpperCase()}
                  </span>
                  <span className="text-ink">{e.text || e.position || e.step || ""}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Kpi
          label="Total Decisions"
          value={num(data.decisions.length)}
          hint="One 7R strategy per microservice cluster"
          icon={<MessagesSquare className="h-4 w-4" />}
        />
        <Kpi
          label="Approved Decisions"
          value={num(counts.approved ?? 0)}
          tone="low"
          hint="Signed off with human audit trail"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <Kpi
          label="Needs Review"
          value={num(counts.proposed ?? data.decisions.filter((d) => d.status === "Proposed").length)}
          tone="medium"
          hint="Pending QA approval"
          icon={<Clock className="h-4 w-4" />}
        />
        <Kpi
          label="Rejected Decisions"
          value={num(counts.rejected ?? 0)}
          tone="high"
          hint="Sent back for re-deliberation"
          icon={<XCircle className="h-4 w-4" />}
        />
        <Kpi
          label="Human Rejection Rate"
          value={pct((data.override_rate ?? 0) * 100, 1)}
          hint="Monitored for Annex 22 compliance"
          icon={<UserCheck className="h-4 w-4" />}
        />
        <Kpi
          label="Active Squads"
          value="3"
          hint="Feeds OR-Tools wave scheduler"
          icon={<Users className="h-4 w-4" />}
        />
      </div>

      {/* Agent Committee Roster */}
      <Card
        title="Council Members & Specialized Perspectives"
        subtitle="Each agent operates under strict instructions to prioritize their domain and cite verifiable graph node IDs."
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {AGENT_ROLES.map((agent) => (
            <div key={agent.name} className="rounded-xl border bg-raised/30 p-3.5 space-y-1.5 text-xs">
              <div className="flex items-center gap-2.5">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded border border-line bg-raised font-mono text-2xs font-bold text-accent">
                  {agent.code}
                </span>
                <div>
                  <h4 className="font-bold text-ink">{agent.name}</h4>
                  <span className="text-3xs font-semibold text-accent uppercase tracking-wider block">
                    {agent.role}
                  </span>
                </div>
              </div>
              <p className="text-2xs text-muted leading-relaxed pt-1 border-t border-line/40">
                {agent.focus}
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* ---------------------------------------------------------------- DECISIONS LIST */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-ink">
          Cluster Decisions &amp; Target Architectures ({data.decisions.length})
        </h3>

        {data.decisions.length === 0 && !isRunning && (
          <Empty
            icon={<MessagesSquare className="h-7 w-7" />}
            title="No Council Decisions Generated Yet"
            hint="Run the Architecture Council to have the 5 specialist agents evaluate each decomposed microservice cluster and vote on 7R strategies and target cloud patterns."
            action={
              <button onClick={startCouncil} className="btn-primary text-xs">
                <Play className="h-4 w-4" /> Run Architecture Council
              </button>
            }
          />
        )}

        {data.decisions.map((dec) => (
          <Card
            key={dec.id}
            title={
              <div className="flex flex-wrap items-center gap-2">
                <StrategyBadge strategy={dec.strategy} />
                <span className="font-bold text-sm text-ink">{dec.cluster_name}</span>
                <TierBadge tier={dec.cluster_gxp_max} size="xs" />
                <span className="text-3xs text-muted font-mono bg-raised px-1.5 py-0.5 rounded">
                  {dec.cluster_size} classes &middot; readiness {dec.cluster_readiness?.toFixed(0)}/100
                </span>
              </div>
            }
            actions={
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "chip text-2xs font-semibold uppercase tracking-wider",
                    dec.status === "Approved"
                      ? "border-low/40 bg-low-soft text-low"
                      : dec.status === "Rejected"
                      ? "border-high/40 bg-high-soft text-high"
                      : "border-medium/40 bg-medium-soft text-medium"
                  )}
                >
                  {dec.status}
                </span>

                <button
                  onClick={() => setTranscriptDecision(dec)}
                  className="btn-ghost py-1 px-2 text-2xs text-accent"
                >
                  <MessageSquare className="h-3.5 w-3.5 inline mr-1" /> Debate Transcript
                </button>
              </div>
            }
          >
            <div className="space-y-4 text-xs">
              {/* Target Pattern and Services */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-2xs font-semibold text-muted">Target Patterns:</span>
                {dec.target_pattern.map((p) => (
                  <span key={p} className="chip bg-accent-soft/70 border-accent/30 text-accent font-semibold text-2xs">
                    {p}
                  </span>
                ))}
                <span className="text-faint">|</span>
                <span className="text-2xs font-semibold text-muted">Services:</span>
                {dec.target_services.map((s) => (
                  <span key={s} className="rounded bg-raised px-2 py-0.5 text-3xs font-medium text-ink">
                    {s}
                  </span>
                ))}
              </div>

              {/* Rationale */}
              <div className="rounded-lg border bg-surface p-3.5 space-y-1 shadow-sm">
                <span className="text-2xs font-semibold uppercase tracking-wider text-muted block">
                  Moderator Consensus Rationale:
                </span>
                <p className="text-xs text-ink leading-relaxed">{dec.rationale}</p>
              </div>

              {/* Recorded Dissent */}
              {dec.dissent.length > 0 && (
                <div className="rounded-lg border border-medium/40 bg-medium-soft/30 p-3 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-medium">
                    <AlertTriangle className="h-4 w-4" /> Recorded Agent Dissent (Annex 22 Audit Requirement)
                  </div>
                  {dec.dissent.map((d, i) => (
                    <div key={i} className="text-2xs space-y-0.5">
                      <span className="font-bold text-ink">{d.agent} ({d.position}):</span>{" "}
                      <span className="text-ink/85">{d.reason}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Effort Estimation & Metadata */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 rounded-lg bg-raised/40 p-3 text-2xs">
                <div>
                  <span className="text-muted block">PERT Duration:</span>
                  <span className="font-mono font-bold text-ink">
                    {weeks(dec.effort_weeks[1])} (likely)
                  </span>
                  <span className="text-3xs text-faint block">
                    Range: {dec.effort_weeks[0]}w – {dec.effort_weeks[2]}w
                  </span>
                </div>
                <div>
                  <span className="text-muted block">Model Confidence:</span>
                  <span className="font-mono font-bold text-ink">
                    {(dec.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div>
                  <span className="text-muted block">Model Provenance:</span>
                  <span className="font-mono font-bold text-accent truncate block">
                    {dec.provenance.model_id || "gemini-3.1-flash-lite"}
                  </span>
                </div>
                <div>
                  <span className="text-muted block">Evidence Nodes Cited:</span>
                  <span className="font-mono font-bold text-ink">
                    {dec.evidence_node_ids.length} verified graph nodes
                  </span>
                </div>
              </div>

              {/* Human Approval Gate Actions */}
              <div className="pt-3 border-t border-line/60 flex flex-wrap items-center justify-between gap-3">
                <div className="text-2xs text-muted">
                  {dec.approvals.length > 0 ? (
                    <span className="flex items-center gap-1.5 text-low font-semibold">
                      <Check className="h-4 w-4" /> Reviewed by {dec.approvals[0].user}: &ldquo;{dec.approvals[0].comment}&rdquo;
                    </span>
                  ) : (
                    <span>Awaiting human sign-off before entering wave scheduling.</span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setApprovalModal({ decision: dec, action: "reject" })}
                    disabled={dec.status === "Rejected"}
                    className="btn-outline py-1.5 px-3 text-xs font-semibold text-high min-h-[36px] hover:bg-high-soft hover:border-high/40"
                  >
                    <X className="h-3.5 w-3.5 mr-1 inline" /> Reject
                  </button>
                  <button
                    onClick={() => setApprovalModal({ decision: dec, action: "approve" })}
                    disabled={dec.status === "Approved"}
                    className="btn-primary py-1.5 px-3.5 text-xs font-semibold min-h-[36px]"
                  >
                    <Check className="h-3.5 w-3.5 mr-1 inline" /> Approve Decision
                  </button>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* ---------------------------------------------------------------- APPROVAL MODAL */}
      <Modal
        open={Boolean(approvalModal)}
        onClose={() => setApprovalModal(null)}
        title={
          approvalModal?.action === "approve"
            ? "Approve Modernization Strategy"
            : "Reject & Request Re-deliberation"
        }
        footer={
          <>
            <button onClick={() => setApprovalModal(null)} className="btn-outline text-xs">
              Cancel
            </button>
            <button
              onClick={() => {
                if (!approvalModal) return;
                if (approvalModal.action === "approve") {
                  approveMutation.mutate({
                    decisionId: approvalModal.decision.id,
                    comment: actionComment.trim() || "Approved architectural decision.",
                  });
                } else {
                  rejectMutation.mutate({
                    decisionId: approvalModal.decision.id,
                    comment: actionComment.trim() || "Rejected architectural decision.",
                  });
                }
              }}
              disabled={approveMutation.isPending || rejectMutation.isPending}
              className={cn(
                "text-xs",
                approvalModal?.action === "approve" ? "btn-primary" : "btn-danger"
              )}
            >
              {approveMutation.isPending || rejectMutation.isPending ? (
                <Spinner />
              ) : approvalModal?.action === "approve" ? (
                <Check className="h-3.5 w-3.5 mr-1" />
              ) : (
                <X className="h-3.5 w-3.5 mr-1" />
              )}
              Confirm {approvalModal?.action === "approve" ? "Approval" : "Rejection"}
            </button>
          </>
        }
      >
        <div className="space-y-4 text-xs">
          <p className="text-muted leading-relaxed">
            Cluster: <strong>{approvalModal?.decision.cluster_name}</strong> &middot; Strategy:{" "}
            <strong>{approvalModal?.decision.strategy}</strong>
          </p>

          <div className="p-3 bg-raised/50 rounded-lg">
            <span className="text-2xs text-muted block mb-1">Acting Authorized User:</span>
            <span className="font-bold text-ink">
              {currentUser?.name || "Modernization Lead"} &middot; {currentUser?.role || "Pharma IT Advisor"}
            </span>
          </div>

          <div>
            <label className="text-2xs font-semibold uppercase tracking-wider text-muted block mb-1">
              Reviewer Notes / Sign-off Comment
            </label>
            <textarea
              rows={3}
              value={actionComment}
              onChange={(e) => setActionComment(e.target.value)}
              placeholder="e.g. Concur with Strangler Fig approach. Re-validation scope minimized appropriately..."
              className="input text-xs"
            />
          </div>
        </div>
      </Modal>

      {/* ---------------------------------------------------------------- TRANSCRIPT DRAWER */}
      <Drawer
        open={Boolean(transcriptDecision)}
        onClose={() => setTranscriptDecision(null)}
        width="max-w-2xl"
        title="Architecture Council Debate Transcript"
        subtitle={transcriptDecision?.cluster_name}
      >
        {transcriptQuery.isLoading && <Loading label="Loading transcript events" />}
        {transcriptQuery.error && <ErrorNote error={apiError(transcriptQuery.error)} />}

        {transcriptQuery.data && (
          <div className="space-y-4 p-5 text-xs">
            <div className="space-y-3">
              {transcriptQuery.data.transcript.map((ev, i) => (
                <div key={i} className="rounded-xl border bg-surface p-3.5 space-y-2 shadow-sm">
                  <div className="flex items-center justify-between text-2xs">
                    <span className="font-bold text-accent">{ev.agent || "Agent"}</span>
                    <span className="mono rounded bg-raised px-1.5 py-0.5 text-muted">
                      Round {ev.round ?? 1} &middot; {ev.stage || "debate"}
                    </span>
                  </div>
                  <p className="text-ink leading-relaxed">{ev.text || ev.position}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
