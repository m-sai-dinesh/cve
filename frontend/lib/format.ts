import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Strategy, Tier } from "./api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const num = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined || Number.isNaN(v)
    ? "-"
    : v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const pct = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? "-" : `${v.toFixed(digits)}%`;

/** A 0..1 ratio as a percentage. */
export const ratio = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? "-" : `${(v * 100).toFixed(digits)}%`;

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function weeks(w: number | null | undefined): string {
  if (w === null || w === undefined) return "-";
  const months = w / 4.345;
  return months >= 2 ? `${w.toFixed(0)}w (${months.toFixed(1)} mo)` : `${w.toFixed(0)}w`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "-";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const s = Math.round((Date.now() - then) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/** `com.acme.lims.result.ResultService` -> `ResultService` */
export const simple = (fqn: string | null | undefined): string =>
  (fqn ?? "").split("#")[0].split(".").pop() ?? (fqn ?? "");

/** `class:com.acme...ResultService` -> `ResultService` */
export const nodeLabel = (nodeId: string): string => {
  const body = nodeId.includes(":") ? nodeId.slice(nodeId.indexOf(":") + 1) : nodeId;
  return simple(body) || body;
};

export const TIER_CLASS: Record<Tier, string> = {
  HIGH: "text-high border-high/35 bg-high-soft",
  MEDIUM: "text-medium border-medium/35 bg-medium-soft",
  LOW: "text-low border-low/35 bg-low-soft",
};

export const TIER_DOT: Record<Tier, string> = {
  HIGH: "bg-high",
  MEDIUM: "bg-medium",
  LOW: "bg-low",
};

export const TIER_HEX: Record<Tier, { light: string; dark: string }> = {
  HIGH: { light: "#b91c1c", dark: "#f87171" },
  MEDIUM: { light: "#b45309", dark: "#fbbf24" },
  LOW: { light: "#15803d", dark: "#4ade80" },
};

/**
 * PRD §18: colour must never be the only signal. Every tier is shown with a
 * glyph and the word as well, so the heatmap is readable with colour vision
 * deficiency and in greyscale print.
 */
export const TIER_GLYPH: Record<Tier, string> = {
  HIGH: "▲",      // filled triangle
  MEDIUM: "◆",    // filled diamond
  LOW: "●",       // filled circle
};

export const STRATEGY_CLASS: Record<string, string> = {
  Retire: "text-muted border-line bg-raised",
  Retain: "text-info border-info/35 bg-info/10",
  Rehost: "text-low border-low/35 bg-low-soft",
  Relocate: "text-low border-low/35 bg-low-soft",
  Replatform: "text-accent border-accent/35 bg-accent-soft",
  Repurchase: "text-medium border-medium/35 bg-medium-soft",
  Refactor: "text-high border-high/35 bg-high-soft",
};

export const STRATEGY_BLURB: Record<Strategy, string> = {
  Retire: "Delete it - nothing calls it and nothing runs it.",
  Retain: "Leave it in place, deliberately, for now.",
  Rehost: "Lift and shift unchanged onto cloud infrastructure.",
  Relocate: "Move the hosting without changing the OS or the application.",
  Replatform: "Keep the code; change the runtime or data platform.",
  Repurchase: "Replace with a commercial product or SaaS.",
  Refactor: "Re-architect or rewrite - the most expensive option.",
};

export function readinessClass(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted";
  if (score >= 80) return "text-low";
  if (score >= 60) return "text-medium";
  return "text-high";
}

export function readinessBar(score: number | null | undefined): string {
  if (score === null || score === undefined) return "bg-faint";
  if (score >= 80) return "bg-low";
  if (score >= 60) return "bg-medium";
  return "bg-high";
}

export const AGENT_INITIALS: Record<string, string> = {
  "Cloud Architect": "CA",
  "Validation & QA Lead": "QA",
  "Security Officer": "SO",
  "FinOps Analyst": "FO",
  "Regulatory Affairs": "RA",
  Moderator: "MD",
  System: "SY",
};

export const AGENT_CLASS: Record<string, string> = {
  "Cloud Architect": "bg-accent/15 text-accent border-accent/30",
  "Validation & QA Lead": "bg-high/15 text-high border-high/30",
  "Security Officer": "bg-medium/15 text-medium border-medium/30",
  "FinOps Analyst": "bg-low/15 text-low border-low/30",
  "Regulatory Affairs": "bg-info/15 text-info border-info/30",
  Moderator: "bg-ink/10 text-ink border-ink/25",
  System: "bg-raised text-muted border-line",
};

export const CHECK_HINT: Record<string, string> = {
  statelessness: "Session state, static mutable fields and in-process caches each mean you cannot run two instances.",
  local_filesystem: "Absolute host paths and java.io file access do not exist in a container.",
  hardcoded_config: "Hosts, connection strings and credentials pinned in configuration.",
  framework_eol: "An unsupported runtime or framework cannot be patched in a managed service.",
  db_coupling: "A table written by two components is what makes them one component.",
  complexity_size: "Complex methods cannot be characterised reliably before a migration.",
  test_coverage: "Without a test, nothing proves the modernized version behaves the same.",
  scheduled_jobs: "@Scheduled on a singleton runs on every replica with no lock.",
  licensing_blockers: "Vendor-specific SQL, interop and licensed SDKs restrict the target.",
  observability: "A managed platform cannot operate what it cannot observe.",
  gxp_tier_penalty: "HIGH tier is not bad code - it means a cutover needs scripted testing and QA approval.",
};
