"""Optional phone push notifications via ntfy.sh (free, no account: install the ntfy app and subscribe to your topic)."""
from __future__ import annotations

import logging
import urllib.request

log = logging.getLogger(__name__)


def notify(topic: str, title: str, message: str) -> None:
    log.info("%s: %s", title, message)
    if not topic:
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode(),
        headers={"Title": title.encode("ascii", "ignore").decode()},
    )
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except OSError as e:
        log.warning("push notification failed: %s", e)
