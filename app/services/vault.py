"""Git-backed Obsidian vault service.

Each workspace ('personal' / 'work') has its own checkout of a private GitHub
repo. Widgets call this service to append/write markdown files, which are
then committed and pushed.

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
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
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
    """Copy the deploy key from CIFS to a local path with strict perms.

    SSH refuses keys with mode > 0600 — and CIFS mounts often won't honor
    chmod, so the canonical fix is to use a local copy.
    """
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
            timeout=60,
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
    """Idempotently make sure the vault is a working git checkout."""
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
        _ensured.add(spec.workspace)


def _resolve(workspace: str) -> WorkspaceSpec:
    spec = WORKSPACES.get(workspace)
    if spec is None:
        raise VaultError(f"unknown workspace '{workspace}'")
    return spec


def append_to_daily(workspace: str, body: str, when: datetime | None = None) -> Path:
    """Append `body` under a `## HH:MM` heading in today's daily note.

    Returns the absolute path of the file written.
    """
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


def _commit_and_push(spec: WorkspaceSpec, message: str) -> None:
    _run_git(spec, "add", ".")
    status = _run_git(spec, "status", "--porcelain")
    if not status.strip():
        log.info("no changes to commit for workspace=%s", spec.workspace)
        return
    _run_git(spec, "commit", "-m", message)
    _run_git(spec, "push", "origin", "HEAD")
