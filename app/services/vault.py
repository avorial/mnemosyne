"""Git-backed Obsidian vault service.

Each workspace ('personal' / 'work') has its own checkout of a private GitHub
repo. Widgets call this service to append/write markdown files (and binary
attachments tracked via Git LFS), which are then committed and pushed.

Design notes:
- Deploy keys live on the CIFS-mounted secrets folder (read-only as far as
  we're concerned). Many CIFS mounts refuse chmod / new-file writes from the
  container, so we copy each key to /tmp on first use with mode 0600 (SSH
  refuses keys with permissive perms).
- We never write known_hosts / ssh_config onto the CIFS share. Instead we
  pass everything inline via GIT_SSH_COMMAND, with UserKnownHostsFile
  pointing at /root/.ssh/known_hosts which is always writable.
- StrictHostKeyChecking=accept-new is enough here: github.com's host keys
  are public, and we trust-on-first-use.
- _attachments/** is tracked via Git LFS so binaries don't bloat the repo.
  .gitattributes is written on first clone if missing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import config

log = logging.getLogger("mnemosyne.vault")

GIT_AUTHOR_NAME = "Mnemosyne"
GIT_AUTHOR_EMAIL = "noreply@mnemosyne.avorial.com"

LOCAL_SSH_DIR = Path("/root/.ssh")
LOCAL_KNOWN_HOSTS = LOCAL_SSH_DIR / "known_hosts"
LOCAL_KEY_DIR = Path("/tmp/mnemosyne-keys")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".heic"}


@dataclass(frozen=True)
class WorkspaceSpec:
    workspace: str
    path: Path
    remote: str               # plain git@github.com URL
    deploy_key_filename: str  # filename inside config.secrets_path


WORKSPACES: dict[str, WorkspaceSpec] = {
    "personal": WorkspaceSpec(
        workspace="personal",
        path=config.vault_personal_path,
        remote="git@github.com:avorial/notes.git",
        deploy_key_filename="deploy_notes",
    ),
    "work": WorkspaceSpec(
        workspace="work",
        path=config.vault_work_path,
        remote="git@github.com:avorial/notes-work.git",
        deploy_key_filename="deploy_notes_work",
    ),
}


class VaultError(RuntimeError):
    pass


_ensure_lock = threading.Lock()
_ensured: set[str] = set()


def _local_key_for(spec: WorkspaceSpec) -> Path:
    """Copy the deploy key from CIFS to a local path with strict perms."""
    src = config.secrets_path / spec.deploy_key_filename
    if not src.exists():
        raise VaultError(f"deploy key not found at {src}")
    LOCAL_KEY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        LOCAL_KEY_DIR.chmod(0o700)
    except PermissionError:
        pass
    dst = LOCAL_KEY_DIR / spec.deploy_key_filename
    src_mtime = src.stat().st_mtime
    if not dst.exists() or dst.stat().st_mtime < src_mtime:
        shutil.copyfile(src, dst)
        dst.chmod(0o600)
    return dst


def _ssh_command(spec: WorkspaceSpec) -> str:
    key = _local_key_for(spec)
    return (
        f"ssh -i {key}"
        f" -o IdentitiesOnly=yes"
        f" -o StrictHostKeyChecking=accept-new"
        f" -o UserKnownHostsFile={LOCAL_KNOWN_HOSTS}"
    )


def _run_git(spec: WorkspaceSpec, *args: str, cwd: Path | None = None) -> str:
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = _ssh_command(spec)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or spec.path),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        raise VaultError(
            f"git {' '.join(args)} failed (exit {e.returncode}): "
            f"{(e.stderr or e.stdout or '').strip()}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise VaultError(f"git {' '.join(args)} timed out") from e
    return result.stdout


def _ensure(spec: WorkspaceSpec) -> None:
    """Idempotently make sure the vault is a working git checkout.

    LFS is intentionally disabled here: on this setup LFS's pre-push hook
    hangs (likely an LFS-API auth path that doesn't have what it needs from
    a deploy-key context). For now binaries go in as regular git objects.
    We `lfs uninstall --local` to make sure no stale hooks linger from older
    deploys.
    """
    with _ensure_lock:
        if spec.workspace in _ensured:
            return
        LOCAL_SSH_DIR.mkdir(parents=True, exist_ok=True)
        LOCAL_KNOWN_HOSTS.touch(exist_ok=True)
        spec.path.mkdir(parents=True, exist_ok=True)
        if not (spec.path / ".git").exists():
            log.info("cloning %s into %s", spec.remote, spec.path)
            _run_git(spec, "clone", spec.remote, str(spec.path), cwd=spec.path.parent)
        _run_git(spec, "config", "user.name", GIT_AUTHOR_NAME)
        _run_git(spec, "config", "user.email", GIT_AUTHOR_EMAIL)
        # Make sure no LFS pre-push hook is lurking from earlier deploys.
        try:
            _run_git(spec, "lfs", "uninstall", "--local")
        except VaultError:
            # `lfs uninstall --local` errors if LFS was never installed — fine.
            pass
        _ensured.add(spec.workspace)


def _resolve(workspace: str) -> WorkspaceSpec:
    spec = WORKSPACES.get(workspace)
    if spec is None:
        raise VaultError(f"unknown workspace '{workspace}'")
    return spec


def _safe_ext(filename: str | None) -> str:
    if not filename:
        return ""
    ext = Path(filename).suffix.lower()
    if not ext:
        return ""
    if not all(c.isalnum() or c == "." for c in ext):
        return ""
    if len(ext) > 12:
        return ""
    return ext


def append_to_daily(workspace: str, body: str, when: datetime | None = None) -> Path:
    """Append `body` under a `## HH:MM` heading in today's daily note."""
    body = body.strip()
    if not body:
        raise VaultError("body is empty")

    spec = _resolve(workspace)
    _ensure(spec)

    when = when or datetime.now()
    date_slug = when.strftime("%Y-%m-%d")
    time_label = when.strftime("%H:%M")
    relpath = Path("Daily") / f"{date_slug}.md"
    abs_path = spec.path / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    if not abs_path.exists():
        abs_path.write_text(f"# {date_slug}\n\n## {time_label}\n\n{body}\n")
    else:
        with abs_path.open("a", encoding="utf-8") as f:
            f.write(f"\n## {time_label}\n\n{body}\n")

    _commit_and_push(spec, f"quick-note: {date_slug} {time_label}")
    return abs_path


