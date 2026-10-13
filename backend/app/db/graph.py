"""The knowledge graph (PRD §16).

The graph is held in a NetworkX MultiDiGraph and persisted as JSON in SQLite, so
ModernRx needs no graph server to run. The *schema* is exactly the one in PRD
§16.1/§16.2 (labels ``Project|Module|Class|Method|Table|Column|Endpoint|Library|
ConfigItem|UseCase|Cluster|Decision`` and relationship types ``CONTAINS|CALLS|
DEPENDS_ON|READS|WRITES|EXPOSES|USES_LIB|CONFIGURED_BY|PART_OF_USECASE|
CO_CHANGES|IN_CLUSTER|DECIDED_FOR|EVIDENCED_BY``), and if ``NEO4J_URI`` is set
the same graph is mirrored into Neo4j for anyone who wants to run live Cypher.

Agents and the chat never run free-form Cypher. They call whitelisted templates
(``TEMPLATES`` below), each of which carries the equivalent Cypher for display.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.logging import get_logger
from .models import GraphBlob

log = get_logger("graph")

NODE_LABELS = (
    "Project", "Module", "Class", "Method", "Table", "Column",
    "Endpoint", "Library", "ConfigItem", "UseCase", "Cluster", "Decision",
)
REL_TYPES = (
    "CONTAINS", "CALLS", "DEPENDS_ON", "READS", "WRITES", "EXPOSES", "USES_LIB",
    "CONFIGURED_BY", "PART_OF_USECASE", "CO_CHANGES", "IN_CLUSTER", "DECIDED_FOR",
    "EVIDENCED_BY",
)


class KnowledgeGraph:
    """A project's digital twin."""

    def __init__(self, project_id: str, g: nx.MultiDiGraph | None = None) -> None:
        self.project_id = project_id
        self.g: nx.MultiDiGraph = g if g is not None else nx.MultiDiGraph()

    # ------------------------------------------------------------------ writes
    def add_node(self, node_id: str, label: str, **props: Any) -> str:
        if label not in NODE_LABELS:
            raise ValueError(f"unknown node label {label!r}")
        if self.g.has_node(node_id):
            self.g.nodes[node_id].update({k: v for k, v in props.items() if v is not None})
        else:
            self.g.add_node(node_id, label=label, id=node_id, **props)
        return node_id

    def add_edge(self, src: str, dst: str, rel: str, **props: Any) -> None:
        if rel not in REL_TYPES:
            raise ValueError(f"unknown relationship type {rel!r}")
        if not (self.g.has_node(src) and self.g.has_node(dst)):
            return  # never create phantom endpoints
        # Collapse duplicates of the same (src, rel, dst) and accumulate `count`.
        for _key, data in list(self.g.get_edge_data(src, dst, default={}).items()):
            if data.get("rel") == rel:
                if "count" in props or "count" in data:
                    data["count"] = data.get("count", 1) + props.get("count", 1)
                for k, v in props.items():
                    if k != "count":
                        data[k] = v
                return
        self.g.add_edge(src, dst, rel=rel, **props)

    def set_prop(self, node_id: str, key: str, value: Any) -> None:
        if self.g.has_node(node_id):
            self.g.nodes[node_id][key] = value

    # ------------------------------------------------------------------- reads
    def has(self, node_id: str) -> bool:
        return self.g.has_node(node_id)

    def node(self, node_id: str) -> dict[str, Any] | None:
        if not self.g.has_node(node_id):
            return None
        return dict(self.g.nodes[node_id])

    def nodes(self, label: str | None = None) -> list[dict[str, Any]]:
        out = []
        for _, data in self.g.nodes(data=True):
            if label is None or data.get("label") == label:
                out.append(dict(data))
        return out

    def node_ids(self, label: str | None = None) -> list[str]:
        return [n["id"] for n in self.nodes(label)]

    def edges(self, rel: str | None = None) -> list[dict[str, Any]]:
        out = []
        for u, v, data in self.g.edges(data=True):
            if rel is None or data.get("rel") == rel:
                out.append({"source": u, "target": v, **data})
        return out

    def out_neighbors(self, node_id: str, rel: str | None = None) -> list[str]:
        if not self.g.has_node(node_id):
            return []
        res = []
        for _, v, data in self.g.out_edges(node_id, data=True):
            if rel is None or data.get("rel") == rel:
                res.append(v)
        return sorted(set(res))

    def in_neighbors(self, node_id: str, rel: str | None = None) -> list[str]:
        if not self.g.has_node(node_id):
            return []
        res = []
        for u, _, data in self.g.in_edges(node_id, data=True):
            if rel is None or data.get("rel") == rel:
                res.append(u)
        return sorted(set(res))

    def children(self, node_id: str) -> list[str]:
        return self.out_neighbors(node_id, "CONTAINS")

    def classes(self) -> list[dict[str, Any]]:
        return self.nodes("Class")

    # --------------------------------------------------------- derived metrics
    def call_graph(self, level: str = "Class") -> nx.DiGraph:
        """Weighted directed call/dependency graph between nodes of one label."""
        dg = nx.DiGraph()
        for n in self.nodes(level):
            dg.add_node(n["id"])
        for u, v, data in self.g.edges(data=True):
            if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
                continue
            su, sv = self._owner(u, level), self._owner(v, level)
            if su and sv and su != sv:
                w = float(data.get("count", 1))
                if dg.has_edge(su, sv):
                    dg[su][sv]["weight"] += w
                else:
                    dg.add_edge(su, sv, weight=w)
        return dg

    def _owner(self, node_id: str, level: str) -> str | None:
        """Walk up CONTAINS until we reach a node of the requested label."""
        seen = set()
        cur = node_id
        while cur and cur not in seen:
            seen.add(cur)
            data = self.g.nodes.get(cur)
            if not data:
                return None
            if data.get("label") == level:
                return cur
            parents = self.in_neighbors(cur, "CONTAINS")
            cur = parents[0] if parents else None
        return None

    def owner_class(self, node_id: str) -> str | None:
        return self._owner(node_id, "Class")

    def blast_radius(self, node_id: str, hops: int = 3) -> list[dict[str, Any]]:
        """Everything that (transitively) depends on this node — PRD §8.3."""
        frontier = {node_id}
        seen = {node_id}
        out: list[dict[str, Any]] = []
        for depth in range(1, hops + 1):
            nxt: set[str] = set()
            for n in frontier:
                for u in self.in_neighbors(n):
                    rel_ok = any(
                        d.get("rel") in ("CALLS", "DEPENDS_ON")
                        for d in (self.g.get_edge_data(u, n) or {}).values()
                    )
                    if rel_ok and u not in seen:
                        seen.add(u)
                        nxt.add(u)
                        data = self.node(u) or {}
                        out.append({
                            "id": u,
                            "label": data.get("label"),
                            "fqn": data.get("fqn", u),
                            "gxpTier": data.get("gxpTier", "LOW"),
                            "hops": depth,
                        })
            frontier = nxt
            if not frontier:
                break
        return out

    # -------------------------------------------------------------- statistics
    def stats(self) -> dict[str, Any]:
        by_label: dict[str, int] = {}
        for _, d in self.g.nodes(data=True):
            by_label[d.get("label", "?")] = by_label.get(d.get("label", "?"), 0) + 1
        by_rel: dict[str, int] = {}
        for _, _, d in self.g.edges(data=True):
            by_rel[d.get("rel", "?")] = by_rel.get(d.get("rel", "?"), 0) + 1
        return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges(),
                "by_label": by_label, "by_rel": by_rel}

    # ------------------------------------------------------------ persistence
    def to_payload(self) -> dict[str, Any]:
        return {
            "nodes": [dict(d) for _, d in self.g.nodes(data=True)],
            "edges": [{"source": u, "target": v, **d} for u, v, d in self.g.edges(data=True)],
        }

    @classmethod
    def from_payload(cls, project_id: str, payload: dict[str, Any]) -> KnowledgeGraph:
        g = nx.MultiDiGraph()
        for n in payload.get("nodes", []):
            nid = n.get("id")
            if nid:
                g.add_node(nid, **n)
        for e in payload.get("edges", []):
            s, t = e.get("source"), e.get("target")
            if s in g and t in g:
                props = {k: v for k, v in e.items() if k not in ("source", "target")}
                g.add_edge(s, t, **props)
        return cls(project_id, g)

    def save(self, db: Session, *, mirror: bool = True) -> None:
        payload = self.to_payload()
        blob = db.get(GraphBlob, self.project_id)
        if blob is None:
            db.add(GraphBlob(project_id=self.project_id, payload_json=payload))
        else:
            blob.payload_json = payload
        db.commit()
        if mirror and settings.neo4j_uri:
            try:
                mirror_to_neo4j(self)
            except Exception as exc:  # never let an optional mirror break analysis
                log.warning("neo4j_mirror_failed", error=str(exc))

    @classmethod
    def load(cls, db: Session, project_id: str) -> KnowledgeGraph:
        blob = db.get(GraphBlob, project_id)
        return cls.from_payload(project_id, blob.payload_json if blob else {})

    @classmethod
    def exists(cls, db: Session, project_id: str) -> bool:
        blob = db.execute(
            select(GraphBlob.project_id).where(GraphBlob.project_id == project_id)
        ).scalar_one_or_none()
        return blob is not None


