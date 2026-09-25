"""Reset the dev database and seed realistic demo data.

Usage:
    .venv/Scripts/python.exe -m scripts.seed_demo_data            # reset + seed
    .venv/Scripts/python.exe -m scripts.seed_demo_data --keep-existing
                                                                  # add missing rows only

Idempotent: every row is keyed by a natural unique constraint (competitor
domain, tracked URL, snapshot timestamp), so re-running the seeder produces
the same dataset rather than duplicating rows. By default it wipes all rows
first so the dev database is reproducible from scratch.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db import Base, SessionLocal, engine, init_db
from app.models import ChangeItem, Competitor, Diff, Snapshot, TrackedUrl
from app.services.diffing import build_change_summary


def _utc(day_offset: int, hour: int) -> datetime:
    """Deterministic timestamp: N days ago at HH:00 UTC, stored naive (SQLite convention)."""
    moment = datetime.now(timezone.utc) - timedelta(days=day_offset)
    moment = moment.replace(hour=hour, minute=0, second=0, microsecond=0)
    return moment.replace(tzinfo=None)


COMPETITORS: list[dict] = [
    {
        "name": "Nimbus Analytics",
        "domain": "nimbus-analytics.demo",
        "cadence": "daily",
        "pages": [
            {
                "url": "https://nimbus-analytics.demo/pricing",
                "page_type": "pricing",
                "snapshots": [
                    {"days_ago": 14, "hour": 9, "text": "Starter $19/month · Team $49/month · Enterprise: contact us"},
                    {"days_ago": 7, "hour": 9, "text": "Starter $19/month · Team $49/month · Enterprise: contact us"},
                    {
                        "days_ago": 1,
                        "hour": 9,
                        "text": "Starter $19/month · Team $39/month (limited offer) · Enterprise: contact us",
                        "material": True,
                        "category": "pricing",
                        "summary": "Nimbus Analytics cut the Team plan from $49 to $39 as a limited offer.",
                        "why": "Undercuts our mid-tier; sales should lead with annual-billing value, not price matching.",
                        "confidence": 0.92,
                    },
                ],
            },
            {
                "url": "https://nimbus-analytics.demo/product",
                "page_type": "product",
                "snapshots": [
                    {"days_ago": 14, "hour": 9, "text": "Dashboards, alerts, and CSV export"},
                    {
                        "days_ago": 2,
                        "hour": 10,
                        "text": "Dashboards, alerts, CSV export, and AI-generated weekly summaries",
                        "material": True,
                        "category": "product",
                        "summary": "Nimbus added AI-generated weekly summaries to their product page.",
                        "why": "Direct feature overlap with our roadmap narrative; expect competitive questions in deals.",
                        "confidence": 0.74,
                    },
                ],
            },
        ],
    },
    {
        "name": "Vector Metrics",
        "domain": "vector-metrics.demo",
        "cadence": "weekly",
        "pages": [
            {
                "url": "https://vector-metrics.demo/pricing",
                "page_type": "pricing",
                "snapshots": [
                    {"days_ago": 21, "hour": 8, "text": "Free · Pro $29/month · Scale $99/month"},
                    {"days_ago": 3, "hour": 8, "text": "Free · Pro $29/month · Scale $99/month"},
                ],
            },
            {
                "url": "https://vector-metrics.demo/careers",
                "page_type": "careers",
                "snapshots": [
                    {"days_ago": 21, "hour": 8, "text": "Open roles: 2 backend engineers, 1 designer"},
                    {
                        "days_ago": 1,
                        "hour": 11,
                        "text": "Open roles: 4 backend engineers, 2 ML engineers, 1 designer — building LLM features",
                        "material": True,
                        "category": "hiring",
                        "summary": "Vector Metrics more than doubled engineering openings, adding ML/LLM roles.",
                        "why": "Hiring signal suggests an AI feature push within one or two quarters.",
                        "confidence": 0.68,
                    },
                ],
            },
        ],
    },
    {
        "name": "Harbor Cloud",
        "domain": "harbor-cloud.demo",
        "cadence": "weekly",
        "pages": [
            {
                "url": "https://harbor-cloud.demo/pricing",
                "page_type": "pricing",
                "snapshots": [
                    {"days_ago": 30, "hour": 7, "text": "Basic $15/month · Plus $35/month"},
                    {
                        "days_ago": 5,
                        "hour": 7,
                        "text": "Basic $15/month · Plus $45/month · New compliance add-on",
                        "material": True,
                        "category": "pricing",
                        "summary": "Harbor Cloud raised the Plus plan from $35 to $45/month and added a paid compliance add-on.",
                        "why": "Price increase creates an opening for win-back campaigns against their price-sensitive customers.",
                        "confidence": 0.85,
                    },
                ],
            },
            {
                "url": "https://harbor-cloud.demo/changelog",
                "page_type": "product",
                "snapshots": [
                    {"days_ago": 30, "hour": 7, "text": "Minor UI refresh and bug fixes"},
                ],
            },
        ],
    },
    {
        "name": "Quiet Loop",
        "domain": "quiet-loop.demo",
        "cadence": "weekly",
        "pages": [
            {
                "url": "https://quiet-loop.demo/pricing",
                "page_type": "pricing",
                "snapshots": [
                    {"days_ago": 14, "hour": 12, "text": "Solo $12/month · Studio $30/month"},
                    {"days_ago": 7, "hour": 12, "text": "Solo $12/month · Studio $30/month"},
                ],
            },
        ],
    },
]


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


def seed(keep_existing: bool = False) -> dict[str, int]:
    if not keep_existing:
        reset_database()

    counts = {"competitors": 0, "tracked_urls": 0, "snapshots": 0, "diffs": 0, "change_items": 0}

    with SessionLocal() as db:
        for spec in COMPETITORS:
            competitor = db.scalar(select(Competitor).where(Competitor.domain == spec["domain"]))
            if competitor is None:
                competitor = Competitor(
                    name=spec["name"],
                    domain=spec["domain"],
                    status="active",
                    crawl_cadence=spec["cadence"],
                    created_at=_utc(30, 6),
                )
                db.add(competitor)
                db.flush()
                counts["competitors"] += 1

            for page_spec in spec["pages"]:
                tracked = db.scalar(select(TrackedUrl).where(TrackedUrl.url == page_spec["url"]))
                if tracked is None:
                    tracked = TrackedUrl(
                        competitor_id=competitor.id,
                        url=page_spec["url"],
                        page_type=page_spec["page_type"],
                    )
                    db.add(tracked)
                    db.flush()
                    counts["tracked_urls"] += 1

                previous: Snapshot | None = None
                for snap_spec in page_spec["snapshots"]:
                    fetched_at = _utc(snap_spec["days_ago"], snap_spec["hour"])
                    existing = db.scalar(
                        select(Snapshot).where(
                            Snapshot.tracked_url_id == tracked.id,
                            Snapshot.fetched_at == fetched_at,
                        )
                    )
                    if existing is not None:
                        previous = existing
                        continue

                    snapshot = Snapshot(
                        tracked_url_id=tracked.id,
                        fetched_at=fetched_at,
                        text_content=snap_spec["text"],
                    )
                    db.add(snapshot)
                    db.flush()
                    counts["snapshots"] += 1
                    tracked.last_crawled_at = fetched_at

                    if previous is not None:
                        summary = build_change_summary(previous.text_content, snapshot.text_content, tracked.url)
                        material = bool(snap_spec.get("material", summary["material_change"]))
                        diff = Diff(
                            tracked_url_id=tracked.id,
                            snapshot_before_id=previous.id,
                            snapshot_after_id=snapshot.id,
                            stage1_score=1.0 if material else 0.0,
                            passed_filter=material,
                        )
                        db.add(diff)
                        db.flush()
                        counts["diffs"] += 1

                        if material:
                            db.add(
                                ChangeItem(
                                    diff_id=diff.id,
                                    category=snap_spec.get("category", summary["category"]),
                                    magnitude="major" if snap_spec.get("category", summary["category"]) == "pricing" else "minor",
                                    summary=snap_spec.get("summary", summary["summary"]),
                                    why_it_matters=snap_spec.get("why", summary["summary"]),
                                    confidence=snap_spec.get("confidence", summary["confidence"]),
                                    status="pending",
                                )
                            )
                            counts["change_items"] += 1

                    previous = snapshot

        db.commit()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the SignalSentry dev database with realistic demo data.")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Add missing demo rows without wiping the database first.",
    )
    args = parser.parse_args()

    counts = seed(keep_existing=args.keep_existing)
    action = "added to existing database" if args.keep_existing else "seeded after full reset"
    print(f"Demo data {action}: {counts}")


if __name__ == "__main__":
    main()
