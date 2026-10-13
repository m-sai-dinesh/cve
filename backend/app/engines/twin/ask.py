"""Ask the Twin (PRD §8.2).

An LLM with three tools: ``cypher_query(template_id, params)`` restricted to the
whitelisted templates, ``get_node(id)`` and ``semantic_search(text)``. Free-form
Cypher is never accepted, so a prompt-injected question cannot reach the graph
with an arbitrary query. Every answer lists the node ids it used.

Without an API key the same tools are driven by intent matching over the
question. That answers the demo questions truthfully from the graph - it simply
cannot paraphrase as fluently, and it says which mode produced the answer.
"""
from __future__ import annotations

import re
from typing import Any

from ...core.llm import get_llm
from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph, TEMPLATES, describe_templates, run_template

log = get_logger("twin.ask")

SYSTEM = """\
You answer questions about a legacy pharmaceutical application using ONLY a
knowledge graph built from its source code, database schema, configuration and
runtime traces.

You have these tools:
  cypher_query(template_id, params)  - run one of the whitelisted templates below
  get_node(node_id)                  - fetch one node's properties
  semantic_search(text)              - find components by name similarity

Rules:
  1. Answer ONLY from tool results. If the tools do not contain the answer, say
     so plainly and name what is missing. Never guess a class name, a table
     name or a number.
  2. Every factual claim must be traceable to a node id you retrieved. List the
     ids you used in `evidence_node_ids`.
  3. Be concrete and brief. Name the class, the table, the method, the count.
  4. GxP tiers are HIGH, MEDIUM, LOW. Explain *why* a component is HIGH when
     relevant (what it writes, what it signs, what it releases).
  5. Never invent a template id or a parameter. Only the templates listed exist.
"""

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "enum": sorted(TEMPLATES)},
                    "table": {"type": "string"},
                    "fqn": {"type": "string"},
                    "name": {"type": "string"},
                    "kind": {"type": "string"},
                    "cluster_id": {"type": "string"},
                    "hops": {"type": "integer"},
                    "min_accessors": {"type": "integer"},
                },
                "required": ["template_id"],
            },
        },
        "reasoning": {"type": "string"},
    },
    "required": ["calls"],
}

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "evidence_node_ids": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "missing": {"type": "string"},
    },
    "required": ["answer", "evidence_node_ids"],
}


# =============================================================================
# Intent routing (used as the plan when no LLM is available, and as a prior)
# =============================================================================

INTENTS: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    (re.compile(r"(?i)\b(who|what|which).*(writ|insert|updat|modif|creat).*\b(audit|trail)"),
     "writers_of_table", {"table": "AUDIT"}),
    (re.compile(r"(?i)\b(writ|insert|updat|modif)\w*\b.*\b(batch|release|disposition)"),
     "writers_of_table", {"table": "BATCH"}),
    (re.compile(r"(?i)\b(writ|insert|updat|modif)\w*\b.*\bresult"),
     "writers_of_table", {"table": "RESULT"}),
    (re.compile(r"(?i)\b(writ|insert|updat|modif)\w*\b.*\bsample"),
     "writers_of_table", {"table": "SAMPLE"}),
    (re.compile(r"(?i)\b(read|select|report|consum)\w*\b.*\bresult"),
     "readers_of_table", {"table": "RESULT"}),
    (re.compile(r"(?i)blast.?radius|impact of chang|what breaks|what depends on"),
     "blast_radius", {}),
    (re.compile(r"(?i)high.?(tier|risk|criticalit)|most critical|validated core"),
     "high_tier_classes", {}),
    (re.compile(r"(?i)shared table|same table|table.*(shared|two|multiple)|coupl\w+ (via|through) (the )?(database|db|data)"),
     "shared_tables", {"min_accessors": 2}),
    (re.compile(r"(?i)end.?of.?life|\beol\b|outdated|unsupported|old (librar|version|dependenc)"),
     "eol_libraries", {}),
    (re.compile(r"(?i)secret|password|credential|hard.?cod"),
     "config_findings", {"kind": "secret"}),
    (re.compile(r"(?i)file (path|share|system)|local (path|file)|network share|\bunc\b"),
     "config_findings", {"kind": "path"}),
    (re.compile(r"(?i)dead code|unused|unreachable|safe to (delete|remove)|retire"),
     "dead_code", {}),
    (re.compile(r"(?i)cluster|service boundar|proposed service|decomposition|microservice"),
     "cluster_summary", {}),
    (re.compile(r"(?i)use.?case|business (flow|transaction|process)|what runs|traffic"),
     "usecase_members", {}),
]

