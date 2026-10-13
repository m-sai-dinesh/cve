"""Repository ingestion: clone/unpack, walk, language-detect, parse (PRD §8.1 1-3).

Produces an ``IngestResult`` that ``graph_builder`` turns into the knowledge
graph. This stage is purely deterministic — no LLM is involved, which is the
PRD's "deterministic first, LLM second" principle (§5).
"""
from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...core.logging import get_logger
from .parsers import config as cfgp
from .parsers.java import JavaFile, language_for, parse_java_source
from .parsers.sql import SqlAccess, analyze_sql_file

log = get_logger("ingest")

SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "target", "build", "dist", "out",
    "bin", "obj", ".idea", ".vscode", "__pycache__", ".venv", "venv", ".mvn",
    ".gradle", "vendor", "coverage", ".next", ".pytest_cache", ".mypy_cache",
}
SKIP_SUFFIXES = {
    ".class", ".jar", ".war", ".ear", ".exe", ".dll", ".so", ".dylib", ".pyc",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".rar", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".bin",
    ".lock", ".map",
}
MAX_FILE_BYTES = 2_000_000

CONFIG_NAMES = {
    "application.properties", "application.yml", "application.yaml", "web.xml",
    "context.xml", "persistence.xml", "app.config", "web.config", ".env",
    "appsettings.json", "hibernate.cfg.xml", "log4j.properties", "logback.xml",
}
BUILD_NAMES = {"pom.xml", "build.gradle", "requirements.txt", "package.json", "composer.json"}

TEXT_LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".rb": "Ruby", ".php": "PHP", ".go": "Go", ".rs": "Rust",
    ".cbl": "COBOL", ".cob": "COBOL", ".cpy": "COBOL", ".jcl": "JCL",
    ".sql": "SQL", ".pls": "PL/SQL", ".prc": "PL/SQL", ".html": "HTML",
    ".jsp": "JSP", ".xml": "XML", ".yml": "YAML", ".yaml": "YAML",
    ".properties": "Properties", ".json": "JSON", ".sh": "Shell", ".bat": "Batch",
    ".css": "CSS", ".md": "Markdown", ".c": "C", ".h": "C", ".cpp": "C++",
}


@dataclass
class IngestResult:
    root: Path
    name: str = ""
    code_files: list[JavaFile] = field(default_factory=list)
    sql_schema: SqlAccess = field(default_factory=SqlAccess)
    sql_files: list[tuple[str, SqlAccess]] = field(default_factory=list)
    configs: list[cfgp.ConfigFile] = field(default_factory=list)
    libraries: list[cfgp.Library] = field(default_factory=list)
    loc_by_language: dict[str, int] = field(default_factory=dict)
    files_by_language: dict[str, int] = field(default_factory=dict)
    test_files: int = 0
    total_files: int = 0
    total_loc: int = 0
    skipped_files: int = 0
    notes: list[str] = field(default_factory=list)

    def primary_language(self) -> str:
        if not self.loc_by_language:
            return "unknown"
        code_only = {k: v for k, v in self.loc_by_language.items()
                     if k not in ("Markdown", "JSON", "YAML", "XML", "Properties", "CSS", "HTML")}
        pool = code_only or self.loc_by_language
        return max(pool.items(), key=lambda kv: kv[1])[0]


def prepare_source(
    *,
    dest: Path,
    repo_url: str = "",
    upload_zip: Path | None = None,
    local_path: Path | None = None,
) -> tuple[Path, list[str]]:
    """Materialise the source to analyse under ``dest``. Returns (root, notes)."""
    notes: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)

    if upload_zip is not None:
        target = dest / "src"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        with zipfile.ZipFile(upload_zip) as zf:
            for member in zf.infolist():
                # Reject absolute paths and ../ escapes before extracting.
                name = member.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    notes.append(f"skipped unsafe archive entry: {name}")
                    continue
                zf.extract(member, target)
        notes.append(f"unpacked archive {upload_zip.name}")
        return _descend_single_dir(target), notes

    if local_path is not None:
        p = Path(local_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"source path does not exist: {p}")
        notes.append(f"analysing local path {p}")
        return p, notes

    if repo_url:
        target = dest / "clone"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        try:
            from git import Repo  # GitPython

            Repo.clone_from(repo_url, target, depth=50)
            notes.append(f"cloned {repo_url} (shallow, 50 commits for co-change mining)")
        except Exception as exc:
            raise RuntimeError(f"git clone failed: {exc}") from exc
        return _descend_single_dir(target), notes

    raise ValueError("one of repo_url, upload_zip or local_path is required")


