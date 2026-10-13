"use client";

import React from "react";
import mermaid from "mermaid";
import { cn } from "@/lib/format";
import { Spinner } from "./ui";

let initialized = false;

export function MermaidViewer({
  chart,
  className,
}: {
  chart: string;
  className?: string;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [svg, setSvg] = React.useState<string>("");
  const [error, setError] = React.useState<string>("");
  const [loading, setLoading] = React.useState<boolean>(true);
  const idRef = React.useRef(`mermaid-${Math.random().toString(36).slice(2, 9)}`);

  React.useEffect(() => {
    if (!initialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "loose",
        fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
      });
      initialized = true;
    }
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    if (!chart || !chart.trim()) {
      setSvg("");
      setLoading(false);
      return;
    }

    const renderChart = async () => {
      try {
        const renderId = `${idRef.current}-${Date.now()}`;
        const { svg: renderedSvg } = await mermaid.render(renderId, chart);
        if (!cancelled) {
          setSvg(renderedSvg);
          setLoading(false);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = (err as Error)?.message || "Failed to render diagram";
          setError(msg);
          setLoading(false);
        }
      }
    };

    renderChart();

    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (loading) {
    return (
      <div className={cn("flex min-h-[240px] items-center justify-center rounded-lg border border-line bg-surface p-6 shadow-sm", className)}>
        <div className="flex items-center gap-2 text-xs text-muted">
          <Spinner /> Rendering diagram...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn("rounded-lg border border-medium/40 bg-medium-soft p-4 text-xs text-medium", className)}>
        <p className="font-semibold">Mermaid rendering error</p>
        <p className="mt-1 font-mono text-[0.6875rem]">{error}</p>
        <details className="mt-2 text-2xs text-muted">
          <summary className="cursor-pointer">Raw diagram text</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-surface p-2 font-mono">{chart}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn("overflow-x-auto rounded-lg border border-line bg-surface p-4 shadow-sm [&_svg]:mx-auto [&_svg]:max-w-full", className)}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
