"use client";

import React from "react";
import cytoscape from "cytoscape";
// @ts-expect-error cytoscape-fcose types
import fcose from "cytoscape-fcose";
import { Maximize2, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import type { GraphEdge, GraphNode, Tier } from "@/lib/api";
import { cn, TIER_HEX } from "@/lib/format";
import { useApp } from "@/lib/store";

if (typeof window !== "undefined") {
  try {
    cytoscape.use(fcose);
  } catch {
    // already registered
  }
}

interface TwinCytoscapeProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId?: string | null;
  onSelectNode: (nodeId: string | null) => void;
  className?: string;
}

export function TwinCytoscape({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  className,
}: TwinCytoscapeProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const cyRef = React.useRef<cytoscape.Core | null>(null);
  const theme = useApp((s) => s.theme);

  React.useEffect(() => {
    if (!containerRef.current) return;

    const isDark = theme === "dark";

    const elements: cytoscape.ElementDefinition[] = [
      ...nodes.map((n) => {
        const tier = (n.gxpTier || "LOW") as Tier;
        const color = isDark ? TIER_HEX[tier]?.dark : TIER_HEX[tier]?.light;
        const shortName = n.fqn?.split(".").pop() || n.label || n.id;
        const isTable = n.kind === "Table" || n.label === "Table";

        return {
          group: "nodes" as const,
          data: {
            id: n.id,
            label: shortName,
            tier: n.gxpTier,
            kind: n.kind || n.label,
            color: isTable ? (isDark ? "#60a5fa" : "#2563eb") : color,
            size: Math.max(28, Math.min(60, Math.sqrt(n.loc || 20) * 4)),
            borderWidth: n.id === selectedNodeId ? 4 : 2,
            borderColor: n.id === selectedNodeId ? (isDark ? "#ffffff" : "#0f172a") : isDark ? "#334155" : "#cbd5e1",
          },
        };
      }),
      ...edges.map((e) => ({
        group: "edges" as const,
        data: {
          id: e.id || `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          rel: e.rel,
          count: e.count || 1,
        },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            width: "data(size)",
            height: "data(size)",
            "font-size": "10px",
            "font-family": "system-ui, -apple-system, sans-serif",
            color: isDark ? "#e2e8f0" : "#1e293b",
            "text-valign": "bottom",
            "text-margin-y": 5,
            "text-background-color": isDark ? "rgba(15, 23, 42, 0.75)" : "rgba(255, 255, 255, 0.75)",
            "text-background-opacity": 0.8,
            "text-background-padding": "2px",
            "text-background-shape": "roundrectangle",
            "border-width": "data(borderWidth)",
            "border-color": "data(borderColor)",
            "transition-property": "border-width, border-color, width, height",
            "transition-duration": 0.15,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 4,
            "border-color": isDark ? "#38bdf8" : "#0284c7",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": isDark ? "#475569" : "#cbd5e1",
            "target-arrow-color": isDark ? "#475569" : "#cbd5e1",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.8,
            opacity: 0.7,
          },
        },
        {
          selector: "edge[rel = 'WRITES']",
          style: {
            "line-color": "#ef4444",
            "target-arrow-color": "#ef4444",
            width: 2,
          },
        },
        {
          selector: "edge[rel = 'READS']",
          style: {
            "line-color": "#3b82f6",
            "target-arrow-color": "#3b82f6",
            "line-style": "dashed",
          },
        },
        {
          selector: "edge[rel = 'CO_CHANGES']",
          style: {
            "line-color": "#a855f7",
            "target-arrow-color": "#a855f7",
            "line-style": "dotted",
          },
        },
      ],
      layout: {
        name: "cose",
        idealEdgeLength: () => 100,
        nodeOverlap: 20,
        refresh: 20,
        fit: true,
        padding: 30,
        randomize: false,
        componentSpacing: 100,
        nodeRepulsion: () => 400000,
        edgeElasticity: () => 100,
        nestingFactor: 5,
        gravity: 80,
        numIter: 1000,
        initialTemp: 200,
        coolingFactor: 0.95,
        minTemp: 1.0,
      } as any,
    });

    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      onSelectNode(node.id());
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        onSelectNode(null);
      }
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, theme, onSelectNode]);

  // Update selected node border without rebuilding full layout
  React.useEffect(() => {
    if (!cyRef.current) return;
    const cy = cyRef.current;
    const isDark = theme === "dark";

    cy.nodes().forEach((n) => {
      if (n.id() === selectedNodeId) {
        n.style({
          "border-width": 4,
          "border-color": isDark ? "#38bdf8" : "#0284c7",
        });
      } else {
        n.style({
          "border-width": 2,
          "border-color": isDark ? "#334155" : "#cbd5e1",
        });
      }
    });
  }, [selectedNodeId, theme]);

  const handleZoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.25);
  const handleZoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() * 0.8);
  const handleFit = () => cyRef.current?.fit(undefined, 30);
  const handleReset = () => {
    cyRef.current?.layout({ name: "cose", fit: true, padding: 30 }).run();
  };

  return (
    <div className={cn("relative overflow-hidden rounded-xl border border-line bg-surface", className)}>
      <div ref={containerRef} className="h-full w-full min-h-[500px]" />

      {/* Floating Canvas Controls */}
      <div className="absolute bottom-4 right-4 flex items-center gap-1 rounded-lg border border-line bg-surface/95 p-1 shadow-card backdrop-blur-sm">
        <button
          onClick={handleZoomIn}
          className="btn-ghost p-2 rounded-lg text-muted hover:text-ink min-h-[34px] min-w-[34px] flex items-center justify-center focus-visible:ring-2 focus-visible:ring-accent/40"
          title="Zoom In"
          aria-label="Zoom In"
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          onClick={handleZoomOut}
          className="btn-ghost p-2 rounded-lg text-muted hover:text-ink min-h-[34px] min-w-[34px] flex items-center justify-center focus-visible:ring-2 focus-visible:ring-accent/40"
          title="Zoom Out"
          aria-label="Zoom Out"
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          onClick={handleFit}
          className="btn-ghost p-2 rounded-lg text-muted hover:text-ink min-h-[34px] min-w-[34px] flex items-center justify-center focus-visible:ring-2 focus-visible:ring-accent/40"
          title="Fit to Screen"
          aria-label="Fit to Screen"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
        <button
          onClick={handleReset}
          className="btn-ghost p-2 rounded-lg text-muted hover:text-ink min-h-[34px] min-w-[34px] flex items-center justify-center focus-visible:ring-2 focus-visible:ring-accent/40"
          title="Reset Layout"
          aria-label="Reset Layout"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      {/* Legend overlay */}
      <div className="absolute top-4 left-4 flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface/95 px-3 py-1.5 text-2xs text-muted shadow-sm backdrop-blur-sm">
        <span className="font-semibold text-ink">Legend:</span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-high" /> High GxP
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-medium" /> Medium
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-low" /> Low
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-accent" /> Table
        </span>
        <span className="text-faint">|</span>
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-3 bg-high" /> Writes
        </span>
        <span className="flex items-center gap-1">
          <span className="h-0.5 w-3 border-t border-dashed border-accent" /> Reads
        </span>
      </div>
    </div>
  );
}
