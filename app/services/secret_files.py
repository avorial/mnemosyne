"""Write pasted secrets (PATs, tokens) to their files on the secrets volume."""

from __future__ import annotations

import os
from pathlib import Path


def write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort; not meaningful on Windows dev machines
