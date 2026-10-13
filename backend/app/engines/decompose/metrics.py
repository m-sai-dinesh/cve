"""Engine 4, part 3 — decomposition metrics (PRD §11.4, §23).

Every number here is computed the same way for all three variants, from the
same graph, so the comparison table is a measurement and not a claim. Each
metric records its own direction (``lower_is_better``) so the UI can never
accidentally present a regression as an improvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from .cluster import NOISE, ObjectiveModel, Partition, TIER_RANK, tier_of
from .features import FeatureMatrices

log = get_logger("decompose.metrics")

METRIC_META: dict[str, dict[str, Any]] = {
    "services": {"title": "Number of services", "lower_is_better": None,
                 "definition": "Count of proposed clusters."},
    "modularity": {"title": "Modularity (Newman Q)", "lower_is_better": False,
                   "definition": "Newman modularity of the partition on the weighted call graph."},
    "icp": {"title": "Inter-cluster call ratio", "lower_is_better": True,
            "definition": "Share of call weight that crosses a cluster boundary."},
    "structural_modularity": {"title": "Structural modularity", "lower_is_better": False,
                              "definition": "Mean intra-cluster cohesion minus mean inter-cluster coupling."},
    "cohesion": {"title": "Cohesion", "lower_is_better": False,
                 "definition": "Mean intra-cluster similarity from the S matrix."},
    "coupling": {"title": "Coupling", "lower_is_better": True,
                 "definition": "Share of call weight crossing boundaries (objective term)."},
    "blast_radius": {"title": "Blast radius", "lower_is_better": True,
                     "definition": "Per PRD 11.3, normalised by class count: size of every "
                                   "HIGH-tier cluster plus the clusters calling into it."},
    "reval_scope_pct": {"title": "Re-validation scope", "lower_is_better": True,
                        "definition": "Percentage of components that a change to the validated "
                                      "core drags into full re-validation: everything inside a "
                                      "cluster holding a HIGH-tier component, plus every cluster "
                                      "that calls into one. Classes a clusterer left unplaced "
                                      "count as single-class units."},
    "high_tier_clusters": {"title": "Clusters holding the validated core", "lower_is_better": True,
                           "definition": "Clusters containing at least one HIGH-tier component."},
    "largest_cluster": {"title": "Largest cluster", "lower_is_better": True,
                        "definition": "Class count of the biggest proposed service."},
    "singletons": {"title": "Single-class clusters", "lower_is_better": True,
                   "definition": "Clusters with exactly one class."},
    "mixed_tier_clusters": {"title": "Mixed-criticality clusters", "lower_is_better": True,
                            "definition": "Clusters that mix HIGH-tier and LOW-tier components, "
                                          "so a utility change re-validates the core."},
    "shared_table_writes": {"title": "Tables written by two clusters", "lower_is_better": True,
                            "definition": "Regulated tables with writers in more than one cluster - "
                                          "each one blocks independent deployment."},
}


@dataclass
class PartitionMetrics:
    variant: str
    values: dict[str, float] = field(default_factory=dict)
    clusters: list[dict[str, Any]] = field(default_factory=list)
    objective: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "metrics": {
                k: {
                    "value": (round(v, 4) if isinstance(v, float) else v),
                    **{mk: mv for mk, mv in METRIC_META.get(k, {}).items()},
                }
                for k, v in self.values.items()
            },
            "clusters": self.clusters,
            "objective": self.objective,
            "notes": self.notes,
        }


def _call_graph(kg: KnowledgeGraph, ids: list[str]) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(ids)
    for u, v, data in kg.g.edges(data=True):
        if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
            continue
        cu, cv = kg.owner_class(u), kg.owner_class(v)
        if cu in g and cv in g and cu != cv:
            w = float(data.get("count", 1))
            if g.has_edge(cu, cv):
                g[cu][cv]["weight"] += w
            else:
                g.add_edge(cu, cv, weight=w)
    return g


def newman_modularity(kg: KnowledgeGraph, ids: list[str], labels: dict[str, int]) -> float:
    g = _call_graph(kg, ids)
    if g.number_of_edges() == 0:
        return 0.0
    communities: dict[int, set[str]] = {}
    for nid, lab in labels.items():
        if nid in g:
            communities.setdefault(lab, set()).add(nid)
    groups = [c for c in communities.values() if c]
    if len(groups) < 2:
        return 0.0
    try:
        return float(nx.community.modularity(g, groups, weight="weight"))
    except Exception:
        return 0.0


def structural_modularity(fm: FeatureMatrices, labels: dict[str, int]) -> float:
    """Mean intra-cluster similarity minus mean inter-cluster similarity."""
    idx = {c: i for i, c in enumerate(fm.node_ids)}
    intra: list[float] = []
    inter: list[float] = []
    ids = [c for c in fm.node_ids if labels.get(c, NOISE) != NOISE]
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            s = float(fm.combined[idx[ids[a]], idx[ids[b]]])
            if labels[ids[a]] == labels[ids[b]]:
                intra.append(s)
            else:
                inter.append(s)
    return float((np.mean(intra) if intra else 0.0) - (np.mean(inter) if inter else 0.0))


def cluster_profiles(kg: KnowledgeGraph, part: Partition) -> list[dict[str, Any]]:
    """Per-cluster detail for the UI and the Council's context."""
    from .cluster import name_clusters

    names = part.names or name_clusters(kg, part)
    out: list[dict[str, Any]] = []
    labels = part.labels

    for lab, members in part.clusters().items():
        if lab == NOISE:
            continue
        tiers = [tier_of(kg, m) for m in members]
        tables: dict[str, dict[str, Any]] = {}
        endpoints: list[str] = []
        loc = cc = hits = 0
        for m in members:
            node = kg.node(m) or {}
            loc += int(node.get("loc") or 0)
            cc += int(node.get("complexity") or 0)
            hits += int(node.get("runtimeHits") or 0)
            for e in kg.out_neighbors(m, "EXPOSES"):
                ed = kg.node(e) or {}
                endpoints.append(f"{ed.get('httpMethod')} {ed.get('path')}")
            for mm in [m, *kg.children(m)]:
                for rel in ("READS", "WRITES"):
                    for t in kg.out_neighbors(mm, rel):
                        td = kg.node(t) or {}
                        entry = tables.setdefault(str(td.get("name")), {
                            "regulated": bool(td.get("regulated")), "mode": set()
                        })
                        entry["mode"].add("W" if rel == "WRITES" else "R")

        # Dependencies on other clusters, with weight.
        deps: dict[int, float] = {}
        dependents: dict[int, float] = {}
        for u, v, data in kg.g.edges(data=True):
            if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
                continue
            cu, cv = kg.owner_class(u), kg.owner_class(v)
            if cu is None or cv is None:
                continue
            lu, lv = labels.get(cu, NOISE), labels.get(cv, NOISE)
            w = float(data.get("count", 1))
            if lu == lab and lv != lab and lv != NOISE:
                deps[lv] = deps.get(lv, 0.0) + w
            if lv == lab and lu != lab and lu != NOISE:
                dependents[lu] = dependents.get(lu, 0.0) + w

        out.append({
            "cluster_id": f"cluster:{lab}",
            "label": lab,
            "name": names.get(lab, f"Cluster {lab}"),
            "size": len(members),
            "members": members,
            "member_names": [str((kg.node(m) or {}).get("name")) for m in members],
            "gxp_max": max(tiers, key=lambda t: TIER_RANK.get(t, 0)) if tiers else "LOW",
            "gxp_counts": {t: tiers.count(t) for t in ("HIGH", "MEDIUM", "LOW")},
            "mixed_tier": "HIGH" in tiers and "LOW" in tiers,
            "readiness_avg": round(
                sum(float((kg.node(m) or {}).get("readiness") or 0) for m in members) / len(members), 1
            ),
            "loc": loc, "complexity": cc, "runtime_hits": hits,
            "tables": [
                {"name": k, "regulated": v["regulated"], "mode": "".join(sorted(v["mode"]))}
                for k, v in sorted(tables.items())
            ],
            "regulated_tables": sorted(k for k, v in tables.items() if v["regulated"]),
            "endpoints": sorted(set(endpoints))[:12],
            "depends_on": [{"cluster_id": f"cluster:{k}", "name": names.get(k, str(k)),
                            "weight": round(v, 1)}
                           for k, v in sorted(deps.items(), key=lambda kv: -kv[1])],
            "depended_on_by": [{"cluster_id": f"cluster:{k}", "name": names.get(k, str(k)),
                                "weight": round(v, 1)}
                               for k, v in sorted(dependents.items(), key=lambda kv: -kv[1])],
        })
    out.sort(key=lambda c: -c["size"])
    return out


