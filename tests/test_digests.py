import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./digests_test.db")

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import ChangeItem, Competitor, Digest, DigestItem, Diff, Snapshot, TrackedUrl
from app.services.digests import DIGEST_MAX_ITEMS


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        yield TestClient(app), db
    Base.metadata.drop_all(bind=engine)


_counter = {"n": 0}


def _seed_change_item(db, *, category="pricing", magnitude="major", confidence=0.9, summary="Price moved") -> ChangeItem:
    _counter["n"] += 1
    n = _counter["n"]
    competitor = Competitor(name=f"Comp{n}", domain=f"comp-{n}.com")
    db.add(competitor)
    db.flush()
    tracked = TrackedUrl(competitor_id=competitor.id, url=f"https://comp-{n}.com/pricing", page_type="pricing")
    db.add(tracked)
    db.flush()
    snapshot = Snapshot(tracked_url_id=tracked.id, fetched_at=datetime.now(timezone.utc), text_content="text")
    db.add(snapshot)
    db.flush()
    diff = Diff(tracked_url_id=tracked.id, snapshot_after_id=snapshot.id, passed_filter=True, stage1_score=1.0)
    db.add(diff)
    db.flush()
    change_item = ChangeItem(
        diff_id=diff.id,
        category=category,
        magnitude=magnitude,
        summary=summary,
        confidence=confidence,
        status="pending",
    )
    db.add(change_item)
    db.commit()
    db.refresh(change_item)
    return change_item


