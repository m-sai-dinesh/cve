"""Build the knowledge graph from parsed source (PRD §8.1 step 8, schema §16).

Node id conventions — stable, human-readable, and what agents cite as evidence:
    Project     project:<id>
    Module      module:<dotted.package>
    Class       class:<fully.qualified.Name>
    Method      method:<fully.qualified.Name#signature>
    Table       table:<NAME>
    Column      column:<TABLE>.<NAME>
    Endpoint    endpoint:<VERB> <path>
    Library     lib:<name>@<version>
    ConfigItem  config:<file>#<key>
    UseCase     usecase:<name>
"""
from __future__ import annotations

import re
from typing import Any

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph
from .ingest import IngestResult
from .parsers.java import JavaFile, MethodInfo, TypeInfo
from .parsers.sql import analyze_sql, looks_like_sql

log = get_logger("graph_builder")

HTTP_ANNOTATIONS = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "DeleteMapping": "DELETE", "PatchMapping": "PATCH", "RequestMapping": "ANY",
    "HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT", "HttpDelete": "DELETE",
}
CONTROLLER_ANNOTATIONS = {"Controller", "RestController", "ApiController", "WebServlet"}
ENTITY_ANNOTATIONS = {"Entity", "Table", "Document"}

# JPA/JDBC call names that imply a read or a write even without visible SQL.
WRITE_CALL_NAMES = {"save", "saveAll", "persist", "merge", "insert", "delete", "deleteById",
                    "remove", "update", "saveAndFlush", "executeUpdate", "batchUpdate"}
READ_CALL_NAMES = {"find", "findAll", "findById", "findOne", "get", "getOne", "query",
                   "queryForObject", "queryForList", "queryForMap", "getResultList",
                   "getSingleResult", "count", "exists", "existsById", "stream"}

PATH_ARG_RE = re.compile(r'"([^"]*)"')
COLUMN_NAME_RE = re.compile(r'name\s*=\s*"([^"]+)"')


def _table_from_entity(t: TypeInfo) -> str | None:
    """Physical table for a JPA entity: @Table(name=...) else the class name."""
    for a in t.annotations:
        if a["name"] == "Table":
            m = COLUMN_NAME_RE.search(a["args"]) or PATH_ARG_RE.search(a["args"])
            if m:
                return m.group(1).upper()
    if t.annotation_names() & ENTITY_ANNOTATIONS:
        return _camel_to_upper(t.name)
    return None


