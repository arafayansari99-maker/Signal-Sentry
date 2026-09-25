from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ChangeItem, Competitor, Digest, DigestItem, Diff, TrackedUrl
from app.services.notifications import send_email_alert

# Digest composition rules (PRD FR6/§2.2.7):
# - rank by magnitude (major first), then confidence
# - hard cap on items; overflow is reported as "minor changes" count
# - items already included in an earlier digest are not re-surfaced
DIGEST_MAX_ITEMS = 15
MAGNITUDE_RANK = {"major": 0, "minor": 1}


def _rank_key(change_item: ChangeItem) -> tuple[int, float]:
    return (MAGNITUDE_RANK.get(change_item.magnitude, 1), -change_item.confidence)


def generate_weekly_digest(db: Session, *, send: bool = False) -> dict[str, Any]:
    """Build, persist, and optionally deliver the weekly digest.

    Selects change items from the last 7 days that have not appeared in any
    earlier digest, ranks them (major first, then confidence), caps the list,
    and stores a Digest + DigestItem rows. Sent change items get status="shown".
    """
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=7)

    previously_sent_ids = set(
        db.scalars(select(DigestItem.change_item_id)).all()
    )

    rows = db.execute(
        select(ChangeItem, Competitor, TrackedUrl)
        .join(Diff, Diff.id == ChangeItem.diff_id)
        .join(TrackedUrl, TrackedUrl.id == Diff.tracked_url_id)
        .join(Competitor, Competitor.id == TrackedUrl.competitor_id)
        .where(ChangeItem.status != "dismissed")
        .order_by(ChangeItem.confidence.desc())
    ).all()

    candidates = []
    for change_item, competitor, tracked_url in rows:
        if change_item.id in previously_sent_ids:
            continue
        fetched_at = change_item.diff.snapshot_after.fetched_at if change_item.diff.snapshot_after else None
        if fetched_at is None:
            continue
        if fetched_at.tzinfo is None:
            # SQLite stores naive datetimes (UTC by convention); make them comparable.
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        if fetched_at < period_start:
            continue
        candidates.append((change_item, competitor, tracked_url))

    candidates.sort(key=lambda row: _rank_key(row[0]))

    if not candidates:
        # Nothing new to send; don't create an empty digest row.
        return {
            "digest_id": None,
            "period_start": period_start.isoformat(),
            "period_end": now.isoformat(),
            "item_count": 0,
            "minor_changes_overflow": 0,
            "candidate_count": 0,
            "delivery": {"status": "skipped", "reason": "no new change items this period"},
            "items": [],
        }

    top_items = candidates[:DIGEST_MAX_ITEMS]
    overflow_count = max(len(candidates) - DIGEST_MAX_ITEMS, 0)

    digest = Digest(
        period_start=period_start,
        period_end=now,
        sent_at=None,
        channel="email",
    )
    db.add(digest)
    db.flush()

    items_payload = []
    for rank, (change_item, competitor, tracked_url) in enumerate(top_items, start=1):
        db.add(DigestItem(digest_id=digest.id, change_item_id=change_item.id, rank=rank))
        change_item.status = "shown"
        items_payload.append(
            {
                "rank": rank,
                "change_item_id": change_item.id,
                "competitor_id": competitor.id,
                "competitor_name": competitor.name,
                "url": tracked_url.url,
                "category": change_item.category,
                "magnitude": change_item.magnitude,
                "summary": change_item.summary,
                "confidence": change_item.confidence,
            }
        )

    delivery: dict[str, Any] = {"status": "skipped", "reason": "send=False or no recipient configured"}
    settings = get_settings()
    if send and settings.alert_email_to and items_payload:
        delivery = send_digest_email(settings.alert_email_to, digest, items_payload)
        if delivery.get("status") == "sent":
            digest.sent_at = now

    db.commit()

    return {
        "digest_id": digest.id,
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "item_count": len(items_payload),
        "minor_changes_overflow": overflow_count,
        "candidate_count": len(candidates),
        "delivery": delivery,
        "items": items_payload,
    }


def compose_digest_message(items: list[dict[str, Any]]) -> str:
    lines = ["SignalSentry weekly digest", "=" * 26, ""]
    for item in items:
        lines.append(f"{item['rank']}. [{item['category']}] {item['competitor_name']}")
        lines.append(f"   {item['summary']}")
        lines.append(f"   Source: {item['url']}  (confidence {item['confidence']:.0%})")
        lines.append("")
    return "\n".join(lines).strip()


def send_digest_email(to_address: str, digest: Digest, items: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.smtp_host or not to_address:
        return {"status": "skipped", "reason": "smtp disabled or recipient missing"}

    from app.services.notifications import _send_email_message

    return _send_email_message(
        to_address=to_address,
        subject=f"SignalSentry weekly digest ({digest.period_start:%b %d} – {digest.period_end:%b %d})",
        body=compose_digest_message(items),
    )
