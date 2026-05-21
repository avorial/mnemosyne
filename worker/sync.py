"""Background sync worker.

In v0.1 this is a heartbeat-only stub. Phases v0.5+ wire real sync tasks
(Asana pull, calendar refresh, GitHub events, git pull on the vaults).
"""

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("mnemosyne.worker")


def main() -> None:
    log.info("worker started (v0.1 stub — no tasks scheduled yet)")
    while True:
        time.sleep(60)
        log.debug("heartbeat")


if __name__ == "__main__":
    main()
