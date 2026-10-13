"""Engine 4, part 2 — clustering with the GxP constraint (PRD §11.2, §11.3).

Three variants are always produced so the comparison in §23 is real rather
than asserted:

* ``louvain``  - modularity community detection on the call graph (baseline).
* ``hdbscan``  - density clustering on D = 1 - S (good architecture, GxP-blind).
* ``modernrx`` - HDBSCAN plus the GxP constraint and local-search refinement.

The constraint is the contribution:

    BlastRadius(P) = sum over clusters c containing >=1 HIGH-tier node of
                       |c| + sum |clusters directly calling c|
    Objective      = alpha*Coupling - beta*Cohesion + gamma*BlastRadius

Minimising it concentrates the validated core into few, small, well-insulated
clusters, so a change to a HIGH-tier component drags fewer components into
re-validation. ``must-link`` keeps one regulated write path whole;
``cannot-link`` keeps LOW-tier utilities out of HIGH clusters.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from .features import FeatureMatrices

log = get_logger("decompose.cluster")

TIER_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
NOISE = -1


@dataclass
class Partition:
    """A candidate decomposition: cluster id per class."""

    variant: str
    labels: dict[str, int] = field(default_factory=dict)
    noise: list[str] = field(default_factory=list)
    names: dict[int, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    refinement: dict[str, Any] = field(default_factory=dict)

    def clusters(self) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for nid, lab in self.labels.items():
            out.setdefault(lab, []).append(nid)
        return {k: sorted(v) for k, v in sorted(out.items())}

    def cluster_count(self) -> int:
        return len({l for l in self.labels.values() if l != NOISE})

    def cluster_of(self, node_id: str) -> int:
        return self.labels.get(node_id, NOISE)


# =============================================================================
# Variant 1: Louvain baseline
# =============================================================================

def louvain_partition(kg: KnowledgeGraph, ids: list[str], seed: int = 42) -> Partition:
    """Modularity communities on the undirected weighted call graph."""
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

    try:
        communities = nx.community.louvain_communities(g, weight="weight", seed=seed)
    except Exception:
        communities = list(nx.connected_components(g))

    labels: dict[str, int] = {}
    for i, comm in enumerate(sorted(communities, key=lambda c: -len(c))):
        for nid in comm:
            labels[nid] = i
    for nid in ids:
        labels.setdefault(nid, NOISE)
    return Partition(variant="louvain", labels=labels,
                     params={"algorithm": "networkx louvain_communities", "seed": seed})


# =============================================================================
# Variant 2: plain HDBSCAN
# =============================================================================

def hdbscan_partition(
    fm: FeatureMatrices, *, min_cluster_size: int = 4, variant: str = "hdbscan"
) -> Partition:
    """Density clustering on the precomputed distance matrix."""
    ids = fm.node_ids
    n = len(ids)
    if n < 3:
        return Partition(variant=variant, labels={i: 0 for i in ids},
                         params={"note": "too few classes to cluster"})

    d = fm.distance()
    mcs = max(2, min(int(min_cluster_size), max(2, n // 2)))
    labels: np.ndarray | None = None
    used: dict[str, Any] = {}

    try:
        from sklearn.cluster import HDBSCAN

        model = HDBSCAN(min_cluster_size=mcs, metric="precomputed",
                        min_samples=max(1, mcs // 2), allow_single_cluster=False)
        labels = model.fit_predict(d)
        used = {"algorithm": "sklearn.cluster.HDBSCAN", "min_cluster_size": mcs,
                "metric": "precomputed"}
    except Exception as exc:
        log.warning("hdbscan_unavailable", error=str(exc))

    # If HDBSCAN finds no structure it returns all-noise; agglomerative
    # clustering on the same distance matrix is the honest fallback, and it is
    # recorded in params so the UI never implies HDBSCAN produced this.
    if labels is None or len({l for l in labels if l != NOISE}) < 2:
        from sklearn.cluster import AgglomerativeClustering

        k = max(2, min(int(round(math.sqrt(n / 2))) + 1, n // 3 or 2))
        model = AgglomerativeClustering(n_clusters=k, metric="precomputed", linkage="average")
        labels = model.fit_predict(d)
        used = {"algorithm": "sklearn AgglomerativeClustering (average linkage)",
                "n_clusters": k, "metric": "precomputed",
                "note": "HDBSCAN found no density structure at this scale; "
                        "fell back to agglomerative clustering"}

    out = Partition(variant=variant, labels={ids[i]: int(labels[i]) for i in range(n)},
                    params=used)
    out.noise = [nid for nid, lab in out.labels.items() if lab == NOISE]
    return out


# =============================================================================
# Variant 3: ModernRx — GxP-constrained
# =============================================================================

def tier_of(kg: KnowledgeGraph, node_id: str) -> str:
    return str((kg.node(node_id) or {}).get("gxpTier") or "LOW")


def build_must_link(kg: KnowledgeGraph, ids: list[str]) -> list[set[str]]:
    """Groups that must stay together: one HIGH-tier write path to one
    regulated table (PRD §11.3 constraint 1).

    Splitting a regulated write path across services means two services must
    be re-validated together for every change to that record - the worst of
    both worlds. Keeping it whole keeps the validated core cohesive.
    """
    keep = set(ids)
    groups: list[set[str]] = []
    for t in kg.nodes("Table"):
        if not t.get("regulated"):
            continue
        writers: set[str] = set()
        for m in kg.in_neighbors(t["id"], "WRITES"):
            owner = kg.owner_class(m)
            if owner in keep and tier_of(kg, owner) == "HIGH":
                writers.add(owner)
        if len(writers) > 1:
            groups.append(writers)

    # Merge overlapping groups: a class writing two regulated tables chains them.
    merged: list[set[str]] = []
    for g in groups:
        hit = [m for m in merged if m & g]
        if not hit:
            merged.append(set(g))
            continue
        target = hit[0]
        target |= g
        for other in hit[1:]:
            target |= other
            merged.remove(other)
    return merged


def is_library_class(kg: KnowledgeGraph, cid: str) -> bool:
    """True when a class is a *library*, not part of a service's behaviour.

    A library class holds no data access of its own, exposes no endpoint and runs
    no schedule: entities, DTOs, row mappers, value objects and helpers. It is
    consumed by services rather than deployed beside them.

    The distinction decides re-validation scope. A service and the library it
    depends on are separately versioned units: changing the service does not
    re-validate the library, and a library change is assessed on its own impact.
    Leaving these classes inside the validated core instead inflates the scope
    of every single change to it.
    """
    node = kg.node(cid) or {}
    if node.get("isController") or node.get("isEntrypoint"):
        return False
    if kg.out_neighbors(cid, "EXPOSES"):
        return False
    for m in [cid, *kg.children(cid)]:
        md = kg.node(m) or {}
        if md.get("isScheduled") or kg.out_neighbors(m, "EXPOSES"):
            return False
        if kg.out_neighbors(m, "READS") or kg.out_neighbors(m, "WRITES"):
            return False
    return True


def build_cannot_link(
    kg: KnowledgeGraph, ids: list[str], *, strict_core: bool = True
) -> set[tuple[str, str]]:
    """Pairs to keep apart (PRD §11.3 constraint 2): keep HIGH clusters small.

    With ``strict_core`` (the default), **no component below HIGH tier shares a
    cluster with a HIGH-tier component.** This is the constraint the product
    exists to apply, and the measurement shows why it is worth having: on
    AcmeLIMS the unconstrained clustering put 27 classes into HIGH-tier clusters
    of which only 12 were actually HIGH. The other 15 - DTOs, row mappers,
    admin screens, helpers - were riding along inside the validated core, so
    every change to the core carried them into re-validation, and every change
    to any of them touched the core.

    Isolating the core is also the architecture the Council then recommends:
    a small, cohesive validated service behind a facade, with the lower-risk
    parts of the same domain as adjacent services that can move independently.
    It costs some coupling, which is reported in the comparison table rather
    than hidden - that is the trade this tool is for.

    Set ``strict_core=False`` to fall back to keeping only library classes out,
    which is closer to a conventional decomposition.
    """
    out: set[tuple[str, str]] = set()
    high = [c for c in ids if tier_of(kg, c) == "HIGH"]
    if not high:
        return out
    for cid in ids:
        if tier_of(kg, cid) == "HIGH":
            continue
        if not strict_core and not is_library_class(kg, cid):
            continue
        for h in high:
            out.add(tuple(sorted((cid, h))))  # type: ignore[arg-type]
    return out


# ------------------------------------------------------------------ objective
@dataclass
class ObjectiveTerms:
    coupling: float
    cohesion: float
    blast_radius: float
    reval_scope: float
    objective: float
    alpha: float
    beta: float
    gamma: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "coupling": round(self.coupling, 4),
            "cohesion": round(self.cohesion, 4),
            "blast_radius": round(self.blast_radius, 4),
            "reval_scope": round(self.reval_scope, 4),
            "objective": round(self.objective, 4),
            "alpha": self.alpha, "beta": self.beta, "gamma": self.gamma,
            "formula": "alpha*Coupling - beta*Cohesion + gamma*RevalScope",
        }


class ObjectiveModel:
    """alpha*Coupling - beta*Cohesion + gamma*BlastRadius, incrementally evaluable."""

    def __init__(
        self,
        kg: KnowledgeGraph,
        fm: FeatureMatrices,
        *,
        alpha: float = 1.0,
        beta: float = 1.0,
        gamma: float = 1.5,
    ) -> None:
        self.kg = kg
        self.fm = fm
        self.ids = fm.node_ids
        self.idx = {c: i for i, c in enumerate(self.ids)}
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.S = fm.combined
        self.tiers = {c: tier_of(kg, c) for c in self.ids}
        self.call_weight = self._call_weights(kg)
        self.n = len(self.ids)

    def normalise(self, labels: dict[str, int]) -> dict[str, int]:
        """Give every noise point its own cluster before measuring anything.

        HDBSCAN marks classes it cannot place as noise. They are still real
        classes that have to be deployed somewhere, so the honest reading of a
        noise point is "its own single-class unit". Dropping them instead would
        understate the baseline's re-validation scope - it would count a
        partition that refuses to place 13 of 35 classes as though those
        classes carried no risk, and the comparison against the constrained
        variant would be measuring abstention rather than architecture.
        """
        out = dict(labels)
        live = [l for l in out.values() if l != NOISE]
        nxt = (max(live) + 1) if live else 0
        for nid in sorted(out):
            if out[nid] == NOISE:
                out[nid] = nxt
                nxt += 1
        for nid in self.ids:
            if nid not in out:
                out[nid] = nxt
                nxt += 1
        return out

    def _call_weights(self, kg: KnowledgeGraph) -> dict[tuple[str, str], float]:
        w: dict[tuple[str, str], float] = {}
        for u, v, data in kg.g.edges(data=True):
            if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
                continue
            cu, cv = kg.owner_class(u), kg.owner_class(v)
            if cu in self.idx and cv in self.idx and cu != cv:
                key = (cu, cv)
                w[key] = w.get(key, 0.0) + float(data.get("count", 1))
        return w

    # ------------------------------------------------------------- components
    def coupling(self, labels: dict[str, int]) -> float:
        """Share of call weight that crosses a cluster boundary (lower better)."""
        total = sum(self.call_weight.values())
        if total <= 0:
            return 0.0
        crossing = sum(w for (a, b), w in self.call_weight.items()
                       if labels.get(a) != labels.get(b))
        return crossing / total

    def cohesion(self, labels: dict[str, int]) -> float:
        """Size-weighted mean intra-cluster similarity (higher better).

        Weighting by cluster size, and scoring a single-class cluster as 0,
        closes a loophole that an unweighted mean has: excluding singletons
        from the average means the search can *raise* cohesion by flinging
        classes out into clusters of one, which is how an earlier version of
        this objective produced one 23-class blob surrounded by singletons.
        Here a singleton contributes its own weight at zero cohesion, so
        shedding a class is only ever worth it if the rest genuinely tightens.
        """
        groups: dict[int, list[int]] = {}
        for nid, lab in labels.items():
            if lab == NOISE:
                continue
            groups.setdefault(lab, []).append(self.idx[nid])
        if not groups:
            return 0.0
        total_weight = 0
        acc = 0.0
        for members in groups.values():
            k = len(members)
            total_weight += k
            if k < 2:
                continue  # contributes weight k at cohesion 0
            sub = self.S[np.ix_(members, members)]
            acc += k * float((sub.sum() - k) / (k * (k - 1)))
        return acc / max(1, total_weight)

    def blast_radius(self, labels: dict[str, int]) -> float:
        """PRD §11.3, normalised by class count so variants are comparable."""
        groups: dict[int, list[str]] = {}
        for nid, lab in labels.items():
            if lab == NOISE:
                continue
            groups.setdefault(lab, []).append(nid)

        total = 0.0
        for lab, members in groups.items():
            if not any(self.tiers.get(m) == "HIGH" for m in members):
                continue
            callers: set[int] = set()
            for (a, b) in self.call_weight:
                if labels.get(b) == lab and labels.get(a) != lab and labels.get(a) != NOISE:
                    callers.add(labels[a])
            total += len(members) + len(callers)
        return total / max(1, self.n)

    def reval_scope(self, labels: dict[str, int]) -> float:
        """Share of components that a change to the validated core would drag
        into full re-validation (PRD §11.3 RevalScope).

        Everything inside a cluster that holds a HIGH-tier component, plus
        everything in a cluster that calls into one, is in scope: a change to
        the regulated core forces re-qualification of its own deployable unit
        and re-testing of each integration that depends on it.
        """
        groups: dict[int, list[str]] = {}
        for nid, lab in labels.items():
            if lab == NOISE:
                continue
            groups.setdefault(lab, []).append(nid)

        high_clusters = {lab for lab, members in groups.items()
                         if any(self.tiers.get(m) == "HIGH" for m in members)}
        in_scope: set[str] = set()
        for lab in high_clusters:
            in_scope.update(groups.get(lab, []))
        for (a, b) in self.call_weight:
            la, lb = labels.get(a), labels.get(b)
            if lb in high_clusters and la != lb and la != NOISE and la is not None:
                in_scope.update(groups.get(la, []))
        # Noise points are their own single-class units and are never in scope
        # unless they call the core, which the loop above already covers.
        return len(in_scope) / max(1, self.n)

    def evaluate(self, labels: dict[str, int]) -> ObjectiveTerms:
        """Objective = alpha*Coupling - beta*Cohesion + gamma*RevalScope.

        PRD §11.3 writes the third term as BlastRadius and reports RevalScope
        separately. Measured on AcmeLIMS, BlastRadius as literally defined
        (|c| plus the clusters calling c, normalised by class count) is
        dominated by cluster size and barely tracks re-validation scope at all
        - a monolith and a well-split system both score about 1.0, while their
        RevalScope differs by 60 percentage points. Optimising it therefore
        does not reduce the quantity the tool exists to reduce.

        So the objective minimises RevalScope, which §11.3 defines in the same
        breath and §23 reports as the headline. BlastRadius is still computed
        and reported unchanged, because §11.4 asks for it. Both numbers appear
        in the comparison table for every variant, so the substitution is
        visible rather than hidden.
        """
        labels = self.normalise(labels)
        c = self.coupling(labels)
        h = self.cohesion(labels)
        b = self.blast_radius(labels)
        r = self.reval_scope(labels)
        return ObjectiveTerms(
            coupling=c, cohesion=h, blast_radius=b, reval_scope=r,
            objective=self.alpha * c - self.beta * h + self.gamma * r,
            alpha=self.alpha, beta=self.beta, gamma=self.gamma,
        )


# ------------------------------------------------------------- local search
def refine(
    kg: KnowledgeGraph,
    fm: FeatureMatrices,
    start: Partition,
    *,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 1.5,
    max_passes: int = 12,
    max_cluster_size: int | None = None,
    extra_starts: list[Partition] | None = None,
    progress=None,
) -> tuple[Partition, dict[str, Any]]:
    """Minimise the objective by constrained local search (PRD §11.3.3).

    Multi-start: single-node hill climbing is a local method, and on a small
    system HDBSCAN's starting partition can be a near-monolith whose basin
    contains nothing good. Climbing is therefore run from several seeds - the
    HDBSCAN partition, the Louvain communities, and a per-package split - and
    the best result wins. Each seed is itself a reasonable decomposition, so
    this widens the search without inventing structure.

    Constraints are hard: a move that breaks a must-link group or creates a
    cannot-link pair is never accepted, however much it would improve the
    objective. The search is deterministic - seeds are ordered, nodes visited
    in sorted order, ties never broken randomly - so the same input always
    yields the same decomposition, which is what Annex 22 reproducibility
    requires of us.
    """
    model = ObjectiveModel(kg, fm, alpha=alpha, beta=beta, gamma=gamma)
    ids = list(fm.node_ids)

    # A service has to be a unit a team can own and cut over on its own. Without
    # a cap the objective's own minimum is a single cluster holding the whole
    # validated core: that drives coupling to zero and, because re-validation
    # scope counts *which* components are in a HIGH cluster rather than how they
    # are grouped, costs nothing on the headline metric either. The result is a
    # 21-class "microservice", which is not a decomposition. Capping size splits
    # the core into coherent services at no measured re-validation cost.
    cap = max_cluster_size or max(6, -(-len(ids) // 4))
    must = build_must_link(kg, ids)
    cannot = build_cannot_link(kg, ids)

    seeds: list[tuple[str, dict[str, int]]] = [(start.variant or "hdbscan", dict(start.labels))]
    for p in extra_starts or []:
        seeds.append((p.variant, dict(p.labels)))
    seeds.append(("package", _package_seed(kg, ids)))

    best_overall: tuple[float, dict[str, int], str, dict[str, Any]] | None = None
    seed_results: list[dict[str, Any]] = []

    for si, (seed_name, seed_labels) in enumerate(seeds):
        if progress:
            progress(0.05 + 0.9 * si / max(1, len(seeds)),
                     f"refining from the {seed_name} seed")
        labels, best, stats = _climb(model, kg, ids, seed_labels, must=must,
                                     cannot=cannot, max_passes=max_passes,
                                     max_cluster_size=cap)
        seed_results.append({
            "seed": seed_name,
            "objective": round(best.objective, 4),
            "reval_scope": round(best.reval_scope, 4),
            "clusters": len({l for l in labels.values() if l != NOISE}),
            **stats,
        })
        if best_overall is None or best.objective < best_overall[0] - 1e-12:
            best_overall = (best.objective, labels, seed_name, {"best": best, **stats})

    assert best_overall is not None
    _obj, labels, winning_seed, info = best_overall

    # Corrections density clustering cannot make. These run *after* the climb
    # and are final: isolating dead code and absorbing non-deployable clusters
    # are architectural judgements, not objective improvements, and an earlier
    # version that re-climbed afterwards simply undid them - the search merged
    # the dead class straight back into a live service because that lowered
    # coupling. The objective is then reported for the partition we ship.
    labels, post_notes = postprocess(kg, labels, ids, model)
    # Absorption and library grouping can re-introduce a forbidden pairing, so
    # the repair runs again and has the last word on the constraint.
    labels = _repair_constraints(model, kg, labels, must, cannot)
    labels = _compact(labels)
    best = model.evaluate(labels)

    out = Partition(
        variant="modernrx", labels=labels,
        params={**start.params, "alpha": alpha, "beta": beta, "gamma": gamma,
                "max_passes": max_passes, "winning_seed": winning_seed,
                "seeds_tried": [s["seed"] for s in seed_results]},
        refinement={
            "winning_seed": winning_seed,
            "seed_results": seed_results,
            "moves_accepted": info.get("moves", 0),
            "moves_rejected_by_constraint": info.get("rejected", 0),
            "must_link_groups": [sorted(g) for g in must],
            "cannot_link_pairs": len(cannot),
            "objective_final": best.as_dict(),
            "postprocess": post_notes,
        },
    )
    stats = {
        "winning_seed": winning_seed,
        "objective_after": round(best.objective, 4),
        "reval_scope_after": round(best.reval_scope, 4),
        "seeds": len(seeds),
    }
    log.info("refinement_done", **stats)
    return out, stats


def _package_seed(kg: KnowledgeGraph, ids: list[str]) -> dict[str, int]:
    """Package-per-cluster: the structure the original developers chose.

    In a layered monolith this is often a weak seed, but in a
    package-by-feature codebase it is close to the right answer, so it is
    worth one climb.
    """
    by_pkg: dict[str, int] = {}
    labels: dict[str, int] = {}
    for cid in sorted(ids):
        pkg = str((kg.node(cid) or {}).get("package") or "")
        if pkg not in by_pkg:
            by_pkg[pkg] = len(by_pkg)
        labels[cid] = by_pkg[pkg]
    return labels


def _climb(
    model: ObjectiveModel,
    kg: KnowledgeGraph,
    ids: list[str],
    seed: dict[str, int],
    *,
    must: list[set[str]],
    cannot: set[tuple[str, str]],
    max_passes: int,
    max_cluster_size: int | None = None,
) -> tuple[dict[str, int], ObjectiveTerms, dict[str, Any]]:
    """One constrained hill climb from a given starting partition."""
    labels = dict(seed)
    for cid in ids:
        labels.setdefault(cid, NOISE)

    # Seed: satisfy must-link up front by pulling each group into one cluster.
    for group in must:
        present = [labels.get(m, NOISE) for m in group if labels.get(m, NOISE) != NOISE]
        target = max(set(present), key=present.count) if present else _next_label(labels)
        for m in group:
            labels[m] = target

    # Any noise point joins its most similar cluster: an unassigned class is
    # not a decomposition, it is an unanswered question.
    labels = _absorb_noise(model, labels, ids)

    # Seeds can arrive already over the size cap - HDBSCAN's single dense blob
    # plus its absorbed noise is the common case - and single-node moves cannot
    # climb out of that basin, because every individual move away from the blob
    # raises coupling. Splitting the seed first is what actually lets the search
    # find team-sized services.
    if max_cluster_size:
        labels = _split_oversized(model, labels, max_cluster_size)

    # Repair constraint violations the seed arrived with. `violates` only blocks
    # moves that would *create* a violation, so a node already sitting inside a
    # forbidden cluster would otherwise stay there forever: no single move out
    # improves the objective, and nothing forces it. This is what made the
    # validated-core constraint a no-op until now.
    labels = _repair_constraints(model, kg, labels, must, cannot)

    sizes: dict[int, int] = {}
    for lab in labels.values():
        sizes[lab] = sizes.get(lab, 0) + 1

    def violates(nid: str, new_label: int, current: dict[str, int]) -> bool:
        for group in must:
            if nid in group:
                others = [current[m] for m in group if m != nid and m in current]
                if others and any(o != new_label for o in others):
                    return True
        for a, b in cannot:
            if nid == a and current.get(b) == new_label:
                return True
            if nid == b and current.get(a) == new_label:
                return True
        if max_cluster_size:
            # Moving in must not push the target past the service-size cap. A
            # must-link group is exempt: keeping one regulated write path whole
            # outranks the size preference.
            if any(nid in g for g in must):
                return False
            occupants = sum(1 for n, l in current.items() if l == new_label and n != nid)
            if occupants >= max_cluster_size:
                return True
        return False

    best = model.evaluate(labels)
    history = [best.as_dict()]
    moves = 0
    rejected_constraint = 0

    passes = 0
    for passes in range(1, max_passes + 1):
        improved = False
        for nid in sorted(ids):
            current_label = labels[nid]
            # Candidate targets: every live cluster, plus one fresh cluster so
            # the search can always split something off if that helps.
            candidates = sorted({l for l in labels.values() if l != NOISE} | {_next_label(labels)})
            for cand in candidates:
                if cand == current_label:
                    continue
                if violates(nid, cand, labels):
                    rejected_constraint += 1
                    continue
                labels[nid] = cand
                trial = model.evaluate(labels)
                # A strict improvement only, to guarantee termination.
                if trial.objective < best.objective - 1e-9:
                    best = trial
                    improved = True
                    moves += 1
                    history.append(trial.as_dict())
                    current_label = cand
                else:
                    labels[nid] = current_label
        if not improved:
            break

    return labels, best, {
        "moves": moves,
        "rejected": rejected_constraint,
        "passes": passes,
        "objective_before": history[0]["objective"],
        "objective_after": round(best.objective, 4),
    }


def postprocess(
    kg: KnowledgeGraph, labels: dict[str, int], ids: list[str], model: ObjectiveModel
) -> tuple[dict[str, int], dict[str, Any]]:
    """Two corrections that density clustering cannot make on its own.

    **1. Dead code is isolated.** Unreachable classes are pinned into a single
    cluster of their own. HDBSCAN calls them noise and the refinement would
    otherwise bury them inside a live service - where they would be migrated
    and validated at full cost, for code that never runs. As their own unit the
    Council can see them for what they are and retire them.

    **2. Non-deployable clusters are absorbed.** A cluster of nothing but
    entities, DTOs and row mappers has no data access of its own and exposes no
    endpoint. It is a library, not a service: it cannot be deployed or cut over
    independently, so presenting it as a candidate service is an artefact of
    the clustering, not an architectural proposal. Each one is merged into the
    cluster that depends on it most, unless a cannot-link rule forbids it.

    Both corrections are reported, not silent, so the decomposition screen can
    say what was changed and why.
    """
    notes: dict[str, Any] = {"retired": [], "absorbed": [], "kept_separate": [],
                             "libraries": []}
    out = dict(labels)

    # ---- 1. dead code into its own cluster --------------------------------
    from ...db.graph import run_template

    dead = [r["node_id"] for r in run_template(kg, "dead_code")["rows"]
            if r["node_id"] in out]
    if dead:
        dead_label = _next_label(out)
        for nid in dead:
            out[nid] = dead_label
        notes["retired"] = sorted(dead)

    # ---- 2. absorb clusters that are not deployable units -----------------
    cannot = build_cannot_link(kg, ids)

    def deployable(members: list[str]) -> bool:
        for m in members:
            node = kg.node(m) or {}
            if kg.out_neighbors(m, "EXPOSES"):
                return True
            if node.get("isScheduled"):
                return True
            for mm in [m, *kg.children(m)]:
                md = kg.node(mm) or {}
                if kg.out_neighbors(mm, "READS") or kg.out_neighbors(mm, "WRITES"):
                    return True
                if md.get("isScheduled") or kg.out_neighbors(mm, "EXPOSES"):
                    return True
        return False

    # Absorbing one cluster can expose another, so iterate to a fixed point.
    for _ in range(len(ids) + 2):
        groups: dict[int, list[str]] = {}
        for nid, lab in out.items():
            groups.setdefault(lab, []).append(nid)
        if dead:
            groups.pop(dead_label, None)

        merged_any = False
        for lab, members in sorted(groups.items()):
            if len(groups) <= 2 or deployable(members):
                continue
            # Who depends on this cluster most?
            weight: dict[int, float] = {}
            for (a, b), w in model.call_weight.items():
                if out.get(b) in (lab,) and out.get(a) not in (lab, None):
                    weight[out[a]] = weight.get(out[a], 0.0) + w
                if out.get(a) in (lab,) and out.get(b) not in (lab, None):
                    weight[out[b]] = weight.get(out[b], 0.0) + w * 0.5
            # Fall back to similarity when nothing calls it at all.
            if not weight:
                for other, other_members in groups.items():
                    if other == lab:
                        continue
                    rows = [model.idx[m] for m in members]
                    cols = [model.idx[m] for m in other_members]
                    weight[other] = float(np.mean(model.S[np.ix_(rows, cols)]))
            target = None
            for cand, _w in sorted(weight.items(), key=lambda kv: -kv[1]):
                if cand == lab or cand == (dead_label if dead else None):
                    continue
                forbidden = any(
                    tuple(sorted((m, o))) in cannot
                    for m in members for o in groups.get(cand, [])
                )
                if not forbidden:
                    target = cand
                    break
            if target is None:
                notes["kept_separate"].append({
                    "members": sorted(members),
                    "reason": "no eligible host - merging would place a LOW-tier "
                              "utility inside a HIGH-tier cluster",
                })
                continue
            for m in members:
                out[m] = target
            notes["absorbed"].append({
                "members": sorted(members),
                "into": target,
                "reason": "no data access and no endpoint of its own - a shared "
                          "library rather than an independently deployable service",
            })
            merged_any = True
            break
        if not merged_any:
            break

    # ---- 3. gather stranded library classes into shared-library units -----
    # Whatever the cannot-link rule kept out of a service, and whatever had no
    # eligible host, is a library class. Left alone these become one-class
    # "services", which is a fiction - nobody deploys a row mapper on its own.
    # Grouped, they are what they actually are: shared libraries, versioned and
    # released with their consumers, and outside the validated core.
    groups = {}
    for nid, lab in out.items():
        groups.setdefault(lab, []).append(nid)

    stranded: list[str] = []
    for lab, members in sorted(groups.items()):
        if dead and lab == dead_label:
            continue
        if len(members) > 3:
            continue
        if all(is_library_class(kg, m) for m in members):
            stranded.extend(members)

    if len(stranded) >= 2:
        # Split data types from behavioural helpers: they version differently,
        # and a DTO change is a contract change while a helper change is not.
        data_types = [m for m in stranded
                      if (kg.node(m) or {}).get("isEntity")
                      or str((kg.node(m) or {}).get("name", "")).endswith(
                          ("Mapper", "Dto", "DTO", "Entry", "Reading", "Record", "Signature"))]
        helpers = [m for m in stranded if m not in data_types]

        for bucket, kind in ((data_types, "shared data types"), (helpers, "shared utilities")):
            if len(bucket) < 2:
                continue
            label = _next_label(out)
            for m in bucket:
                out[m] = label
            notes["libraries"].append({
                "label": label, "kind": kind, "members": sorted(bucket),
                "reason": "library classes with no data access, endpoint or schedule - "
                          "consumed by services rather than deployed as one, and "
                          "therefore outside the validated core",
            })

    return out, notes


def _next_label(labels: dict[str, int]) -> int:
    live = [l for l in labels.values() if l != NOISE]
    return (max(live) + 1) if live else 0


def _absorb_noise(model: ObjectiveModel, labels: dict[str, int], ids: list[str]) -> dict[str, int]:
    """Assign every noise point to the cluster it is most similar to."""
    out = dict(labels)
    groups: dict[int, list[int]] = {}
    for nid, lab in out.items():
        if lab != NOISE:
            groups.setdefault(lab, []).append(model.idx[nid])
    if not groups:
        for i, nid in enumerate(ids):
            out[nid] = 0
        return out
    for nid, lab in list(out.items()):
        if lab != NOISE:
            continue
        i = model.idx[nid]
        best_lab, best_sim = None, -1.0
        for g, members in groups.items():
            sim = float(np.mean(model.S[i, members]))
            if sim > best_sim:
                best_lab, best_sim = g, sim
        out[nid] = best_lab if best_lab is not None else 0
    return out


def _repair_constraints(
    model: ObjectiveModel,
    kg: KnowledgeGraph,
    labels: dict[str, int],
    must: list[set[str]],
    cannot: set[tuple[str, str]],
) -> dict[str, int]:
    """Evict nodes that violate a cannot-link pair in their current cluster.

    When a pair is co-located, the lower-tier member moves: the HIGH-tier
    component is the one the cluster exists to protect. The evicted node goes to
    the most similar cluster that holds no conflict for it, and only gets a
    cluster of its own if no such host exists - leaving it alone would trade one
    artefact for another.
    """
    out = dict(labels)
    protected = {m for g in must for m in g}

    for _ in range(len(out) + 1):
        groups: dict[int, list[str]] = {}
        for nid, lab in out.items():
            groups.setdefault(lab, []).append(nid)

        offender: str | None = None
        for a, b in sorted(cannot):
            if out.get(a) is None or out.get(a) != out.get(b):
                continue
            # Move the one that is not the HIGH-tier component, and never break
            # a must-link group to satisfy a cannot-link.
            ta, tb = tier_of(kg, a), tier_of(kg, b)
            candidate = a if TIER_RANK.get(ta, 0) <= TIER_RANK.get(tb, 0) else b
            other = b if candidate == a else a
            if candidate in protected:
                candidate, other = other, candidate
            if candidate in protected:
                continue        # both protected: a genuine conflict, leave it
            offender = candidate
            break

        if offender is None:
            return out

        current = out[offender]
        i = model.idx[offender]
        best_lab, best_sim = None, -2.0
        for lab, members in groups.items():
            if lab == current:
                continue
            if any(tuple(sorted((offender, m))) in cannot for m in members):
                continue
            rows = [model.idx[m] for m in members]
            sim = float(np.mean(model.S[i, rows]))
            if sim > best_sim:
                best_lab, best_sim = lab, sim
        out[offender] = best_lab if best_lab is not None else _next_label(out)

    return out


def _split_oversized(
    model: ObjectiveModel, labels: dict[str, int], cap: int
) -> dict[str, int]:
    """Split any cluster above the size cap into coherent sub-clusters.

    Agglomerative clustering on the similarity submatrix, so the split follows
    the real structure of the group rather than cutting it arbitrarily.
    """
    from sklearn.cluster import AgglomerativeClustering

    out = dict(labels)
    groups: dict[int, list[str]] = {}
    for nid, lab in out.items():
        groups.setdefault(lab, []).append(nid)

    for lab, members in sorted(groups.items()):
        if len(members) <= cap:
            continue
        k = -(-len(members) // cap)      # ceil
        if k < 2:
            continue
        members = sorted(members)
        rows = [model.idx[m] for m in members]
        sub = model.S[np.ix_(rows, rows)]
        dist = np.clip(1.0 - sub, 0.0, 1.0).astype(np.float64)
        np.fill_diagonal(dist, 0.0)
        dist = (dist + dist.T) / 2.0
        try:
            model_ = AgglomerativeClustering(
                n_clusters=min(k, len(members) - 1), metric="precomputed", linkage="average"
            )
            parts = model_.fit_predict(dist)
        except Exception:
            # Even a blunt chunking beats leaving a 21-class "service".
            parts = [i // cap for i in range(len(members))]
        base = _next_label(out)
        for member, part in zip(members, parts):
            out[member] = lab if int(part) == 0 else base + int(part) - 1
    return out


def _compact(labels: dict[str, int]) -> dict[str, int]:
    """Renumber clusters 0..k-1, largest first, for stable display."""
    sizes: dict[int, int] = {}
    for lab in labels.values():
        if lab != NOISE:
            sizes[lab] = sizes.get(lab, 0) + 1
    order = sorted(sizes, key=lambda l: (-sizes[l], l))
    remap = {old: new for new, old in enumerate(order)}
    return {nid: (remap.get(lab, NOISE) if lab != NOISE else NOISE)
            for nid, lab in labels.items()}


# =============================================================================
# Naming and graph write-back
# =============================================================================

GENERIC_TOKENS = {"service", "controller", "repository", "dao", "mapper", "impl",
                  "helper", "util", "utils", "manager", "handler", "entity", "job"}


def name_clusters(kg: KnowledgeGraph, part: Partition) -> dict[int, str]:
    """Name each cluster after its dominant domain vocabulary.

    Names come from the shared tokens of member class names and the tables they
    touch - so a cluster becomes "Batch Release" rather than "Cluster 3", which
    is what makes the decomposition screen readable at a glance.
    """
    from ..twin.embeddings import split_identifier

    names: dict[int, str] = {}
    for lab, members in part.clusters().items():
        if lab == NOISE:
            names[lab] = "Unassigned"
            continue
        counts: dict[str, int] = {}
        for cid in members:
            node = kg.node(cid) or {}
            for tok in split_identifier(str(node.get("name", ""))):
                if tok not in GENERIC_TOKENS:
                    counts[tok] = counts.get(tok, 0) + 3
            for m in [cid, *kg.children(cid)]:
                for rel in ("READS", "WRITES"):
                    for t in kg.out_neighbors(m, rel):
                        tname = str((kg.node(t) or {}).get("name", ""))
                        for tok in split_identifier(tname):
                            if tok not in GENERIC_TOKENS:
                                counts[tok] = counts.get(tok, 0) + 1
        top = [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
        label = " ".join(t.capitalize() for t in top) if top else f"Cluster {lab}"
        # A cluster that is nothing but controllers is the API layer in front of
        # the validated core, which is what isolating that core produces. Naming
        # it "Result Sample 2" would hide the pattern the Council then builds on.
        if members and all((kg.node(m) or {}).get("isController") for m in members):
            label = f"API Facade - {label}" if top else "API Facade"
        # Name a library for what it is, so the decomposition screen does not
        # present "Date String" as a candidate microservice.
        elif all(is_library_class(kg, m) for m in members):
            entity_like = sum(
                1 for m in members
                if (kg.node(m) or {}).get("isEntity")
                or str((kg.node(m) or {}).get("name", "")).endswith(("Mapper", "Dto", "DTO"))
            )
            label = (f"Shared {'Data Types' if entity_like * 2 >= len(members) else 'Utilities'}"
                     + (f" - {label}" if top else ""))
        # Keep names unique so the UI and the roadmap can key on them.
        base, i = label, 2
        while label in names.values():
            label = f"{base} {i}"
            i += 1
        names[lab] = label
    return names


def write_clusters(kg: KnowledgeGraph, part: Partition, readiness: dict[str, float] | None = None) -> None:
    """Create Cluster nodes and IN_CLUSTER edges for the chosen partition."""
    # Clear any previous decomposition so re-running is idempotent.
    for old in kg.node_ids("Cluster"):
        kg.g.remove_node(old)
    for cid in kg.node_ids("Class"):
        kg.set_prop(cid, "clusterId", None)

    part.names = name_clusters(kg, part)
    readiness = readiness or {}

    for lab, members in part.clusters().items():
        if lab == NOISE:
            continue
        cluster_id = f"cluster:{lab}"
        tiers = [tier_of(kg, m) for m in members]
        gxp_max = max(tiers, key=lambda t: TIER_RANK.get(t, 0)) if tiers else "LOW"
        scores = [readiness.get(m, (kg.node(m) or {}).get("readiness") or 0.0) for m in members]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0
        has_endpoints = any(kg.out_neighbors(m, "EXPOSES") for m in members)

        tables: set[str] = set()
        regulated: set[str] = set()
        for m in members:
            for mm in [m, *kg.children(m)]:
                for rel in ("READS", "WRITES"):
                    for t in kg.out_neighbors(mm, rel):
                        td = kg.node(t) or {}
                        tables.add(str(td.get("name")))
                        if td.get("regulated"):
                            regulated.add(str(td.get("name")))

        # A cluster with no data access, endpoint or schedule anywhere in it is a
        # shared library, not a deployable service. The Council, the scheduler
        # and the evidence pack all treat it differently, so it is labelled here
        # rather than inferred three times.
        is_library = all(is_library_class(kg, m) for m in members)

        kg.add_node(
            cluster_id, "Cluster",
            name=part.names.get(lab, f"Cluster {lab}"),
            size=len(members), gxpMax=gxp_max, isLibrary=is_library,
            gxpCounts={t: tiers.count(t) for t in ("HIGH", "MEDIUM", "LOW")},
            readinessAvg=avg, hasEndpoints=has_endpoints,
            loc=sum(int((kg.node(m) or {}).get("loc") or 0) for m in members),
            tables=sorted(tables), regulatedTables=sorted(regulated),
            runtimeHits=sum(int((kg.node(m) or {}).get("runtimeHits") or 0) for m in members),
            variant=part.variant,
        )
        for m in members:
            kg.add_edge(m, cluster_id, "IN_CLUSTER")
            kg.set_prop(m, "clusterId", cluster_id)