def shared_table_writes(kg: KnowledgeGraph, labels: dict[str, int]) -> int:
    """Tables written from more than one cluster — hard blockers to splitting."""
    count = 0
    for t in kg.nodes("Table"):
        writing_clusters: set[int] = set()
        for m in kg.in_neighbors(t["id"], "WRITES"):
            owner = kg.owner_class(m)
            lab = labels.get(owner, NOISE) if owner else NOISE
            if lab != NOISE:
                writing_clusters.add(lab)
        if len(writing_clusters) > 1:
            count += 1
    return count


def evaluate(
    kg: KnowledgeGraph,
    fm: FeatureMatrices,
    part: Partition,
    *,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 1.5,
) -> PartitionMetrics:
    ids = fm.node_ids
    model = ObjectiveModel(kg, fm, alpha=alpha, beta=beta, gamma=gamma)
    # Measure every variant on the same footing: noise points become
    # single-class units (see ObjectiveModel.normalise).
    labels = model.normalise(part.labels)
    terms = model.evaluate(part.labels)

    groups: dict[int, int] = {}
    for lab in labels.values():
        groups[lab] = groups.get(lab, 0) + 1
    sizes = list(groups.values())
    profiles = cluster_profiles(kg, part)

    m = PartitionMetrics(variant=part.variant)
    m.values = {
        # Counting the unplaced classes as the units they really are.
        "services": float(len(groups)),
        "modularity": newman_modularity(kg, ids, labels),
        "icp": terms.coupling,
        "structural_modularity": structural_modularity(fm, labels),
        "cohesion": terms.cohesion,
        "coupling": terms.coupling,
        "blast_radius": terms.blast_radius,
        "reval_scope_pct": 100.0 * terms.reval_scope,
        "high_tier_clusters": float(sum(
            1 for lab, _n in groups.items()
            if any(tier_of(kg, nid) == "HIGH" for nid, l in labels.items() if l == lab)
        )),
        "largest_cluster": float(max(sizes) if sizes else 0),
        "singletons": float(sum(1 for s in sizes if s == 1)),
        "mixed_tier_clusters": float(sum(
            1 for lab in groups
            if {tier_of(kg, nid) for nid, l in labels.items() if l == lab} >= {"HIGH", "LOW"}
        )),
        "shared_table_writes": float(shared_table_writes(kg, labels)),
    }
    m.clusters = profiles
    m.objective = terms.as_dict()
    if part.noise:
        m.notes.append(
            f"{len(part.noise)} class(es) were density outliers: "
            f"{', '.join(n.split('.')[-1] for n in part.noise[:6])}"
            + (" and others" if len(part.noise) > 6 else "")
            + " - refactor or retire candidates."
        )
    if part.params.get("note"):
        m.notes.append(str(part.params["note"]))
    return m


