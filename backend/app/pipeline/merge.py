"""Combine the records of a long meeting's parts into one record.

Code joins the parts (minutes in order, all items). Then one small "cross-check"
call to the model may only REMOVE items, and must name the later item that
replaces each one (a proposal accepted later, a decision reversed later, a
duplicate). Code checks every removal before applying it, so merging can never
add or reword anything.
"""

import logging
from typing import Any, Literal

from app.pipeline.errors import STAGE_DOCUMENTER, PipelineError
from app.pipeline.llm_json import ReplyCutOff, estimate_tokens, only_required, request_structured
from app.pipeline.models import ActionItem, Decision, MeetingRecord, OpenItem, RecordModel, Topic
from app.pipeline.retry import RetryCallback
from app.prompt_loader import load_prompt

logger = logging.getLogger("app.pipeline.merge")

RECONCILE_OUTPUT_TOKENS = 2500

Item = Decision | ActionItem | OpenItem


class Removal(RecordModel):
    item: str  # e.g. "O1"
    replaced_by: str  # e.g. "D5"
    reason: Literal["accepted_later", "answered_later", "superseded", "duplicate"]


class CrossCheck(RecordModel):
    removals: list[Removal]
    summary: str


def merge_parts(
    parts: list[MeetingRecord], client: Any, model: str, max_request_tokens: int, on_retry: RetryCallback | None = None
) -> MeetingRecord:
    """Join the parts' records, then apply the cross-check's (validated) removals and summary."""
    items = label_items(parts)
    warnings = [warning for part in parts for warning in part.warnings]
    minutes = join_minutes([part.minutes for part in parts])

    system_prompt = load_prompt("documenter_reconcile")
    user_message = cross_check_input(parts, items)
    schema = only_required(CrossCheck.model_json_schema())
    request_size = estimate_tokens(system_prompt + user_message + str(schema)) + RECONCILE_OUTPUT_TOKENS

    if request_size > max_request_tokens:
        # Too many items to cross-check in one request: keep everything and say so.
        summary = " ".join(part.summary for part in parts)
        warnings.append(
            "This meeting had too many items to cross-check between its parts within the AI service's limit, "
            "so a proposal accepted later (or a decision changed later) may still appear in both forms."
        )
        removed: set[str] = set()
    else:
        try:
            check = request_structured(
                client, model, system_prompt, user_message, "cross_check", schema, CrossCheck.model_validate_json,
                STAGE_DOCUMENTER, "DOCUMENTER", RECONCILE_OUTPUT_TOKENS, on_retry, what="a cross-check",
            )
        except ReplyCutOff:
            raise PipelineError(
                STAGE_DOCUMENTER,
                "the cross-check between the meeting's parts was too long for the output limit",
                "Try again, or raise DOCUMENTER_MAX_REQUEST_TOKENS if you are on a paid plan.",
            ) from None
        summary = check.summary
        removed = apply_removals(check.removals, items, warnings)

    kept = {label: item for label, (part, item) in items.items() if label not in removed}
    return MeetingRecord(
        summary=summary,
        minutes=minutes,
        decisions=[i for i in kept.values() if isinstance(i, Decision)],
        action_items=[i for i in kept.values() if isinstance(i, ActionItem)],
        open_items=[i for i in kept.values() if isinstance(i, OpenItem)],
        warnings=warnings,
        fix_counts={"superseded": len(removed)} if removed else {},
    )


def label_items(parts: list[MeetingRecord]) -> dict[str, tuple[int, Item]]:
    """Give every item a short label: D1, D2... decisions, A1... actions, O1... open items."""
    labelled: dict[str, tuple[int, Item]] = {}
    counts = {"D": 0, "A": 0, "O": 0}
    for part_number, part in enumerate(parts, start=1):
        for prefix, group in (("D", part.decisions), ("A", part.action_items), ("O", part.open_items)):
            for item in group:
                counts[prefix] += 1
                labelled[f"{prefix}{counts[prefix]}"] = (part_number, item)
    return labelled


