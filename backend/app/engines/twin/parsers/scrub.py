"""Source scrubbing shared by the language parsers.

Parsing C-family source with regexes only works if comments and string literals
are removed first — otherwise a brace inside a string breaks every block match.
``scrub`` replaces each comment and literal with same-length padding so **all
character offsets and line numbers stay identical** to the original file, and
hands back the literals it lifted out.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scrubbed:
    code: str                                   # same length as the original
    literals: list[tuple[int, str]] = field(default_factory=list)  # (line, text)
    original: str = ""

    def line_of(self, index: int) -> int:
        return self.original.count("\n", 0, max(0, index)) + 1

    def literal_texts(self) -> list[str]:
        return [t for _, t in self.literals]


def scrub(src: str, line_comment: str = "//") -> Scrubbed:
    """Blank out comments and string/char literals, preserving offsets."""
    out: list[str] = []
    literals: list[tuple[int, str]] = []
    i, n = 0, len(src)
    line = 1
    lc_len = len(line_comment)

    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            out.append(ch)
            i += 1
            continue

        # ---- line comment ----
        if src.startswith(line_comment, i):
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
            continue

        # ---- block comment ----
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            chunk = src[i:j]
            out.append("".join("\n" if c == "\n" else " " for c in chunk))
            line += chunk.count("\n")
            i = j
            continue

        # ---- string / char literal ----
        if ch in ('"', "'"):
            # Java text block: """ ... """
            if ch == '"' and src.startswith('"""', i):
                j = src.find('"""', i + 3)
                j = n if j == -1 else j + 3
                chunk = src[i:j]
                literals.append((line, chunk[3:-3] if len(chunk) >= 6 else ""))
                out.append("".join("\n" if c == "\n" else " " for c in chunk))
                line += chunk.count("\n")
                i = j
                continue
            quote = ch
            j = i + 1
            buf: list[str] = []
            while j < n:
                c = src[j]
                if c == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                    continue
                if c == quote or c == "\n":
                    break
                buf.append(c)
                j += 1
            end = min(j + 1, n)
            text = "".join(buf)
            if quote == '"':
                literals.append((line, text))
            out.append(" " * (end - i))
            i = end
            continue

        out.append(ch)
        i += 1

    code = "".join(out)
    # Padding must never change the length, or every offset downstream shifts.
    assert len(code) == len(src), "scrub changed source length"
    return Scrubbed(code=code, literals=literals, original=src)


def match_block(code: str, open_index: int) -> int:
    """Index just past the ``}`` matching the ``{`` at ``open_index`` (or len)."""
    depth = 0
    for i in range(open_index, len(code)):
        c = code[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(code)
