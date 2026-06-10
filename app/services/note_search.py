"""Search across the vault's markdown — find that thing you captured.

Scans the workspace's checkout directly (no index to maintain, no extra
state): newest files first, all query terms must match (AND, case
insensitive), stop as soon as enough hits exist. Reading the note still
happens in Obsidian; this returns just enough snippet to recognize it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services import vault
from app.services.calendar_types import local_tz

log = logging.getLogger("mnemosyne.note_search")

MAX_RESULTS = 20
MAX_FILES_SCANNED = 5000
SNIPPET_RADIUS = 70
SKIP_DIRS = {".git", "_attachments", ".obsidian", ".trash"}


@dataclass(frozen=True)
class Hit:
    relpath: str          # "Inbox/2026-05-12T09-14-02.md"
    title: str            # first heading, or the filename stem
    pre: str              # snippet text before the match
    match: str            # the matched text itself (first term)
    post: str             # snippet text after the match
    modified: str         # "May 12"


def _iter_md_files(root: Path):
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            for entry in d.iterdir():
                if entry.is_dir():
                    if entry.name not in SKIP_DIRS and not entry.name.startswith("."):
                        stack.append(entry)
                elif entry.suffix.lower() == ".md":
                    yield entry
        except OSError:
            continue


def _title_of(text: str, path: Path) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or path.stem
    return path.stem


_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)
_HEADING_RE = re.compile(r"^#+\s*", re.M)


def _plain(text: str) -> str:
    """Markdown chrome out of snippets: frontmatter block, heading marks."""
    return _HEADING_RE.sub("", _FRONTMATTER_RE.sub("", text))


def _snippet(text: str, term: str) -> tuple[str, str, str]:
    low = text.lower()
    i = low.find(term.lower())
    if i < 0:
        return text[: SNIPPET_RADIUS * 2], "", ""
    start = max(0, i - SNIPPET_RADIUS)
    end = min(len(text), i + len(term) + SNIPPET_RADIUS)
    pre = ("…" if start > 0 else "") + text[start:i]
    post = text[i + len(term):end] + ("…" if end < len(text) else "")
    return pre, text[i:i + len(term)], post


def search(workspace: str, query: str, limit: int = MAX_RESULTS) -> list[Hit]:
    terms = [t for t in query.lower().split() if t]
    if not terms:
        return []
    spec = vault.WORKSPACES.get(workspace)
    if spec is None or not spec.path.exists():
        return []

    files = []
    for f in _iter_md_files(spec.path):
        try:
            files.append((f.stat().st_mtime, f))
        except OSError:
            continue
        if len(files) >= MAX_FILES_SCANNED:
            break
    files.sort(key=lambda t: t[0], reverse=True)

    tz = local_tz()
    hits: list[Hit] = []
    for mtime, f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        haystack = text.lower() + "\n" + f.name.lower()
        if not all(t in haystack for t in terms):
            continue
        # Snippet around the first term found in the body (fall back to
        # the top of the file for filename-only matches).
        pre, match, post = _snippet(_plain(text), terms[0])
        # Collapse newlines/runs of space but keep the boundary spacing
        # around the highlighted match intact.
        pre_clean = " ".join(pre.split()) + (" " if pre[-1:].isspace() else "")
        post_clean = (" " if post[:1].isspace() else "") + " ".join(post.split())
        dt = datetime.fromtimestamp(mtime, tz)
        hits.append(
            Hit(
                relpath=f.relative_to(spec.path).as_posix(),
                title=_title_of(text, f),
                pre=pre_clean,
                match=match,
                post=post_clean,
                modified=f"{dt.strftime('%b')} {dt.day}",
            )
        )
        if len(hits) >= limit:
            break
    return hits