TABLE_HINT = re.compile(
    r"(?i)\b(audit_trail|audit|result_signature|result|sample|batch|deviation|capa|"
    r"stability_study|stability|test_specification|specification|spec|chain_of_custody|"
    r"custody|instrument_import|lims_user|coa_report)\b"
)


def plan_from_question(kg: KnowledgeGraph, question: str) -> list[dict[str, Any]]:
    """Choose templates and parameters from the question's wording."""
    calls: list[dict[str, Any]] = []
    for rx, template_id, params in INTENTS:
        if rx.search(question):
            call = {"template_id": template_id, **params}
            if template_id in ("writers_of_table", "readers_of_table") and "table" not in params:
                m = TABLE_HINT.search(question)
                if m:
                    call["table"] = m.group(1).upper()
            if template_id == "blast_radius":
                target = _guess_class(kg, question)
                if not target:
                    continue
                call["fqn"] = target
                call["hops"] = 3
            if template_id == "usecase_members":
                call["name"] = _guess_usecase(kg, question) or ""
            if call not in calls:
                calls.append(call)

    # A named class in the question is always worth profiling.
    named = _guess_class(kg, question)
    if named and not any(c["template_id"] == "class_detail" for c in calls):
        calls.insert(0, {"template_id": "class_detail", "fqn": named})

    # A named table with no verb: show both sides.
    if not calls:
        m = TABLE_HINT.search(question)
        if m:
            t = m.group(1).upper()
            calls = [{"template_id": "writers_of_table", "table": t},
                     {"template_id": "readers_of_table", "table": t}]

    if not calls:
        calls = [{"template_id": "high_tier_classes"}]
    return calls[:4]


def _guess_class(kg: KnowledgeGraph, question: str) -> str | None:
    """Find a class the question names, by exact then fuzzy match."""
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", question))
    by_simple = {str(c.get("name")): str(c.get("fqn")) for c in kg.classes()}
    for w in words:
        if w in by_simple:
            return by_simple[w]
    lowered = {k.lower(): v for k, v in by_simple.items()}
    for w in words:
        if w.lower() in lowered:
            return lowered[w.lower()]
    # Token overlap: "the review service" -> ReviewService
    from .embeddings import split_identifier

    q_tokens = {t for w in words for t in split_identifier(w)}
    best, best_score = None, 0.0
    for simple, fqn in by_simple.items():
        toks = set(split_identifier(simple))
        if not toks:
            continue
        score = len(q_tokens & toks) / len(toks)
        if score > best_score and score >= 0.5:
            best, best_score = fqn, score
    return best


def _guess_usecase(kg: KnowledgeGraph, question: str) -> str | None:
    from .embeddings import split_identifier

    q = {t for t in split_identifier(question)}
    best, best_score = None, 0.0
    for u in kg.nodes("UseCase"):
        name = str(u.get("name") or "")
        toks = set(split_identifier(name))
        if not toks:
            continue
        score = len(q & toks) / len(toks)
        if score > best_score:
            best, best_score = name, score
    return best if best_score >= 0.34 else None


# =============================================================================
# Answering
# =============================================================================

