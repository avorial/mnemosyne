"""OAuth token persistence — one JSON file per provider under the secrets dir.

Same philosophy as the Asana PAT: secrets live as small files on the mounted
secrets volume, never in the database, never cached longer than needed.
The refresh token is the durable credential; access tokens are short-lived
and re-minted from it.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger("mnemosyne.oauth")

# Refresh this many seconds before the access token actually expires.
EXPIRY_SLACK_SECONDS = 60


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: int       # unix seconds
    account: str = ""     # human label: the connected account's email

    @property
    def access_expired(self) -> bool:
        return time.time() >= self.expires_at - EXPIRY_SLACK_SECONDS


def load(path: Path) -> TokenSet | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return TokenSet(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            expires_at=int(data.get("expires_at", 0)),
            account=data.get("account", ""),
        )
    except (json.JSONDecodeError, ValueError, OSError):
        log.exception("unreadable token file %s", path)
        return None


def save(path: Path, tokens: TokenSet) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(tokens), indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort; not meaningful on Windows dev machines


def clear(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.exception("failed to remove token file %s", path)
