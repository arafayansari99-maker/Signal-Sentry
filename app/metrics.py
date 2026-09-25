from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ChangeItem, Competitor, Diff, Snapshot, TrackedUrl

router = APIRouter(tags=["metrics"])


@router.get("/metrics/overview")
def metrics_overview(db: Session = Depends(get_db)) -> dict:
    """Live totals powering the dashboard stat cards and signal trend chart."""
    window_start = datetime.now(timezone.utc) - timedelta(days=7)

    total_competitors = db.scalar(select(func.count()).select_from(Competitor)) or 0
    active_tracked_urls = db.scalar(
        select(func.count())
        .select_from(TrackedUrl)
        .join(Competitor, Competitor.id == TrackedUrl.competitor_id)
        .where(Competitor.status == "active")
    ) or 0
    total_tracked_urls = db.scalar(select(func.count()).select_from(TrackedUrl)) or 0

    by_category_rows = db.execute(
        select(ChangeItem.category, func.count())
        .join(Diff, Diff.id == ChangeItem.diff_id)
        .group_by(ChangeItem.category)
    ).all()
    by_category = {category: count for category, count in by_category_rows}

    recent_change_items = db.scalar(
        select(func.count())
        .select_from(ChangeItem)
        .join(Diff, Diff.id == ChangeItem.diff_id)
        .join(Snapshot, Snapshot.id == Diff.snapshot_after_id)
        .where(Snapshot.fetched_at >= window_start)
    ) or 0

    return {
        "total_competitors": total_competitors,
        "total_tracked_urls": total_tracked_urls,
        "active_tracked_urls": active_tracked_urls,
        "coverage_percent": (
            round(100 * active_tracked_urls / total_tracked_urls, 1) if total_tracked_urls else 0.0
        ),
        "change_items_by_category": {
            "pricing": by_category.get("pricing", 0),
            "product": by_category.get("product", 0),
            "hiring": by_category.get("hiring", 0),
        },
        "recent_change_items_7d": recent_change_items,
        "trend": _signal_trend(db, days=12),
    }


@router.get("/metrics/trend")
def metrics_trend(days: int = 12, db: Session = Depends(get_db)) -> dict:
    if days < 1 or days > 90:
        raise HTTPException(status_code=422, detail="days must be between 1 and 90")
    return {"days": days, "trend": _signal_trend(db, days=days)}


def _signal_trend(db: Session, days: int) -> list[dict]:
    """Per-day count of material changes for the last `days` days, oldest first.

    Diffs carry no timestamp of their own, so material changes are bucketed by
    the fetch time of their after-snapshot.
    """
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).date()

    fetched_at_rows = db.execute(
        select(Snapshot.fetched_at)
        .join(Diff, Diff.snapshot_after_id == Snapshot.id)
        .where(Diff.passed_filter.is_(True))
        .where(Snapshot.fetched_at >= start)
    ).scalars().all()

    counts_by_day = Counter(timestamp.date() for timestamp in fetched_at_rows)
    trend = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        trend.append({"date": day.isoformat(), "material_changes": counts_by_day.get(day, 0)})
    return trend
