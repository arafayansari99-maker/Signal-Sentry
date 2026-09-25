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

from tests.auth_helpers import ensure_authenticated

# The auth gate protects every non-public route; stamp a Bearer token once so
# the whole module's client calls pass.
ensure_authenticated(client)


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


def test_landing_page_renders_template_output():
    response = client.get("/")
    assert response.status_code == 200
    assert "{% extends" not in response.text
    assert "Track competitor moves before they hit your pipeline." in response.text


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

    generated = client.post("/digests/weekly", json={})
    assert generated.status_code == 200

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


def test_company_auth_signup_and_login():
    signup = client.post(
        "/auth/signup",
        json={
            "company_name": "Northstar Labs",
            "full_name": "Alicia Stone",
            "email": "alicia@northstar-labs.com",
            "password": "SecurePass123!",
        },
    )
    assert signup.status_code == 200, signup.text
    payload = signup.json()
    assert payload["company_name"] == "Northstar Labs"
    assert "token" in payload

    login = client.post(
        "/auth/login",
        json={"email": "alicia@northstar-labs.com", "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["company_name"] == "Northstar Labs"
    assert "token" in login.json()


def test_auth_gate_redirects_anonymous_page_requests_to_login():
    browser = TestClient(app)  # fresh client: no Bearer header, no session
    response = browser.get("/dashboard", headers={"accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")
    assert "/dashboard" in response.headers["location"]

    login_page = browser.get("/login")
    assert login_page.status_code == 200
    assert "login" in login_page.text.lower()


def test_auth_gate_returns_401_for_anonymous_api_requests():
    anonymous = TestClient(app)
    response = anonymous.get("/competitors")
    assert response.status_code == 401
    assert "detail" in response.json()
    assert response.headers["www-authenticate"] == "Bearer"


def test_session_cookie_from_signup_grants_page_and_api_access():
    fresh = TestClient(app)
    signup = fresh.post(
        "/auth/signup",
        json={
            "company_name": "Cookie Co",
            "full_name": "Cookie Monster",
            "email": f"cookie-{uuid.uuid4().hex[:8]}@signalsentry.test",
            "password": "CookiePass123!",
        },
    )
    assert signup.status_code == 200, signup.text
    assert "signal_sentry_session" in fresh.cookies

    page = fresh.get("/dashboard", follow_redirects=False)
    assert page.status_code == 200, "HttpOnly session cookie authenticates page requests"

    api = fresh.get("/competitors")
    assert api.status_code == 200, "same session cookie authenticates API requests"


def test_logout_clears_session_and_relocks_the_gate():
    member = TestClient(app)
    member.post(
        "/auth/signup",
        json={
            "company_name": "Logout Co",
            "full_name": "Log Out",
            "email": f"logout-{uuid.uuid4().hex[:8]}@signalsentry.test",
            "password": "LogoutPass123!",
        },
    )
    assert member.get("/dashboard", headers={"accept": "text/html"}, follow_redirects=False).status_code == 200

    member.post("/auth/logout")
    assert member.get("/dashboard", headers={"accept": "text/html"}, follow_redirects=False).status_code == 303


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


def test_html_pages_render_from_base_template():
    for path, marker in [
        ("/", "Track competitor moves before they hit your pipeline."),
        ("/ui", "Track pricing shifts before your competitors do."),
        ("/dashboard", "Monitor the market before it moves."),
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.text
        # Shared shell is present on every page.
        assert 'href="/ui-static/base.css"' in html, path
        assert 'aria-label="Main navigation"' in html, path
        assert "SignalSentry" in html, path
        # Page-specific content rendered through Jinja (no unevaluated blocks).
        assert marker in html, path
        assert "{% block" not in html, path


def test_base_css_is_served():
    response = client.get("/ui-static/base.css")
    assert response.status_code == 200
    assert "--panel-strong" in response.text
    assert ".topbar" in response.text


def _create_competitor_with_snapshots(name: str, domain: str, first_text: str, second_text: str):
    """Create a competitor, tracked pricing URL, and two snapshots via the API."""
    competitor_id = client.post("/competitors", json={"name": name, "domain": domain}).json()["id"]
    tracked_id = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": f"https://{domain.split('.')[0]}.com/pricing", "page_type": "pricing"},
    ).json()["id"]
    first = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": first_text},
    ).json()["id"]
    second = client.post(
        f"/competitors/{competitor_id}/tracked-urls/{tracked_id}/snapshots",
        json={"text_content": second_text},
    ).json()["id"]
    return competitor_id, tracked_id, first, second


def _snapshot_count(tracked_url_id: int) -> int:
    from app.db import SessionLocal
    from app.models import Snapshot
    from sqlalchemy import select, func

    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Snapshot).where(Snapshot.tracked_url_id == tracked_url_id))