def test_post_weekly_digest_persists_digest_and_items(client):
    client, db = client
    high = _seed_change_item(db, confidence=0.95, magnitude="major", summary="Cut Pro pricing")
    low = _seed_change_item(db, confidence=0.60, magnitude="minor", summary="Tweaked copy")

    response = client.post("/digests/weekly", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["digest_id"] > 0
    assert payload["item_count"] == 2
    assert payload["items"][0]["change_item_id"] == high.id  # major + higher confidence ranks first
    assert payload["items"][1]["change_item_id"] == low.id

    with SessionLocal() as check:
        digest = check.get(Digest, payload["digest_id"])
        assert digest is not None
        stored = check.query(DigestItem).filter(DigestItem.digest_id == digest.id).all()
        assert len(stored) == 2
        statuses = {ci.id: ci.status for ci in check.query(ChangeItem).all()}
        assert statuses[high.id] == "shown"
        assert statuses[low.id] == "shown"


def test_second_digest_excludes_already_sent_items(client):
    client, db = client
    _seed_change_item(db, summary="First week change")
    client.post("/digests/weekly", json={})

    fresh = _seed_change_item(db, summary="Second week change")
    second = client.post("/digests/weekly", json={})
    assert second.status_code == 200
    items = second.json()["items"]
    assert [item["change_item_id"] for item in items] == [fresh.id]


def test_dismissed_items_are_excluded_from_digest(client):
    client, db = client
    dismissed = _seed_change_item(db, summary="Not relevant change")
    client.post(f"/change-items/{dismissed.id}/feedback", json={"label": "not_relevant"})

    response = client.post("/digests/weekly", json={})
    assert response.status_code == 200
    assert response.json()["item_count"] == 0


def test_digest_caps_items_at_hard_limit(client):
    client, db = client
    for i in range(DIGEST_MAX_ITEMS + 5):
        _seed_change_item(db, confidence=0.5 + i / 100, summary=f"Change {i}")

    response = client.post("/digests/weekly", json={})
    payload = response.json()
    assert payload["item_count"] == DIGEST_MAX_ITEMS
    assert payload["minor_changes_overflow"] == 5


def test_old_change_items_are_outside_the_weekly_window(client):
    client, db = client
    item = _seed_change_item(db, summary="Ancient change")
    diff = item.diff
    snapshot = db.get(Snapshot, diff.snapshot_after_id)
    snapshot.fetched_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()

    response = client.post("/digests/weekly", json={})
    assert response.status_code == 200
    assert response.json()["item_count"] == 0


def test_feedback_endpoint_validates_label_and_updates_status(client):
    client, db = client
    item = _seed_change_item(db, summary="Feedback target")

    bad = client.post(f"/change-items/{item.id}/feedback", json={"label": "meh"})
    assert bad.status_code == 422

    missing = client.post("/change-items/99999/feedback", json={"label": "relevant"})
    assert missing.status_code == 404

    not_relevant = client.post(
        f"/change-items/{item.id}/feedback",
        json={"label": "not_relevant", "user_id": "priya"},
    )
    assert not_relevant.status_code == 200
    body = not_relevant.json()
    assert body["label"] == "not_relevant"
    assert body["change_item_status"] == "dismissed"

    listing = client.get(f"/change-items/{item.id}/feedback")
    assert listing.status_code == 200
    feedback_rows = listing.json()["feedback"]
    assert len(feedback_rows) == 1
    assert feedback_rows[0]["user_id"] == "priya"
    assert listing.json()["change_item_status"] == "dismissed"


def test_evidence_view_returns_before_and_after_snapshots(client):
    client, db = client
    from datetime import datetime, timezone

    competitor = Competitor(name="Evidence Co", domain="evidence-co.com")
    db.add(competitor)
    db.flush()
    tracked = TrackedUrl(competitor_id=competitor.id, url="https://evidence-co.com/pricing", page_type="pricing")
    db.add(tracked)
    db.flush()
    before = Snapshot(
        tracked_url_id=tracked.id,
        fetched_at=datetime.now(timezone.utc),
        text_content="Pro plan $49/month with priority support",
        screenshot_url="https://img.example.com/before.png",
    )
    after = Snapshot(
        tracked_url_id=tracked.id,
        fetched_at=datetime.now(timezone.utc),
        text_content="Pro plan $39/month with priority support and SSO",
        screenshot_url="https://img.example.com/after.png",
    )
    db.add_all([before, after])
    db.flush()
    diff = Diff(
        tracked_url_id=tracked.id,
        snapshot_before_id=before.id,
        snapshot_after_id=after.id,
        passed_filter=True,
        stage1_score=1.0,
    )
    db.add(diff)
    db.flush()
    item = ChangeItem(
        diff_id=diff.id,
        category="pricing",
        magnitude="major",
        summary="Pro price cut from 49 to 39",
        why_it_matters="Undercuts our entry tier",
        confidence=0.95,
        status="shown",
    )
    db.add(item)
    db.commit()

    response = client.get(f"/change-items/{item.id}/evidence")
    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"] == "Pro price cut from 49 to 39"
    assert payload["why_it_matters"] == "Undercuts our entry tier"
    assert payload["competitor"]["name"] == "Evidence Co"
    assert payload["tracked_url"]["url"] == "https://evidence-co.com/pricing"
    assert payload["diff"]["material_change"] is True
    assert payload["before"]["snapshot_id"] == before.id
    assert "$49/month" in payload["before"]["text_content"]
    assert payload["before"]["screenshot_url"] == "https://img.example.com/before.png"
    assert payload["after"]["snapshot_id"] == after.id
    assert "$39/month" in payload["after"]["text_content"]
    # Changed tokens include the real diff vocabulary from both sides.
    assert "$39/month" in payload["diff"]["changed_tokens"]
    assert "sso" in payload["diff"]["changed_tokens"]


def test_evidence_view_handles_missing_before_snapshot(client):
    client, db = client
    from datetime import datetime, timezone

    competitor = Competitor(name="Baseline Co", domain="baseline-co.com")
    db.add(competitor)
    db.flush()
    tracked = TrackedUrl(competitor_id=competitor.id, url="https://baseline-co.com/pricing", page_type="pricing")
    db.add(tracked)
    db.flush()
    only = Snapshot(tracked_url_id=tracked.id, fetched_at=datetime.now(timezone.utc), text_content="First look")
    db.add(only)
    db.flush()
    diff = Diff(tracked_url_id=tracked.id, snapshot_before_id=None, snapshot_after_id=only.id, passed_filter=False)
    db.add(diff)
    db.flush()
    item = ChangeItem(diff_id=diff.id, category="product", summary="Baseline stored", confidence=0.0)
    db.add(item)
    db.commit()

    response = client.get(f"/change-items/{item.id}/evidence")
    assert response.status_code == 200
    payload = response.json()
    assert payload["before"] is None  # first observation: no baseline exists
    assert payload["after"]["snapshot_id"] == only.id
    assert payload["after"]["text_content"] == "First look"


def test_evidence_view_404_for_unknown_change_item(client):
    client, _ = client
    assert client.get("/change-items/999999/evidence").status_code == 404


def test_relevant_feedback_keeps_item_pending(client):
    client, db = client
    item = _seed_change_item(db)

    response = client.post(f"/change-items/{item.id}/feedback", json={"label": "relevant"})
    assert response.status_code == 200
    assert response.json()["change_item_status"] == "pending"

    # A pending, relevant item still surfaces in the digest.
    digest = client.post("/digests/weekly", json={})
    assert [i["change_item_id"] for i in digest.json()["items"]] == [item.id]


def test_get_weekly_digest_returns_most_recent(client):
    client, db = client
    # No change items yet: no empty digest row is created.
    first = client.post("/digests/weekly", json={})
    assert first.status_code == 200
    assert first.json()["digest_id"] is None

    second_item = _seed_change_item(db, summary="Newer change")
    second = client.post("/digests/weekly", json={})
    assert second.json()["digest_id"] is not None

    latest = client.get("/digests/weekly")
    assert latest.status_code == 200
    payload = latest.json()
    assert [i["change_item_id"] for i in payload["digest_items"]] == [second_item.id]
    assert payload["digest_id"] == second.json()["digest_id"]

    listing = client.get("/digests")
    assert listing.status_code == 200
    assert len(listing.json()["digests"]) == 1  # empty-digest POST created no row

    empty = client.get("/digests/weekly")
    assert empty.status_code == 200  # digests exist, so latest is returned


def test_get_weekly_digest_404_before_any_digest(client):
    client, _ = client
    assert client.get("/digests/weekly").status_code == 404