# =============================================================================
# Whitelisted query templates (PRD §8.2: "only whitelisted query templates, no
# free Cypher → safe"). Each entry declares its params, its real Cypher (shown
# in the UI so reviewers can see the query), and a Python executor.
# =============================================================================

def _q_writers_of_table(kg: KnowledgeGraph, table: str = "", **_: Any) -> list[dict[str, Any]]:
    needle = (table or "").lower()
    rows = []
    for t in kg.nodes("Table"):
        if needle and needle not in t["name"].lower():
            continue
        for m in kg.in_neighbors(t["id"], "WRITES"):
            md = kg.node(m) or {}
            rows.append({
                "method": md.get("fqn", m), "class": md.get("owner", ""),
                "table": t["name"], "gxpTier": md.get("gxpTier", "LOW"),
                "fanIn": md.get("fanIn", 0), "node_id": m,
            })
    rows.sort(key=lambda r: (-r["fanIn"], r["method"]))
    return rows


def _q_readers_of_table(kg: KnowledgeGraph, table: str = "", **_: Any) -> list[dict[str, Any]]:
    needle = (table or "").lower()
    rows = []
    for t in kg.nodes("Table"):
        if needle and needle not in t["name"].lower():
            continue
        for m in kg.in_neighbors(t["id"], "READS"):
            md = kg.node(m) or {}
            rows.append({"method": md.get("fqn", m), "table": t["name"],
                         "gxpTier": md.get("gxpTier", "LOW"), "node_id": m})
    return rows