def _descend_single_dir(path: Path) -> Path:
    """An archive or clone that contains exactly one top folder: use that."""
    entries = [p for p in path.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return path


def walk_source(root: Path) -> list[Path]:
    """All candidate files, pruning build output and binaries."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in SKIP_SUFFIXES:
                continue
            found.append(p)
    return sorted(found)


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
    except OSError:
        return None
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _is_test(rel: str) -> bool:
    low = rel.lower().replace("\\", "/")
    return (
        "/test/" in low or "/tests/" in low or "/src/test" in low or "__tests__" in low
        or low.endswith(("test.java", "tests.java", "test.cs", "_test.py", "test.py", ".spec.ts", ".test.ts"))
        or Path(low).name.startswith("test_")
    )


def ingest(root: Path, *, name: str = "", progress=None) -> IngestResult:
    """Parse everything under ``root``."""
    res = IngestResult(root=root, name=name or root.name)
    files = walk_source(root)
    res.total_files = len(files)
    total = max(1, len(files))

    for i, path in enumerate(files):
        if progress and i % 25 == 0:
            progress(i / total, f"parsing {path.name}")
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        lower = path.name.lower()
        text = _read_text(path)
        if text is None:
            res.skipped_files += 1
            continue

        if _is_test(rel):
            res.test_files += 1

        lang = language_for(path.name)
        if lang:
            try:
                jf = parse_java_source(text, rel, lang)
                res.code_files.append(jf)
                _tally(res, lang, jf.loc)
            except Exception as exc:
                res.notes.append(f"parse failed for {rel}: {type(exc).__name__}")
                res.skipped_files += 1
            continue

        ext = path.suffix.lower()
        if ext in (".sql", ".pls", ".prc", ".pkb", ".pks"):
            acc = analyze_sql_file(text)
            res.sql_files.append((rel, acc))
            res.sql_schema.merge(acc)
            _tally(res, "SQL", _lines(text))
            continue

        if lower in BUILD_NAMES or lower.endswith((".csproj", ".vbproj")):
            res.libraries.extend(cfgp.parse_build_file(text, rel))
            _tally(res, TEXT_LANG_BY_EXT.get(ext, "Config"), _lines(text))
            continue

        if lower in CONFIG_NAMES or ext in (".properties", ".env") or lower.startswith("application-"):
            res.configs.append(cfgp.parse_config(text, rel))
            _tally(res, TEXT_LANG_BY_EXT.get(ext, "Config"), _lines(text))
            continue

        if ext in (".xml", ".yml", ".yaml", ".json", ".config"):
            # Still worth scanning for hosts, paths and credentials.
            cf = cfgp.parse_config(text, rel)
            if cf.items:
                res.configs.append(cf)
            _tally(res, TEXT_LANG_BY_EXT.get(ext, "Config"), _lines(text))
            continue

        _tally(res, TEXT_LANG_BY_EXT.get(ext, "Other"), _lines(text))

    res.total_loc = sum(res.loc_by_language.values())
    if progress:
        progress(1.0, f"parsed {res.total_files} files")
    log.info("ingest_done", files=res.total_files, loc=res.total_loc,
             types=sum(len(f.types) for f in res.code_files))
    return res


def _tally(res: IngestResult, lang: str, loc: int) -> None:
    res.loc_by_language[lang] = res.loc_by_language.get(lang, 0) + loc
    res.files_by_language[lang] = res.files_by_language.get(lang, 0) + 1


def _lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.strip())


def enrich_with_lizard(res: IngestResult, root: Path) -> dict[str, Any]:
    """Overlay `lizard`'s cyclomatic complexity on the parsed methods (PRD §8.1.6).

    The parser carries its own McCabe fallback, so this is an accuracy upgrade
    rather than a dependency: if lizard cannot read a file we keep our number.
    """
    stats = {"files": 0, "functions": 0, "replaced": 0}
    try:
        import lizard
    except ImportError:
        return stats

    by_file: dict[str, dict[str, int]] = {}
    for jf in res.code_files:
        abs_path = root / jf.path
        if not abs_path.exists():
            continue
        try:
            analysis = lizard.analyze_file(str(abs_path))
        except Exception:
            continue
        stats["files"] += 1
        bucket = by_file.setdefault(jf.path, {})
        for fn in analysis.function_list:
            simple = fn.name.split("::")[-1]
            bucket[simple] = max(bucket.get(simple, 0), int(fn.cyclomatic_complexity))
            stats["functions"] += 1

    for jf in res.code_files:
        bucket = by_file.get(jf.path, {})
        for t in jf.types:
            for m in t.methods:
                c = bucket.get(m.name)
                if c:
                    m.complexity = c
                    stats["replaced"] += 1
    return stats