def cross_check_input(parts: list[MeetingRecord], items: dict[str, tuple[int, Item]]) -> str:
    lines = ["Part summaries:"]
    lines += [f"Part {n}: {part.summary}" for n, part in enumerate(parts, start=1)]
    lines += ["", "Items:"]
    lines += [f"[{label}] (part {part}) {describe(item)}" for label, (part, item) in items.items()]
    return "\n".join(lines)


def describe(item: Item) -> str:
    if isinstance(item, Decision):
        return f"Decision: {item.text}"
    if isinstance(item, ActionItem):
        details = [f"owner: {item.owner}" if item.owner else "", f"deadline: {item.deadline}" if item.deadline else ""]
        extra = ", ".join(d for d in details if d)
        return f"Action: {item.task}" + (f" [{extra}]" if extra else "")
    raised = f" [raised by {item.raised_by}]" if item.raised_by else ""
    return f"{item.kind.capitalize()}: {item.text}{raised}"


def apply_removals(removals: list[Removal], items: dict[str, tuple[int, Item]], warnings: list[str]) -> set[str]:
    """Check each removal makes sense; return the labels to remove. Invalid ones are ignored (and logged)."""
    removed: set[str] = set()
    for removal in removals:
        problem = _removal_problem(removal, items, removed)
        if problem:
            logger.warning("Ignored cross-check removal %s: %s", removal.model_dump(), problem)
            continue
        removed.add(removal.item)
        note = _removal_note(removal, items)
        if note not in warnings:  # the same item repeated several times needs only one note
            warnings.append(note)
    return removed


def _removal_problem(removal: Removal, items: dict[str, tuple[int, Item]], removed: set[str]) -> str | None:
    if removal.item not in items or removal.replaced_by not in items:
        return "unknown item"
    if removal.item == removal.replaced_by:
        return "an item can't replace itself"
    if removal.item in removed:
        return "already removed"
    if removal.replaced_by in removed:
        return "the replacing item was itself removed"
    item_part, item = items[removal.item]
    by_part, by = items[removal.replaced_by]

    if removal.reason == "duplicate":
        return None if type(item) is type(by) else "duplicates must be the same kind of item"
    if by_part < item_part:
        return "the replacing item must come later in the meeting"
    if removal.reason == "accepted_later":
        ok = isinstance(item, OpenItem) and item.kind == "proposal" and isinstance(by, Decision | ActionItem)
        return None if ok else "only a proposal can be accepted, by a decision or action item"
    if removal.reason == "answered_later":
        ok = isinstance(item, OpenItem) and item.kind == "question" and isinstance(by, Decision | ActionItem)
        return None if ok else "only a question can be answered, by a decision or action item"
    # superseded
    ok = isinstance(item, Decision | ActionItem) and type(item) is type(by)
    return None if ok else "only a decision or action item can be superseded, by one of the same kind"


def _removal_note(removal: Removal, items: dict[str, tuple[int, Item]]) -> str:
    item, by = items[removal.item][1], items[removal.replaced_by][1]
    item_text, by_text = _short(item), _short(by)
    return {
        "accepted_later": f"The proposal \"{item_text}\" was accepted later in the meeting, so it is listed as: \"{by_text}\".",
        "answered_later": f"The question \"{item_text}\" was answered later in the meeting: \"{by_text}\".",
        "superseded": f"\"{item_text}\" was changed later in the meeting; only the final outcome is listed: \"{by_text}\".",
        "duplicate": f"\"{item_text}\" was mentioned more than once; it is listed once as \"{by_text}\".",
    }[removal.reason]


def _short(item: Item) -> str:
    return item.task if isinstance(item, ActionItem) else item.text


def join_minutes(parts_minutes: list[list[Topic]]) -> list[Topic]:
    """Minutes in order. A topic that runs across a part boundary (same title) becomes one topic."""
    joined: list[Topic] = []
    for minutes in parts_minutes:
        for topic in minutes:
            if joined and joined[-1].topic.strip().lower() == topic.topic.strip().lower():
                joined[-1].points += topic.points
                joined[-1].segment_ids += topic.segment_ids
            else:
                joined.append(topic.model_copy(deep=True))
    return joined