def _q_blast_radius(kg: KnowledgeGraph, fqn: str = "", hops: int = 3, **_: Any) -> list[dict[str, Any]]:
    target = _resolve(kg, fqn)
    return kg.blast_radius(target, int(hops)) if target else []


def _q_high_tier_classes(kg: KnowledgeGraph, **_: Any) -> list[dict[str, Any]]:
    return [
        {"fqn": c.get("fqn", c["id"]), "gxpTier": c.get("gxpTier"), "gxpTags": c.get("gxpTags", []),
         "readiness": c.get("readiness"), "loc": c.get("loc"), "node_id": c["id"]}
        for c in kg.classes() if c.get("gxpTier") == "HIGH"
    ]


def _q_class_detail(kg: KnowledgeGraph, fqn: str = "", **_: Any) -> list[dict[str, Any]]:
    cid = _resolve(kg, fqn)
    if not cid:
        return []
    d = kg.node(cid) or {}
    methods = [kg.node(m) or {} for m in kg.children(cid)]
    tables: set[str] = set()
    for m in [cid, *kg.children(cid)]:
        for rel in ("READS", "WRITES"):
            for t in kg.out_neighbors(m, rel):
                td = kg.node(t) or {}
                tables.add(f"{rel}:{td.get('name', t)}")
    return [{
        "fqn": d.get("fqn"), "loc": d.get("loc"), "complexity": d.get("complexity"),
        "fanIn": d.get("fanIn"), "fanOut": d.get("fanOut"), "gxpTier": d.get("gxpTier"),
        "gxpTags": d.get("gxpTags", []), "readiness": d.get("readiness"),
        "clusterId": d.get("clusterId"), "runtimeHits": d.get("runtimeHits", 0),
        "methods": [m.get("name") for m in methods], "tables": sorted(tables), "node_id": cid,
    }]


