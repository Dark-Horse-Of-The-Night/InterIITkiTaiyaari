"""Turn a MeetingRecord into Markdown and JSON. Plain code, no LLM.

Both outputs come from the same MeetingRecord, so they always contain the same items.
"""

import json

from app.pipeline.models import Evidence, MeetingRecord

UNSPECIFIED = "Unspecified"
NONE_RECORDED = "_None recorded._"


def record_to_json(record: MeetingRecord) -> str:
    """The machine-readable record. Missing owners/deadlines stay null."""
    return json.dumps(record.model_dump(), indent=2, ensure_ascii=False)


def record_to_markdown(record: MeetingRecord, title: str = "Meeting record") -> str:
    """The human-readable record. Missing owners/deadlines are shown as "Unspecified"."""
    lines = [f"# {title}", "", "## Summary", "", record.summary or NONE_RECORDED, ""]

    lines += ["## Minutes", ""]
    if not record.minutes:
        lines += [NONE_RECORDED, ""]
    for topic in record.minutes:
        lines += [f"### {topic.topic}", ""]
        lines += [f"- {point}" for point in topic.points]
        lines.append("")

    lines += ["## Key decisions", ""]
    if not record.decisions:
        lines.append(NONE_RECORDED)
    for number, decision in enumerate(record.decisions, start=1):
        lines.append(f"{number}. {decision.text} {_source(decision.evidence)}")
    lines.append("")

    lines += ["## Action items", ""]
    if not record.action_items:
        lines.append(NONE_RECORDED)
    else:
        lines += ["| # | Task | Owner | Deadline | Source |", "|---|------|-------|----------|--------|"]
        for number, item in enumerate(record.action_items, start=1):
            cells = [str(number), item.task, item.owner or UNSPECIFIED, item.deadline or UNSPECIFIED, _time(item.evidence)]
            lines.append("| " + " | ".join(_table_cell(cell) for cell in cells) + " |")
    lines.append("")

    lines += ["## Open proposals and questions", ""]
    if not record.open_items:
        lines.append(NONE_RECORDED)
    for item in record.open_items:
        raised_by = f", raised by {item.raised_by}" if item.raised_by else ""
        lines.append(f"- **{item.kind.capitalize()}{raised_by}:** {item.text} {_source(item.evidence)}")
    lines.append("")

    if record.warnings:
        lines += ["## Notes on this record", "", "_Automatic checks adjusted the following:_", ""]
        lines += [f"- {warning}" for warning in record.warnings]
        lines.append("")

    return "\n".join(lines)


def format_time(seconds: float) -> str:
    """Seconds -> "mm:ss"."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


def _time(evidence: Evidence) -> str:
    return format_time(evidence.start) if evidence.start is not None else ""


def _source(evidence: Evidence) -> str:
    """Timestamp and quote, e.g. _(00:26, "we decided to use OAuth")_."""
    time = _time(evidence)
    return f'_({time}: "{evidence.quote}")_' if time else f'_("{evidence.quote}")_'


def _table_cell(text: str) -> str:
    """Stop "|" or line breaks inside a cell from breaking the Markdown table."""
    return text.replace("|", "\\|").replace("\n", " ")