def compare(results: dict[str, PartitionMetrics], *, baseline: str = "hdbscan",
            champion: str = "modernrx") -> dict[str, Any]:
    """The headline comparison of §23 — champion against baseline."""
    if baseline not in results or champion not in results:
        return {}
    b, c = results[baseline], results[champion]
    deltas: dict[str, Any] = {}
    for key in b.values:
        if key not in c.values:
            continue
        before, after = float(b.values[key]), float(c.values[key])
        lower_better = METRIC_META.get(key, {}).get("lower_is_better")
        change = after - before
        pct = (change / before * 100.0) if before else None
        improved = None
        if lower_better is True:
            improved = change < -1e-9
        elif lower_better is False:
            improved = change > 1e-9
        deltas[key] = {
            "title": METRIC_META.get(key, {}).get("title", key),
            "baseline": round(before, 4), "champion": round(after, 4),
            "delta": round(change, 4),
            "delta_pct": (round(pct, 1) if pct is not None else None),
            "lower_is_better": lower_better,
            "improved": improved,
        }

    reval = deltas.get("reval_scope_pct", {})
    blast = deltas.get("blast_radius", {})
    mixed = deltas.get("mixed_tier_clusters", {})
    core = deltas.get("high_tier_clusters", {})

    def reduction(d: dict[str, Any]) -> tuple[float | None, float | None]:
        if not d or d.get("baseline") in (None, 0):
            return None, None
        drop = d["baseline"] - d["champion"]
        return round(drop, 4), round(100.0 * drop / d["baseline"], 1)

    reval_pp, reval_pct = reduction(reval)
    blast_abs, blast_pct = reduction(blast)

    headline = {
        "baseline_variant": baseline,
        "champion_variant": champion,
        # The §23 headline number.
        "reval_scope_before": reval.get("baseline"),
        "reval_scope_after": reval.get("champion"),
        "reval_scope_reduction_pp": reval_pp,
        "reval_scope_reduction_pct": reval_pct,
        # The §11.3 blast-radius formula, which the constraint targets directly.
        "blast_radius_before": blast.get("baseline"),
        "blast_radius_after": blast.get("champion"),
        "blast_radius_reduction_pct": blast_pct,
        # Why it moved: the validated core is isolated and concentrated.
        "mixed_tier_before": mixed.get("baseline"),
        "mixed_tier_after": mixed.get("champion"),
        "core_clusters_before": core.get("baseline"),
        "core_clusters_after": core.get("champion"),
        # The cost, stated rather than buried.
        "coupling_before": (deltas.get("coupling") or {}).get("baseline"),
        "coupling_after": (deltas.get("coupling") or {}).get("champion"),
        "tradeoff": (
            "Isolating the validated core raises inter-cluster coupling: the "
            "regulated services now talk to adjacent ones across a boundary "
            "instead of inside a shared cluster. That is the intended trade - "
            "the Council's Strangler Fig and API-facade recommendations are how "
            "the remaining coupling gets managed."
        ),
    }
    return {"deltas": deltas, "headline": headline}
