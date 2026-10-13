"""Step 2 of Engine 2: LLM classification of ambiguous components (PRD §9.2).

Only components that touch the regulated domain but fired no deterministic rule
reach this module. Gemini is called with ``response_schema`` so the reply is
conforming JSON, and every returned tag is then checked against the rule
vocabulary and every evidence id against the graph — a claim citing a node that
does not exist is discarded, not trusted.

With no API key this falls back to a transparent heuristic. The fallback is
*marked as such* on every hit it produces (``source="heuristic"``), so nothing
downstream can mistake a heuristic guess for a model judgement.
"""
from __future__ import annotations

import re
from typing import Any

from ...core.llm import get_llm
from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from .scanner import TagHit

log = get_logger("gxp.classifier")

VALID_TAGS = {
    "AUDIT_TRAIL", "E_SIGNATURE", "ACCESS_CONTROL", "DATA_INTEGRITY",
    "PRODUCT_RELEASE", "TIME_SOURCE", "REPORTING_ONLY",
}
VALID_TIERS = {"HIGH", "MEDIUM", "LOW"}

MAX_BATCH = 12

SYSTEM = """\
You are a GxP computer-system validation analyst classifying components of a \
pharmaceutical application for regulatory criticality.

Frameworks: 21 CFR Part 11, EU GMP Annex 11, FDA Computer Software Assurance \
(risk-based), ALCOA++.

Tier definitions you MUST follow exactly:
  HIGH   - decides batch disposition/release, applies or verifies an electronic \
signature, writes the audit trail, or creates/modifies GxP records.
  MEDIUM - reads GxP records without modifying them, or enforces access control.
  LOW    - UI helpers, formatting, utilities, and anything with no GxP data path.

Rules you MUST obey:
  1. Judge ONLY from the evidence supplied. Do not invent methods, tables or \
annotations that are not listed.
  2. Every component you classify must cite at least one evidence_node_id drawn \
from the ids given to you.
  3. If the evidence does not support a tier above LOW, answer LOW. Over-tagging \
is a real cost: it inflates the validation scope and the migration estimate.
  4. rationale must be one sentence naming the specific evidence that decided it.
"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "tier": {"type": "string", "enum": sorted(VALID_TIERS)},
                    "tags": {"type": "array", "items": {"type": "string", "enum": sorted(VALID_TAGS)}},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                    "evidence_node_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["node_id", "tier", "tags", "rationale", "evidence_node_ids"],
            },
        }
    },
    "required": ["classifications"],
}


def describe_component(kg: KnowledgeGraph, cid: str) -> dict[str, Any]:
    """The evidence bundle for one class. Metadata only — never raw source.

    PRD §15 data minimisation: identifiers, annotations and table access are
    enough to tier a component, and they contain no patient or product data.
    """
    d = kg.node(cid) or {}
    methods = []
    for mid in kg.children(cid)[:40]:
        md = kg.node(mid) or {}
        reads = [str((kg.node(t) or {}).get("name")) for t in kg.out_neighbors(mid, "READS")]
        writes = [str((kg.node(t) or {}).get("name")) for t in kg.out_neighbors(mid, "WRITES")]
        methods.append({
            "node_id": mid,
            "name": md.get("name"),
            "annotations": md.get("annotations", []),
            "reads_tables": sorted(set(reads)),
            "writes_tables": sorted(set(writes)),
            "params": (md.get("params") or [])[:6],
            "stamps_local_time": bool(md.get("usesNewDate")),
            "sql": (md.get("sqlLiterals") or [])[:2],
        })
    return {
        "node_id": cid,
        "class": d.get("fqn"),
        "annotations": d.get("annotations", []),
        "extends": d.get("extends", []),
        "loc": d.get("loc"),
        "runtime_hits": d.get("runtimeHits", 0),
        "methods": methods,
    }


def classify_ambiguous(
    kg: KnowledgeGraph, node_ids: list[str], rules: dict[str, Any]
) -> tuple[list[TagHit], dict[str, str]]:
    llm = get_llm()
    if not llm.available:
        return _heuristic(kg, node_ids, rules)

    hits: list[TagHit] = []
    tiers: dict[str, str] = {}
    tag_meta = rules.get("tags", {}) or {}

    for batch in _chunks(node_ids, MAX_BATCH):
        payload = [describe_component(kg, cid) for cid in batch]
        prompt = (
            "Classify each component below for GxP criticality.\n\n"
            "Return one entry per component, using its node_id verbatim.\n\n"
            f"COMPONENTS:\n{_as_json(payload)}"
        )
        res = llm.generate(prompt, system=SYSTEM, input_payload=payload, schema=RESPONSE_SCHEMA)
        if res.data is None:
            log.warning("gxp_llm_batch_failed", error=res.error, size=len(batch))
            h, t = _heuristic(kg, batch, rules)
            hits.extend(h)
            tiers.update(t)
            continue

        requested = set(batch)
        for c in (res.data or {}).get("classifications", []):
            nid = str(c.get("node_id", ""))
            if nid not in requested:
                continue  # never accept a verdict on a node we did not ask about
            tier = str(c.get("tier", "LOW")).upper()
            if tier not in VALID_TIERS:
                continue
            tags = [str(t).upper() for t in (c.get("tags") or [])
                    if str(t).upper() in VALID_TAGS]
            evidence = [e for e in (c.get("evidence_node_ids") or []) if kg.has(str(e))]
            if tier != "LOW" and not evidence:
                # Unevidenced escalation is exactly what we promised to reject.
                log.info("gxp_llm_rejected_no_evidence", node=nid, tier=tier)
                continue
            tiers[nid] = tier
            for tag in tags or (["DATA_INTEGRITY"] if tier != "LOW" else []):
                hits.append(TagHit(
                    node_id=nid, tag=tag, rule_id="LLM_CLASSIFIER",
                    confidence=float(c.get("confidence") or 0.6),
                    rationale=str(c.get("rationale", ""))[:400],
                    clause=tag_meta.get(tag, {}).get("clause", ""),
                    source="llm",
                ))
    log.info("gxp_llm_done", asked=len(node_ids), classified=len(tiers))
    return hits, tiers


# ---------------------------------------------------------------- fallback
def _heuristic(
    kg: KnowledgeGraph, node_ids: list[str], rules: dict[str, Any]
) -> tuple[list[TagHit], dict[str, str]]:
    """Deterministic stand-in: tier from the data path alone.

    This is intentionally conservative. It only escalates a component that
    actually reads or writes a regulated table, and it never claims a tag the
    table access does not justify.
    """
    entity_rx = re.compile(rules.get("gxp_entity_regex", "(?i)sample|result|batch"))
    tag_meta = rules.get("tags", {}) or {}
    hits: list[TagHit] = []
    tiers: dict[str, str] = {}

    for cid in node_ids:
        reads: set[str] = set()
        writes: set[str] = set()
        for mid in [cid, *kg.children(cid)]:
            for t in kg.out_neighbors(mid, "WRITES"):
                writes.add(str((kg.node(t) or {}).get("name", "")))
            for t in kg.out_neighbors(mid, "READS"):
                reads.add(str((kg.node(t) or {}).get("name", "")))

        gxp_writes = {t for t in writes if entity_rx.search(t)}
        gxp_reads = {t for t in reads - writes if entity_rx.search(t)}

        if gxp_writes:
            tier, tag = "HIGH", "DATA_INTEGRITY"
            why = f"writes the regulated table(s) {', '.join(sorted(gxp_writes))}"
        elif gxp_reads:
            tier, tag = "MEDIUM", "REPORTING_ONLY"
            why = f"reads {', '.join(sorted(gxp_reads))} without writing GxP data"
        else:
            continue

        tiers[cid] = tier
        hits.append(TagHit(
            node_id=cid, tag=tag, rule_id="HEURISTIC_DATA_PATH",
            confidence=0.55, source="heuristic",
            rationale=f"No GEMINI_API_KEY configured; tiered from the data path: {why}.",
            clause=tag_meta.get(tag, {}).get("clause", ""),
        ))
    log.info("gxp_heuristic_done", asked=len(node_ids), classified=len(tiers))
    return hits, tiers


def _chunks(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _as_json(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=1, default=str)
