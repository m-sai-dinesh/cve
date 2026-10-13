"""Engine 2 — GxP Criticality Scanner (PRD §9).

Three steps, in this order, because explainability depends on it:

1. **Deterministic rules** from ``rules.yaml`` — regex, annotations, call
   targets and table access. Every tag this produces can be traced to a rule id
   and a regulatory clause.
2. **LLM classification** for the residue only: nodes that touch the regulated
   domain but fired no rule (see ``classifier.py``).
3. **Propagation** — a LOW method that calls into a HIGH write path inherits
   ``MEDIUM (indirect)``, because the Annex 11 draft covers indirect impact.

Then the compliance-gap checks run: those look for a *missing* control (no
reason column, local clock, shared admin account) rather than a present one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph

log = get_logger("gxp")

RULES_PATH = Path(__file__).with_name("rules.yaml")

TIER_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def tier_max(*tiers: str) -> str:
    best = "LOW"
    for t in tiers:
        if TIER_ORDER.get(t or "LOW", 0) > TIER_ORDER[best]:
            best = t
    return best


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class TagHit:
    node_id: str
    tag: str
    rule_id: str
    confidence: float
    rationale: str
    clause: str = ""
    source: str = "rule"           # rule | llm | propagated | override

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "tag": self.tag, "rule_id": self.rule_id,
            "confidence": round(self.confidence, 3), "rationale": self.rationale,
            "clause": self.clause, "source": self.source,
        }


@dataclass
class ComplianceGap:
    id: str
    severity: str
    title: str
    clause: str
    detail: str
    remediation: str
    evidence_node_ids: list[str] = field(default_factory=list)
    evidence_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "severity": self.severity, "title": self.title,
            "clause": self.clause, "detail": " ".join(self.detail.split()),
            "remediation": " ".join(self.remediation.split()),
            "evidence_node_ids": self.evidence_node_ids[:25],
            "evidence_count": len(self.evidence_node_ids),
            "evidence_note": self.evidence_note,
        }


@dataclass
class GxpResult:
    hits: list[TagHit] = field(default_factory=list)
    gaps: list[ComplianceGap] = field(default_factory=list)
    tiers: dict[str, str] = field(default_factory=dict)
    tags_by_node: dict[str, list[str]] = field(default_factory=dict)
    ambiguous: list[str] = field(default_factory=list)
    llm_classified: int = 0
    propagated: int = 0
    rules_version: str = ""

    def summary(self) -> dict[str, Any]:
        counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        class_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for nid, tier in self.tiers.items():
            counts[tier] = counts.get(tier, 0) + 1
            if nid.startswith("class:"):
                class_counts[tier] = class_counts.get(tier, 0) + 1
        tag_counts: dict[str, int] = {}
        for h in self.hits:
            tag_counts[h.tag] = tag_counts.get(h.tag, 0) + 1
        total_classes = sum(class_counts.values()) or 1
        return {
            "nodes_tiered": len(self.tiers),
            "tier_counts": counts,
            "class_tier_counts": class_counts,
            "pct_high_classes": round(100 * class_counts["HIGH"] / total_classes, 1),
            "tag_counts": tag_counts,
            "gaps": len(self.gaps),
            "gaps_by_severity": _count_by(self.gaps, "severity"),
            "llm_classified": self.llm_classified,
            "propagated": self.propagated,
            "rules_version": self.rules_version,
        }


def _count_by(items: list[Any], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = getattr(it, attr)
        out[k] = out.get(k, 0) + 1
    return out


# =============================================================================
# Rule matching
# =============================================================================

class RuleEngine:
    def __init__(self, kg: KnowledgeGraph, rules: dict[str, Any] | None = None) -> None:
        self.kg = kg
        self.rules = rules or load_rules()
        self.tag_meta: dict[str, dict[str, str]] = self.rules.get("tags", {}) or {}
        self._compiled = [(r, self._compile(r)) for r in self.rules.get("rules", [])]

    def _compile(self, rule: dict[str, Any]) -> dict[str, Any]:
        m = dict(rule.get("match", {}) or {})
        for key in ("name_regex", "fqn_regex", "owner_regex", "writes_table_regex",
                    "reads_table_regex", "literal_regex", "param_name_regex"):
            if m.get(key):
                m[key] = re.compile(m[key])
        return m

    # -------------------------------------------------------------- matching
    def run(self) -> list[TagHit]:
        hits: list[TagHit] = []
        for label in ("Table", "Class", "Method", "Column"):
            for node in self.kg.nodes(label):
                for rule, m in self._compiled:
                    if m.get("node") and m["node"] != label:
                        continue
                    if self._matches(node, m):
                        tag = rule["tag"]
                        hits.append(TagHit(
                            node_id=node["id"], tag=tag, rule_id=rule["id"],
                            confidence=float(rule.get("confidence", 0.8)),
                            rationale=rule.get("rationale", ""),
                            clause=self.tag_meta.get(tag, {}).get("clause", ""),
                            source="rule",
                        ))
        return hits

    def _matches(self, node: dict[str, Any], m: dict[str, Any]) -> bool:
        nid = node["id"]
        name = str(node.get("name") or "")
        fqn = str(node.get("fqn") or name)

        if (rx := m.get("name_regex")) and not rx.search(name):
            return False
        if (rx := m.get("fqn_regex")) and not rx.search(fqn):
            return False
        if (rx := m.get("owner_regex")) and not rx.search(str(node.get("owner", ""))):
            return False

        if anns := m.get("annotation_any"):
            present = set(node.get("annotations", []) or [])
            if not present & set(anns):
                return False

        if prop := m.get("prop_true"):
            if not node.get(prop):
                return False

        if rx := m.get("writes_table_regex"):
            if not any(rx.search(self._table_name(t))
                       for t in self.kg.out_neighbors(nid, "WRITES")):
                return False

        if rx := m.get("reads_table_regex"):
            if not any(rx.search(self._table_name(t))
                       for t in self.kg.out_neighbors(nid, "READS")):
                return False

        if m.get("no_writes") and self.kg.out_neighbors(nid, "WRITES"):
            return False

        if calls := m.get("calls_any"):
            if not self._calls_any(node, calls):
                return False

        if rx := m.get("literal_regex"):
            if not self._literal_match(node, rx):
                return False

        if rx := m.get("param_name_regex"):
            if not any(rx.search(p) for p in (node.get("params", []) or [])):
                return False

        if types := m.get("param_type_any"):
            params = " ".join(node.get("params", []) or [])
            if not any(t in params for t in types):
                return False

        return True

    def _table_name(self, table_node_id: str) -> str:
        return str((self.kg.node(table_node_id) or {}).get("name", ""))

    def _calls_any(self, node: dict[str, Any], calls: list[str]) -> bool:
        """A call target appears either as a resolved CALLS edge or as an
        unresolved external call recorded on the method."""
        wanted = {c.split(".")[-1] for c in calls} | set(calls)
        for ext in node.get("externalCalls", []) or []:
            if ext in wanted or ext.split(".")[-1] in wanted:
                return True
        for mid in self.kg.out_neighbors(node["id"], "CALLS"):
            target = self.kg.node(mid) or {}
            if target.get("name") in wanted:
                return True
            if f"{target.get('ownerClass')}.{target.get('name')}" in wanted:
                return True
        return False

    def _literal_match(self, node: dict[str, Any], rx: re.Pattern[str]) -> bool:
        """Search the SQL and identifiers associated with a node.

        Method bodies are not retained on the graph, so the searchable surface
        is: table and column names it touches, its own parameters, and the
        external call names recorded during linking. This keeps the graph small
        without losing the literal evidence the rules need.
        """
        haystack: list[str] = [str(node.get("name", "")), str(node.get("fqn", ""))]
        haystack += [str(p) for p in (node.get("params", []) or [])]
        haystack += [str(e) for e in (node.get("externalCalls", []) or [])]
        for rel in ("READS", "WRITES"):
            for t in self.kg.out_neighbors(node["id"], rel):
                td = self.kg.node(t) or {}
                haystack.append(str(td.get("name", "")))
                for col in self.kg.out_neighbors(t, "CONTAINS"):
                    haystack.append(str((self.kg.node(col) or {}).get("name", "")))
        if node.get("usesNewDate"):
            haystack.append("new Date() System.currentTimeMillis()")
        if node.get("sqlLiterals"):
            haystack += [str(s) for s in node["sqlLiterals"]]
        return any(rx.search(h) for h in haystack if h)


# =============================================================================
# Tier assignment, propagation and gaps
# =============================================================================

def assign_tiers(kg: KnowledgeGraph, hits: list[TagHit], rules: dict[str, Any]) -> dict[str, str]:
    """PRD §9.2 tier formula, applied per node."""
    cfg = rules.get("tiers", {}) or {}
    high_tags = set(cfg.get("HIGH", {}).get("any_tag", []))
    medium_tags = set(cfg.get("MEDIUM", {}).get("any_tag", []))

    by_node: dict[str, set[str]] = {}
    for h in hits:
        by_node.setdefault(h.node_id, set()).add(h.tag)

    tiers: dict[str, str] = {}
    for nid, tags in by_node.items():
        writes = bool(kg.out_neighbors(nid, "WRITES"))
        if nid.startswith("class:"):
            writes = writes or any(
                kg.out_neighbors(m, "WRITES") for m in kg.children(nid)
            )
        if tags & high_tags:
            tiers[nid] = "HIGH"
        elif "DATA_INTEGRITY" in tags and writes:
            tiers[nid] = "HIGH"
        elif "DATA_INTEGRITY" in tags or tags & medium_tags:
            tiers[nid] = "MEDIUM"
        else:
            tiers[nid] = "LOW"
    return tiers


def roll_up_to_classes(kg: KnowledgeGraph, tiers: dict[str, str],
                       hits: list[TagHit]) -> tuple[dict[str, str], list[TagHit]]:
    """A class is at least as critical as its most critical method.

    Rules match methods and tables; the architecture decisions are made about
    classes and clusters. Without this roll-up a service whose only HIGH
    behaviour lives in one method would be scored as LOW.
    """
    extra: list[TagHit] = []
    tags_by_node: dict[str, set[str]] = {}
    for h in hits:
        tags_by_node.setdefault(h.node_id, set()).add(h.tag)

    for cid in kg.node_ids("Class"):
        best = tiers.get(cid, "LOW")
        inherited: set[str] = set()
        for mid in kg.children(cid):
            best = tier_max(best, tiers.get(mid, "LOW"))
            inherited |= tags_by_node.get(mid, set())
        # Tables the class touches also carry criticality.
        for mid in [cid, *kg.children(cid)]:
            for rel in ("READS", "WRITES"):
                for t in kg.out_neighbors(mid, rel):
                    t_tier = tiers.get(t, "LOW")
                    if rel == "WRITES":
                        best = tier_max(best, t_tier)
                    elif t_tier == "HIGH":
                        best = tier_max(best, "MEDIUM")
        own = tags_by_node.get(cid, set())
        for tag in inherited - own:
            extra.append(TagHit(
                node_id=cid, tag=tag, rule_id="ROLLUP_FROM_METHOD",
                confidence=0.8, source="propagated",
                rationale="Inherited from a method of this class.",
            ))
        if best != tiers.get(cid):
            tiers[cid] = best
    return tiers, extra


def propagate_indirect(kg: KnowledgeGraph, tiers: dict[str, str]) -> tuple[dict[str, str], list[TagHit], int]:
    """PRD §9.2 step 3: callers of HIGH write paths inherit MEDIUM (indirect).

    One hop only, and never a downgrade. Propagating further would turn the
    whole call graph MEDIUM and destroy the signal the decomposition needs.
    """
    extra: list[TagHit] = []
    count = 0
    high_nodes = [n for n, t in tiers.items() if t == "HIGH"]
    for nid in high_nodes:
        if not nid.startswith(("method:", "class:")):
            continue
        for caller in kg.in_neighbors(nid, "CALLS") + kg.in_neighbors(nid, "DEPENDS_ON"):
            if tiers.get(caller, "LOW") == "LOW":
                tiers[caller] = "MEDIUM"
                count += 1
                extra.append(TagHit(
                    node_id=caller, tag="DATA_INTEGRITY", rule_id="PROPAGATED_INDIRECT",
                    confidence=0.6, source="propagated",
                    rationale=f"Calls into a HIGH-tier path ({_short(nid)}); "
                              f"Annex 11 covers systems with indirect impact.",
                    clause="EU GMP Annex 11 (indirect impact)",
                ))
    return tiers, extra, count


def _short(node_id: str) -> str:
    return node_id.split(":", 1)[-1].split("#")[0].rsplit(".", 1)[-1]


# =============================================================================
# Compliance gap checks (PRD §9.4)
# =============================================================================

def detect_gaps(kg: KnowledgeGraph, rules: dict[str, Any], tiers: dict[str, str]) -> list[ComplianceGap]:
    catalog = {g["id"]: g for g in rules.get("gaps", [])}
    found: list[ComplianceGap] = []

    def emit(gap_id: str, evidence: list[str], note: str = "") -> None:
        spec = catalog.get(gap_id)
        if not spec or not evidence:
            return
        found.append(ComplianceGap(
            id=spec["id"], severity=spec["severity"], title=spec["title"],
            clause=spec.get("clause", ""), detail=spec.get("detail", ""),
            remediation=spec.get("remediation", ""),
            evidence_node_ids=evidence, evidence_note=note,
        ))

    audit_rx = re.compile(rules.get("audit_table_regex", "(?i)audit"))
    audit_tables = [t for t in kg.nodes("Table") if audit_rx.search(t.get("name", ""))]

    # --- audit trail cannot record a reason -------------------------------
    missing_reason = []
    for t in audit_tables:
        cols = {str((kg.node(c) or {}).get("name", "")).upper()
                for c in kg.out_neighbors(t["id"], "CONTAINS")}
        if cols and not any(re.search(r"REASON|JUSTIFICATION|COMMENT", c) for c in cols):
            missing_reason.append(t["id"])
    emit("AUDIT_NO_REASON", missing_reason,
         note=f"checked {len(audit_tables)} audit table(s)")

    # --- actor stored as free text ----------------------------------------
    free_text_actor = []
    for t in audit_tables:
        for c in kg.out_neighbors(t["id"], "CONTAINS"):
            cd = kg.node(c) or {}
            nm = str(cd.get("name", "")).upper()
            ty = str(cd.get("type", "")).upper()
            if re.search(r"CHANGED_BY|SIGNED_BY|ENTERED_BY|PERFORMED_BY|USER_NAME", nm) \
                    and ("VARCHAR" in ty or "CHAR" in ty or not ty):
                free_text_actor.append(c)
    emit("AUDIT_NO_ENTITY_LINK", free_text_actor)

    # --- application-server clock on GxP writes ---------------------------
    local_clock = []
    for mid in kg.node_ids("Method"):
        d = kg.node(mid) or {}
        if d.get("usesNewDate") and kg.out_neighbors(mid, "WRITES"):
            local_clock.append(mid)
    emit("LOCAL_TIME_SOURCE", local_clock,
         note=f"{len(local_clock)} write path(s) stamp records from the app server clock")

    # --- credentials in configuration -------------------------------------
    secrets = [c["id"] for c in kg.nodes("ConfigItem") if c.get("isSecret")]
    admin_secrets = [c["id"] for c in kg.nodes("ConfigItem")
                     if c.get("isSecret") and re.search(r"(?i)admin|root|sa\b", c.get("key", ""))]
    emit("SHARED_ADMIN_ACCOUNT", admin_secrets)
    emit("SECRETS_IN_CONFIG", [s for s in secrets if s not in admin_secrets])

    # --- GxP write with no audit-trail entry ------------------------------
    audit_table_ids = {t["id"] for t in audit_tables}
    audit_writers: set[str] = set()
    for t in audit_table_ids:
        audit_writers |= set(kg.in_neighbors(t, "WRITES"))
    audit_writer_classes = {kg.owner_class(m) for m in audit_writers}

    unaudited: list[str] = []
    for mid in kg.node_ids("Method"):
        writes = [t for t in kg.out_neighbors(mid, "WRITES") if t not in audit_table_ids]
        if not writes:
            continue
        if not any(tiers.get(t) in ("HIGH", "MEDIUM") for t in writes):
            continue
        if mid in audit_writers:
            continue
        # Does it reach the audit service, directly or one hop away?
        reaches = False
        for callee in kg.out_neighbors(mid, "CALLS"):
            if callee in audit_writers or kg.owner_class(callee) in audit_writer_classes:
                reaches = True
                break
            for deeper in kg.out_neighbors(callee, "CALLS"):
                if deeper in audit_writers:
                    reaches = True
                    break
            if reaches:
                break
        if not reaches:
            unaudited.append(mid)
    emit("NO_AUDIT_ON_GXP_WRITE", unaudited,
         note=f"{len(unaudited)} GxP write path(s) with no reachable audit-trail call")

    # --- local filesystem dependence on a GxP data path -------------------
    file_paths = [c["id"] for c in kg.nodes("ConfigItem") if c.get("kind") == "path"]
    file_methods = [m for m in kg.node_ids("Method") if (kg.node(m) or {}).get("usesLocalFile")]
    emit("LOCAL_FILE_DEPENDENCE", file_methods + file_paths)

    # --- database console exposed -----------------------------------------
    console = [c["id"] for c in kg.nodes("ConfigItem")
               if re.search(r"(?i)h2[.-]?console|console\.enabled", c.get("key", ""))]
    emit("H2_CONSOLE_ENABLED", console)

    # --- schema altered automatically at startup --------------------------
    auto_ddl = [c["id"] for c in kg.nodes("ConfigItem")
                if re.search(r"(?i)ddl-auto|hbm2ddl", c.get("key", ""))]
    emit("AUTO_SCHEMA_UPDATE", auto_ddl)

    # --- session state ----------------------------------------------------
    sessions = [m for m in kg.node_ids("Method") if (kg.node(m) or {}).get("usesHttpSession")]
    sessions += [c["id"] for c in kg.nodes("ConfigItem") if c.get("kind") == "session"]
    emit("STATEFUL_SESSION", sessions)

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    found.sort(key=lambda g: (order.get(g.severity, 3), g.id))
    return found


# =============================================================================
# Orchestration
# =============================================================================

def scan(
    kg: KnowledgeGraph,
    *,
    use_llm: bool = True,
    progress=None,
) -> GxpResult:
    """Run the full Engine 2 pipeline and write results onto the graph."""
    rules = load_rules()
    res = GxpResult(rules_version=str(rules.get("version", "")))

    if progress:
        progress(0.1, "applying deterministic GxP rules")
    engine = RuleEngine(kg, rules)
    res.hits = engine.run()
    res.tiers = assign_tiers(kg, res.hits, rules)

    if progress:
        progress(0.35, "rolling criticality up to classes")
    res.tiers, rollup = roll_up_to_classes(kg, res.tiers, res.hits)
    res.hits.extend(rollup)

    # Step 2: LLM only for the genuinely ambiguous residue.
    res.ambiguous = find_ambiguous(kg, res.tiers, rules)
    if use_llm and res.ambiguous:
        if progress:
            progress(0.5, f"classifying {len(res.ambiguous)} ambiguous component(s)")
        from .classifier import classify_ambiguous

        llm_hits, llm_tiers = classify_ambiguous(kg, res.ambiguous, rules)
        res.hits.extend(llm_hits)
        for nid, tier in llm_tiers.items():
            res.tiers[nid] = tier_max(res.tiers.get(nid, "LOW"), tier)
        res.llm_classified = len(llm_tiers)

    if progress:
        progress(0.7, "propagating indirect impact")
    res.tiers, propagated, n = propagate_indirect(kg, res.tiers)
    res.hits.extend(propagated)
    res.propagated = n

    if progress:
        progress(0.85, "checking for compliance gaps")
    res.gaps = detect_gaps(kg, rules, res.tiers)

    # Collect tags per node and write everything onto the graph.
    for h in res.hits:
        tags = res.tags_by_node.setdefault(h.node_id, [])
        if h.tag not in tags:
            tags.append(h.tag)

    write_to_graph(kg, res)
    if progress:
        progress(1.0, f"{res.summary()['class_tier_counts']['HIGH']} HIGH-tier classes, "
                      f"{len(res.gaps)} compliance gaps")
    log.info("gxp_scan_done", **res.summary())
    return res


def find_ambiguous(kg: KnowledgeGraph, tiers: dict[str, str], rules: dict[str, Any]) -> list[str]:
    """Classes that touch the regulated domain but no rule tiered above LOW.

    This is the only population the LLM sees, which keeps token cost bounded
    and keeps the deterministic engine responsible for everything it can decide.
    """
    entity_rx = re.compile(rules.get("gxp_entity_regex", "(?i)sample|result|batch"))
    out: list[str] = []
    for c in kg.classes():
        cid = c["id"]
        if tiers.get(cid, "LOW") != "LOW":
            continue
        if c.get("isTest"):
            continue
        touches = False
        for mid in [cid, *kg.children(cid)]:
            for rel in ("READS", "WRITES"):
                for t in kg.out_neighbors(mid, rel):
                    if entity_rx.search(str((kg.node(t) or {}).get("name", ""))):
                        touches = True
                        break
        if not touches and entity_rx.search(str(c.get("name", ""))):
            touches = True
        if touches:
            out.append(cid)
    return out


def write_to_graph(kg: KnowledgeGraph, res: GxpResult) -> None:
    """Persist tiers, tags and evidence onto graph nodes."""
    evidence: dict[str, list[dict[str, Any]]] = {}
    for h in res.hits:
        evidence.setdefault(h.node_id, []).append(h.as_dict())

    for nid, tier in res.tiers.items():
        if not kg.has(nid):
            continue
        kg.set_prop(nid, "gxpTier", tier)
        kg.set_prop(nid, "gxpTags", res.tags_by_node.get(nid, []))
        kg.set_prop(nid, "gxpEvidence", evidence.get(nid, [])[:12])

    # Everything untagged is explicitly LOW, not unknown.
    for label in ("Class", "Method", "Table"):
        for nid in kg.node_ids(label):
            if kg.node(nid).get("gxpTier") is None:
                kg.set_prop(nid, "gxpTier", "LOW")
                kg.set_prop(nid, "gxpTags", [])

    # A table is "regulated" when it holds GxP records.
    for t in kg.nodes("Table"):
        tags = set(res.tags_by_node.get(t["id"], []))
        regulated = bool(tags & {"DATA_INTEGRITY", "AUDIT_TRAIL", "E_SIGNATURE",
                                 "PRODUCT_RELEASE", "ACCESS_CONTROL"})
        kg.set_prop(t["id"], "regulated", regulated)

    for g in res.gaps:
        for nid in g.evidence_node_ids:
            if kg.has(nid):
                gaps = list(kg.node(nid).get("complianceGaps", []) or [])
                if g.id not in gaps:
                    gaps.append(g.id)
                kg.set_prop(nid, "complianceGaps", gaps)


def apply_override(kg: KnowledgeGraph, node_id: str, new_tier: str, reason: str, user: str) -> dict[str, Any]:
    """A QA reviewer's tier override (PRD §9.2 human review queue)."""
    node = kg.node(node_id)
    if node is None:
        raise KeyError(node_id)
    old = node.get("gxpTier", "LOW")
    kg.set_prop(node_id, "gxpTier", new_tier)
    kg.set_prop(node_id, "gxpOverridden", True)
    kg.set_prop(node_id, "gxpOverrideReason", reason)
    kg.set_prop(node_id, "gxpOverrideBy", user)
    ev = list(node.get("gxpEvidence", []) or [])
    ev.insert(0, {
        "node_id": node_id, "tag": "OVERRIDE", "rule_id": "HUMAN_OVERRIDE",
        "confidence": 1.0, "source": "override",
        "rationale": f"{user} set tier {old} -> {new_tier}: {reason}",
    })
    kg.set_prop(node_id, "gxpEvidence", ev[:12])
    return {"node_id": node_id, "old_tier": old, "new_tier": new_tier}
