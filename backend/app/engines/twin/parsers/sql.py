"""SQL / stored-procedure parsing (PRD §8.1: which procedure reads/writes which table).

Uses ``sqlglot`` to resolve tables and the access mode, including SQL found in
Java string literals and JPA/JPQL-ish queries. Falls back to regex extraction
for dialect oddities sqlglot rejects, because a missed table is a missed GxP
finding and silence is worse than an approximate answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter)

# Regex fallbacks
RE_INSERT = re.compile(r"(?i)\binsert\s+into\s+[`\"\[]?([\w.$]+)")
RE_UPDATE = re.compile(r"(?i)\bupdate\s+[`\"\[]?([\w.$]+)")
RE_DELETE = re.compile(r"(?i)\bdelete\s+from\s+[`\"\[]?([\w.$]+)")
RE_MERGE = re.compile(r"(?i)\bmerge\s+into\s+[`\"\[]?([\w.$]+)")
RE_FROM = re.compile(r"(?i)\bfrom\s+[`\"\[]?([\w.$]+)")
RE_JOIN = re.compile(r"(?i)\bjoin\s+[`\"\[]?([\w.$]+)")
RE_DDL_TABLE = re.compile(r"(?i)\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?([\w.$]+)")
RE_COLUMNS = re.compile(r"(?i)^\s*[`\"\[]?(\w+)[`\"\]]?\s+(varchar|char|number|numeric|decimal|int|integer|bigint|smallint|date|datetime|timestamp|clob|blob|text|boolean|bit|float|double|real)", re.M)

NOISE = {
    "dual", "select", "where", "values", "set", "table", "and", "or", "on", "as",
    "null", "true", "false", "case", "when", "then", "else", "end",
}


@dataclass
class SqlAccess:
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    columns: dict[str, set[str]] = field(default_factory=dict)
    statements: int = 0
    parse_failures: int = 0

    def merge(self, other: SqlAccess) -> None:
        self.reads |= other.reads
        self.writes |= other.writes
        self.statements += other.statements
        self.parse_failures += other.parse_failures
        for t, cols in other.columns.items():
            self.columns.setdefault(t, set()).update(cols)

    def tables(self) -> set[str]:
        return self.reads | self.writes


def _clean(name: str) -> str:
    name = (name or "").strip().strip('`"[]();,')
    if "." in name:
        name = name.split(".")[-1]
    return name.upper()


def _usable(name: str) -> bool:
    n = _clean(name)
    return bool(n) and n.lower() not in NOISE and not n.isdigit() and re.fullmatch(r"[A-Z_][A-Z0-9_$]*", n) is not None


def analyze_sql(text: str, dialect: str | None = None) -> SqlAccess:
    """Resolve table reads/writes for one SQL blob (may hold several statements)."""
    acc = SqlAccess()
    if not text or not text.strip():
        return acc

    normalized = _normalize_jpql(text)
    parsed_ok = False
    try:
        trees = sqlglot.parse(normalized, read=dialect, error_level=sqlglot.ErrorLevel.IGNORE)
        for tree in trees:
            if tree is None:
                continue
            acc.statements += 1
            parsed_ok = True
            is_write = isinstance(tree, WRITE_NODES)
            write_targets: set[str] = set()
            if is_write:
                target = tree.this
                if isinstance(target, exp.Schema):
                    target = target.this
                if isinstance(target, exp.Table):
                    nm = _clean(target.name)
                    if _usable(nm):
                        write_targets.add(nm)
                        acc.writes.add(nm)
            for tbl in tree.find_all(exp.Table):
                nm = _clean(tbl.name)
                if not _usable(nm):
                    continue
                if nm not in write_targets:
                    acc.reads.add(nm)
            for cdef in tree.find_all(exp.ColumnDef):
                for t in write_targets:
                    acc.columns.setdefault(t, set()).add(_clean(cdef.name))
    except Exception:
        acc.parse_failures += 1

    if not parsed_ok or not acc.tables():
        _regex_fallback(normalized, acc)
    return acc


def _normalize_jpql(text: str) -> str:
    """Make JPQL / named-parameter SQL palatable to a SQL parser."""
    t = re.sub(r":\w+", "?", text)             # :namedParam -> ?
    t = re.sub(r"\{\s*\w+\s*\}", "?", t)       # {placeholder} -> ?
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _regex_fallback(text: str, acc: SqlAccess) -> None:
    for rx, bucket in (
        (RE_INSERT, acc.writes), (RE_UPDATE, acc.writes), (RE_DELETE, acc.writes),
        (RE_MERGE, acc.writes), (RE_DDL_TABLE, acc.writes),
        (RE_FROM, acc.reads), (RE_JOIN, acc.reads),
    ):
        for m in rx.finditer(text):
            name = _clean(m.group(1))
            if _usable(name):
                bucket.add(name)
    acc.reads -= acc.writes
    if acc.tables():
        acc.statements = max(acc.statements, 1)


def analyze_sql_file(text: str, dialect: str | None = None) -> SqlAccess:
    """A .sql file: also harvests CREATE TABLE column definitions for the schema."""
    acc = analyze_sql(text, dialect)
    for m in RE_DDL_TABLE.finditer(text):
        table = _clean(m.group(1))
        if not _usable(table):
            continue
        acc.writes.add(table)
        start = m.end()
        open_paren = text.find("(", start)
        if open_paren == -1:
            continue
        depth, i = 0, open_paren
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = text[open_paren : i + 1]
        cols = {_clean(c.group(1)) for c in RE_COLUMNS.finditer(block)}
        if cols:
            acc.columns.setdefault(table, set()).update(cols)
    return acc


def looks_like_sql(text: str) -> bool:
    if not text or len(text) < 12:
        return False
    t = text.lower()
    has_verb = any(v in t for v in ("select ", "insert into", "update ", "delete from", "merge into"))
    has_shape = any(k in t for k in (" from ", " set ", " values", " where ", " into "))
    return has_verb and has_shape