def _camel_to_upper(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _join_path(*parts: str) -> str:
    out = "/" + "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return out or "/"


def _annotation_path(args: str) -> str:
    """The path out of @GetMapping("/x") or @RequestMapping(value="/x", ...)."""
    if not args:
        return ""
    m = re.search(r'(?:value|path)\s*=\s*"([^"]*)"', args) or PATH_ARG_RE.search(args)
    return m.group(1) if m else ""


class GraphBuilder:
    def __init__(self, project_id: str, project_name: str, target_cloud: str = "AWS") -> None:
        self.kg = KnowledgeGraph(project_id)
        self.project_node = f"project:{project_id}"
        self.kg.add_node(self.project_node, "Project", name=project_name, targetCloud=target_cloud)
        # simple class name -> [class node id]; used to resolve calls
        self._by_simple: dict[str, list[str]] = {}
        self._by_fqn: dict[str, str] = {}
        # field/variable type hints per class: name -> simple type
        self._field_types: dict[str, dict[str, str]] = {}
        self._method_index: dict[str, list[str]] = {}   # class node -> method nodes
        self._tables: set[str] = set()

    # ------------------------------------------------------------------ pass 1
    def add_structure(self, res: IngestResult) -> None:
        """Modules, classes, methods, fields, endpoints — no cross-links yet."""
        for jf in res.code_files:
            module_id = self._ensure_module(jf)
            for t in jf.types:
                cid = f"class:{t.fqn}"
                anns = t.annotation_names()
                self.kg.add_node(
                    cid, "Class",
                    fqn=t.fqn, name=t.name, kind=t.kind, package=t.package, path=jf.path,
                    language=jf.language, loc=t.loc,
                    complexity=sum(m.complexity for m in t.methods),
                    maxMethodComplexity=max([m.complexity for m in t.methods] or [0]),
                    methodCount=len(t.methods),
                    annotations=sorted(anns),
                    extends=t.extends,
                    isEntrypoint=bool(anns & CONTROLLER_ANNOTATIONS) or any(
                        m.name == "main" and m.is_static for m in t.methods
                    ),
                    isController=bool(anns & CONTROLLER_ANNOTATIONS),
                    isEntity=bool(anns & ENTITY_ANNOTATIONS),
                    isTest=_looks_test(jf.path, t.name),
                    startLine=t.start_line, endLine=t.end_line,
                    fanIn=0, fanOut=0, runtimeHits=0,
                )
                self.kg.add_edge(module_id, cid, "CONTAINS")
                self._by_simple.setdefault(t.name, []).append(cid)
                self._by_fqn[t.fqn] = cid

                # Field types let us resolve `this.auditService.record(...)`.
                ftypes = self._field_types.setdefault(cid, {})
                for f in t.fields:
                    ftypes[f["name"]] = _base_type(f["type"])

                # Readiness signals that live at field level (PRD §10).
                # A static non-final field is shared process state: it works on
                # one instance and diverges the moment a second one starts.
                static_mutable = [
                    f["name"] for f in t.fields
                    if f.get("static") and not f.get("final")
                ]
                # A static *final* collection is just as mutable in practice -
                # `static final Map CACHE = new HashMap<>()` is the classic
                # unflushable in-process cache.
                static_collections = [
                    f["name"] for f in t.fields
                    if f.get("static")
                    and _base_type(f["type"]) in ("Map", "List", "Set", "HashMap",
                                                  "ArrayList", "HashSet", "Collection")
                ]
                if static_mutable:
                    self.kg.set_prop(cid, "staticMutableFields", static_mutable)
                if static_collections:
                    self.kg.set_prop(cid, "staticCollectionFields", static_collections)
                # @Value / @ConfigurationProperties means this class reads config.
                reads_config = any(
                    "Value" in (f.get("annotations") or [])
                    or "ConfigurationProperties" in (f.get("annotations") or [])
                    for f in t.fields
                ) or bool(anns & {"ConfigurationProperties", "PropertySource"})
                if reads_config:
                    self.kg.set_prop(cid, "readsConfig", True)

                table = _table_from_entity(t)
                if table:
                    self._ensure_table(table, regulated=None)
                    self.kg.set_prop(cid, "entityTable", table)
                    for f in t.fields:
                        col = f.get("annotation_args", {}).get("Column", "")
                        m = COLUMN_NAME_RE.search(col) if col else None
                        cname = (m.group(1) if m else _camel_to_upper(f["name"])).upper()
                        col_id = f"column:{table}.{cname}"
                        self.kg.add_node(col_id, "Column", name=cname, table=table, type=f["type"])
                        self.kg.add_edge(f"table:{table}", col_id, "CONTAINS")

                class_path = self._controller_base_path(t)
                for m in t.methods:
                    self._add_method(cid, t, m, jf)
                    self._add_endpoint(cid, t, m, class_path)

        for name, libs in self._group_libs(res).items():
            self._add_library(name, libs)
        self._add_configs(res)
        self._add_schema_tables(res)

    def _ensure_module(self, jf: JavaFile) -> str:
        pkg = jf.package or "(default)"
        mid = f"module:{pkg}"
        if not self.kg.has(mid):
            self.kg.add_node(mid, "Module", name=pkg, path=_pkg_path(jf.path, pkg),
                             language=jf.language)
            self.kg.add_edge(self.project_node, mid, "CONTAINS")
        return mid

    def _controller_base_path(self, t: TypeInfo) -> str:
        for a in t.annotations:
            if a["name"] in HTTP_ANNOTATIONS:
                return _annotation_path(a["args"])
        return ""

    def _add_method(self, cid: str, t: TypeInfo, m: MethodInfo, jf: JavaFile) -> None:
        mid = f"method:{t.fqn}#{m.signature}"
        anns = [a["name"] for a in m.annotations]
        self.kg.add_node(
            mid, "Method",
            fqn=f"{t.fqn}.{m.name}", name=m.name, signature=m.signature,
            owner=t.fqn, ownerClass=t.name, path=jf.path,
            loc=m.loc, complexity=m.complexity, returnType=m.return_type,
            params=[f"{ty} {nm}".strip() for ty, nm in m.params],
            modifiers=m.modifiers, annotations=anns,
            isStatic=m.is_static,
            isScheduled="Scheduled" in anns,
            isTransactional="Transactional" in anns,
            isSecured=bool({"PreAuthorize", "Secured", "RolesAllowed"} & set(anns)),
            startLine=m.start_line, endLine=m.end_line,
            fanIn=0, fanOut=0, runtimeHits=0,
        )
        self.kg.add_edge(cid, mid, "CONTAINS")
        self._method_index.setdefault(cid, []).append(mid)

        # Cloud-hostile constructs, recorded here so Engine 3 need not re-parse.
        body = m.body or ""
        signals = {
            "usesLocalFile": bool(re.search(r"\bnew\s+(File|FileReader|FileWriter|FileInputStream|FileOutputStream|RandomAccessFile)\s*\(", body)),
            "usesNewDate": bool(re.search(r"\bnew\s+Date\s*\(\s*\)|System\.currentTimeMillis\s*\(\s*\)|LocalDateTime\.now\s*\(\s*\)|new\s+Timestamp\s*\(", body)),
            "usesHttpSession": "HttpSession" in body or "getSession()" in body
                               or any("HttpSession" in ty for ty, _ in m.params),
            "usesReflection": "Class.forName" in body or ".getDeclaredMethod" in body,
            "usesThreads": bool(re.search(r"\bnew\s+Thread\s*\(|Executors\.", body)),
            "catchesAndSwallows": bool(re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", body)),
            # Reads or writes a class-level collection used as a cache.
            "usesInMemoryCache": bool(
                re.search(r"(?i)\b\w*CACHE\w*\s*\.\s*(put|get|containsKey|clear|remove)\s*\(", body)
            ),
            "readsConfig": bool(
                "Value" in anns or "ConfigurationProperties" in anns
                or re.search(r"(getProperty|getenv|System\.getProperty)\s*\(", body)
            ),
        }
        for k, v in signals.items():
            if v:
                self.kg.set_prop(mid, k, True)

        self._record_sql(mid, m)

    def _record_sql(self, mid: str, m: MethodInfo) -> None:
        """Attach READS/WRITES from SQL literals in the method body."""
        reads: set[str] = set()
        writes: set[str] = set()
        for lit in m.literals:
            if not looks_like_sql(lit):
                continue
            acc = analyze_sql(lit)
            reads |= acc.reads
            writes |= acc.writes
        # Multi-line SQL is usually built by "..." + "..." concatenation; the
        # literals arrive separately, so also try the whole body's literals joined.
        if not (reads or writes) and m.literals:
            joined = " ".join(m.literals)
            if looks_like_sql(joined):
                acc = analyze_sql(joined)
                reads |= acc.reads
                writes |= acc.writes
        if reads or writes:
            self.kg.set_prop(mid, "hasInlineSql", True)
            # Keep the SQL itself (clipped) as evidence: the GxP rules search it
            # for audit-shape columns and clock functions, and the UI shows it
            # when a reviewer clicks the node.
            sql_text = [re.sub(r"\s+", " ", s).strip()[:400]
                        for s in m.literals if looks_like_sql(s)]
            if sql_text:
                self.kg.set_prop(mid, "sqlLiterals", sql_text[:6])
        for t in writes:
            self._ensure_table(t, regulated=None)
            self.kg.add_edge(mid, f"table:{t}", "WRITES")
        for t in reads - writes:
            self._ensure_table(t, regulated=None)
            self.kg.add_edge(mid, f"table:{t}", "READS")

    def _add_endpoint(self, cid: str, t: TypeInfo, m: MethodInfo, base: str) -> None:
        for a in m.annotations:
            verb = HTTP_ANNOTATIONS.get(a["name"])
            if verb is None:
                continue
            path = _join_path(base, _annotation_path(a["args"]))
            eid = f"endpoint:{verb} {path}"
            self.kg.add_node(eid, "Endpoint", httpMethod=verb, path=path,
                             handler=f"{t.fqn}.{m.name}")
            self.kg.add_edge(f"method:{t.fqn}#{m.signature}", eid, "EXPOSES")
            self.kg.add_edge(cid, eid, "EXPOSES")
            return

    def _ensure_table(self, name: str, regulated: bool | None) -> str:
        tid = f"table:{name}"
        if not self.kg.has(tid):
            self.kg.add_node(tid, "Table", name=name, schema="", regulated=False,
                             rowCountEstimate=None)
            self._tables.add(name)
        if regulated is not None:
            self.kg.set_prop(tid, "regulated", regulated)
        return tid

    def _group_libs(self, res: IngestResult) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for lib in res.libraries:
            out.setdefault(f"{lib.name}@{lib.version}", []).append(lib)
        return out

    def _add_library(self, key: str, libs: list[Any]) -> None:
        lib = libs[0]
        lid = f"lib:{key}"
        self.kg.add_node(lid, "Library", name=lib.name, version=lib.version,
                         group=lib.group, scope=lib.scope, eol=lib.eol,
                         eolReason=lib.eol_reason)
        self.kg.add_edge(self.project_node, lid, "USES_LIB")

    def _add_configs(self, res: IngestResult) -> None:
        for cf in res.configs:
            for item in cf.items:
                if item.kind == "setting":
                    continue  # only findings become graph nodes
                cid = f"config:{cf.path}#{item.key}"
                self.kg.add_node(cid, "ConfigItem", key=item.key,
                                 valueMasked=item.value_masked, kind=item.kind,
                                 file=cf.path, line=item.line, isSecret=item.is_secret,
                                 note=item.note)
                self.kg.add_edge(self.project_node, cid, "CONFIGURED_BY")

    def _add_schema_tables(self, res: IngestResult) -> None:
        """Tables and columns declared in .sql DDL."""
        for table in res.sql_schema.tables():
            self._ensure_table(table, regulated=None)
        for table, cols in res.sql_schema.columns.items():
            self._ensure_table(table, regulated=None)
            for c in cols:
                col_id = f"column:{table}.{c}"
                self.kg.add_node(col_id, "Column", name=c, table=table, type="")
                self.kg.add_edge(f"table:{table}", col_id, "CONTAINS")

    # ------------------------------------------------------------------ pass 2
    def link_calls(self, res: IngestResult) -> dict[str, int]:
        """Resolve method calls into CALLS edges and class DEPENDS_ON edges."""
        stats = {"resolved": 0, "unresolved": 0, "ambiguous": 0,
                 "instantiations": 0, "type_refs": 0}
        # method name -> method node ids, for same-class and interface dispatch
        by_name: dict[str, list[str]] = {}
        for mid in self.kg.node_ids("Method"):
            by_name.setdefault((self.kg.node(mid) or {}).get("name", ""), []).append(mid)

        for jf in res.code_files:
            for t in jf.types:
                cid = self._by_fqn.get(t.fqn)
                if not cid:
                    continue
                ftypes = self._field_types.get(cid, {})
                import_simple = {imp.rsplit(".", 1)[-1]: imp for imp in jf.imports}

                for m in t.methods:
                    src_mid = f"method:{t.fqn}#{m.signature}"
                    local_types = _local_var_types(m)
                    for call in m.calls:
                        recv, name, count = call["receiver"], call["name"], int(call["count"])
                        target_cid = self._resolve_receiver(
                            recv, t, ftypes, local_types, import_simple
                        )
                        if target_cid is None:
                            stats["unresolved"] += 1
                            self._record_external(src_mid, recv, name, count)
                            continue

                        tgt_mid = self._pick_method(target_cid, name)
                        if tgt_mid:
                            self.kg.add_edge(src_mid, tgt_mid, "CALLS", count=count)
                            stats["resolved"] += 1
                        if target_cid != cid:
                            self.kg.add_edge(cid, target_cid, "DEPENDS_ON", count=count)
                        # Infer data access through a delegate we could not see.
                        self._infer_access(src_mid, recv, name, ftypes, local_types)

                    # `new Foo()` is a dependency just as much as a call is.
                    # Without this, row mappers and filters that are only ever
                    # instantiated look like dead code.
                    for created in m.news:
                        tgt = self._lookup_type(_base_type(created), import_simple)
                        if tgt and tgt != cid:
                            self.kg.add_edge(cid, tgt, "DEPENDS_ON", count=1)
                            self.kg.set_prop(tgt, "isInstantiated", True)
                            stats["instantiations"] += 1

                self._link_declared_types(cid, t, import_simple, stats)
        self._recompute_degrees()
        return stats

    def _link_declared_types(
        self, cid: str, t: TypeInfo, import_simple: dict[str, str], stats: dict[str, int]
    ) -> None:
        """Field, parameter and return types are structural dependencies too.

        This is what makes an entity or DTO visibly *used* rather than dead:
        nothing calls `Sample`, but plenty of signatures mention it.
        """
        referenced: set[str] = set()
        for f in t.fields:
            referenced.add(_base_type(f["type"]))
        for m in t.methods:
            referenced.add(_base_type(m.return_type))
            for ty, _ in m.params:
                referenced.add(_base_type(ty))
        for simple in referenced:
            if not simple or simple == t.name:
                continue
            tgt = self._lookup_type(simple, import_simple)
            if tgt and tgt != cid:
                self.kg.add_edge(cid, tgt, "DEPENDS_ON", count=1)
                self.kg.set_prop(tgt, "isTypeReferenced", True)
                stats["type_refs"] += 1

    def _resolve_receiver(
        self,
        recv: str,
        t: TypeInfo,
        ftypes: dict[str, str],
        local_types: dict[str, str],
        import_simple: dict[str, str],
    ) -> str | None:
        """Map a call receiver expression to a Class node, if it is ours."""
        if not recv:
            return self._by_fqn.get(t.fqn)  # unqualified call = same class
        head = recv.split(".")[0]
        if head in ("this", "super"):
            rest = recv.split(".")[1:]
            if not rest:
                return self._by_fqn.get(t.fqn)
            head = rest[0]
        # a field or local variable whose declared type we know
        for table in (local_types, ftypes):
            ty = table.get(head)
            if ty:
                return self._lookup_type(ty, import_simple)
        # a static call on a type name
        return self._lookup_type(head, import_simple)

    def _lookup_type(self, simple: str, import_simple: dict[str, str]) -> str | None:
        fqn = import_simple.get(simple)
        if fqn and fqn in self._by_fqn:
            return self._by_fqn[fqn]
        candidates = self._by_simple.get(simple)
        if not candidates:
            return None
        return candidates[0] if len(candidates) == 1 else candidates[0]

    def _pick_method(self, class_node: str, name: str) -> str | None:
        for mid in self._method_index.get(class_node, []):
            if (self.kg.node(mid) or {}).get("name") == name:
                return mid
        return None

    def _record_external(self, src_mid: str, recv: str, name: str, count: int) -> None:
        node = self.kg.node(src_mid)
        if node is None:
            return
        ext = set(node.get("externalCalls", []))
        label = f"{recv}.{name}" if recv else name
        if len(ext) < 40:
            ext.add(label)
        self.kg.set_prop(src_mid, "externalCalls", sorted(ext))

    def _infer_access(
        self, src_mid: str, recv: str, name: str,
        ftypes: dict[str, str], local_types: dict[str, str],
    ) -> None:
        """A `repository.save(x)` with no visible SQL still writes its entity's table."""
        if name not in WRITE_CALL_NAMES and name not in READ_CALL_NAMES:
            return
        head = recv.split(".")[0] if recv else ""
        ty = local_types.get(head) or ftypes.get(head) or ""
        if not ty:
            return
        # FooRepository / FooDao -> entity Foo -> its table
        base = re.sub(r"(Repository|Dao|DAO|Mapper|Store)$", "", ty)
        if base == ty or not base:
            return
        cand = self._by_simple.get(base)
        if not cand:
            return
        table = (self.kg.node(cand[0]) or {}).get("entityTable")
        if not table:
            return
        rel = "WRITES" if name in WRITE_CALL_NAMES else "READS"
        self._ensure_table(table, regulated=None)
        self.kg.add_edge(src_mid, f"table:{table}", rel)

    def _recompute_degrees(self) -> None:
        """fanIn / fanOut for classes and methods, from CALLS + DEPENDS_ON."""
        for label in ("Class", "Method"):
            for nid in self.kg.node_ids(label):
                fan_in = len([u for u in self.kg.in_neighbors(nid)
                              if self._is_dep(u, nid)])
                fan_out = len([v for v in self.kg.out_neighbors(nid)
                               if self._is_dep(nid, v)])
                self.kg.set_prop(nid, "fanIn", fan_in)
                self.kg.set_prop(nid, "fanOut", fan_out)
        # A class's effective fan-in also counts calls into its methods.
        for cid in self.kg.node_ids("Class"):
            callers: set[str] = set()
            for mid in self.kg.children(cid):
                for u in self.kg.in_neighbors(mid, "CALLS"):
                    owner = self.kg.owner_class(u)
                    if owner and owner != cid:
                        callers.add(owner)
            direct = {u for u in self.kg.in_neighbors(cid, "DEPENDS_ON")}
            self.kg.set_prop(cid, "fanIn", len(callers | direct))

    def _is_dep(self, u: str, v: str) -> bool:
        data = self.kg.g.get_edge_data(u, v) or {}
        return any(d.get("rel") in ("CALLS", "DEPENDS_ON") for d in data.values())

    # ------------------------------------------------------------------ finish
    def finalize(self, res: IngestResult) -> KnowledgeGraph:
        self.kg.set_prop(self.project_node, "loc", res.total_loc)
        self.kg.set_prop(self.project_node, "files", res.total_files)
        self.kg.set_prop(self.project_node, "languages", res.loc_by_language)
        self.kg.set_prop(self.project_node, "primaryLanguage", res.primary_language())
        self.kg.set_prop(self.project_node, "testFiles", res.test_files)
        return self.kg


def _base_type(t: str) -> str:
    """`List<Foo>` -> Foo; `Foo[]` -> Foo; `java.util.Foo` -> Foo."""
    t = t.strip()
    inner = re.search(r"<\s*([A-Za-z_][\w.]*)", t)
    if inner and t.split("<")[0].strip() in (
        "List", "Set", "Collection", "Iterable", "Optional", "ArrayList", "HashSet", "Stream"
    ):
        t = inner.group(1)
    t = t.split("<")[0].replace("[]", "").strip()
    return t.rsplit(".", 1)[-1]


LOCAL_VAR_RE = re.compile(r"\b([A-Z][\w.]*(?:<[^;=()]*>)?)\s+([a-z_]\w*)\s*=")


def _local_var_types(m: MethodInfo) -> dict[str, str]:
    out = {nm: _base_type(ty) for ty, nm in m.params if nm}
    for mo in LOCAL_VAR_RE.finditer(m.body or ""):
        out.setdefault(mo.group(2), _base_type(mo.group(1)))
    return out


def _pkg_path(file_path: str, pkg: str) -> str:
    p = file_path.replace("\\", "/")
    frag = pkg.replace(".", "/")
    i = p.find(frag)
    return p[: i + len(frag)] if i != -1 else p.rsplit("/", 1)[0]


def _looks_test(path: str, type_name: str) -> bool:
    low = path.lower().replace("\\", "/")
    return "/test/" in low or "/tests/" in low or type_name.endswith(("Test", "Tests", "IT", "Spec"))


def build_graph(
    res: IngestResult, *, project_id: str, project_name: str, target_cloud: str = "AWS",
    progress=None,
) -> tuple[KnowledgeGraph, dict[str, Any]]:
    b = GraphBuilder(project_id, project_name, target_cloud)
    if progress:
        progress(0.1, "creating modules, classes and methods")
    b.add_structure(res)
    if progress:
        progress(0.6, "resolving call graph")
    link_stats = b.link_calls(res)
    kg = b.finalize(res)
    if progress:
        progress(1.0, f"graph built: {kg.g.number_of_nodes()} nodes")
    log.info("graph_built", **kg.stats(), **link_stats)
    return kg, {"links": link_stats, "graph": kg.stats()}
