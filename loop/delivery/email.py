"""Email delivery channel (v0.2 roadmap).

Stubbed for the v0.1 slice. Intended backend is Resend or SES; briefs are
pre-generated on a schedule and mailed, never generated on request.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_brief(to_email: str, subject: str, brief_html: str) -> None:  # pragma: no cover
    raise NotImplementedError(
        "Email delivery is a v0.2 feature. Plug in Resend/SES here."
    )