def _q_shared_tables(kg: KnowledgeGraph, min_accessors: int = 2, **_: Any) -> list[dict[str, Any]]:
    """Tables reached by more than one class.

    Counting *accessors* rather than only writers is the right coupling signal:
    a table one service writes and another reads is exactly the dependency that
    stops either being extracted independently, even though it has one writer.
    """
    rows = []
    for t in kg.nodes("Table"):
        writers = {kg.owner_class(m) for m in kg.in_neighbors(t["id"], "WRITES")}
        writers.discard(None)
        readers = {kg.owner_class(m) for m in kg.in_neighbors(t["id"], "READS")}
        readers.discard(None)
        accessors = writers | readers
        if len(accessors) >= int(min_accessors):
            rows.append({
                "table": t["name"], "regulated": t.get("regulated", False),
                "accessor_count": len(accessors), "writer_count": len(writers),
                "writers": sorted(kg.node(w).get("fqn", w) for w in writers if w),
                "readers": sorted(kg.node(r).get("fqn", r) for r in readers - writers if r),
                "shared_write": len(writers) > 1,
                "node_id": t["id"],
            })
    rows.sort(key=lambda r: (-r["writer_count"], -r["accessor_count"]))
    return rows


def _q_eol_libraries(kg: KnowledgeGraph, **_: Any) -> list[dict[str, Any]]:
    return [
        {"name": l.get("name"), "version": l.get("version"), "eol": l.get("eol"),
         "reason": l.get("eolReason", ""), "node_id": l["id"]}
        for l in kg.nodes("Library") if l.get("eol")
    ]


def _q_config_findings(kg: KnowledgeGraph, kind: str = "", **_: Any) -> list[dict[str, Any]]:
    return [
        {"key": c.get("key"), "value": c.get("valueMasked"), "kind": c.get("kind"),
         "file": c.get("file"), "node_id": c["id"]}
        for c in kg.nodes("ConfigItem") if not kind or c.get("kind") == kind
    ]


def _q_usecase_members(kg: KnowledgeGraph, name: str = "", **_: Any) -> list[dict[str, Any]]:
    rows = []
    for uc in kg.nodes("UseCase"):
        if name and name.lower() not in uc.get("name", "").lower():
            continue
        for m in kg.in_neighbors(uc["id"], "PART_OF_USECASE"):
            md = kg.node(m) or {}
            hits = 0
            for d in (kg.g.get_edge_data(m, uc["id"]) or {}).values():
                if d.get("rel") == "PART_OF_USECASE":
                    hits = d.get("hits", 0)
            rows.append({"usecase": uc.get("name"), "member": md.get("fqn", m),
                         "hits": hits, "gxpTier": md.get("gxpTier"), "node_id": m})
    rows.sort(key=lambda r: -r["hits"])
    return rows


def _q_dead_code(kg: KnowledgeGraph, **_: Any) -> list[dict[str, Any]]:
    """Classes nothing reaches.

    A class is only called dead when *every* route to it is absent: no inbound
    call or dependency, no runtime hit, not an HTTP/main entrypoint, not
    instantiated anywhere, not named in any signature, and not container-managed
    (a Spring stereotype means the framework constructs it by reflection, which
    static analysis cannot see). Being strict here matters — recommending the
    deletion of live code is the worst mistake this tool could make.
    """
    rows = []
    for c in kg.classes():
        if c.get("fanIn", 0) or c.get("runtimeHits", 0):
            continue
        if c.get("isEntrypoint") or c.get("isInstantiated") or c.get("isTypeReferenced"):
            continue
        if _container_managed(c) or c.get("isEntity") or c.get("isTest"):
            continue
        rows.append({
            "fqn": c.get("fqn"), "loc": c.get("loc"), "path": c.get("path"),
            "methodCount": c.get("methodCount"), "node_id": c["id"],
        })
    rows.sort(key=lambda r: -(r.get("loc") or 0))
    return rows