def answer(kg: KnowledgeGraph, question: str) -> dict[str, Any]:
    llm = get_llm()
    calls = plan_from_question(kg, question)
    reasoning = ""

    # With a model available, let it choose the tools; keep the heuristic plan
    # as the fallback so a bad plan still produces a real answer.
    if llm.available:
        catalog = [
            {"id": t["id"], "description": t["description"], "params": t["params"]}
            for t in describe_templates()
        ]
        res = llm.generate(
            "Choose up to 4 template calls that will answer this question.\n\n"
            f"QUESTION: {question}\n\n"
            f"AVAILABLE TEMPLATES:\n{_json(catalog)}\n\n"
            f"Context: this project has "
            f"{len(kg.classes())} classes, {len(kg.nodes('Table'))} tables, "
            f"{len(kg.nodes('Cluster'))} proposed clusters, "
            f"{len(kg.nodes('UseCase'))} runtime use cases.",
            system=SYSTEM, schema=PLAN_SCHEMA, input_payload={"question": question},
        )
        if isinstance(res.data, dict) and res.data.get("calls"):
            chosen = [c for c in res.data["calls"] if c.get("template_id") in TEMPLATES]
            if chosen:
                calls = chosen[:4]
            reasoning = str(res.data.get("reasoning") or "")

    # Execute the plan.
    results: list[dict[str, Any]] = []
    evidence: list[str] = []
    for call in calls:
        template_id = str(call.get("template_id"))
        params = {k: v for k, v in call.items() if k != "template_id"}
        out = run_template(kg, template_id, params)
        results.append(out)
        for row in out.get("rows", []):
            nid = row.get("node_id")
            if nid and kg.has(str(nid)) and str(nid) not in evidence:
                evidence.append(str(nid))

    if llm.available:
        res = llm.generate(
            f"QUESTION: {question}\n\n"
            f"TOOL RESULTS:\n{_json(results)}\n\n"
            "Answer the question from these results only. Cite the node ids you "
            "used. If the results do not answer it, say so and name what is missing.",
            system=SYSTEM, schema=ANSWER_SCHEMA,
            input_payload={"question": question, "results": results},
        )
        if isinstance(res.data, dict) and res.data.get("answer"):
            cited = [e for e in (res.data.get("evidence_node_ids") or []) if kg.has(str(e))]
            return {
                "question": question,
                "answer": str(res.data["answer"]),
                "evidence_node_ids": cited or evidence[:12],
                "evidence": _describe(kg, cited or evidence[:12]),
                "templates_used": [r["template_id"] for r in results],
                "queries": [{"template_id": r["template_id"], "cypher": r.get("cypher"),
                             "params": r.get("params"), "row_count": r.get("row_count")}
                            for r in results],
                "confidence": float(res.data.get("confidence") or 0.7),
                "missing": str(res.data.get("missing") or ""),
                "reasoning": reasoning,
                "generator": "gemini",
                "model_id": res.model_id,
            }
        log.warning("ask_llm_failed", error=res.error)

    return _compose(kg, question, results, evidence, reasoning)


