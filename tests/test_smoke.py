from app.services.diffing import has_material_change
from app.services.discovery import discover_urls
from app.workers.pipeline import run_pipeline


def test_discovery_returns_candidate_urls():
    candidates = discover_urls("example.com")
    assert candidates
    assert any(item["page_type"] == "pricing" for item in candidates)


def test_material_change_detects_real_differences():
    assert has_material_change("$19/month", "$29/month") is True


def test_pipeline_returns_summary_payload():
    payload = run_pipeline("example.com", "old pricing", "new pricing")
    assert payload["competitor_domain"] == "example.com"
    assert isinstance(payload["candidate_urls"], list)
    assert "material_change" in payload


def test_process_page_change_detects_pricing_shift():
    from app.workers.pipeline import process_page_change

    payload = process_page_change(
        "example.com",
        "https://example.com/pricing",
        "Basic plan $19/month",
        "Basic plan $29/month",
    )

    assert payload["material_change"] is True
    assert payload["page_type"] == "pricing"
    assert payload["confidence"] >= 0.5
