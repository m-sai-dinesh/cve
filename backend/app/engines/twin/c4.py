"""Auto-generated C4 diagrams in Mermaid (PRD §8.2).

C4 level 1 (context), 2 (containers) and 3 (components) are rendered from the
graph, plus a sequence diagram per runtime use case — which is the one view a
validation reviewer actually asks for, because it shows the path a GxP record
takes through the system.
"""
from __future__ import annotations

import re
from typing import Any

from ...db.graph import KnowledgeGraph

TIER_CLASS = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}

STYLE_BLOCK = """
    classDef high fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fee2e2;
    classDef medium fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7;
    classDef low fill:#14532d,stroke:#22c55e,stroke-width:1px,color:#dcfce7;
    classDef ext fill:#1e293b,stroke:#64748b,stroke-width:1px,color:#e2e8f0;
    classDef store fill:#1e3a8a,stroke:#3b82f6,stroke-width:1px,color:#dbeafe;
"""


def _mid(prefix: str, text: str) -> str:
    """A Mermaid-safe node id."""
    return prefix + re.sub(r"[^A-Za-z0-9]", "_", text)[:60]


def _label(text: str) -> str:
    """Escape a label for a Mermaid node."""
    return str(text).replace('"', "'").replace("\n", " ")


def context_diagram(kg: KnowledgeGraph) -> str:
    """C4 L1: the system, its users, and the systems it talks to."""
    project = (kg.nodes("Project") or [{}])[0]
    name = project.get("name", "System")
    lines = ["graph TB"]
    lines.append('    user["Lab analyst / Reviewer / QP<br/><i>Person</i>"]')
    lines.append(f'    sys["{_label(name)}<br/><i>Software system</i>"]')
    lines.append("    user -->|uses| sys")

    externals: dict[str, str] = {}
    for c in kg.nodes("ConfigItem"):
        kind, key, val = c.get("kind"), c.get("key", ""), c.get("valueMasked", "")
        if kind in ("url", "host") and val:
            label = _peer_label(key)
            externals[label] = kind
        elif kind == "jdbc":
            externals["Relational database"] = "store"
        elif kind == "path":
            externals["Instrument / report file share"] = "store"

    for label, kind in sorted(externals.items()):
        nid = _mid("x_", label)
        lines.append(f'    {nid}["{_label(label)}<br/><i>External</i>"]')
        lines.append(f"    sys -->|integrates| {nid}")
        lines.append(f"    class {nid} {'store' if kind == 'store' else 'ext'}")

    lines.append(STYLE_BLOCK)
    return "\n".join(lines)


def _peer_label(key: str) -> str:
    k = key.lower()
    for token, label in (
        ("mes", "MES (manufacturing execution)"), ("erp", "ERP"),
        ("ldap", "Directory service (LDAP)"), ("smtp", "Mail relay"),
        ("qms", "QMS"), ("mail", "Mail relay"),
    ):
        if token in k:
            return label
    return key


def container_diagram(kg: KnowledgeGraph) -> str:
    """C4 L2: deployable units. Before decomposition the monolith is one box;
    after, each proposed cluster is a candidate container."""
    clusters = kg.nodes("Cluster")
    lines = ["graph TB"]
    lines.append('    user["Lab user"]')

    if not clusters:
        project = (kg.nodes("Project") or [{}])[0]
        lines.append(f'    mono["{_label(project.get("name", "Monolith"))}<br/>'
                     f'<i>Single deployable: {project.get("primaryLanguage", "")}, '
                     f'{project.get("loc", 0):,} LOC</i>"]')
        lines.append("    user --> mono")
        for t in sorted(kg.nodes("Table"), key=lambda n: n.get("name", ""))[:12]:
            tid = _mid("t_", t["name"])
            lines.append(f'    {tid}[("{_label(t["name"])}")]')
            lines.append(f"    mono --> {tid}")
            lines.append(f"    class {tid} store")
        lines.append(STYLE_BLOCK)
        return "\n".join(lines)

    for cl in sorted(clusters, key=lambda c: c.get("name", "")):
        cid = _mid("c_", cl["id"])
        tier = cl.get("gxpMax", "LOW")
        lines.append(
            f'    {cid}["{_label(cl.get("name", cl["id"]))}<br/>'
            f'<i>{cl.get("size", 0)} classes &middot; GxP {tier} &middot; '
            f'readiness {round(cl.get("readinessAvg") or 0)}</i>"]'
        )
        lines.append(f"    class {cid} {TIER_CLASS.get(tier, 'low')}")
        if cl.get("hasEndpoints"):
            lines.append(f"    user --> {cid}")

    # Inter-cluster dependencies, aggregated from class-level calls.
    seen: set[tuple[str, str]] = set()
    for u, v, data in kg.g.edges(data=True):
        if data.get("rel") not in ("CALLS", "DEPENDS_ON"):
            continue
        cu = _cluster_of(kg, u)
        cv = _cluster_of(kg, v)
        if cu and cv and cu != cv and (cu, cv) not in seen:
            seen.add((cu, cv))
            lines.append(f"    {_mid('c_', cu)} --> {_mid('c_', cv)}")

    for t in sorted(kg.nodes("Table"), key=lambda n: n.get("name", "")):
        if not t.get("regulated"):
            continue
        tid = _mid("t_", t["name"])
        lines.append(f'    {tid}[("{_label(t["name"])}<br/><i>regulated</i>")]')
        lines.append(f"    class {tid} store")

    lines.append(STYLE_BLOCK)
    return "\n".join(lines)


