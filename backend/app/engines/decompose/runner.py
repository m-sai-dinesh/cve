"""Engine 4 orchestration: build features, run all three variants, compare.

All three partitions are always computed, because the claim ModernRx makes is
comparative. The chosen variant is written back to the graph as ``Cluster``
nodes; the other two are kept for the comparison table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from . import metrics as M
from .cluster import (
    Partition,
    hdbscan_partition,
    louvain_partition,
    refine,
    write_clusters,
)
from .features import FeatureMatrices, build_features

log = get_logger("decompose")

VARIANTS = ("louvain", "hdbscan", "modernrx")


@dataclass
class DecompositionResult:
    features: FeatureMatrices | None = None
    partitions: dict[str, Partition] = field(default_factory=dict)
    metrics: dict[str, M.PartitionMetrics] = field(default_factory=dict)
    comparison: dict[str, Any] = field(default_factory=dict)
    chosen: str = "modernrx"
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, variant: str | None = None) -> dict[str, Any]:
        v = variant or self.chosen
        payload = self.metrics[v].as_dict() if v in self.metrics else {}
        return {
            **payload,
            "chosen": self.chosen,
            "available_variants": [k for k in VARIANTS if k in self.metrics],
            "comparison": self.comparison,
            "params": self.params,
            "signals": {
                "available": (self.features.available if self.features else {}),
                "weights": ({k: round(v, 4) for k, v in self.features.weights.items()}
                            if self.features else {}),
            },
            "refinement": (self.partitions[v].refinement if v in self.partitions else {}),
        }

    def table(self) -> dict[str, Any]:
        """Side-by-side metric table for the decomposition screen."""
        rows = []
        for key, meta in M.METRIC_META.items():
            row = {"metric": key, "title": meta.get("title", key),
                   "definition": meta.get("definition", ""),
                   "lower_is_better": meta.get("lower_is_better")}
            for v in VARIANTS:
                if v in self.metrics and key in self.metrics[v].values:
                    val = self.metrics[v].values[key]
                    row[v] = round(val, 4) if isinstance(val, float) else val
            rows.append(row)
        return {"rows": rows, "variants": [v for v in VARIANTS if v in self.metrics]}


def run(
    kg: KnowledgeGraph,
    *,
    weights: list[float] | None = None,
    gamma: float = 1.5,
    alpha: float = 1.0,
    beta: float = 1.0,
    min_cluster_size: int = 4,
    emb=None,
    readiness: dict[str, float] | None = None,
    chosen: str = "modernrx",
    progress=None,
) -> DecompositionResult:
    def step(frac: float, msg: str) -> None:
        if progress:
            progress(frac, msg)

    step(0.05, "building the similarity matrix")
    fm = build_features(kg, weights=weights, emb=emb)
    res = DecompositionResult(features=fm, chosen=chosen, params={
        "weights": {k: round(v, 4) for k, v in fm.weights.items()},
        "alpha": alpha, "beta": beta, "gamma": gamma,
        "min_cluster_size": min_cluster_size,
    })
    if fm.n < 3:
        log.warning("decompose_too_small", classes=fm.n)
        return res

    step(0.2, "variant 1/3: Louvain baseline")
    res.partitions["louvain"] = louvain_partition(kg, fm.node_ids)

    step(0.35, "variant 2/3: HDBSCAN (GxP-blind)")
    res.partitions["hdbscan"] = hdbscan_partition(fm, min_cluster_size=min_cluster_size)

    step(0.5, "variant 3/3: ModernRx (GxP-constrained refinement)")
    modernrx, _stats = refine(
        kg, fm, res.partitions["hdbscan"],
        alpha=alpha, beta=beta, gamma=gamma,
        extra_starts=[res.partitions["louvain"]],
        progress=lambda f, m: step(0.5 + 0.3 * f, m),
    )
    res.partitions["modernrx"] = modernrx

    step(0.85, "scoring all three decompositions")
    for name, part in res.partitions.items():
        from .cluster import name_clusters

        part.names = name_clusters(kg, part)
        res.metrics[name] = M.evaluate(kg, fm, part, alpha=alpha, beta=beta, gamma=gamma)

    res.comparison = M.compare(res.metrics, baseline="hdbscan", champion="modernrx")

    step(0.95, f"writing the {chosen} decomposition to the graph")
    if chosen in res.partitions:
        write_clusters(kg, res.partitions[chosen], readiness)
        # Cluster profiles must be recomputed after write-back so the Cluster
        # node ids in the graph and in the metrics agree.
        res.metrics[chosen].clusters = M.cluster_profiles(kg, res.partitions[chosen])

    head = res.comparison.get("headline", {})
    step(1.0, (f"re-validation scope {head.get('reval_scope_before')}% -> "
               f"{head.get('reval_scope_after')}%")
         if head.get("reval_scope_before") is not None
         else f"{res.partitions[chosen].cluster_count()} services proposed")
    log.info("decompose_done", chosen=chosen,
             services={k: v.cluster_count() for k, v in res.partitions.items()},
             headline=head)
    return res
