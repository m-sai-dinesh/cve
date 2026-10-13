"""Runtime trace ingestion (PRD §8.1 step 4 — the Mono2Micro idea).

Reads OTLP/JSON spans (as exported by the OpenTelemetry Java agent, gzipped or
plain) and projects them onto the graph:

* ``runtimeHits`` per method and class — what the system *actually* executes,
  as opposed to what the call graph says it could;
* ``UseCase`` nodes with ``PART_OF_USECASE {hits}`` edges — which components
  collaborate to serve one business transaction;
* observed caller->callee edges from span parentage, which recovers calls static
  analysis misses (interface dispatch, Spring proxies, reflection).

That last point is why traces are worth the trouble: they turn a guess into a
measurement.
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph

log = get_logger("runtime")


@dataclass
class Span:
    span_id: str
    parent_id: str
    name: str
    namespace: str = ""
    function: str = ""
    usecase: str = ""
    trace_id: str = ""
    duration_ns: int = 0

    @property
    def fqn(self) -> str:
        if self.namespace and self.function:
            return f"{self.namespace}.{self.function}"
        return self.name


@dataclass
class TraceSummary:
    spans: int = 0
    traces: int = 0
    use_cases: dict[str, int] = field(default_factory=dict)
    mapped_methods: int = 0
    unmapped_spans: int = 0
    observed_edges: int = 0
    total_hits: int = 0
    mean_latency_ms: dict[str, float] = field(default_factory=dict)


def _attr(attrs: list[dict[str, Any]], key: str) -> str:
    for a in attrs or []:
        if a.get("key") == key:
            v = a.get("value") or {}
            return str(v.get("stringValue") or v.get("intValue") or "")
    return ""


def load_spans(path: Path) -> list[Span]:
    """Parse an OTLP/JSON export (``.json`` or ``.json.gz``)."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)

    out: list[Span] = []
    for rs in payload.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []) or rs.get("instrumentationLibrarySpans", []):
            for sp in ss.get("spans", []):
                attrs = sp.get("attributes", [])
                try:
                    dur = int(sp.get("endTimeUnixNano", 0)) - int(sp.get("startTimeUnixNano", 0))
                except (TypeError, ValueError):
                    dur = 0
                out.append(Span(
                    span_id=sp.get("spanId", ""),
                    parent_id=sp.get("parentSpanId", "") or "",
                    name=sp.get("name", ""),
                    namespace=_attr(attrs, "code.namespace"),
                    function=_attr(attrs, "code.function"),
                    usecase=_attr(attrs, "modernrx.usecase"),
                    trace_id=sp.get("traceId", ""),
                    duration_ns=max(0, dur),
                ))
    return out


