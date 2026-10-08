"""Turn a MeetingRecord into Markdown and JSON. Plain code, no LLM.

Both outputs come from the same MeetingRecord (plus the code-made trust report and speaking
stats), so they always contain the same items.
"""

import json
from typing import Any

from app.pipeline.models import Evidence, MeetingRecord, SpeakingStats, TrustReport

UNSPECIFIED = "Unspecified"
NONE_RECORDED = "_None recorded._"


def record_to_json(record: MeetingRecord, trust: TrustReport | None = None, speaking: SpeakingStats | None = None) -> str:
    """The machine-readable record. Missing owners/deadlines stay null."""
    data: dict[str, Any] = record.model_dump(exclude={"fix_counts"})  # the trust report covers these counts
    if trust:
        data["trust_report"] = trust.model_dump()
    if speaking:
        data["speaking_stats"] = speaking.model_dump()
    return json.dumps(data, indent=2, ensure_ascii=False)


def record_to_markdown(
    record: MeetingRecord,
    title: str = "Meeting record",
    trust: TrustReport | None = None,
    speaking: SpeakingStats | None = None,
) -> str:
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

    if speaking:
        lines += _speaking_section(speaking)
    if trust:
        lines += _trust_section(trust)
    elif record.warnings:
        lines += ["## Notes on this record", "", "_Automatic checks adjusted the following:_", ""]
        lines += [f"- {warning}" for warning in record.warnings]
        lines.append("")

    return "\n".join(lines)


def _speaking_section(speaking: SpeakingStats) -> list[str]:
    lines = ["## Who spoke", "", "| Speaker | Talk time | Share | Turns | Questions |", "|---|---|---|---|---|"]
    for s in speaking.speakers:
        cells = [s.speaker, format_time(s.seconds), f"{round(s.share * 100)}%", str(s.turns), str(s.questions)]
        lines.append("| " + " | ".join(_table_cell(cell) for cell in cells) + " |")
    return lines + [""]


def _trust_section(trust: TrustReport) -> list[str]:
    """Every count comes from a check the code ran on this recording."""
    blocked = sum(trust.edits_blocked.values())
    facts = [
        f"{_count(trust.items_verified, 'item')} (decisions, tasks, open items) checked: each one's quote was found in the transcript",
        f"{_count(trust.items_removed, 'item')} removed because the quote was not in the transcript",
        f"{_count(trust.details_removed, 'guessed owner, deadline or name', 'guessed owners, deadlines or names')} removed (not said in the recording)",
        f"{_count(trust.owners_unspecified, 'task owner')} and {_count(trust.deadlines_unspecified, 'deadline')} left Unspecified because nobody stated them",
        f"{_count(trust.corrections, 'term correction')} made; {_count(blocked, 'risky edit')} blocked"
        + (f" ({', '.join(f'{n} {reason}' for reason, n in trust.edits_blocked.items())})" if blocked else ""),
    ]
    if trust.items_superseded:
        facts.append(f"{_count(trust.items_superseded, 'item')} replaced by a later outcome (long meeting cross-check)")
    if trust.speakers_named or trust.speakers_unnamed:
        facts.append(f"{_count(trust.speakers_named, 'speaker')} named from evidence; {trust.speakers_unnamed} kept as labels")
    facts.append(
        f"{_count(trust.unclear_segments, 'transcript line')} from unclear audio; {_count(trust.unclear_items, 'record item')} quoting them"
    )
    lines = ["## Trust report", ""] + [f"- {fact}" for fact in facts] + [""]
    if trust.notes:
        lines += ["### What the checks changed", ""] + [f"- {note}" for note in trust.notes] + [""]
    return lines


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


def _count(n: int, singular: str, plural: str | None = None) -> str:
    """3, "item" -> "3 items"; 1, "item" -> "1 item"."""
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


def _table_cell(text: str) -> str:
    """Stop "|" or line breaks inside a cell from breaking the Markdown table."""
    return text.replace("|", "\\|").replace("\n", " ")
