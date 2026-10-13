"""Engine 4, part 1 — the similarity matrix of PRD §11.1.

    S(i,j) = w1*Structural + w2*Runtime + w3*Data + w4*CoChange + w5*Semantic
    default w = [0.30, 0.20, 0.25, 0.10, 0.15]

Each term is built independently, normalised to [0, 1], and kept so the UI can
show *why* two classes were grouped. When a signal is absent for a project (no
traces, no git history) its weight is redistributed over the remaining terms
rather than silently scoring every pair as dissimilar — a missing measurement
must not masquerade as evidence of difference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph

log = get_logger("decompose.features")

TERMS = ("structural", "runtime", "data", "cochange", "semantic")


@dataclass
class FeatureMatrices:
    node_ids: list[str] = field(default_factory=list)
    terms: dict[str, np.ndarray] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    available: dict[str, bool] = field(default_factory=dict)
    combined: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))

    @property
    def n(self) -> int:
        return len(self.node_ids)

    def distance(self) -> np.ndarray:
        """D = 1 - S, with an exact zero diagonal (HDBSCAN requires it)."""
        d = (1.0 - self.combined).astype(np.float64)
        np.fill_diagonal(d, 0.0)
        d = (d + d.T) / 2.0          # enforce exact symmetry
        return np.clip(d, 0.0, 1.0)

    def explain_pair(self, a: str, b: str) -> dict[str, Any]:
        """Per-term contribution for one pair — the UI's 'why these together?'."""
        if a not in self.node_ids or b not in self.node_ids:
            return {}
        i, j = self.node_ids.index(a), self.node_ids.index(b)
        contributions = {
            t: {
                "raw": round(float(self.terms[t][i, j]), 4),
                "weight": round(self.weights.get(t, 0.0), 4),
                "contribution": round(float(self.terms[t][i, j]) * self.weights.get(t, 0.0), 4),
            }
            for t in TERMS if t in self.terms
        }
        return {
            "a": a, "b": b,
            "similarity": round(float(self.combined[i, j]), 4),
            "terms": contributions,
        }


def _normalise(m: np.ndarray) -> np.ndarray:
    """Scale to [0, 1] by the maximum off-diagonal value."""
    if m.size == 0:
        return m
    work = m.astype(np.float32).copy()
    np.fill_diagonal(work, 0.0)
    peak = float(work.max())
    if peak > 0:
        work = work / peak
    np.fill_diagonal(work, 1.0)
    return np.clip(work, 0.0, 1.0)


def _symmetrise(m: np.ndarray) -> np.ndarray:
    return np.maximum(m, m.T)


# =============================================================================
# The five terms
# =============================================================================

def structural_matrix(kg: KnowledgeGraph, ids: list[str]) -> np.ndarray:
    """Static calls and dependencies between classes, log-damped.

    Log damping matters: one class calling another 400 times is more coupled
    than one calling it twice, but not 200 times more coupled.
    """
    n = len(ids)
    idx = {c: i for i, c in enumerate(ids)}
    m = np.zeros((n, n), dtype=np.float32)
    for u, v, data in kg.g.edges(data=True):
        if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
            continue
        cu, cv = kg.owner_class(u), kg.owner_class(v)
        if cu is None or cv is None or cu == cv:
            continue
        if cu not in idx or cv not in idx:
            continue
        w = float(data.get("count", 1))
        m[idx[cu], idx[cv]] += np.log1p(w)
    m = _symmetrise(m)
    np.fill_diagonal(m, 0.0)
    return _normalise(m)


def runtime_matrix(kg: KnowledgeGraph, ids: list[str]) -> tuple[np.ndarray, bool]:
    """Co-occurrence in traces of the same use case (the Mono2Micro signal).

    Two classes that always appear together serving one business transaction
    belong in one service, whatever the static graph says. Cosine over the
    use-case hit vectors, which normalises away raw traffic volume.
    """
    n = len(ids)
    idx = {c: i for i, c in enumerate(ids)}
    usecases = kg.node_ids("UseCase")
    if not usecases:
        return np.zeros((n, n), dtype=np.float32), False

    vectors = np.zeros((n, len(usecases)), dtype=np.float32)
    for k, uid in enumerate(usecases):
        for member in kg.in_neighbors(uid, "PART_OF_USECASE"):
            cid = member if member in idx else kg.owner_class(member)
            if cid is None or cid not in idx:
                continue
            hits = 0
            for d in (kg.g.get_edge_data(member, uid) or {}).values():
                if d.get("rel") == "PART_OF_USECASE":
                    hits = max(hits, int(d.get("hits", 0)))
            vectors[idx[cid], k] += float(hits)

    if not vectors.any():
        return np.zeros((n, n), dtype=np.float32), False

    vectors = np.log1p(vectors)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = vectors / norms
    m = (unit @ unit.T).astype(np.float32)
    np.fill_diagonal(m, 1.0)
    return np.clip(m, 0.0, 1.0), True