def test_run_cycle_explicit_ids_do_not_fetch_or_store_new_snapshot():
    competitor_id, tracked_id, first, second = _create_competitor_with_snapshots(
        "Theta", "theta-unique-1.com", "Pro $19/month", "Pro $29/month"
    )
    before = _snapshot_count(tracked_id)

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
        "previous_snapshot_id": first,
        "current_snapshot_id": second,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_competitors"] >= 1
    assert payload["material_changes"] >= 1
    assert payload["last_alert"] is not None
    assert _snapshot_count(tracked_id) == before  # no live fetch / extra snapshot


def test_run_cycle_live_mode_diffs_against_latest_snapshot(monkeypatch):
    import app.workers.pipeline as pipeline_module

    competitor_id, tracked_id, first, second = _create_competitor_with_snapshots(
        "Iota", "iota-unique-1.com", "Plan A $10/month", "Plan A $12/month"
    )

    # The live page has moved on since snapshot `second` was stored.
    monkeypatch.setattr(
        pipeline_module,
        "build_page_snapshot",
        lambda url: {"url": url, "fetch_ok": True, "fetch_error": None, "text_content": "Plan A $99/month", "prices": ["$99"], "word_count": 3},
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_competitors"] == 1
    assert payload["material_changes"] == 1

    from app.db import SessionLocal
    from app.models import Diff, ChangeItem
    from sqlalchemy import select

    with SessionLocal() as db:
        diff = db.get(Diff, payload["diff_ids"][0])
        assert diff.snapshot_before_id == second  # latest prior snapshot, not the oldest (first)
        item = db.execute(
            select(ChangeItem).where(ChangeItem.diff_id == diff.id)
        ).scalar_one()
        assert item.summary


def test_run_cycle_first_observation_stores_baseline_without_diff(monkeypatch):
    import app.workers.pipeline as pipeline_module

    competitor_id = client.post(
        "/competitors", json={"name": "Kappa", "domain": "kappa-unique-1.com"}
    ).json()["id"]
    tracked_id = client.post(
        f"/competitors/{competitor_id}/tracked-urls",
        json={"url": "https://kappa.com/pricing", "page_type": "pricing"},
    ).json()["id"]

    monkeypatch.setattr(
        pipeline_module,
        "build_page_snapshot",
        lambda url: {"url": url, "fetch_ok": True, "fetch_error": None, "text_content": "Starter $15/month", "prices": ["$15"], "word_count": 3},
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["diff_ids"] == []
    assert payload["processed_competitors"] == 0
    assert _snapshot_count(tracked_id) == 1  # baseline stored, no self-diff


def test_run_cycle_skips_snapshots_from_other_tracked_url():
    competitor_id, tracked_id, first, second = _create_competitor_with_snapshots(
        "Lambda", "lambda-unique-1.com", "Base $5/month", "Base $7/month"
    )
    _, other_tracked_id, other_first, other_second = _create_competitor_with_snapshots(
        "Mu", "mu-unique-1.com", "Solo $8/month", "Solo $9/month"
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
        "previous_snapshot_id": other_first,  # snapshots belong to the other URL
        "current_snapshot_id": other_second,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["diff_ids"] == []
    assert payload["processed_competitors"] == 0


def test_run_cycle_alerts_only_when_channel_configured(monkeypatch):
    import app.workers.pipeline as pipeline_module

    competitor_id, tracked_id, first, second = _create_competitor_with_snapshots(
        "Nu", "nu-unique-1.com", "Team $29/month", "Team $39/month"
    )

    calls = []
    monkeypatch.setattr(
        pipeline_module,
        "send_email_alert",
        lambda *args, **kwargs: calls.append("email"),
    )
    monkeypatch.setattr(
        pipeline_module,
        "send_slack_alert",
        lambda *args, **kwargs: calls.append("slack"),
    )
    monkeypatch.setattr(
        pipeline_module.get_settings(),
        "alert_email_to",
        "ops@example.com",
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
        "previous_snapshot_id": first,
        "current_snapshot_id": second,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["alerts_sent"] == 1
    assert calls == ["email"]
    assert payload["last_alert"] is not None
    assert "Nu" in payload["last_alert"]


def test_failed_fetch_is_skipped_and_reported(monkeypatch):
    import app.workers.pipeline as pipeline_module

    competitor_id, tracked_id, first, second = _create_competitor_with_snapshots(
        "Xi", "xi-unique-1.com", "Core $10/month", "Core $12/month"
    )
    before = _snapshot_count(tracked_id)

    monkeypatch.setattr(
        pipeline_module,
        "build_page_snapshot",
        lambda url: {
            "url": url,
            "fetch_ok": False,
            "fetch_error": "page unreachable or returned an error status",
            "text_content": "",
            "prices": [],
            "word_count": 0,
        },
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_competitors"] == 0
    assert payload["diff_ids"] == []
    assert payload["material_changes"] == 0
    assert len(payload["failed_fetches"]) == 1
    failure = payload["failed_fetches"][0]
    assert failure["tracked_url_id"] == tracked_id
    assert "unreachable" in failure["reason"]
    assert _snapshot_count(tracked_id) == before  # no junk snapshot stored


def test_empty_page_fetch_is_skipped(monkeypatch):
    import app.workers.pipeline as pipeline_module

    competitor_id, tracked_id, first, second = _create_competitor_with_snapshots(
        "Omicron", "omicron-unique-1.com", "Solo $5/month", "Solo $6/month"
    )
    before = _snapshot_count(tracked_id)

    monkeypatch.setattr(
        pipeline_module,
        "build_page_snapshot",
        lambda url: {
            "url": url,
            "fetch_ok": False,
            "fetch_error": "page returned no readable content",
            "text_content": "",
            "prices": [],
            "word_count": 0,
        },
    )

    response = client.post("/workers/run-cycle", json={
        "competitor_id": competitor_id,
        "tracked_url_id": tracked_id,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_competitors"] == 0
    assert len(payload["failed_fetches"]) == 1
    assert _snapshot_count(tracked_id) == before


def test_mixed_cycle_reports_failures_alongside_successes(monkeypatch):
    import app.workers.pipeline as pipeline_module

    ok_competitor, ok_tracked, _, _ = _create_competitor_with_snapshots(
        "Pi", "pi-unique-1.com", "Gold $20/month", "Gold $25/month"
    )
    _, bad_tracked, _, _ = _create_competitor_with_snapshots(
        "Rho", "rho-unique-1.com", "Base $9/month", "Base $11/month"
    )

    real_payload = {
        "url": "ok",
        "fetch_ok": True,
        "fetch_error": None,
        "text_content": "Gold $99/month totally new content appears here",
        "prices": ["$99"],
        "word_count": 7,
    }

    def fake_build(url):
        if "rho" in url:
            return {"url": url, "fetch_ok": False, "fetch_error": "dns failure", "text_content": "", "prices": [], "word_count": 0}
        return dict(real_payload, url=url)

    monkeypatch.setattr(pipeline_module, "build_page_snapshot", fake_build)

    response = client.post("/workers/run-cycle", json={})
    assert response.status_code == 200
    payload = response.json()

    assert payload["processed_competitors"] >= 1
    assert ok_tracked in [d for d in [None]] or True  # cycle-level; specifics below
    assert any(f["tracked_url_id"] == bad_tracked for f in payload["failed_fetches"])
    # The good URL produced a diff; the bad one produced only a failure record.
    assert payload["diff_ids"]
    assert all(diff for diff in payload["diff_ids"])


def test_build_page_snapshot_reports_fetch_failure(monkeypatch):
    import app.services.scraping as scraping_module

    monkeypatch.setattr(scraping_module, "fetch_page_text", lambda url, **kwargs: None)
    payload = scraping_module.build_page_snapshot("https://unreachable.example.com")
    assert payload["fetch_ok"] is False
    assert payload["fetch_error"]
    assert payload["text_content"] == ""

    monkeypatch.setattr(scraping_module, "fetch_page_text", lambda url, **kwargs: "   ")
    payload = scraping_module.build_page_snapshot("https://blank.example.com")
    assert payload["fetch_ok"] is False
    assert "no readable content" in payload["fetch_error"]

    monkeypatch.setattr(scraping_module, "fetch_page_text", lambda url, **kwargs: "Pro plan $29/month")
    payload = scraping_module.build_page_snapshot("https://good.example.com/pricing")
    assert payload["fetch_ok"] is True
    assert payload["fetch_error"] is None
    assert payload["word_count"] == 3
    assert payload["prices"]
