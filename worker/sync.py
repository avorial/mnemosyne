"""Background sync worker.

Periodically reconciles local mirrors with their upstream sources.

v0.5: pulls Asana 'My Tasks' for every workspace that has a mapping, every 5
minutes. Future phases (v0.6 Google Calendar, v0.7 GitHub activity) will hook
their pulls into this same loop.
"""

from __future__ import annotations

import asyncio
import logging

from app import db
from app.services import asana_client, todos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("mnemosyne.worker")

POLL_SECONDS = 300  # 5 minutes


async def _poll_asana_once() -> None:
    mappings = todos.all_mappings()
    if not mappings:
        log.debug("no Asana workspace mappings; skipping pull")
        return
    for m in mappings:
        try:
            count = await todos.sync_from_asana(m.workspace)
            log.info(
                "asana pull workspace=%s asana=%s tasks=%d",
                m.workspace, m.asana_workspace_name, count,
            )
        except asana_client.AsanaNotConfigured:
            log.info("asana PAT not configured; skipping")
            return
        except Exception:
            log.exception("asana pull failed for workspace=%s", m.workspace)


async def main() -> None:
    log.info("worker starting (poll every %ds)", POLL_SECONDS)
    db.init()
    while True:
        try:
            await _poll_asana_once()
        except Exception:
            log.exception("poll iteration crashed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
