"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity, ChevronDown, Moon, ShieldCheck, Sun, UserRound,
} from "lucide-react";
import Link from "next/link";
import React from "react";
import { Api } from "@/lib/api";
import { cn } from "@/lib/format";
import { useApp } from "@/lib/store";
import { Tip } from "./ui";

export function Header() {
  const { currentUser, setCurrentUser, theme, toggleTheme } = useApp();
  const [open, setOpen] = React.useState(false);

  const users = useQuery({ queryKey: ["users"], queryFn: Api.users, staleTime: 300_000 });
  const health = useQuery({
    queryKey: ["health"], queryFn: Api.health,
    refetchInterval: 60_000, staleTime: 30_000,
  });

  // Default to the architect so the app is usable immediately; approvals still
  // require an explicit choice of a user with the right role.
  React.useEffect(() => {
    if (!currentUser && users.data?.length) {
      setCurrentUser(users.data.find((u) => u.role === "Architect") ?? users.data[0]);
    }
  }, [users.data, currentUser, setCurrentUser]);

  React.useEffect(() => {
    const close = () => setOpen(false);
    if (open) {
      document.addEventListener("click", close);
      return () => document.removeEventListener("click", close);
    }
  }, [open]);

  const llm = health.data?.llm;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface">
      <div className="mx-auto flex h-14 w-full max-w-[1600px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white shadow-sm">
            <ShieldCheck className="h-4.5 w-4.5" strokeWidth={2.4} />
          </span>
          <span className="hidden sm:block">
            <span className="block text-sm font-bold leading-tight tracking-tight">ModernRx</span>
            <span className="block text-[0.625rem] font-medium leading-tight text-muted">
              Pharma IT / Cloud Advisor
            </span>
          </span>
        </Link>

        <div className="flex-1" />

        {/* Model provenance */}
        {llm && (
          <Tip
            text={
              llm.available
                ? `Gemini is configured. Model ${llm.model_id} is pinned and recorded with every AI output.`
                : "No GEMINI_API_KEY configured. Fallback deterministic reasoners active."
            }
          >
            <span className={cn("chip hidden cursor-help items-center gap-1.5 px-2.5 py-1 md:inline-flex shadow-sm",
              llm.available
                ? "border-low/35 bg-low-soft text-low"
                : "border-medium/35 bg-medium-soft text-medium")}>
              <Activity className="h-3 w-3" />
              {llm.available ? llm.model_id : "Deterministic mode"}
            </span>
          </Tip>
        )}

        <button onClick={toggleTheme} className="btn-ghost p-2 rounded-lg min-h-[38px] min-w-[38px] flex items-center justify-center focus-visible:ring-2 focus-visible:ring-accent/40"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        {/* Unified Modernization Lead profile */}
        <div className="flex items-center gap-2 rounded-lg border border-line bg-raised px-2.5 py-1 text-xs">
          <span className="grid h-6 w-6 place-items-center rounded bg-accent/15 text-[0.625rem] font-bold text-accent">
            ML
          </span>
          <div className="hidden sm:block text-left">
            <span className="block font-semibold leading-tight text-ink">Modernization Lead</span>
            <span className="block text-[0.625rem] font-medium leading-tight text-muted">Pharma IT / Cloud</span>
          </div>
        </div>
      </div>
    </header>
  );
}

function initials(name: string): string {
  return name.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("");
}
