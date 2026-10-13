"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Clock, Cloud, FileCode2, Plus, Trash2, Upload, Zap,
} from "lucide-react";
import Link from "next/link";
import React from "react";
import { Api, apiError, type Project } from "@/lib/api";
import { cn, duration, num, relative, shortDate } from "@/lib/format";
import { useApp } from "@/lib/store";
import {
  Banner, Card, Empty, ErrorNote, Loading, Modal, PageHeader, Spinner, TierBadge,
} from "@/components/ui";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const [wizard, setWizard] = React.useState(false);
  const projects = useQuery({
    queryKey: ["projects"], queryFn: Api.projects, refetchInterval: 5000,
  });
  const health = useQuery({ queryKey: ["health"], queryFn: Api.health });

  const remove = useMutation({
    mutationFn: (id: string) => Api.deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  return (
    <>
      <PageHeader
        kicker="Pharma IT / Cloud"
        title="AI-Powered Application Modernization Advisor"
        subtitle="Legacy pharma applications are difficult to maintain, scale, and migrate. Organizations struggle to assess modernization opportunities and cloud readiness efficiently."
        actions={
          <button onClick={() => setWizard(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New assessment
          </button>
        }
      />

      {/* Core Mission: Objectives & Expected Outcomes Showcase */}
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-line bg-surface/90 p-5 shadow-card">
          <div className="mb-3.5 flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-accent">5 Core Objectives</h3>
            <span className="rounded-full bg-accent/15 px-2.5 py-0.5 text-2xs font-semibold text-accent">Mission</span>
          </div>
          <ol className="space-y-2.5 text-xs text-ink/90">
            <li className="flex items-start gap-2">
              <span className="font-bold text-accent">1.</span>
              <span><strong>Analyze existing architectures:</strong> Parse code, DDL, config & runtime calls into a queryable Living Twin.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-accent">2.</span>
              <span><strong>Evaluate cloud readiness:</strong> Score components across 11 architectural & 12-factor dimensions.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-accent">3.</span>
              <span><strong>Identify modernization risks:</strong> Tag GxP regulatory criticality & flag dead code quick wins.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-accent">4.</span>
              <span><strong>Recommend target architecture:</strong> Propose bounded contexts (Strangler Fig, Event-Driven, Microservices).</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-accent">5.</span>
              <span><strong>Generate migration roadmaps:</strong> Optimize wave schedules with GxP freeze windows & Monte Carlo simulations.</span>
            </li>
          </ol>
        </div>

        <div className="rounded-xl border border-line bg-surface/90 p-5 shadow-card">
          <div className="mb-3.5 flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-low">5 Expected Outcomes</h3>
            <span className="rounded-full bg-low/15 px-2.5 py-0.5 text-2xs font-semibold text-low">Target Impact</span>
          </div>
          <ul className="space-y-2.5 text-xs text-ink/90">
            <li className="flex items-center gap-2">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-low/15 text-xs font-bold text-low">⚡</span>
              <span><strong>1. Faster architecture assessments:</strong> Automated repository analysis in seconds.</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-low/15 text-xs font-bold text-low">🧭</span>
              <span><strong>2. Clear migration strategy:</strong> 7R recommendations with PERT effort estimates.</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-low/15 text-xs font-bold text-low">🛡️</span>
              <span><strong>3. Reduced transformation risk:</strong> Blast-radius optimization cuts re-validation scope.</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-low/15 text-xs font-bold text-low">📈</span>
              <span><strong>4. Improved scalability & maintainability:</strong> Lower inter-service coupling & modularity.</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-low/15 text-xs font-bold text-low">☁️</span>
              <span><strong>5. Accelerated cloud adoption:</strong> Actionable wave roadmap with FDA CSA assurance evidence.</span>
            </li>
          </ul>
        </div>
      </div>

      {projects.isLoading && <Loading label="Loading assessments" />}
      {projects.isError && (
        <ErrorNote error={apiError(projects.error)} retry={() => projects.refetch()} />
      )}

      {projects.data?.length === 0 && (
        <Empty
          icon={<FileCode2 className="h-7 w-7" />}
          title="No assessments yet"
          hint={
            <>
              Start one from a Git URL, a local path, or a zip upload. The demo
              application <code className="mono">AcmeLIMS</code> is seeded by
              running <code className="mono">python -m app.seed</code> in the
              backend directory.
            </>
          }
          action={
            <button onClick={() => setWizard(true)} className="btn-primary">
              <Plus className="h-4 w-4" /> New assessment
            </button>
          }
        />
      )}

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {projects.data?.map((p) => (
          <ProjectCard key={p.id} project={p}
            onDelete={() => {
              if (confirm(`Delete the assessment "${p.name}"? The audit log keeps a record of the deletion.`)) {
                remove.mutate(p.id);
              }
            }} />
        ))}
      </div>

      <NewAssessment open={wizard} onClose={() => setWizard(false)} />
    </>
  );
}

function ProjectCard({ project: p, onDelete }: { project: Project; onDelete: () => void }) {
  const s = p.summary ?? {};
  const gxp = s.gxp?.class_tier_counts;
  const head = s.decomposition?.comparison?.headline;
  const running = p.status === "analyzing";

  return (
    <article className="card group flex flex-col overflow-hidden border-line transition-all duration-200 hover:shadow-pop">
      <div className="flex items-start justify-between gap-3 border-b border-line bg-surface/80 p-5 pb-4">
        <div className="min-w-0">
          <Link href={`/projects/${p.id}/overview`}
            className="block truncate text-base font-bold tracking-tight hover:text-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 rounded">
            {p.name}
          </Link>
          <p className="mt-0.5 flex items-center gap-2 text-2xs text-muted">
            <Cloud className="h-3 w-3" /> {p.target_cloud}
            <span className="text-faint">&middot;</span>
            created {shortDate(p.created_at)}
          </p>
        </div>
        <span className={cn("chip shrink-0 px-2.5 py-1 shadow-2xs",
          running ? "border-accent/35 bg-accent-soft text-accent"
            : p.has_twin ? "border-low/35 bg-low-soft text-low"
            : "border-line bg-raised text-muted")}>
          {running && <Spinner className="h-2.5 w-2.5" />}
          {running ? "analysing" : p.status}
        </span>
      </div>

      {p.has_twin ? (
        <div className="flex-1 space-y-3.5 p-5">
          <div className="grid grid-cols-3 gap-2.5 text-center">
            <Stat label="LOC" value={num(s.loc)} />
            <Stat label="Components" value={num(s.components)} />
            <Stat label="Services" value={num(s.decomposition?.clusters)} />
          </div>

          {gxp && (
            <div>
              <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wider text-muted">
                GxP criticality
              </p>
              <div className="flex h-2 overflow-hidden rounded-full bg-raised border border-line/40">
                {(["HIGH", "MEDIUM", "LOW"] as const).map((t) => {
                  const total = gxp.HIGH + gxp.MEDIUM + gxp.LOW || 1;
                  return (
                    <div key={t} title={`${t}: ${gxp[t]} components`}
                      className={{ HIGH: "bg-high", MEDIUM: "bg-medium", LOW: "bg-low" }[t]}
                      style={{ width: `${(gxp[t] / total) * 100}%` }} />
                  );
                })}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {(["HIGH", "MEDIUM", "LOW"] as const).map((t) => (
                  <TierBadge key={t} tier={t} size="xs"
                    title={`${gxp[t]} ${t}-tier components`} />
                ))}
                <span className="ml-auto text-2xs tabular-nums text-muted font-medium">
                  {gxp.HIGH} / {gxp.MEDIUM} / {gxp.LOW}
                </span>
              </div>
            </div>
          )}

          {head?.reval_scope_reduction_pct != null && (
            <div className="rounded-lg border border-accent/35 bg-accent-soft/70 px-3.5 py-2.5 shadow-2xs">
              <p className="text-2xs font-bold uppercase tracking-wider text-accent">
                Re-validation scope
              </p>
              <p className="mt-0.5 text-sm font-extrabold text-accent">
                {head.reval_scope_before.toFixed(0)}% &rarr;{" "}
                {head.reval_scope_after.toFixed(0)}%
                <span className="ml-1.5 text-xs font-semibold">
                  ({head.reval_scope_reduction_pct > 0 ? "-" : "+"}
                  {Math.abs(head.reval_scope_reduction_pct).toFixed(0)}%)
                </span>
              </p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-2xs text-muted pt-1">
            {s.assessment_seconds != null && (
              <span className="flex items-center gap-1 font-medium">
                <Clock className="h-3 w-3 text-faint" /> assessed in {duration(s.assessment_seconds)}
              </span>
            )}
            {p.counts.decisions > 0 && (
              <span>{p.counts.approved}/{p.counts.decisions} decisions approved</span>
            )}
            {p.counts.evidence_packs > 0 && (
              <span>{p.counts.evidence_packs} evidence pack(s)</span>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 p-5">
          <p className="text-xs leading-relaxed text-muted">
            {running
              ? "Analysis in progress - the twin, GxP scan, readiness scores and decomposition are being built."
              : "Not analysed yet. Open the assessment and run the analysis to build the architecture twin."}
          </p>
          <p className="mono mt-3 truncate text-2xs text-faint">
            {p.repo_url || p.source_path || "no source configured"}
          </p>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 border-t border-line bg-raised/50 px-5 py-3">
        <button onClick={onDelete}
          className="btn-ghost p-2 rounded-lg text-faint opacity-80 sm:opacity-0 transition-all
                     hover:text-high hover:bg-high-soft focus-visible:opacity-100 min-h-[38px] min-w-[38px] flex items-center justify-center group-hover:opacity-100"
          aria-label={`Delete ${p.name}`}>
          <Trash2 className="h-4 w-4" />
        </button>
        <Link href={`/projects/${p.id}/overview`} className="btn-outline py-2 px-3 text-xs font-semibold shadow-sm min-h-[38px]">
          {p.has_twin ? "Open" : "Analyse"} <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-raised/80 border border-line/40 px-2.5 py-2.5">
      <div className="text-sm font-bold tabular-nums leading-none">{value}</div>
      <div className="mt-1 text-[0.625rem] font-semibold uppercase tracking-wider text-muted">{label}</div>
    </div>
  );
}

// =============================================================================
// New assessment wizard
// =============================================================================

function NewAssessment({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const user = useApp((s) => s.currentUser);
  const [mode, setMode] = React.useState<"path" | "repo" | "zip">("path");
  const [name, setName] = React.useState("");
  const [value, setValue] = React.useState("");
  const [cloud, setCloud] = React.useState("AWS");
  const [traces, setTraces] = React.useState(true);
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setName(""); setValue(""); setFile(null); setError(""); setMode("path");
    }
  }, [open]);

  const create = useMutation({
    mutationFn: async () => {
      if (mode === "zip") {
        if (!file) throw new Error("Choose a .zip archive of the repository");
        const form = new FormData();
        form.append("name", name.trim());
        form.append("target_cloud", cloud);
        form.append("use_runtime_traces", String(traces));
        form.append("created_by", user?.id ?? "");
        form.append("file", file);
        return Api.uploadProject(form);
      }
      return Api.createProject({
        name: name.trim(),
        repo_url: mode === "repo" ? value.trim() : "",
        source_path: mode === "path" ? value.trim() : "",
        target_cloud: cloud,
        use_runtime_traces: traces,
        created_by: user?.id ?? "",
      });
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      window.location.href = `/projects/${p.id}/overview?autostart=1`;
    },
    onError: (e) => setError(apiError(e)),
  });

  const ready = name.trim().length > 1 && (mode === "zip" ? !!file : value.trim().length > 2);

  return (
    <Modal open={open} onClose={onClose} title="New assessment" wide
      footer={
        <>
          <button onClick={onClose} className="btn-outline">Cancel</button>
          <button className="btn-primary" disabled={!ready || create.isPending}
            onClick={() => { setError(""); create.mutate(); }}>
            {create.isPending ? <Spinner /> : <Zap className="h-4 w-4" />}
            Create and analyse
          </button>
        </>
      }>
      <div className="space-y-5">
        <div>
          <label className="label" htmlFor="asm-name">Assessment name</label>
          <input id="asm-name" className="input" value={name} autoFocus
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. AcmeLIMS - cloud readiness" />
        </div>

        <div>
          <span className="label">Source</span>
          <div className="mb-3 flex gap-1 rounded-lg border bg-raised p-1">
            {([
              ["path", "Local path"],
              ["repo", "Git URL"],
              ["zip", "Zip upload"],
            ] as const).map(([m, label]) => (
              <button key={m} onClick={() => setMode(m)}
                className={cn("flex-1 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                  mode === m ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
                {label}
              </button>
            ))}
          </div>

          {mode === "path" && (
            <>
              <input className="input" value={value} onChange={(e) => setValue(e.target.value)}
                placeholder="C:\\path\\to\\repository" />
              <p className="mt-1.5 text-2xs text-muted">
                A folder on the machine running the backend. Nothing is copied or
                uploaded - the analysis reads it in place.
              </p>
            </>
          )}
          {mode === "repo" && (
            <>
              <input className="input" value={value} onChange={(e) => setValue(e.target.value)}
                placeholder="https://github.com/org/repo.git" />
              <p className="mt-1.5 text-2xs text-muted">
                Shallow-cloned with the last 50 commits, which is what the
                co-change coupling signal needs.
              </p>
            </>
          )}
          {mode === "zip" && (
            <>
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border
                                border-dashed px-4 py-6 hover:bg-raised">
                <Upload className="h-5 w-5 shrink-0 text-faint" />
                <span className="min-w-0 text-xs">
                  <span className="block font-semibold">
                    {file ? file.name : "Choose a .zip archive"}
                  </span>
                  <span className="block text-muted">
                    {file
                      ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
                      : "Up to 200 MB. Archive entries with absolute or ../ paths are rejected."}
                  </span>
                </span>
                <input type="file" accept=".zip" className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
            </>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="asm-cloud">Target cloud</label>
            <select id="asm-cloud" className="input" value={cloud}
              onChange={(e) => setCloud(e.target.value)}>
              <option value="AWS">AWS</option>
              <option value="Azure">Azure</option>
              <option value="GCP">Google Cloud</option>
            </select>
            <p className="mt-1.5 text-2xs text-muted">
              The Council stays cloud-agnostic on patterns and names concrete
              services for this cloud.
            </p>
          </div>
          <div>
            <span className="label">Runtime traces</span>
            <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5">
              <input type="checkbox" checked={traces} className="mt-0.5"
                onChange={(e) => setTraces(e.target.checked)} />
              <span className="text-xs leading-snug">
                <span className="block font-semibold">Ingest OpenTelemetry traces</span>
                <span className="block text-muted">
                  Uses an exported trace file if one is present. Gives real call
                  frequency and use-case membership.
                </span>
              </span>
            </label>
          </div>
        </div>

        {error && <ErrorNote error={error} />}
      </div>
    </Modal>
  );
}
