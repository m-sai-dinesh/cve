"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, Check, ChevronDown, Circle, Diamond, Info,
  Loader2, Triangle, X,
} from "lucide-react";
import React from "react";
import type { Tier } from "@/lib/api";
import {
  cn, num, readinessBar, readinessClass, STRATEGY_CLASS, TIER_CLASS, TIER_DOT,
} from "@/lib/format";

// =============================================================================
// Tier badge — PRD §18: never colour alone
// =============================================================================

const TIER_ICON: Record<Tier, typeof Triangle> = {
  HIGH: Triangle,
  MEDIUM: Diamond,
  LOW: Circle,
};

export function TierBadge({
  tier, size = "sm", showLabel = true, title,
}: {
  tier: Tier; size?: "xs" | "sm" | "md"; showLabel?: boolean; title?: string;
}) {
  const Icon = TIER_ICON[tier] ?? Circle;
  return (
    <span
      className={cn("chip", TIER_CLASS[tier],
        size === "xs" && "px-1.5 py-0 text-[0.625rem]",
        size === "md" && "px-2.5 py-1 text-xs")}
      title={title ?? `GxP criticality: ${tier}`}
    >
      {/* The glyph carries the meaning so colour is never the only signal. */}
      <Icon className={cn(size === "md" ? "h-3 w-3" : "h-2.5 w-2.5", "shrink-0")}
            fill="currentColor" strokeWidth={0} aria-hidden />
      {showLabel && tier}
    </span>
  );
}

export function StrategyBadge({ strategy, className }: { strategy: string; className?: string }) {
  return (
    <span className={cn("chip", STRATEGY_CLASS[strategy] ?? "border-line bg-raised text-muted",
      "px-2.5 py-1 text-xs", className)}>
      {strategy}
    </span>
  );
}

export function Dot({ tier }: { tier: Tier }) {
  return <span className={cn("inline-block h-2 w-2 shrink-0 rounded-full", TIER_DOT[tier])} />;
}

// =============================================================================
// Layout primitives
// =============================================================================

export function PageHeader({
  title, subtitle, actions, kicker,
}: {
  title: React.ReactNode; subtitle?: React.ReactNode;
  actions?: React.ReactNode; kicker?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        {kicker && (
          <div className="mb-1.5 text-2xs font-bold uppercase tracking-widest text-accent">
            {kicker}
          </div>
        )}
        <h1 className="text-xl font-extrabold tracking-tight sm:text-2xl lg:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({
  title, subtitle, actions, children, className, bodyClass, dense,
}: {
  title?: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode;
  children: React.ReactNode; className?: string; bodyClass?: string; dense?: boolean;
}) {
  return (
    <section className={cn("card overflow-hidden transition-shadow duration-200 border-line/90", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface/90 px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold tracking-tight">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn(dense ? "" : "p-5", bodyClass)}>{children}</div>
    </section>
  );
}

export function Kpi({
  label, value, unit, hint, tone, icon, trend,
}: {
  label: string; value: React.ReactNode; unit?: string; hint?: string;
  tone?: "high" | "medium" | "low" | "accent"; icon?: React.ReactNode;
  trend?: { value: string; good: boolean };
}) {
  const toneClass = tone
    ? { high: "text-high", medium: "text-medium", low: "text-low", accent: "text-accent" }[tone]
    : "text-ink";
  return (
    <div className="card-pad group relative transition-all duration-150 hover:shadow-card hover:border-line">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-2xs font-semibold uppercase tracking-wider text-muted">{label}</span>
        {icon && <span className="text-faint transition-colors group-hover:text-muted">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={cn("kpi text-2xl sm:text-3xl font-extrabold tracking-tight", toneClass)}>{value}</span>
        {unit && <span className="text-xs font-medium text-muted">{unit}</span>}
        {trend && (
          <span className={cn("ml-1 text-xs font-semibold",
            trend.good ? "text-low" : "text-high")}>
            {trend.value}
          </span>
        )}
      </div>
      {hint && <p className="mt-1.5 text-xs leading-snug text-muted">{hint}</p>}
    </div>
  );
}

export function Meter({
  value, max = 100, className, label,
}: { value: number; max?: number; className?: string; label?: string }) {
  const pctVal = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-2 w-full overflow-hidden rounded-full bg-raised/90 border border-line/40"
           role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}
           aria-label={label ?? "score"}>
        <div className={cn("h-full rounded-full transition-all duration-300 ease-out", readinessBar(value))}
             style={{ width: `${pctVal}%` }} />
      </div>
      <span className={cn("w-9 shrink-0 text-right text-xs font-semibold tabular-nums",
        readinessClass(value))}>
        {num(value)}
      </span>
    </div>
  );
}

// =============================================================================
// State
// =============================================================================

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} aria-hidden />;
}

