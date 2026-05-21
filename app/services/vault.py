"""Git-backed Obsidian vault service.

Each workspace ('personal' / 'work') has its own checkout of a private GitHub
repo. Widgets call this service to append/write markdown files, which are
then committed and pushed.

On first use per workspace, the service writes an SSH config (so the deploy
keys at /mnt/mnemosyne/secrets/deploy_notes{_work} can be used as the SSH
identity for github.com), then clones the repo if the vault directory isn't
already a git checkout.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import config

log = logging.getLogger("mnemosyne.vault")

GIT_AUTHOR_NAME = "Mnemosyne"
GIT_AUTHOR_EMAIL = "noreply@mnemosyne.avorial.com"

SSH_CONFIG_TEMPLATE = """\
Host github-notes
  HostName github.com
  User git
  IdentityFile {personal_key}
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile {known_hosts}

Host github-notes-work
  HostName github.com
  User git
  IdentityFile {work_key}
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile {known_hosts}
"""


@dataclass(frozen=True)
class WorkspaceSpec:
    workspace: str
    path: Path
    remote: str  # git URL using ssh host alias
    deploy_key_filename: str


WORKSPACES: dict[str, WorkspaceSpec] = {
    "personal": WorkspaceSpec(
        workspace="personal",
        path=config.vault_personal_path,
        remote="git@github-notes:avorial/notes.git",
        deploy_key_filename="deploy_notes",
    ),
    "work": WorkspaceSpec(
        workspace="work",
        path=config.vault_work_path,
        remote="git@github-notes-work:avorial/notes-work.git",
        deploy_key_filename="deploy_notes_work",
    ),
}


class VaultError(RuntimeError):
    pass


_ensure_lock = threading.Lock()
_ensured: set[str] = set()


def _run_git(spec: WorkspaceSpec, *args: str, cwd: Path | None = None) -> str:
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = f"ssh -F {config.secrets_path / 'ssh_config'}"
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
            f"git {' '.join(args)} failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise VaultError(f"git {' '.join(args)} timed out") from e
    return result.stdout


def _write_ssh_config() -> None:
    ssh_config_path = config.secrets_path / "ssh_config"
    if ssh_config_path.exists():
        return
    ssh_config_path.parent.mkdir(parents=True, exist_ok=True)
    known_hosts = config.secrets_path / "known_hosts"
    known_hosts.touch(exist_ok=True)
    try:
        known_hosts.chmod(0o600)
    except PermissionError:
        # CIFS mounts often ignore chmod; non-fatal.
        pass
    content = SSH_CONFIG_TEMPLATE.format(
        personal_key=config.secrets_path / "deploy_notes",
        work_key=config.secrets_path / "deploy_notes_work",
        known_hosts=known_hosts,
    )
    ssh_config_path.write_text(content)
    try:
        ssh_config_path.chmod(0o600)
    except PermissionError:
        pass


def _ensure(spec: WorkspaceSpec) -> None:
    """Idempotently make sure the vault is a working git checkout."""
    with _ensure_lock:
        if spec.workspace in _ensured:
            return
        _write_ssh_config()
        spec.path.mkdir(parents=True, exist_ok=True)
        if not (spec.path / ".git").exists():
            log.info("cloning %s into %s", spec.remote, spec.path)
            # Clone into an existing (possibly non-empty) directory.
            _run_git(spec, "clone", spec.remote, str(spec.path), cwd=spec.path.parent)
            # Configure author identity on the new clone.
            _run_git(spec, "config", "user.name", GIT_AUTHOR_NAME)
            _run_git(spec, "config", "user.email", GIT_AUTHOR_EMAIL)
        else:
            # Existing checkout — make sure author identity is set.
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
    # If nothing staged (e.g. retried operation), skip.
    status = _run_git(spec, "status", "--porcelain")
    if not status.strip():
        log.info("no changes to commit for workspace=%s", spec.workspace)
        return
    _run_git(spec, "commit", "-m", message)
    _run_git(spec, "push", "origin", "HEAD")