def _compose(
    kg: KnowledgeGraph, question: str, results: list[dict[str, Any]],
    evidence: list[str], reasoning: str,
) -> dict[str, Any]:
    """Build the answer from the tool results without a model.

    Each template gets its own phrasing, because a generic "here are N rows"
    would be useless to the person asking.
    """
    parts: list[str] = []
    for r in results:
        tid = r.get("template_id")
        rows = r.get("rows") or []
        n = r.get("row_count") or 0
        if r.get("error"):
            parts.append(f"The `{tid}` query could not run: {r['error']}.")
            continue
        if not rows:
            parts.append(f"No results for `{tid}`"
                         + (f" with {r.get('params')}" if r.get("params") else "") + ".")
            continue

        if tid == "writers_of_table":
            table = rows[0].get("table")
            tiers = {row.get("gxpTier") for row in rows}
            names = sorted({str(row["method"]).rsplit(".", 2)[-2] for row in rows if row.get("method")})
            parts.append(
                f"**{n} method(s) write to {table}**, in "
                f"{len(names)} class(es): {', '.join(names[:6])}"
                + (f" and {len(names) - 6} more" if len(names) > 6 else "")
                + f". GxP tier(s) involved: {', '.join(sorted(t for t in tiers if t))}. "
                + "The highest fan-in writer is "
                + f"`{rows[0].get('method')}` ({rows[0].get('fanIn')} inbound dependencies)."
            )
        elif tid == "readers_of_table":
            table = rows[0].get("table")
            names = sorted({str(row["method"]).rsplit(".", 2)[-2] for row in rows if row.get("method")})
            parts.append(f"**{n} method(s) read {table}** without writing it, across "
                         f"{len(names)} class(es): {', '.join(names[:6])}.")
        elif tid == "class_detail":
            d = rows[0]
            parts.append(
                f"**{str(d.get('fqn')).rsplit('.', 1)[-1]}** is GxP "
                f"**{d.get('gxpTier')}** ({', '.join(d.get('gxpTags') or []) or 'no tags'}), "
                f"{d.get('loc')} LOC, complexity {d.get('complexity')}, readiness "
                f"{d.get('readiness')}/100, {int(d.get('runtimeHits') or 0):,} observed calls. "
                f"Fan-in {d.get('fanIn')}, fan-out {d.get('fanOut')}. "
                + (f"Data access: {', '.join(d.get('tables') or [])}. " if d.get("tables") else "")
                + (f"It is in cluster `{d.get('clusterId')}`." if d.get("clusterId") else "")
            )
        elif tid == "blast_radius":
            by_tier: dict[str, int] = {}
            for row in rows:
                by_tier[str(row.get("gxpTier"))] = by_tier.get(str(row.get("gxpTier")), 0) + 1
            parts.append(
                f"**{n} component(s) depend on it** within 3 hops"
                + (f" ({by_tier.get('HIGH', 0)} HIGH, {by_tier.get('MEDIUM', 0)} MEDIUM, "
                   f"{by_tier.get('LOW', 0)} LOW tier)" if by_tier else "")
                + f". Nearest dependents: "
                + ", ".join(str(r.get("fqn")).rsplit(".", 1)[-1] for r in rows[:6])
                + ". Each of these would be in scope for re-validation if it changed."
            )
        elif tid == "high_tier_classes":
            parts.append(
                f"**{n} component(s) are HIGH GxP tier** - the validated core: "
                + ", ".join(str(r.get("fqn")).rsplit(".", 1)[-1] for r in rows[:10])
                + (f" and {n - 10} more" if n > 10 else "") + "."
            )
        elif tid == "shared_tables":
            worst = rows[0]
            multi = [r for r in rows if r.get("shared_write")]
            parts.append(
                f"**{n} table(s) are reached by more than one class.** "
                + (f"{len(multi)} are written by more than one class, which is the "
                   f"hard blocker to splitting them: "
                   f"{', '.join(str(r.get('table')) for r in multi)}. " if multi else "")
                + f"Most shared: {worst.get('table')} "
                  f"({worst.get('accessor_count')} accessors, "
                  f"{worst.get('writer_count')} writer(s))."
            )
        elif tid == "eol_libraries":
            parts.append(
                f"**{n} dependency/dependencies are past end of life**: "
                + "; ".join(f"{r.get('name')} {r.get('version')} ({r.get('reason')})"
                            for r in rows[:6]) + "."
            )
        elif tid == "config_findings":
            kind = (r.get("params") or {}).get("kind") or "finding"
            parts.append(
                f"**{n} configuration {kind} finding(s)**: "
                + "; ".join(f"`{r.get('key')}` = {r.get('value')}" for r in rows[:6])
                + ". Values of secrets are masked at parse time and never stored in full."
            )
        elif tid == "dead_code":
            total = sum(int(r.get("loc") or 0) for r in rows)
            parts.append(
                f"**{n} class(es) appear unreachable** ({total} LOC): "
                + ", ".join(str(r.get("fqn")).rsplit(".", 1)[-1] for r in rows[:8])
                + ". No inbound call, no type reference, no instantiation and no runtime "
                  "hit. Confirm reflection is not in use before deleting."
            )
        elif tid == "cluster_summary":
            parts.append(
                f"**{n} proposed service(s)**: "
                + "; ".join(f"{r.get('name')} ({r.get('size')} classes, GxP "
                            f"{r.get('gxpMax')}, readiness {r.get('readinessAvg')})"
                            for r in rows[:8]) + "."
            )
        elif tid == "usecase_members":
            uc = rows[0].get("usecase")
            parts.append(
                f"**{uc}** involves {len({r.get('member') for r in rows})} method(s). "
                f"Busiest: "
                + ", ".join(f"{str(r.get('member')).rsplit('.', 2)[-2]}."
                            f"{str(r.get('member')).rsplit('.', 1)[-1]} "
                            f"({int(r.get('hits') or 0):,})" for r in rows[:5]) + "."
            )
        else:
            parts.append(f"`{tid}` returned {n} row(s).")

    text = " ".join(parts) if parts else (
        "I could not find anything in the twin that answers that. Try naming a "
        "class, a table, or ask about GxP tiers, shared tables, dead code, "
        "end-of-life libraries or configuration findings."
    )
    return {
        "question": question,
        "answer": text,
        "evidence_node_ids": evidence[:14],
        "evidence": _describe(kg, evidence[:14]),
        "templates_used": [r["template_id"] for r in results],
        "queries": [{"template_id": r["template_id"], "cypher": r.get("cypher"),
                     "params": r.get("params"), "row_count": r.get("row_count")}
                    for r in results],
        "confidence": 0.8 if any(r.get("rows") for r in results) else 0.2,
        "missing": "",
        "reasoning": reasoning,
        "generator": "deterministic",
        "model_id": "",
    }


def _describe(kg: KnowledgeGraph, node_ids: list[str]) -> list[dict[str, Any]]:
    out = []
    for nid in node_ids:
        n = kg.node(nid) or {}
        out.append({
            "node_id": nid, "kind": n.get("label"),
            "name": n.get("fqn") or n.get("name") or nid,
            "gxpTier": n.get("gxpTier"), "readiness": n.get("readiness"),
        })
    return out


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=1, default=str)[:12000]
