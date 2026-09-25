import itertools
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./metrics_test.db")

from app.db import Base, engine, SessionLocal
from app.main import app
from app.models import ChangeItem, Competitor, Diff, Snapshot, TrackedUrl

_seed_counter = itertools.count(1)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        test_client = TestClient(app)
        from tests.auth_helpers import ensure_authenticated

        ensure_authenticated(test_client)
        yield test_client, db
    Base.metadata.drop_all(bind=engine)


def _seed(db, *, fetched_at, category="pricing", passed=True):
    competitor = Competitor(name="Acme", domain=f"acme-{next(_seed_counter)}.com")
    db.add(competitor)
    db.flush()
    tracked = TrackedUrl(competitor_id=competitor.id, url="https://acme.com/pricing", page_type="pricing")
    db.add(tracked)
    db.flush()
    snapshot = Snapshot(tracked_url_id=tracked.id, fetched_at=fetched_at, text_content="text")
    db.add(snapshot)
    db.flush()
    diff = Diff(tracked_url_id=tracked.id, snapshot_after_id=snapshot.id, passed_filter=passed, stage1_score=1.0 if passed else 0.0)
    db.add(diff)
    db.flush()
    db.add(ChangeItem(diff_id=diff.id, category=category, summary="s", confidence=0.9))
    db.commit()


def test_metrics_overview_counts(client):
    client, db = client
    now = datetime.now(timezone.utc)
    _seed(db, fetched_at=now, category="pricing")
    _seed(db, fetched_at=now, category="product")
    _seed(db, fetched_at=now - timedelta(days=2), category="hiring", passed=False)

    response = client.get("/metrics/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_competitors"] == 3
    assert payload["total_tracked_urls"] == 3
    assert payload["coverage_percent"] == 100.0
    assert payload["change_items_by_category"] == {"pricing": 1, "product": 1, "hiring": 1}
    assert payload["recent_change_items_7d"] == 3
    assert len(payload["trend"]) == 12


def test_metrics_trend_counts_material_changes_per_day(client):
    client, db = client
    now = datetime.now(timezone.utc)
    _seed(db, fetched_at=now - timedelta(days=1), category="pricing")
    _seed(db, fetched_at=now - timedelta(days=1), category="pricing")
    _seed(db, fetched_at=now - timedelta(days=3), category="product", passed=False)

    response = client.get("/metrics/trend?days=7")
    assert response.status_code == 200
    trend = response.json()["trend"]
    assert len(trend) == 7
    by_date = {entry["date"]: entry["material_changes"] for entry in trend}
    assert by_date[(now - timedelta(days=1)).date().isoformat()] == 2
    assert sum(entry["material_changes"] for entry in trend) == 2  # failed filter excluded


def test_metrics_trend_rejects_invalid_days(client):
    client, _ = client
    assert client.get("/metrics/trend?days=0").status_code == 422
    assert client.get("/metrics/trend?days=91").status_code == 422


def test_metrics_empty_database(client):
    client, _ = client
    response = client.get("/metrics/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_competitors"] == 0
    assert payload["coverage_percent"] == 0.0
    assert payload["change_items_by_category"] == {"pricing": 0, "product": 0, "hiring": 0}
    assert all(entry["material_changes"] == 0 for entry in payload["trend"])
