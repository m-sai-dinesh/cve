"""Git co-change mining (PRD §8.1 step 5).

Files that change in the same commit are coupled in practice even when nothing
in the code says so — a shared implicit contract, a copy-pasted rule, a feature
that always spans both. Co-change is the one similarity signal that sees it,
which is why it gets its own term in the decomposition matrix (§11.1 w4).

Scoring: for each commit touching 2..``max_files_per_commit`` source files, every
pair gets ``1 / (n - 1)`` so a sweeping refactor cannot swamp the signal, and
commits touching more than the cap are skipped entirely (they are reformattings
and licence-header changes, not design coupling). The result is normalised to
[0, 1] per pair.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ...core.logging import get_logger
from ...db.graph import KnowledgeGraph

log = get_logger("gitmining")


@dataclass
class CoChangeResult:
    available: bool = False
    reason: str = ""
    commits_scanned: int = 0
    commits_used: int = 0
    authors: int = 0
    pairs: dict[tuple[str, str], float] = field(default_factory=dict)
    file_commits: dict[str, int] = field(default_factory=dict)
    first_commit: str = ""
    last_commit: str = ""

    def weight(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self.pairs.get((a, b)) or self.pairs.get((b, a)) or 0.0


CODE_SUFFIXES = {".java", ".cs", ".kt", ".scala", ".py", ".js", ".ts", ".sql", ".xml", ".properties"}


def mine_cochange(
    root: Path, *, max_commits: int = 400, max_files_per_commit: int = 30
) -> CoChangeResult:
    res = CoChangeResult()
    try:
        from git import InvalidGitRepositoryError, NoSuchPathError, Repo
    except ImportError:
        res.reason = "GitPython is not installed"
        return res

    try:
        repo = Repo(root, search_parent_directories=True)
    except Exception as exc:  # InvalidGitRepositoryError / NoSuchPathError
        res.reason = f"not a git repository ({type(exc).__name__})"
        return res

    if repo.bare:
        res.reason = "repository is bare"
        return res

    try:
        commits = list(repo.iter_commits(max_count=max_commits))
    except Exception as exc:
        res.reason = f"could not read history: {exc}"
        return res

    if not commits:
        res.reason = "repository has no commits"
        return res

    raw: dict[tuple[str, str], float] = defaultdict(float)
    authors: set[str] = set()

    for commit in commits:
        res.commits_scanned += 1
        authors.add(str(commit.author.email or commit.author.name))
        try:
            files = [f for f in commit.stats.files.keys()
                     if Path(str(f)).suffix.lower() in CODE_SUFFIXES]
        except Exception:
            continue
        if not 2 <= len(files) <= max_files_per_commit:
            for f in files:
                res.file_commits[_norm(f)] = res.file_commits.get(_norm(f), 0) + 1
            continue
        res.commits_used += 1
        norm = sorted({_norm(f) for f in files})
        for f in norm:
            res.file_commits[f] = res.file_commits.get(f, 0) + 1
        share = 1.0 / (len(norm) - 1)
        for i in range(len(norm)):
            for j in range(i + 1, len(norm)):
                raw[(norm[i], norm[j])] += share

    if raw:
        peak = max(raw.values())
        res.pairs = {k: v / peak for k, v in raw.items()}
    res.authors = len(authors)
    res.available = True
    res.first_commit = commits[-1].hexsha[:10]
    res.last_commit = commits[0].hexsha[:10]
    log.info("cochange_mined", commits=res.commits_scanned, used=res.commits_used,
             pairs=len(res.pairs))
    return res


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def apply_cochange(kg: KnowledgeGraph, res: CoChangeResult) -> int:
    """Write CO_CHANGES edges between classes whose files change together."""
    if not res.available or not res.pairs:
        return 0

    # class node -> normalised repo path (a path may host several classes)
    by_path: dict[str, list[str]] = defaultdict(list)
    for cid in kg.node_ids("Class"):
        p = _norm((kg.node(cid) or {}).get("path", ""))
        if p:
            by_path[p].append(cid)

    # Repo paths from git are repo-root relative; graph paths are source-root
    # relative. Match on the longest common suffix.
    def resolve(git_path: str) -> list[str]:
        if git_path in by_path:
            return by_path[git_path]
        for p, ids in by_path.items():
            if git_path.endswith(p) or p.endswith(git_path):
                return ids
        return []

    written = 0
    for (fa, fb), w in res.pairs.items():
        if w <= 0.05:
            continue  # below this the signal is noise
        for ca in resolve(fa):
            for cb in resolve(fb):
                if ca != cb:
                    kg.add_edge(ca, cb, "CO_CHANGES", weight=round(w, 4))
                    written += 1
    for cid in kg.node_ids("Class"):
        p = _norm((kg.node(cid) or {}).get("path", ""))
        for gp, n in res.file_commits.items():
            if p and (gp.endswith(p) or p.endswith(gp)):
                kg.set_prop(cid, "commitCount", n)
                break
    return written
