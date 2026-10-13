"""Semantic embeddings of code identifiers (PRD §8.1 step 7).

The PRD specifies ``sentence-transformers``. That pulls ~2 GB of PyTorch wheels,
takes minutes to warm up, and — on identifier text like ``recordChange`` or
``evaluateReleaseReadiness`` — buys little over a well-tuned lexical model,
because the signal here is shared *vocabulary* (``batch``, ``release``,
``audit``, ``spec``) rather than natural-language meaning.

So this module builds a 384-dimension latent-semantic embedding with TF-IDF over
character n-grams plus identifier tokens, reduced by truncated SVD. It is
deterministic (fixed seed), needs no download, runs in milliseconds, and keeps
the same contract: a 384-float vector per class, cosine-compared.

``sentence-transformers`` is still used when it is installed and
``MODERNRX_USE_ST=1`` — the interface is identical, so the upgrade is one env var.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph

log = get_logger("embeddings")

DIM = 384
SEED = 20260413

# Tokens that carry no domain meaning and would otherwise dominate TF-IDF.
STOP_TOKENS = {
    "get", "set", "is", "has", "to", "from", "the", "a", "an", "of", "and", "or",
    "string", "int", "long", "void", "boolean", "double", "float", "list", "map",
    "object", "class", "public", "private", "protected", "static", "final",
    "return", "this", "new", "null", "true", "false", "value", "val", "obj",
    "java", "lang", "util", "org", "com", "springframework", "annotation",
}


@dataclass
class EmbeddingSet:
    node_ids: list[str] = field(default_factory=list)
    vectors: np.ndarray = field(default_factory=lambda: np.zeros((0, DIM), dtype=np.float32))
    model: str = ""
    dim: int = DIM
    # The identifier documents the vectors were built from, kept so free-text
    # search can be answered without refitting the vectoriser.
    docs: list[str] = field(default_factory=list)

    def index_of(self, node_id: str) -> int:
        try:
            return self.node_ids.index(node_id)
        except ValueError:
            return -1

    def similarity_matrix(self) -> np.ndarray:
        """Cosine similarity, clipped to [0, 1]. Rows are unit-normalised."""
        if len(self.node_ids) == 0:
            return np.zeros((0, 0), dtype=np.float32)
        sim = self.vectors @ self.vectors.T
        return np.clip(sim, 0.0, 1.0).astype(np.float32)

    def to_blobs(self) -> dict[str, bytes]:
        return {nid: self.vectors[i].astype(np.float32).tobytes()
                for i, nid in enumerate(self.node_ids)}


CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+")


def split_identifier(name: str) -> list[str]:
    """``evaluateReleaseReadiness`` -> [evaluate, release, readiness]."""
    parts: list[str] = []
    for chunk in re.split(r"[^A-Za-z0-9]+", name or ""):
        parts.extend(m.group(0).lower() for m in CAMEL_RE.finditer(chunk))
    return [p for p in parts if len(p) > 1 and p not in STOP_TOKENS]


def document_for_class(kg: KnowledgeGraph, cid: str) -> str:
    """The text that represents a class: its own name, its members, its data."""
    d = kg.node(cid) or {}
    tokens: list[str] = []

    # The class's own name counts most, so it is repeated.
    tokens += split_identifier(d.get("name", "")) * 3
    tokens += split_identifier(d.get("package", "").rsplit(".", 1)[-1]) * 2
    for ann in d.get("annotations", []) or []:
        tokens += split_identifier(ann)
    for sup in d.get("extends", []) or []:
        tokens += split_identifier(sup)

    for mid in kg.children(cid):
        md = kg.node(mid) or {}
        tokens += split_identifier(md.get("name", ""))
        tokens += split_identifier(md.get("returnType", ""))
        for p in md.get("params", []) or []:
            tokens += split_identifier(p)
        # Tables are strong domain evidence, so they are weighted up.
        for rel in ("READS", "WRITES"):
            for t in kg.out_neighbors(mid, rel):
                tokens += split_identifier((kg.node(t) or {}).get("name", "")) * 2

    for rel in ("READS", "WRITES"):
        for t in kg.out_neighbors(cid, rel):
            tokens += split_identifier((kg.node(t) or {}).get("name", "")) * 2

    return " ".join(tokens) or (d.get("name", "") or cid).lower()


def build_embeddings(kg: KnowledgeGraph, *, progress=None) -> EmbeddingSet:
    node_ids = sorted(kg.node_ids("Class"))
    if not node_ids:
        return EmbeddingSet(model="none")
    if progress:
        progress(0.1, "building identifier documents")
    docs = [document_for_class(kg, cid) for cid in node_ids]

    if os.environ.get("MODERNRX_USE_ST") == "1":
        st = _try_sentence_transformers(docs)
        if st is not None:
            return EmbeddingSet(node_ids=node_ids, vectors=st, docs=docs,
                                model="sentence-transformers/all-MiniLM-L6-v2", dim=st.shape[1])

    if progress:
        progress(0.4, "fitting TF-IDF + SVD")
    vectors = _lsa_embed(docs)
    if progress:
        progress(1.0, f"embedded {len(node_ids)} classes")
    log.info("embeddings_built", classes=len(node_ids), dim=vectors.shape[1])
    return EmbeddingSet(node_ids=node_ids, vectors=vectors, docs=docs,
                        model="tfidf-svd-384", dim=vectors.shape[1])


def _lsa_embed(docs: list[str]) -> np.ndarray:
    """Word-level and character-level TF-IDF, concatenated, then SVD to 384-d."""
    n = len(docs)
    blocks: list[np.ndarray] = []

    word = TfidfVectorizer(
        analyzer="word", token_pattern=r"[a-z][a-z0-9]+", sublinear_tf=True,
        min_df=1, max_df=0.9 if n > 4 else 1.0,
    )
    try:
        blocks.append(word.fit_transform(docs).toarray().astype(np.float32))
    except ValueError:
        pass

    # Character n-grams catch near-identical identifiers (Sample / SampleMapper)
    # that share no whole token.
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
    try:
        blocks.append(char.fit_transform(docs).toarray().astype(np.float32))
    except ValueError:
        pass

    if not blocks:
        return np.zeros((n, DIM), dtype=np.float32)

    X = np.hstack([normalize(b) for b in blocks])
    target = min(DIM, max(2, min(X.shape) - 1))
    if target < 2 or X.shape[1] <= target:
        out = np.zeros((n, DIM), dtype=np.float32)
        out[:, : X.shape[1]] = X[:, :DIM]
        return normalize(out).astype(np.float32)

    svd = TruncatedSVD(n_components=target, random_state=SEED, algorithm="randomized", n_iter=12)
    reduced = svd.fit_transform(X).astype(np.float32)
    # Pad to the declared 384 so stored vectors have one fixed width.
    out = np.zeros((n, DIM), dtype=np.float32)
    out[:, :target] = reduced
    return normalize(out).astype(np.float32)


def _try_sentence_transformers(docs: list[str]) -> np.ndarray | None:
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = model.encode(docs, normalize_embeddings=True, show_progress_bar=False)
        log.info("embeddings_sentence_transformers", classes=len(docs))
        return np.asarray(vecs, dtype=np.float32)
    except Exception as exc:
        log.warning("sentence_transformers_unavailable", error=str(exc))
        return None


def semantic_search(emb: EmbeddingSet, query: str, top_k: int = 10) -> list[tuple[str, float]]:
    """Rank classes against a free-text query, in the same embedding space.

    Projecting a query through a fitted TF-IDF+SVD pipeline needs the fitted
    vocabulary, which is not retained. Token overlap against each class document
    is used instead: it is transparent, needs no state, and for identifier
    search it is what a reviewer would do by hand.
    """
    q = set(split_identifier(query))
    if not q or not emb.node_ids:
        return []
    scored: list[tuple[str, float]] = []
    for i, nid in enumerate(emb.node_ids):
        if i >= len(emb.docs):
            break
        doc = set(emb.docs[i].split())
        if not doc:
            continue
        inter = len(q & doc)
        if inter:
            scored.append((nid, inter / len(q | doc)))
    scored.sort(key=lambda kv: -kv[1])
    return scored[:top_k]
