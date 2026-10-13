"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarRange, FileCheck2, GitFork, LayoutDashboard, MessagesSquare,
  Network, ScrollText, ShieldAlert, Gauge, ChevronLeft, MessageCircleQuestion,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import React from "react";
import { Api } from "@/lib/api";
import { cn, duration } from "@/lib/format";
import { useApp } from "@/lib/store";
import { AskTwin } from "@/components/AskTwin";

const NAV = [
  { slug: "overview", label: "Overview", Icon: LayoutDashboard, engine: null },
  { slug: "twin", label: "Twin graph", Icon: Network, engine: 1 },
  { slug: "gxp", label: "GxP heatmap", Icon: ShieldAlert, engine: 2 },
  { slug: "readiness", label: "Readiness", Icon: Gauge, engine: 3 },
  { slug: "decomposition", label: "Decomposition", Icon: GitFork, engine: 4 },
  { slug: "council", label: "Council", Icon: MessagesSquare, engine: 5 },
  { slug: "roadmap", label: "Roadmap", Icon: CalendarRange, engine: 6 },
  { slug: "evidence", label: "Evidence", Icon: FileCheck2, engine: 7 },
  { slug: "audit", label: "Audit", Icon: ScrollText, engine: null },
] as const;

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const pathname = usePathname();
  const { chatOpen, setChatOpen } = useApp();

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () => Api.project(id),
    refetchInterval: (q) => (q.state.data?.status === "analyzing" ? 2000 : 20_000),
  });

  const p = project.data;
  const counts = p?.counts;

  return (
    <div className="flex flex-col gap-5 lg:flex-row">
      {/* ------------------------------------------------------------- nav */}
      <nav className="shrink-0 lg:w-56" aria-label="Assessment sections">
        <Link href="/" className="btn-ghost mb-2.5 w-full justify-start px-2.5 py-2 text-xs font-semibold rounded-lg focus-visible:ring-2 focus-visible:ring-accent/40">
          <ChevronLeft className="h-4 w-4" /> All assessments
        </Link>

        <div className="card mb-3 p-3.5 border-line shadow-sm">
          <p className="truncate text-sm font-bold leading-tight" title={p?.name}>
            {p?.name ?? "Loading..."}
          </p>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-2xs text-muted">
            <span className="font-medium text-ink/80">{p?.target_cloud}</span>
            {p?.summary?.assessment_seconds != null && (
              <>
                <span className="text-faint">&middot;</span>
                <span className="tabular-nums">{duration(p.summary.assessment_seconds)}</span>
              </>
            )}
          </p>
          {p?.status === "analyzing" && (
            <p className="mt-2.5 flex items-center gap-1.5 text-2xs font-semibold text-accent">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
              analysing
            </p>
          )}
        </div>

        <ul className="card overflow-hidden border-line shadow-sm divide-y divide-line/30">
          {NAV.map(({ slug, label, Icon, engine }) => {
            const href = `/projects/${id}/${slug}`;
            const active = pathname === href;
            const badge =
              slug === "council" && counts?.decisions
                ? `${counts.approved}/${counts.decisions}`
                : slug === "evidence" && counts?.evidence_packs
                ? String(counts.evidence_packs)
                : undefined;
            return (
              <li key={slug}>
                <Link href={href}
                  className={cn(
                    "flex items-center gap-2.5 border-l-[3px] px-3.5 py-2.5 text-xs font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
                    active
                      ? "border-l-accent bg-accent-soft/75 text-accent font-semibold"
                      : "border-l-transparent text-muted hover:bg-raised/80 hover:text-ink",
                  )}>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                  {engine && (
                    <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[0.5625rem] font-bold tabular-nums",
                      active ? "bg-accent/15 text-accent" : "bg-raised text-faint")}
                      title={`Engine ${engine}`}>
                      {engine}
                    </span>
                  )}
                  {badge && (
                    <span className="shrink-0 rounded bg-low-soft px-1.5 py-0.5 text-[0.5625rem]
                                     font-bold tabular-nums text-low">
                      {badge}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        <button onClick={() => setChatOpen(true)}
          className="btn-outline mt-3 w-full justify-start py-2.5 px-3 text-xs font-semibold shadow-sm hover:border-accent/40">
          <MessageCircleQuestion className="h-4 w-4 text-accent" /> Ask the Twin
        </button>
      </nav>

      <div className="min-w-0 flex-1">{children}</div>

      <AskTwin projectId={id} open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