SPRING_STEREOTYPES = {
    "Component", "Service", "Repository", "Controller", "RestController",
    "Configuration", "SpringBootApplication", "Bean", "ControllerAdvice",
    "Aspect", "Entity", "Embeddable", "Converter", "WebServlet", "WebFilter",
}


def _container_managed(node: dict[str, Any]) -> bool:
    return bool(set(node.get("annotations", []) or []) & SPRING_STEREOTYPES)


def _q_cluster_summary(kg: KnowledgeGraph, cluster_id: str = "", **_: Any) -> list[dict[str, Any]]:
    rows = []
    for cl in kg.nodes("Cluster"):
        if cluster_id and cl["id"] != cluster_id and cl.get("name") != cluster_id:
            continue
        members = [kg.node(m) or {} for m in kg.in_neighbors(cl["id"], "IN_CLUSTER")]
        rows.append({
            "cluster_id": cl["id"], "name": cl.get("name"), "size": len(members),
            "gxpMax": cl.get("gxpMax"), "readinessAvg": cl.get("readinessAvg"),
            "members": [m.get("fqn") for m in members], "node_id": cl["id"],
        })
    return rows


def _resolve(kg: KnowledgeGraph, fqn: str) -> str | None:
    """Accept a node id, a fully-qualified name, or a bare class name."""
    if not fqn:
        return None
    if kg.has(fqn):
        return fqn
    low = fqn.lower()
    best = None
    for n in kg.g.nodes(data=True):
        nid, data = n
        name = str(data.get("fqn") or data.get("name") or nid)
        if name.lower() == low:
            return nid
        if name.lower().endswith("." + low) or name.lower().split(".")[-1] == low:
            best = best or nid
    return best


TEMPLATES: dict[str, dict[str, Any]] = {
    "writers_of_table": {
        "description": "Which methods WRITE to a (regulated) table, highest fan-in first.",
        "params": {"table": "table name or fragment"},
        "cypher": "MATCH (m:Method)-[:WRITES]->(t:Table)\nWHERE toLower(t.name) CONTAINS toLower($table)\nRETURN m.fqn, m.owner, t.name, m.gxpTier, m.fanIn\nORDER BY m.fanIn DESC",
        "fn": _q_writers_of_table,
    },
    "readers_of_table": {
        "description": "Which methods READ a table (read-only consumers).",
        "params": {"table": "table name or fragment"},
        "cypher": "MATCH (m:Method)-[:READS]->(t:Table)\nWHERE toLower(t.name) CONTAINS toLower($table)\nRETURN m.fqn, t.name, m.gxpTier",
        "fn": _q_readers_of_table,
    },
    "blast_radius": {
        "description": "Everything that transitively depends on a class — the re-validation blast radius.",
        "params": {"fqn": "class fully-qualified or simple name", "hops": "1..5 (default 3)"},
        "cypher": "MATCH (c:Class {fqn:$fqn})<-[:CALLS|DEPENDS_ON*1..3]-(x)\nRETURN DISTINCT x.fqn, x.gxpTier",
        "fn": _q_blast_radius,
    },
    "high_tier_classes": {
        "description": "All HIGH GxP-tier classes (the validated core).",
        "params": {},
        "cypher": "MATCH (c:Class {gxpTier:'HIGH'})\nRETURN c.fqn, c.gxpTags, c.readiness, c.loc",
        "fn": _q_high_tier_classes,
    },
    "class_detail": {
        "description": "Full profile of one class: metrics, GxP tags, tables, methods, cluster.",
        "params": {"fqn": "class name"},
        "cypher": "MATCH (c:Class {fqn:$fqn})\nOPTIONAL MATCH (c)-[:CONTAINS]->(m:Method)\nOPTIONAL MATCH (m)-[r:READS|WRITES]->(t:Table)\nRETURN c, collect(m.name), collect(type(r)+':'+t.name)",
        "fn": _q_class_detail,
    },
    "shared_tables": {
        "description": "Tables written by more than one class — the database-coupling blockers.",
        "params": {"min_writers": "minimum distinct writing classes (default 2)"},
        "cypher": "MATCH (c:Class)-[:CONTAINS]->(:Method)-[:WRITES]->(t:Table)\nWITH t, count(DISTINCT c) AS writers\nWHERE writers >= $min_writers\nRETURN t.name, t.regulated, writers ORDER BY writers DESC",
        "fn": _q_shared_tables,
    },
    "eol_libraries": {
        "description": "Third-party libraries past end-of-life.",
        "params": {},
        "cypher": "MATCH (l:Library {eol:true}) RETURN l.name, l.version",
        "fn": _q_eol_libraries,
    },
    "config_findings": {
        "description": "Configuration items: hosts, local paths, ports, secrets (values masked).",
        "params": {"kind": "host|path|secret|port|url (optional)"},
        "cypher": "MATCH (c:ConfigItem) WHERE $kind = '' OR c.kind = $kind\nRETURN c.key, c.valueMasked, c.kind",
        "fn": _q_config_findings,
    },
    "usecase_members": {
        "description": "Which methods participate in a runtime use case, by hit count.",
        "params": {"name": "use-case name fragment"},
        "cypher": "MATCH (m:Method)-[r:PART_OF_USECASE]->(u:UseCase)\nWHERE toLower(u.name) CONTAINS toLower($name)\nRETURN u.name, m.fqn, r.hits ORDER BY r.hits DESC",
        "fn": _q_usecase_members,
    },
    "dead_code": {
        "description": "Classes with no inbound calls and no runtime hits — retire candidates.",
        "params": {},
        "cypher": "MATCH (c:Class) WHERE c.fanIn = 0 AND c.runtimeHits = 0\nRETURN c.fqn, c.loc",
        "fn": _q_dead_code,
    },
    "cluster_summary": {
        "description": "Proposed service clusters with size, max GxP tier and average readiness.",
        "params": {"cluster_id": "cluster id or name (optional)"},
        "cypher": "MATCH (c:Cluster)<-[:IN_CLUSTER]-(m:Class)\nRETURN c.id, c.name, count(m), c.gxpMax, c.readinessAvg",
        "fn": _q_cluster_summary,
    },
}


