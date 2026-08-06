"""Per-channel formatting of a brief payload.

The web reader renders via Jinja templates (see loop/api + loop/templates); this
module handles the plain-text rendering used by the CLI dry-run and, later, the
Telegram channel.
"""

from __future__ import annotations


def render_brief_text(brief: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("LOOP — everything you missed, in five minutes")
    lines.append("=" * 60)
    lines.append(
        f"Away for {brief['days_away']} day(s) · "
        f"{brief['stories_moved']} moved · {brief['stories_new']} new"
    )

    label_titles = {
        "important_regardless": "IMPORTANT — regardless of your interests",
        "for_you": "FOR YOU",
    }

    for section in brief["sections"]:
        stories = section["stories"]
        if not stories:
            continue
        lines.append("")
        lines.append(label_titles.get(section["label"], section["label"].upper()))
        lines.append("-" * 60)
        for s in stories:
            lines.append(f"• {s['title'] or '(untitled story)'}")
            if s.get("state_summary"):
                lines.append(f"    {s['state_summary']}")
            lines.append(
                f"    {s['new_event_count']} new · "
                f"{s['distinct_sources']} sources · "
                f"importance {s['importance']}"
            )
    lines.append("")
    lines.append("(AI-generated summaries. Click through for the full story.)")
    return "\n".join(lines)