def _cluster_of(kg: KnowledgeGraph, node_id: str) -> str | None:
    owner = kg.owner_class(node_id)
    if not owner:
        return None
    return (kg.node(owner) or {}).get("clusterId")


def component_diagram(kg: KnowledgeGraph, module: str = "", limit: int = 28) -> str:
    """C4 L3: classes inside one module (or the busiest classes overall)."""
    classes = kg.classes()
    if module:
        classes = [c for c in classes if c.get("package", "").startswith(module)]
    classes = sorted(classes, key=lambda c: -(c.get("fanIn", 0) + c.get("fanOut", 0)))[:limit]
    keep = {c["id"] for c in classes}

    lines = ["graph LR"]
    by_pkg: dict[str, list[dict[str, Any]]] = {}
    for c in classes:
        by_pkg.setdefault(c.get("package", "(default)"), []).append(c)

    for pkg, members in sorted(by_pkg.items()):
        lines.append(f'    subgraph {_mid("s_", pkg)}["{_label(pkg.rsplit(".", 1)[-1])}"]')
        for c in sorted(members, key=lambda n: n.get("name", "")):
            nid = _mid("n_", c["id"])
            tier = c.get("gxpTier", "LOW")
            tags = ", ".join((c.get("gxpTags") or [])[:2])
            sub = f"<br/><i>{_label(tags)}</i>" if tags else ""
            lines.append(f'        {nid}["{_label(c.get("name"))}{sub}"]')
            lines.append(f"        class {nid} {TIER_CLASS.get(tier, 'low')}")
        lines.append("    end")

    for u, v, data in kg.g.edges(data=True):
        if data.get("rel") != "DEPENDS_ON":
            continue
        if u in keep and v in keep and u != v:
            lines.append(f"    {_mid('n_', u)} --> {_mid('n_', v)}")

    lines.append(STYLE_BLOCK)
    return "\n".join(lines)


def usecase_sequence(kg: KnowledgeGraph, usecase_name: str) -> str:
    """Sequence diagram for one observed use case, ordered by runtime hits."""
    uid = f"usecase:{usecase_name}"
    if not kg.has(uid):
        for u in kg.nodes("UseCase"):
            if usecase_name.lower() in u.get("name", "").lower():
                uid = u["id"]
                break
        else:
            return "sequenceDiagram\n    Note over System: no runtime trace for this use case"

    members: list[tuple[int, str, str]] = []
    for mid in kg.in_neighbors(uid, "PART_OF_USECASE"):
        d = kg.node(mid) or {}
        if d.get("label") != "Method":
            continue
        hits = 0
        for e in (kg.g.get_edge_data(mid, uid) or {}).values():
            if e.get("rel") == "PART_OF_USECASE":
                hits = e.get("hits", 0)
        members.append((hits, str(d.get("ownerClass", "?")), str(d.get("name", "?"))))
    members.sort(key=lambda x: -x[0])

    lines = ["sequenceDiagram", "    autonumber", "    actor User"]
    participants: list[str] = []
    for _, cls, _m in members:
        if cls not in participants:
            participants.append(cls)
    for p in participants[:10]:
        lines.append(f"    participant {_mid('p_', p)} as {_label(p)}")

    prev = "User"
    for hits, cls, method in members[:14]:
        pid = _mid("p_", cls)
        if cls not in participants[:10]:
            continue
        lines.append(f"    {prev}->>{pid}: {_label(method)}() <br/>{hits:,} calls observed")
        prev = pid
    return "\n".join(lines)


def generate_all(kg: KnowledgeGraph) -> dict[str, Any]:
    """Every diagram the UI and the evidence pack need."""
    usecases = sorted(kg.nodes("UseCase"), key=lambda u: u.get("name", ""))
    return {
        "context": context_diagram(kg),
        "containers": container_diagram(kg),
        "components": component_diagram(kg),
        "usecases": {
            u["name"]: usecase_sequence(kg, u["name"]) for u in usecases[:12]
        },
        "modules": sorted({c.get("package", "") for c in kg.classes() if c.get("package")}),
    }