def apply_traces(kg: KnowledgeGraph, spans: list[Span], *, progress=None) -> TraceSummary:
    """Fold spans into the graph. Returns what was and was not mapped."""
    summary = TraceSummary(spans=len(spans))

    # Index the graph for span->method resolution.
    by_fqn: dict[str, list[str]] = defaultdict(list)
    for mid in kg.node_ids("Method"):
        d = kg.node(mid) or {}
        by_fqn[d.get("fqn", "")].append(mid)
        # Also index Class.method so a span named "AuditService.recordChange" resolves.
        owner_simple = str(d.get("ownerClass", ""))
        if owner_simple:
            by_fqn[f"{owner_simple}.{d.get('name', '')}"].append(mid)

    hits: dict[str, int] = defaultdict(int)
    durations: dict[str, list[int]] = defaultdict(list)
    usecase_hits: dict[tuple[str, str], int] = defaultdict(int)
    observed: dict[tuple[str, str], int] = defaultdict(int)
    span_to_method: dict[str, str] = {}
    traces: set[str] = set()
    total = max(1, len(spans))

    for i, sp in enumerate(spans):
        if progress and i % 2000 == 0:
            progress(0.2 + 0.5 * i / total, f"mapping span {i:,}/{len(spans):,}")
        traces.add(sp.trace_id)
        candidates = by_fqn.get(sp.fqn) or by_fqn.get(sp.name) or []
        if not candidates:
            summary.unmapped_spans += 1
            continue
        mid = candidates[0]
        span_to_method[sp.span_id] = mid
        hits[mid] += 1
        durations[mid].append(sp.duration_ns)
        if sp.usecase:
            usecase_hits[(sp.usecase, mid)] += 1
            summary.use_cases[sp.usecase] = summary.use_cases.get(sp.usecase, 0) + 1

    # Caller -> callee from span parentage.
    for sp in spans:
        if not sp.parent_id:
            continue
        child = span_to_method.get(sp.span_id)
        parent = span_to_method.get(sp.parent_id)
        if child and parent and child != parent:
            observed[(parent, child)] += 1

    summary.traces = len(traces)
    summary.mapped_methods = len(hits)
    summary.total_hits = sum(hits.values())

    if progress:
        progress(0.75, "writing runtime metrics onto the graph")

    for mid, n in hits.items():
        kg.set_prop(mid, "runtimeHits", n)
        ds = durations[mid]
        if ds:
            mean_ms = sum(ds) / len(ds) / 1e6
            kg.set_prop(mid, "meanLatencyMs", round(mean_ms, 3))
            kg.set_prop(mid, "p95LatencyMs", round(sorted(ds)[int(0.95 * (len(ds) - 1))] / 1e6, 3))
            summary.mean_latency_ms[mid] = round(mean_ms, 3)

    # Roll hits up to the owning class.
    class_hits: dict[str, int] = defaultdict(int)
    for mid, n in hits.items():
        owner = kg.owner_class(mid)
        if owner:
            class_hits[owner] += n
    for cid, n in class_hits.items():
        kg.set_prop(cid, "runtimeHits", n)

    # Use-case nodes and membership.
    for (uc, mid), n in usecase_hits.items():
        uid = f"usecase:{uc}"
        if not kg.has(uid):
            kg.add_node(uid, "UseCase", name=uc)
        kg.add_edge(mid, uid, "PART_OF_USECASE", hits=n)
        owner = kg.owner_class(mid)
        if owner:
            kg.add_edge(owner, uid, "PART_OF_USECASE", hits=n)

    # Observed calls: strengthen existing edges, add the ones static analysis missed.
    for (parent, child), n in observed.items():
        existing = kg.g.get_edge_data(parent, child) or {}
        if any(d.get("rel") == "CALLS" for d in existing.values()):
            for d in existing.values():
                if d.get("rel") == "CALLS":
                    d["runtimeCount"] = n
                    d["confirmedAtRuntime"] = True
        else:
            kg.add_edge(parent, child, "CALLS", count=1, runtimeCount=n,
                        observedOnly=True, confirmedAtRuntime=True)
            summary.observed_edges += 1
        pc, cc = kg.owner_class(parent), kg.owner_class(child)
        if pc and cc and pc != cc:
            kg.add_edge(pc, cc, "DEPENDS_ON", count=1, runtimeCount=n)

    if progress:
        progress(1.0, f"{summary.total_hits:,} runtime hits over "
                      f"{len(summary.use_cases)} use cases")
    log.info("traces_applied", spans=summary.spans, traces=summary.traces,
             mapped=summary.mapped_methods, unmapped=summary.unmapped_spans,
             usecases=len(summary.use_cases), observed_edges=summary.observed_edges)
    return summary


def find_trace_file(root: Path) -> Path | None:
    """Locate a trace export shipped alongside the source."""
    for pattern in ("usecases/*traces*.json.gz", "usecases/*traces*.json",
                    "**/*traces*.json.gz", "**/*otel*.json", "**/*spans*.json"):
        for p in sorted(root.glob(pattern)):
            if p.is_file():
                return p
    return None


def ingest_traces(kg: KnowledgeGraph, root: Path, *, progress=None) -> TraceSummary | None:
    path = find_trace_file(root)
    if path is None:
        log.info("no_traces_found", root=str(root))
        return None
    if progress:
        progress(0.05, f"reading {path.name}")
    spans = load_spans(path)
    summary = apply_traces(kg, spans, progress=progress)
    return summary
