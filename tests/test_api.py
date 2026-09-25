import os
import tempfile
import uuid

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"cia_test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from fastapi.testclient import TestClient

from app.main import app
from app.services.notifications import compose_alert_message
from app.services.scraping import fetch_page_text

client = TestClient(app)


def test_scraper_and_alert_helpers():
    text = fetch_page_text(
        "https://example.com",
        html_override="<html><body><h1>Acme plans</h1><p>Starter $29/month</p></body></html>",
    )
    assert "Acme plans" in text
    assert "Starter $29/month" in text

    message = compose_alert_message("Acme", "pricing", "Starter plan increased to $29/month")
    assert "Acme" in message
    assert "pricing" in message.lower()


def test_create_competitor():
    response = client.post(
        "/competitors",
        json={"name": "Acme", "domain": "acme-unique-2.com"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Acme"
    assert payload["domain"] == "acme-unique-2.com"


def test_list_competitors():
    response = client.get("/competitors")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_discovery_endpoint():
    response = client.post(
        "/competitors/discover",
        json={"domain": "acme-unique-discover.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "acme-unique-discover.com"
    assert isinstance(data["candidates"], list)
    assert any(item["page_type"] == "pricing" for item in data["candidates"])


def test_create_tracked_url_and_snapshot():
    competitor_response = client.post(
        "/competitors",
        json={"name": "Beta", "domain": "beta-unique-1.com"},
    )
    competitor_id = competitor_response.json()["id"]

    tracked = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": "https://beta.com/pricing", "page_type": "pricing"},
    )
    assert tracked.status_code == 200
    tracked_id = tracked.json()["id"]

    snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Basic plan $19/month", "screenshot_url": "https://example.com/snap.png"},
    )
    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["text_content"] == "Basic plan $19/month"
    assert payload["tracked_url_id"] == tracked_id


def test_diff_and_change_item_from_snapshots():
    competitor_response = client.post(
        "/competitors",
        json={"name": "Gamma", "domain": "gamma-unique-1.com"},
    )
    competitor_id = competitor_response.json()["id"]

    tracked = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": "https://gamma.com/pricing", "page_type": "pricing"},
    )
    tracked_id = tracked.json()["id"]

    first_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Basic plan $19/month", "screenshot_url": "https://example.com/snap1.png"},
    )
    second_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Basic plan $29/month", "screenshot_url": "https://example.com/snap2.png"},
    )

    diff_response = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/diffs",
        json={
            "previous_snapshot_id": first_snapshot.json()["id"],
            "current_snapshot_id": second_snapshot.json()["id"],
        },
    )
    assert diff_response.status_code == 200
    diff_payload = diff_response.json()
    assert diff_payload["material_change"] is True
    assert diff_payload["category"] == "pricing"
    assert diff_payload["summary"]


def test_digest_generation_groups_by_competitor_and_category():
    competitor_response = client.post(
        "/competitors",
        json={"name": "Delta", "domain": "delta-unique-1.com"},
    )
    competitor_id = competitor_response.json()["id"]

    tracked = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": "https://delta.com/pricing", "page_type": "pricing"},
    )
    tracked_id = tracked.json()["id"]

    first_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Basic plan $19/month", "screenshot_url": "https://example.com/delta-snap1.png"},
    )
    second_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Basic plan $29/month", "screenshot_url": "https://example.com/delta-snap2.png"},
    )

    client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/diffs",
        json={
            "previous_snapshot_id": first_snapshot.json()["id"],
            "current_snapshot_id": second_snapshot.json()["id"],
        },
    )

    response = client.get(f"/competitors/{competitor_id}/digest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["competitor_name"] == "Delta"
    assert payload["highlights"]
    assert any(item["category"] == "pricing" for item in payload["highlights"])


def test_weekly_digest_and_urgent_pricing_path():
    competitor_response = client.post(
        "/competitors",
        json={"name": "Epsilon", "domain": "epsilon-unique-1.com"},
    )
    competitor_id = competitor_response.json()["id"]

    tracked = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": "https://epsilon.com/pricing", "page_type": "pricing"},
    )
    tracked_id = tracked.json()["id"]

    first_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Starter $19/month", "screenshot_url": "https://example.com/eps-snap1.png"},
    )
    second_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Starter $29/month", "screenshot_url": "https://example.com/eps-snap2.png"},
    )

    client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/diffs",
        json={
            "previous_snapshot_id": first_snapshot.json()["id"],
            "current_snapshot_id": second_snapshot.json()["id"],
        },
    )

    weekly = client.get("/digests/weekly")
    assert weekly.status_code == 200
    weekly_payload = weekly.json()
    assert weekly_payload["summary"]
    assert any(item["competitor_name"] == "Epsilon" for item in weekly_payload["digest_items"])

    urgent = client.get(f"/competitors/{competitor_id}/urgent-pricing")
    assert urgent.status_code == 200
    urgent_payload = urgent.json()
    assert urgent_payload["urgent"] is True
    assert urgent_payload["category"] == "pricing"


def test_monitoring_cycle_runs_for_all_competitors():
    competitor_response = client.post(
        "/competitors",
        json={"name": "Zeta", "domain": "zeta-unique-1.com"},
    )
    competitor_id = competitor_response.json()["id"]

    tracked = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": "https://zeta.com/pricing", "page_type": "pricing"},
    )
    tracked_id = tracked.json()["id"]

    first_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Gold $39/month", "screenshot_url": "https://example.com/zeta-snap1.png"},
    )
    second_snapshot = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": "Gold $49/month", "screenshot_url": "https://example.com/zeta-snap2.png"},
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
        "previous_snapshot_id": first_snapshot.json()["id"],
        "current_snapshot_id": second_snapshot.json()["id"],
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_competitors"] >= 1
    assert payload["material_changes"] >= 1


def test_queue_monitor_status_payload():
    response = client.get("/workers/queue-status")
    assert response.status_code == 200
    payload = response.json()
    assert "available" in payload
    assert "queued" in payload
    assert "started" in payload
    assert "failed" in payload