def save_attachment(workspace: str, filename: str | None, content: bytes) -> Path:
    """Write a binary attachment to _attachments/YYYY/MM/<uuid>.<ext>.

    Returns the vault-relative path (e.g. _attachments/2026/05/abc123.png).
    Does NOT commit — the caller commits along with the inbox note that
    references the attachment.
    """
    if not content:
        raise VaultError("empty attachment")
    spec = _resolve(workspace)
    _ensure(spec)
    now = datetime.now()
    subdir = Path("_attachments") / now.strftime("%Y") / now.strftime("%m")
    abs_subdir = spec.path / subdir
    abs_subdir.mkdir(parents=True, exist_ok=True)
    ext = _safe_ext(filename)
    rel = subdir / f"{uuid.uuid4().hex}{ext}"
    (spec.path / rel).write_bytes(content)
    return rel


def write_inbox(
    workspace: str,
    body: str,
    attachments: list[Path] | None = None,
    when: datetime | None = None,
) -> Path:
    """Create an Inbox/<timestamp>.md note with body + embedded attachments."""
    body = (body or "").strip()
    attachments = attachments or []
    if not body and not attachments:
        raise VaultError("inbox entry needs text or at least one attachment")

    spec = _resolve(workspace)
    _ensure(spec)
    when = when or datetime.now()
    slug = when.strftime("%Y-%m-%dT%H-%M-%S")
    relpath = Path("Inbox") / f"{slug}.md"
    abs_path = spec.path / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("---")
    lines.append(f"created: {when.isoformat(timespec='seconds')}")
    lines.append("tags: [inbox]")
    lines.append("---")
    lines.append("")
    if body:
        lines.append(body)
        lines.append("")
    for att in attachments:
        att_posix = att.as_posix()
        if att.suffix.lower() in IMAGE_EXTS:
            lines.append(f"![[{att_posix}]]")
        else:
            lines.append(f"[{att.name}]({att_posix})")
    abs_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = f"inbox: {slug}"
    if attachments:
        summary += f" (+{len(attachments)})"
    _commit_and_push(spec, summary)
    return abs_path


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(s: str, max_len: int = 60) -> str:
    s = s.lower()
    s = _SLUG_RE.sub("-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-")


def write_bookmark(
    workspace: str,
    url: str,
    title: str,
    description: str = "",
    when: datetime | None = None,
) -> Path:
    """Write a bookmark note to Links/<slug>.md with YAML frontmatter.

    Returns the absolute path. The vault-relative path is the second segment
    of the return value if needed by the caller (use `.relative_to`).
    """
    spec = _resolve(workspace)
    _ensure(spec)
    when = when or datetime.now()

    title = (title or url).strip() or url
    description = (description or "").strip()
    base_slug = _slugify(title) or when.strftime("%Y-%m-%dT%H-%M-%S")
    relpath = Path("Links") / f"{base_slug}.md"
    abs_path = spec.path / relpath
    if abs_path.exists():
        i = 2
        while True:
            relpath = Path("Links") / f"{base_slug}-{i}.md"
            abs_path = spec.path / relpath
            if not abs_path.exists():
                break
            i += 1
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    fm: list[str] = ["---"]
    fm.append(f"url: {json.dumps(url)}")
    fm.append(f"title: {json.dumps(title)}")
    if description:
        fm.append(f"description: {json.dumps(description)}")
    fm.append(f"captured_at: {when.isoformat(timespec='seconds')}")
    fm.append("tags: [link]")
    fm.append("---")
    fm.append("")
    fm.append(f"# {title}")
    fm.append("")
    if description:
        fm.append(f"> {description}")
        fm.append("")
    fm.append(f"<{url}>")
    fm.append("")
    abs_path.write_text("\n".join(fm), encoding="utf-8")

    _commit_and_push(spec, f"link: {title[:60]}")
    return abs_path


def _commit_and_push(spec: WorkspaceSpec, message: str) -> None:
    _run_git(spec, "add", ".")
    status = _run_git(spec, "status", "--porcelain")
    if not status.strip():
        log.info("no changes to commit for workspace=%s", spec.workspace)
        return
    _run_git(spec, "commit", "-m", message)
    _run_git(spec, "push", "origin", "HEAD")