def run_template(kg: KnowledgeGraph, template_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a whitelisted template. Unknown ids are rejected, never guessed."""
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        return {
            "template_id": template_id, "error": "unknown template",
            "available": sorted(TEMPLATES), "rows": [],
        }
    params = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        rows = tpl["fn"](kg, **params)
    except TypeError as exc:
        return {"template_id": template_id, "error": f"bad params: {exc}",
                "expects": tpl["params"], "rows": []}
    return {
        "template_id": template_id, "description": tpl["description"],
        "cypher": tpl["cypher"], "params": params,
        "row_count": len(rows), "rows": rows[:200],
    }


def describe_templates() -> list[dict[str, Any]]:
    return [
        {"id": k, "description": v["description"], "params": v["params"], "cypher": v["cypher"]}
        for k, v in sorted(TEMPLATES.items())
    ]


# ----------------------------------------------------------- optional mirror
def mirror_to_neo4j(kg: KnowledgeGraph) -> None:
    """Push the graph into a real Neo4j when NEO4J_URI is configured."""
    from neo4j import GraphDatabase  # imported lazily — optional dependency

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    payload = kg.to_payload()
    with driver.session() as s:
        s.run("MATCH (n {projectId:$pid}) DETACH DELETE n", pid=kg.project_id)
        for n in payload["nodes"]:
            label = n.get("label", "Node")
            props = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                     for k, v in n.items() if k != "label"}
            props["projectId"] = kg.project_id
            s.run(f"CREATE (n:{label}) SET n = $props", props=props)
        for e in payload["edges"]:
            rel = e.get("rel", "DEPENDS_ON")
            props = {k: v for k, v in e.items()
                     if k not in ("source", "target", "rel") and not isinstance(v, (list, dict))}
            s.run(
                f"MATCH (a {{id:$s, projectId:$pid}}), (b {{id:$t, projectId:$pid}}) "
                f"CREATE (a)-[r:{rel}]->(b) SET r = $props",
                s=e["source"], t=e["target"], pid=kg.project_id, props=props,
            )
    driver.close()
    log.info("neo4j_mirrored", project=kg.project_id, nodes=len(payload["nodes"]))
