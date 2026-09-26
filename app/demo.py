from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

DEMO_COMPETITORS: list[dict] = [
    {
        "id": 1,
        "name": "Nimbus Analytics",
        "domain": "nimbus-analytics.demo",
        "status": "active",
        "crawl_cadence": "daily",
        "created_at": datetime(2026, 1, 8, tzinfo=timezone.utc),
    },
    {
        "id": 2,
        "name": "Vector Metrics",
        "domain": "vector-metrics.demo",
        "status": "active",
        "crawl_cadence": "daily",
        "created_at": datetime(2026, 1, 12, tzinfo=timezone.utc),
    },
    {
        "id": 3,
        "name": "Harbor Cloud",
        "domain": "harbor-cloud.demo",
        "status": "active",
        "crawl_cadence": "weekly",
        "created_at": datetime(2026, 1, 16, tzinfo=timezone.utc),
    },
    {
        "id": 4,
        "name": "Quiet Loop",
        "domain": "quiet-loop.demo",
        "status": "active",
        "crawl_cadence": "weekly",
        "created_at": datetime(2026, 1, 20, tzinfo=timezone.utc),
    },
]

DEMO_TRACKED_URLS: list[dict] = [
    {"id": 1, "competitor_id": 1, "url": "https://nimbus-analytics.demo/pricing", "page_type": "pricing", "exclude": False},
    {"id": 2, "competitor_id": 2, "url": "https://vector-metrics.demo/product", "page_type": "product", "exclude": False},
    {"id": 3, "competitor_id": 3, "url": "https://harbor-cloud.demo/pricing", "page_type": "pricing", "exclude": False},
]

DEMO_DIGEST_ITEMS: list[dict] = [
    {
        "rank": 1,
        "change_item_id": 101,
        "competitor_name": "Nimbus Analytics",
        "url": "https://nimbus-analytics.demo/pricing",
        "category": "pricing",
        "magnitude": "major",
        "summary": "Nimbus Analytics cut the Team plan from $49 to $39 as a limited offer.",
        "confidence": 0.94,
    },
    {
        "rank": 2,
        "change_item_id": 102,
        "competitor_name": "Harbor Cloud",
        "url": "https://harbor-cloud.demo/pricing",
        "category": "pricing",
        "magnitude": "major",
        "summary": "Harbor Cloud raised the Plus plan from $35 to $45/month and added a paid compliance add-on.",
        "confidence": 0.91,
    },
    {
        "rank": 3,
        "change_item_id": 103,
        "competitor_name": "Vector Metrics",
        "url": "https://vector-metrics.demo/product",
        "category": "product",
        "magnitude": "minor",
        "summary": "Vector Metrics added AI-generated weekly summaries to its product page.",
        "confidence": 0.86,
    },
    {
        "rank": 4,
        "change_item_id": 104,
        "competitor_name": "Quiet Loop",
        "url": "https://quiet-loop.demo/careers",
        "category": "hiring",
        "magnitude": "minor",
        "summary": "Quiet Loop listed new roles focused on enterprise security and compliance.",
        "confidence": 0.79,
    },
]


def demo_metrics(days: int = 12) -> dict:
    today = date.today()
    counts = [0, 1, 0, 2, 1, 0, 2, 0, 1, 1, 0, 1]
    trend = [
        {
            "date": (today - timedelta(days=days - offset - 1)).isoformat(),
            "material_changes": counts[-days + offset] if days <= len(counts) else 0,
        }
        for offset in range(days)
    ]
    return {
        "total_competitors": len(DEMO_COMPETITORS),
        "total_tracked_urls": len(DEMO_TRACKED_URLS),
        "active_tracked_urls": len(DEMO_TRACKED_URLS),
        "coverage_percent": 100.0,
        "change_items_by_category": {"pricing": 2, "product": 1, "hiring": 1},
        "recent_change_items_7d": 4,
        "trend": trend,
    }


def demo_digest() -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    return {
        "digest_id": 1,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "sent_at": None,
        "summary": f"{len(DEMO_DIGEST_ITEMS)} change items in this demo digest.",
        "digest_items": DEMO_DIGEST_ITEMS,
    }


def demo_evidence(change_item_id: int) -> dict:
    item = next((entry for entry in DEMO_DIGEST_ITEMS if entry["change_item_id"] == change_item_id), None)
    if item is None:
        return {}

    competitor = next((entry for entry in DEMO_COMPETITORS if entry["name"] == item["competitor_name"]), None)
    fetched_at = datetime.now(timezone.utc).isoformat()
    before_text = f"Pricing page: listed plan information for {item['competitor_name']}."
    after_text = item["summary"]
    return {
        "change_item_id": change_item_id,
        "status": "shown",
        "category": item["category"],
        "magnitude": item["magnitude"],
        "summary": item["summary"],
        "why_it_matters": "A sample signal included to demonstrate the evidence review workflow.",
        "confidence": item["confidence"],
        "competitor": {"id": competitor["id"], "name": competitor["name"], "domain": competitor["domain"]},
        "tracked_url": {"id": item["rank"], "url": item["url"], "page_type": item["category"]},
        "diff": {"id": change_item_id, "material_change": True, "stage1_score": item["confidence"], "changed_tokens": [item["summary"]]},
        "before": {"snapshot_id": change_item_id * 2, "fetched_at": fetched_at, "text_content": before_text, "screenshot_url": None},
        "after": {"snapshot_id": change_item_id * 2 + 1, "fetched_at": fetched_at, "text_content": after_text, "screenshot_url": None},
    }
