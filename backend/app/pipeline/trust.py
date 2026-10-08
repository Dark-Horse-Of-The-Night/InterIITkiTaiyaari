"""The trust report: what the automatic checks verified, removed or blocked. Code only, no model."""

from app.pipeline.models import MeetingRecord, RefinedTranscript, Transcript, TrustReport


def build_trust_report(raw: Transcript, refined: RefinedTranscript, record: MeetingRecord) -> TrustReport:
    """Count the checks that ran on this recording, from the data each stage already produced."""
    items = [*record.decisions, *record.action_items, *record.open_items]
    labels = {segment.speaker for segment in refined.segments if segment.speaker}
    named = {name.name for name in refined.speaker_names}
    return TrustReport(
        items_verified=len(items),
        items_removed=record.fix_counts.get("unsupported_item", 0),
        details_removed=record.fix_counts.get("unstated_detail", 0),
        items_superseded=record.fix_counts.get("superseded", 0),
        owners_unspecified=sum(1 for item in record.action_items if item.owner is None),
        deadlines_unspecified=sum(1 for item in record.action_items if item.deadline is None),
        corrections=len(refined.corrections),
        edits_blocked=dict(refined.blocked_edits),
        speakers_named=len(labels & named),
        speakers_unnamed=len(labels - named),
        unclear_segments=sum(1 for segment in raw.segments if segment.unclear),
        unclear_items=sum(1 for item in items if item.evidence.unclear),
        notes=refined.warnings + record.warnings,
    )
