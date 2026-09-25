from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import ChangeItem, Competitor, Diff, Snapshot, TrackedUrl
from app.services.diffing import build_change_summary, has_material_change
from app.services.discovery import discover_urls
from app.services.notifications import compose_alert_message, send_email_alert, send_slack_alert
from app.services.scraping import build_page_snapshot


def run_pipeline(competitor_domain: str, previous_text: str, current_text: str) -> dict:
    candidate_urls = discover_urls(competitor_domain)
    material_change = has_material_change(previous_text, current_text)

    return {
        "competitor_domain": competitor_domain,
        "candidate_urls": candidate_urls,
        "material_change": material_change,
    }


def process_page_change(competitor_domain: str, url: str, previous_text: str, current_text: str) -> dict:
    summary = build_change_summary(previous_text, current_text, url)
    return {
        "competitor_domain": competitor_domain,
        "url": url,
        "page_type": summary["page_type"],
        "category": summary["category"],
        "material_change": summary["material_change"],
        "confidence": summary["confidence"],
        "summary": summary["summary"],
        "changed_tokens": summary["changed_tokens"],
    }


def run_monitoring_cycle(competitor_id: int | None = None, tracked_url_id: int | None = None, previous_snapshot_id: int | None = None, current_snapshot_id: int | None = None) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        targets = []
        if competitor_id is not None and tracked_url_id is not None:
            targets.append((competitor_id, tracked_url_id))
        else:
            query = select(Competitor.id, TrackedUrl.id).join(TrackedUrl, TrackedUrl.competitor_id == Competitor.id)
            if competitor_id is not None:
                query = query.where(Competitor.id == competitor_id)
            rows = db.execute(query).all()
            targets = [(competitor_pk, tracked_pk) for competitor_pk, tracked_pk in rows]

        processed = 0
        material = 0
        created_diff_ids = []
        alerts_sent = 0

        for current_competitor_id, current_tracked_url_id in targets:
            tracked_url = db.get(TrackedUrl, current_tracked_url_id)
            if tracked_url is None or tracked_url.competitor_id != current_competitor_id:
                continue

            competitor = db.get(Competitor, current_competitor_id)
            if competitor is None:
                continue

            snapshot_payload = build_page_snapshot(tracked_url.url)
            snapshot = Snapshot(
                tracked_url_id=current_tracked_url_id,
                fetched_at=datetime.now(timezone.utc),
                text_content=snapshot_payload["text_content"],
                structured_data={"prices": snapshot_payload["prices"]},
            )
            db.add(snapshot)
            db.flush()

            if len(db.execute(select(Snapshot).where(Snapshot.tracked_url_id == current_tracked_url_id).order_by(Snapshot.fetched_at.asc())).scalars().all()) > 1:
                previous_snapshot = db.execute(
                    select(Snapshot)
                    .where(Snapshot.tracked_url_id == current_tracked_url_id)
                    .order_by(Snapshot.fetched_at.asc())
                    .offset(0)
                    .limit(1)
                ).scalar_one_or_none()
                if previous_snapshot is None:
                    continue
            else:
                previous_snapshot = snapshot

            if previous_snapshot_id is not None and current_snapshot_id is not None:
                previous_snapshot = db.get(Snapshot, previous_snapshot_id)
                current_snapshot = db.get(Snapshot, current_snapshot_id)
                if previous_snapshot is None or current_snapshot is None:
                    continue
            else:
                current_snapshot = snapshot

            summary = build_change_summary(previous_snapshot.text_content, current_snapshot.text_content, tracked_url.url)
            diff = Diff(
                tracked_url_id=current_tracked_url_id,
                snapshot_before_id=previous_snapshot.id,
                snapshot_after_id=current_snapshot.id,
                stage1_score=1.0 if summary["material_change"] else 0.0,
                passed_filter=summary["material_change"],
            )
            db.add(diff)
            db.flush()

            change_item = ChangeItem(
                diff_id=diff.id,
                category=summary["category"],
                magnitude="major" if summary["category"] == "pricing" else "minor",
                summary=summary["summary"],
                why_it_matters=summary["summary"],
                confidence=summary["confidence"],
                status="pending",
            )
            db.add(change_item)
            db.flush()
            processed += 1
            if summary["material_change"]:
                material += 1
                alerts_sent += 1
                alert_message = compose_alert_message(competitor.name, summary["category"], summary["summary"])
                if settings.alert_email_to:
                    send_email_alert(settings.alert_email_to, competitor.name, summary["category"], summary["summary"])
                if settings.slack_webhook_url:
                    send_slack_alert(settings.slack_webhook_url, competitor.name, summary["category"], summary["summary"])
            created_diff_ids.append(diff.id)

        db.commit()
        return {
            "processed_competitors": processed,
            "material_changes": material,
            "diff_ids": created_diff_ids,
            "alerts_sent": alerts_sent,
            "last_alert": alert_message if 'alert_message' in locals() else None,
        }
