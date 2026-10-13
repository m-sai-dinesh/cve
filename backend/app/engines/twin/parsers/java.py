"""Java / C#-family static parser (PRD §8.1 step 3).

Extracts packages, types, annotations, fields, methods, method calls, SQL
embedded in string literals, and the cloud-hostile constructs the readiness
scorer looks for (``new Date()``, ``new File(``, HTTP session use, static mutable
state). Pure Python: no native grammars to build, so it runs anywhere.

Deliberate scope: this resolves call *targets by simple name* within the project
and records unresolved external calls by their receiver type. That is exactly
what the decomposition and blast-radius engines need, and it is honest about
what it cannot see (reflection, Spring wiring by interface).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .scrub import Scrubbed, match_block, scrub

PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.M)
NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.M)

TYPE_RE = re.compile(
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|sealed|partial|strictfp)\s+)*)"
    r"(?P<kind>class|interface|enum|record)\s+(?P<name>[A-Za-z_]\w*)"
    r"(?P<generics><[^{;]*?>)?"
    r"(?P<rest>(?:\s+(?:extends|implements|:)\s*[^{]*)?)\s*\{"
)

# Matches up to the method name and its opening paren only. The parameter list
# is then paren-matched, because annotated parameters such as
# `@RequestParam("id") long id` contain parentheses of their own and would cut a
# `[^)]*` class short.
METHOD_HEAD_RE = re.compile(
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized|native|default|virtual|override|async)\s+)*)"
    r"(?P<ret>[A-Za-z_][\w.<>,\[\]\s?]*?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*\("
)
# After the parameter list: optional throws clause, then a body or a semicolon.
METHOD_TAIL_RE = re.compile(r"\s*(?P<throws>throws\s+[\w.,\s]+?)?\s*(?P<end>[{;])")

FIELD_RE = re.compile(
    r"(?P<mods>(?:(?:public|protected|private|static|final|volatile|transient|readonly)\s+)+)"
    r"(?P<type>[A-Za-z_][\w.<>,\[\]\s?]*?)\s+(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;"
)

ANNOTATION_RE = re.compile(r"@([A-Za-z_]\w*)(?:\s*\(([^)]*)\))?")
CALL_RE = re.compile(r"(?:(?P<recv>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\.\s*)?(?P<name>[a-z_]\w*)\s*\(")
NEW_RE = re.compile(r"\bnew\s+([A-Za-z_][\w.]*)\s*\(")

SQL_HINT_RE = re.compile(r"(?i)\b(select|insert\s+into|update|delete\s+from|merge\s+into|call|exec)\b")

CONTROL_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "try", "return", "synchronized",
    "do", "else", "throw", "new", "super", "this", "assert", "case", "break",
    "continue", "finally", "lock", "using", "foreach", "yield",
}

# Reserved words that METHOD_RE can otherwise mistake for a return type.
NON_METHOD_NAMES = CONTROL_KEYWORDS | {"record", "class", "interface", "enum"}

LANG_BY_EXT = {".java": "Java", ".cs": "C#", ".kt": "Kotlin", ".scala": "Scala", ".groovy": "Groovy"}


@dataclass
class MethodInfo:
    name: str
    signature: str
    return_type: str = ""
    params: list[tuple[str, str]] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    annotations: list[dict[str, str]] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    loc: int = 0
    body: str = ""
    calls: list[dict[str, str]] = field(default_factory=list)
    news: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    sql: list[str] = field(default_factory=list)
    complexity: int = 1

    @property
    def is_static(self) -> bool:
        return "static" in self.modifiers


@dataclass
class TypeInfo:
    name: str
    kind: str
    package: str = ""
    modifiers: list[str] = field(default_factory=list)
    annotations: list[dict[str, str]] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    loc: int = 0

    @property
    def fqn(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name

    def annotation_names(self) -> set[str]:
        return {a["name"] for a in self.annotations}


@dataclass
class JavaFile:
    path: str
    language: str = "Java"
    package: str = ""
    imports: list[str] = field(default_factory=list)
    types: list[TypeInfo] = field(default_factory=list)
    loc: int = 0
    literals: list[str] = field(default_factory=list)


def parse_java_source(src: str, path: str = "", language: str = "Java") -> JavaFile:
    s = scrub(src)
    code = s.code
    pkg_m = PACKAGE_RE.search(code) or NAMESPACE_RE.search(code)
    package = pkg_m.group(1) if pkg_m else ""
    out = JavaFile(
        path=path,
        language=language,
        package=package,
        imports=[m.group(1) for m in IMPORT_RE.finditer(code)],
        loc=_count_code_lines(code),
        literals=s.literal_texts(),
    )

    for tm in TYPE_RE.finditer(code):
        brace = code.index("{", tm.end() - 1)
        end = match_block(code, brace)
        # Nested types are reported by their own match; skip a type whose opening
        # brace sits inside an already-emitted type body.
        if any(t.start_line <= s.line_of(tm.start()) and s.line_of(end) <= t.end_line for t in out.types):
            continue
        info = TypeInfo(
            name=tm.group("name"),
            kind=tm.group("kind"),
            package=package,
            modifiers=tm.group("mods").split(),
            annotations=_annotations_before(code, tm.start(), s.original),
            extends=_supertypes(tm.group("rest") or ""),
            start_line=s.line_of(tm.start()),
            end_line=s.line_of(end),
        )
        lo, hi = brace + 1, max(brace + 1, end - 1)
        body = code[lo:hi]
        body_orig = s.original[lo:hi]      # same offsets: scrubbing preserves length
        info.loc = _count_code_lines(body)
        info.fields = _parse_fields(body, body_orig)
        info.methods = _parse_methods(body, body_orig, s, offset=lo, owner=info.name)
        out.types.append(info)

    return out


# ----------------------------------------------------------------- internals
def _count_code_lines(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip())


def _supertypes(rest: str) -> list[str]:
    rest = rest.replace("extends", " ").replace("implements", " ").replace(":", " ")
    return [p.strip().split("<")[0] for p in re.split(r"[,\s]+", rest) if p.strip()]


def _annotations_before(code: str, index: int, original: str | None = None) -> list[dict[str, str]]:
    """Annotations in the ~600 chars preceding a declaration.

    ``code`` is scrubbed, so annotation arguments that were string literals are
    now blank. ``original`` is the same slice of unscrubbed source; because
    scrubbing preserves offsets, argument text can be read back from it at the
    identical index. That is how ``@RequestMapping("/samples")`` keeps its path.
    """
    lo = max(0, index - 600)
    window = code[lo:index]
    cut = max(window.rfind(";"), window.rfind("}"), window.rfind("{"))
    window = window[cut + 1 :]
    base = lo + cut + 1

    out: list[dict[str, str]] = []
    for m in ANNOTATION_RE.finditer(window):
        args = (m.group(2) or "").strip()
        if original is not None and m.group(2) is not None:
            raw = original[base + m.start(2) : base + m.end(2)].strip()
            if raw:
                args = raw
        out.append({"name": m.group(1), "args": args})
    return out


def _parse_fields(body: str, body_orig: str = "") -> list[dict[str, Any]]:
    fields_out: list[dict[str, Any]] = []
    for fm in FIELD_RE.finditer(body):
        # A field declaration never has a '(' before its ';' — that is a method.
        if "(" in body[fm.start() : fm.end()].split("=")[0]:
            continue
        mods = fm.group("mods").split()
        ftype = fm.group("type").strip()
        if ftype in NON_METHOD_NAMES:
            continue
        anns = _annotations_before(body, fm.start(), body_orig or None)
        fields_out.append({
            "name": fm.group("name"), "type": ftype, "modifiers": mods,
            "static": "static" in mods, "final": "final" in mods,
            "annotations": [a["name"] for a in anns],
            "annotation_args": {a["name"]: a["args"] for a in anns if a["args"]},
        })
    return fields_out


def _match_parens(code: str, open_index: int) -> int:
    """Index just past the ``)`` matching the ``(`` at ``open_index``."""
    depth = 0
    for i in range(open_index, len(code)):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _parse_methods(body: str, body_orig: str, s: Scrubbed, offset: int, owner: str) -> list[MethodInfo]:
    methods: list[MethodInfo] = []
    consumed: list[tuple[int, int]] = []
    for mm in METHOD_HEAD_RE.finditer(body):
        start, ret, name = mm.start(), mm.group("ret").strip(), mm.group("name")
        if any(a <= start < b for a, b in consumed):
            continue  # inside a method we already took (a lambda or inner class)
        if name in NON_METHOD_NAMES or ret.split()[-1] in NON_METHOD_NAMES:
            continue
        if ret in ("", "return", "else", "new"):
            continue

        paren_open = mm.end() - 1
        paren_close = _match_parens(body, paren_open)
        if paren_close == -1:
            continue
        params_src = body[paren_open + 1 : paren_close - 1]
        tail = METHOD_TAIL_RE.match(body, paren_close)
        if tail is None:
            continue  # a call expression, not a declaration

        if tail.group("end") == "{":
            brace = body.index("{", tail.end() - 1)
            end = match_block(body, brace)
            mbody = body[brace + 1 : max(brace + 1, end - 1)]
        else:
            end = tail.end()
            mbody = ""  # abstract / interface method
        consumed.append((start, end))

        is_ctor = name == owner
        info = MethodInfo(
            name=name,
            signature=f"{name}({_param_types(params_src)})",
            return_type="<init>" if is_ctor else ret,
            params=_params(params_src),
            modifiers=mm.group("mods").split(),
            annotations=_annotations_before(body, start, body_orig or None),
            start_line=s.line_of(offset + start),
            end_line=s.line_of(offset + end),
            loc=_count_code_lines(mbody) or 1,
            body=mbody,
        )
        info.calls = _calls(mbody)
        info.news = sorted({m.group(1) for m in NEW_RE.finditer(mbody)})
        info.literals = [t for ln, t in s.literals if info.start_line <= ln <= info.end_line]
        info.sql = [t for t in info.literals if SQL_HINT_RE.search(t)]
        info.complexity = _cyclomatic(mbody)
        methods.append(info)
    methods.sort(key=lambda m: m.start_line)
    return methods


def _params(params: str) -> list[tuple[str, str]]:
    out = []
    for raw in _split_params(params):
        raw = ANNOTATION_RE.sub("", raw).strip().replace("final ", "")
        if not raw:
            continue
        bits = raw.rsplit(" ", 1)
        if len(bits) == 2:
            out.append((bits[0].strip(), bits[1].strip()))
        else:
            out.append((raw, ""))
    return out


def _param_types(params: str) -> str:
    return ",".join(t for t, _ in _params(params))


def _split_params(params: str) -> list[str]:
    """Split on commas that are not inside generics."""
    out, depth, buf = [], 0, []
    for c in params:
        if c in "<([":
            depth += 1
        elif c in ">)]":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    if buf:
        out.append("".join(buf))
    return out


def _calls(body: str) -> list[dict[str, str]]:
    seen: dict[tuple[str, str], int] = {}
    for cm in CALL_RE.finditer(body):
        name = cm.group("name")
        if name in CONTROL_KEYWORDS:
            continue
        recv = (cm.group("recv") or "").strip()
        if recv.endswith(("if", "while", "for", "switch", "return")):
            recv = ""
        key = (recv, name)
        seen[key] = seen.get(key, 0) + 1
    return [{"receiver": r, "name": n, "count": c} for (r, n), c in sorted(seen.items())]


_DECISION_RE = re.compile(r"\b(if|for|while|case|catch|&&|\|\||\?)\b|\?\s*[^:]*:")


def _cyclomatic(body: str) -> int:
    """McCabe complexity. `lizard` is used where available; this is the fallback
    and keeps the parser usable on its own."""
    if not body.strip():
        return 1
    count = 1
    for token in ("if ", "if(", "for ", "for(", "while ", "while(", "case ", "catch ", "catch(", "&&", "||"):
        count += body.count(token)
    return max(1, count)


def language_for(path: str) -> str | None:
    for ext, lang in LANG_BY_EXT.items():
        if path.lower().endswith(ext):
            return lang
    return None
