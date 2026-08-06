"""Telegram delivery channel (v0.2 roadmap).

Stubbed for the v0.1 slice. The brief payload and text renderer already exist
(loop.delivery.brief / loop.delivery.render); wiring this up is a bot token plus
a `sendMessage` call.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_brief(chat_id: str, brief_text: str) -> None:  # pragma: no cover
    raise NotImplementedError(
        "Telegram delivery is a v0.2 feature. The brief text is ready to send "
        "via loop.delivery.render.render_brief_text()."
    )