def data_matrix(kg: KnowledgeGraph, ids: list[str]) -> tuple[np.ndarray, bool]:
    """Jaccard overlap of the tables each class touches.

    Writes count double: two classes writing one table are far more coupled
    than two merely reading it, and that asymmetry is exactly what decides
    whether a boundary is drawable.
    """
    n = len(ids)
    reads: list[set[str]] = []
    writes: list[set[str]] = []
    for cid in ids:
        r: set[str] = set()
        w: set[str] = set()
        for m_ in [cid, *kg.children(cid)]:
            w |= set(kg.out_neighbors(m_, "WRITES"))
            r |= set(kg.out_neighbors(m_, "READS"))
        reads.append(r - w)
        writes.append(w)

    if not any(reads) and not any(writes):
        return np.zeros((n, n), dtype=np.float32), False

    m = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            all_i, all_j = reads[i] | writes[i], reads[j] | writes[j]
            if not all_i or not all_j:
                continue
            union = all_i | all_j
            shared_writes = writes[i] & writes[j]
            shared_any = all_i & all_j
            score = (len(shared_any) + len(shared_writes)) / (len(union) + len(shared_writes))
            m[i, j] = m[j, i] = score
    np.fill_diagonal(m, 1.0)
    return _normalise(m), True


def cochange_matrix(kg: KnowledgeGraph, ids: list[str]) -> tuple[np.ndarray, bool]:
    """CO_CHANGES edges written by the git-mining stage."""
    n = len(ids)
    idx = {c: i for i, c in enumerate(ids)}
    m = np.zeros((n, n), dtype=np.float32)
    found = False
    for u, v, data in kg.g.edges(data=True):
        if data.get("rel") != "CO_CHANGES":
            continue
        if u not in idx or v not in idx:
            continue
        w = float(data.get("weight", 0.0))
        if w <= 0:
            continue
        found = True
        i, j = idx[u], idx[v]
        m[i, j] = m[j, i] = max(m[i, j], w)
    np.fill_diagonal(m, 1.0)
    return (_normalise(m), True) if found else (m, False)


def semantic_matrix(ids: list[str], emb) -> tuple[np.ndarray, bool]:
    """Cosine similarity of the identifier embeddings."""
    n = len(ids)
    if emb is None or not getattr(emb, "node_ids", None):
        return np.zeros((n, n), dtype=np.float32), False
    full = emb.similarity_matrix()
    pos = {nid: i for i, nid in enumerate(emb.node_ids)}
    m = np.zeros((n, n), dtype=np.float32)
    for a in range(n):
        ia = pos.get(ids[a])
        if ia is None:
            continue
        for b in range(a + 1, n):
            ib = pos.get(ids[b])
            if ib is None:
                continue
            m[a, b] = m[b, a] = float(full[ia, ib])
    np.fill_diagonal(m, 1.0)
    return np.clip(m, 0.0, 1.0), True


# =============================================================================
# Assembly
# =============================================================================

def build_features(
    kg: KnowledgeGraph,
    *,
    weights: list[float] | None = None,
    emb=None,
    progress=None,
) -> FeatureMatrices:
    ids = sorted(c["id"] for c in kg.classes() if not c.get("isTest"))
    w = list(weights or [0.30, 0.20, 0.25, 0.10, 0.15])
    if len(w) != 5:
        raise ValueError("weights must have 5 entries (structural, runtime, data, cochange, semantic)")

    fm = FeatureMatrices(node_ids=ids)
    if not ids:
        return fm

    if progress:
        progress(0.1, "structural coupling")
    fm.terms["structural"] = structural_matrix(kg, ids)
    fm.available["structural"] = bool(fm.terms["structural"].any())

    if progress:
        progress(0.3, "runtime co-occurrence")
    fm.terms["runtime"], fm.available["runtime"] = runtime_matrix(kg, ids)

    if progress:
        progress(0.5, "data access overlap")
    fm.terms["data"], fm.available["data"] = data_matrix(kg, ids)

    if progress:
        progress(0.65, "git co-change")
    fm.terms["cochange"], fm.available["cochange"] = cochange_matrix(kg, ids)

    if progress:
        progress(0.8, "semantic similarity")
    fm.terms["semantic"], fm.available["semantic"] = semantic_matrix(ids, emb)

    # Redistribute the weight of any signal this project does not have, so an
    # unmeasured dimension never reads as dissimilarity.
    raw = dict(zip(TERMS, w))
    live = {t: raw[t] for t in TERMS if fm.available.get(t)}
    missing = {t: raw[t] for t in TERMS if not fm.available.get(t)}
    total_live = sum(live.values())
    if total_live <= 0:
        raise RuntimeError("no similarity signal is available for this project")
    scale = (total_live + sum(missing.values())) / total_live
    fm.weights = {t: v * scale for t, v in live.items()}
    for t in missing:
        fm.weights[t] = 0.0

    combined = np.zeros((len(ids), len(ids)), dtype=np.float32)
    for t in TERMS:
        if fm.weights.get(t):
            combined += fm.weights[t] * fm.terms[t]
    np.fill_diagonal(combined, 1.0)
    fm.combined = np.clip(combined, 0.0, 1.0)

    if progress:
        progress(1.0, f"similarity over {len(ids)} classes")
    log.info("features_built", classes=len(ids),
             available={k: bool(v) for k, v in fm.available.items()},
             weights={k: round(v, 3) for k, v in fm.weights.items()},
             redistributed=bool(missing))
    return fm