export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Spinner /> {label}...
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="relative h-12 overflow-hidden rounded-lg bg-raised">
          <div className="absolute inset-0 -translate-x-full animate-shimmer
                          bg-gradient-to-r from-transparent via-surface/70 to-transparent" />
        </div>
      ))}
    </div>
  );
}

export function Empty({
  title, hint, action, icon,
}: { title: string; hint?: React.ReactNode; action?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed
                    px-6 py-12 text-center">
      <div className="mb-3 text-faint">{icon ?? <Info className="h-7 w-7" />}</div>
      <p className="text-sm font-semibold">{title}</p>
      {hint && <p className="mt-1.5 max-w-md text-xs leading-relaxed text-muted">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = typeof error === "string" ? error : (error as Error)?.message ?? "Something failed";
  return (
    <div className="flex items-start gap-3 rounded-xl border border-high/35 bg-high-soft p-4">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-high" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-high">Could not load this</p>
        <p className="mt-1 break-words text-xs text-high/85">{msg}</p>
      </div>
      {retry && (
        <button onClick={retry} className="btn-outline shrink-0 py-1 text-xs">Retry</button>
      )}
    </div>
  );
}

export function Banner({
  tone = "info", title, children, action,
}: {
  tone?: "info" | "warn" | "danger" | "ok";
  title?: React.ReactNode; children?: React.ReactNode; action?: React.ReactNode;
}) {
  const map = {
    info: { cls: "border-info/35 bg-info/10 text-info", Icon: Info },
    warn: { cls: "border-medium/40 bg-medium-soft text-medium", Icon: AlertTriangle },
    danger: { cls: "border-high/40 bg-high-soft text-high", Icon: AlertTriangle },
    ok: { cls: "border-low/40 bg-low-soft text-low", Icon: Check },
  }[tone];
  return (
    <div className={cn("flex items-start gap-3 rounded-xl border p-4", map.cls)}>
      <map.Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 text-xs leading-relaxed">
        {title && <p className="mb-0.5 text-sm font-semibold">{title}</p>}
        {children}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

// =============================================================================
// Interaction
// =============================================================================

export function Tabs<T extends string>({
  tabs, value, onChange, className,
}: {
  tabs: { value: T; label: React.ReactNode; count?: number }[];
  value: T; onChange: (v: T) => void; className?: string;
}) {
  return (
    <div className={cn("flex gap-1 rounded-lg border border-line bg-raised p-1", className)} role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
            value === t.value
              ? "bg-surface text-ink shadow-sm"
              : "text-muted hover:text-ink hover:bg-surface/50",
          )}>
          {t.label}
          {t.count !== undefined && (
            <span className={cn("rounded px-1 text-[0.625rem] tabular-nums",
              value === t.value ? "bg-raised text-muted" : "bg-surface/60 text-faint")}>
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Collapse({
  title, children, defaultOpen = false, badge,
}: {
  title: React.ReactNode; children: React.ReactNode;
  defaultOpen?: boolean; badge?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="rounded-lg border border-line">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left
                   text-xs font-semibold transition-colors duration-150 hover:bg-raised
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 rounded-lg">
        <span className="flex min-w-0 items-center gap-2">{title}{badge}</span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted transition-transform duration-200",
          open && "rotate-180")} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }}
            className="overflow-hidden">
            <div className="border-t border-line px-4 py-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function Modal({
  open, onClose, title, children, footer, wide,
}: {
  open: boolean; onClose: () => void; title: React.ReactNode;
  children: React.ReactNode; footer?: React.ReactNode; wide?: boolean;
}) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={onClose} />
          <motion.div role="dialog" aria-modal="true"
            initial={{ scale: 0.96, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97 }}
            transition={{ duration: 0.16 }}
            className={cn("card relative z-10 flex max-h-[88vh] w-full flex-col shadow-pop border-line rounded-2xl",
              wide ? "max-w-3xl" : "max-w-lg")}>
            <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
              <button onClick={onClose} className="btn-ghost p-1.5 rounded-lg focus-visible:ring-2 focus-visible:ring-accent/40" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
            {footer && (
              <footer className="flex items-center justify-end gap-2 border-t border-line px-5 py-3.5">
                {footer}
              </footer>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Drawer({
  open, onClose, title, subtitle, children, width = "max-w-xl",
}: {
  open: boolean; onClose: () => void; title: React.ReactNode;
  subtitle?: React.ReactNode; children: React.ReactNode; width?: string;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-40 flex justify-end"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] transition-opacity" onClick={onClose} />
          <motion.aside
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 360, damping: 34 }}
            className={cn("relative z-10 flex h-full w-full flex-col border-l border-line bg-surface shadow-pop",
              width)}>
            <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold tracking-tight">{title}</h2>
                {subtitle && <p className="mt-0.5 truncate text-xs text-muted">{subtitle}</p>}
              </div>
              <button onClick={onClose} className="btn-ghost shrink-0 p-1.5 rounded-lg focus-visible:ring-2 focus-visible:ring-accent/40" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Tip({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <span className="group/tip relative inline-flex">
      {children}
      <span className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-1.5
                       w-max max-w-xs -translate-x-1/2 rounded-md border border-line bg-surface px-2.5 py-1.5
                       text-2xs leading-snug text-muted opacity-0 shadow-pop transition-opacity
                       group-hover/tip:opacity-100">
        {text}
      </span>
    </span>
  );
}

export function InfoDot({ text }: { text: string }) {
  return (
    <Tip text={text}>
      <Info className="h-3 w-3 cursor-help text-faint hover:text-muted transition-colors" aria-label={text} />
    </Tip>
  );
}

export function ProgressBar({
  value, label, status,
}: { value: number; label?: string; status?: string }) {
  const p = Math.max(0, Math.min(100, value * 100));
  const failed = status === "failed";
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
        <span className="min-w-0 truncate text-muted">{label}</span>
        <span className="shrink-0 font-semibold tabular-nums">{p.toFixed(0)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-raised">
        <motion.div className={cn("h-full rounded-full", failed ? "bg-high" : "bg-accent")}
          initial={{ width: 0 }} animate={{ width: `${p}%` }}
          transition={{ duration: 0.35, ease: "easeOut" }} />
      </div>
    </div>
  );
}

/** Copy-to-clipboard for hashes and node ids. */
export function CopyText({ text, className }: { text: string; className?: string }) {
  const [done, setDone] = React.useState(false);
  return (
    <button
      className={cn("mono inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 border border-line/50 bg-raised/50 hover:bg-raised transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 active:scale-[0.98]", className)}
      title={`${text} - click to copy`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1200);
        } catch {
          /* clipboard blocked: the title attribute still shows the full value */
        }
      }}>
      {done ? <Check className="h-3 w-3 text-low" /> : null}
      <span className="truncate">{text}</span>
    </button>
  );
}
