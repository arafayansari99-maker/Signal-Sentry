import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy import select
from pydantic import BaseModel

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.demo import (
    DEMO_COMPETITORS,
    DEMO_DIGEST_ITEMS,
    DEMO_TRACKED_URLS,
    demo_digest,
    demo_evidence,
    demo_metrics,
)
from app.metrics import router as metrics_router
from app.models import (
    ChangeItem,
    CompanyAccount,
    Competitor,
    Digest,
    DigestItem,
    Diff,
    Feedback,
    Snapshot,
    TrackedUrl,
)
from app.schemas import CompetitorCreate, CompetitorRead, FeedbackCreate
from app.services.digests import generate_weekly_digest
from app.services.diffing import build_change_summary
from app.services.discovery import discover_urls
from app.workers.pipeline import run_monitoring_cycle
from app.workers.scheduler import scheduler_status, start_scheduler, stop_scheduler
from app.queue import enqueue_monitoring_cycle, get_queue_status

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
frontend_origin = settings.frontend_url.strip().rstrip("/")
if not frontend_origin:
    frontend_origin = next(
        (
            origin.strip().rstrip("/")
            for origin in settings.allowed_origins.split(",")
            if origin.strip().startswith("https://")
        ),
        "",
    )
templates.env.globals["dashboard_url"] = (
    f"{frontend_origin}/dashboard"
    if frontend_origin
    else "/site/dashboard" if os.getenv("VERCEL") else "/dashboard"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    should_start_scheduler = (
        settings.background_queue_enabled
        and not settings.demo_mode
        and not os.getenv("VERCEL")
    )
    if should_start_scheduler:
        start_scheduler()
    try:
        yield
    finally:
        if should_start_scheduler:
            stop_scheduler()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
allowed_origins = [
    origin.strip()
    for origin in settings.allowed_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/ui-static", StaticFiles(directory=BASE_DIR / "static"), name="ui_static")
if settings.demo_mode:
    @app.get("/metrics/overview")
    def demo_metrics_overview() -> dict:
        return demo_metrics()

    @app.get("/metrics/trend")
    def demo_metrics_trend(days: int = 12) -> dict:
        if days < 1 or days > 90:
            raise HTTPException(status_code=422, detail="days must be between 1 and 90")
        return {"days": days, "trend": demo_metrics(days=days)["trend"]}
else:
    app.include_router(metrics_router)
    init_db()


@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request) -> Response:
    if settings.api_only_mode or os.getenv("VERCEL"):
        return JSONResponse(
            {
                "service": settings.app_name,
                "status": "ok",
                "docs": "/docs",
                "health": "/health",
            }
        )
    return templates.TemplateResponse(request=request, name="landing.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> Response:
    if settings.api_only_mode or os.getenv("VERCEL"):
        return JSONResponse({"message": "The dashboard UI is served by the frontend project."})
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})


@app.get("/site/landing", response_class=HTMLResponse)
def site_landing_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="landing.html")


@app.get("/site/dashboard", response_class=HTMLResponse)
def site_dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})


@app.get("/ui", response_class=HTMLResponse)
def ui_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="ui.html")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/api")
def root() -> dict[str, str]:
    return {"message": "Competitive Intelligence Agent is running."}


@app.get("/export/competitors")
def export_competitors() -> JSONResponse:
    payload = list_competitors()
    return JSONResponse(
        content=[item.model_dump(mode="json") for item in payload],
        headers={"Content-Disposition": "attachment; filename=competitors.json"},
        media_type="application/json",
    )


@app.get("/export/digest")
def export_digest() -> JSONResponse:
    if settings.demo_mode:
        return JSONResponse(
            content=demo_digest(),
            headers={"Content-Disposition": "attachment; filename=weekly-digest.json"},
            media_type="application/json",
        )

    try:
        payload = get_weekly_digest()
    except HTTPException:
        payload = {
            "digest_id": None,
            "period_start": None,
            "period_end": None,
            "sent_at": None,
            "summary": "No digest generated yet.",
            "digest_items": [],
        }

    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": "attachment; filename=weekly-digest.json"},
        media_type="application/json",
    )


@app.get("/competitors", response_model=list[CompetitorRead])
def list_competitors() -> list[CompetitorRead]:
    if settings.demo_mode:
        return [CompetitorRead.model_validate(item) for item in DEMO_COMPETITORS]

    with SessionLocal() as db:
        records = db.scalars(select(Competitor).order_by(Competitor.id)).all()
        return [
            CompetitorRead(
                id=record.id,
                name=record.name,
                domain=record.domain,
                status=record.status,
                crawl_cadence=record.crawl_cadence,
                created_at=record.created_at,
            )
            for record in records
        ]


@app.post("/competitors", response_model=CompetitorRead)
def create_competitor(payload: CompetitorCreate) -> CompetitorRead:
    if settings.demo_mode:
        if any(item["domain"] == payload.domain for item in DEMO_COMPETITORS):
            raise HTTPException(status_code=409, detail="Competitor with this domain already exists")
        competitor = {
            "id": max((item["id"] for item in DEMO_COMPETITORS), default=0) + 1,
            **payload.model_dump(),
            "created_at": datetime.now(timezone.utc),
        }
        DEMO_COMPETITORS.append(competitor)
        return CompetitorRead.model_validate(competitor)

    with SessionLocal() as db:
        existing = db.execute(select(Competitor).where(Competitor.domain == payload.domain)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Competitor with this domain already exists")

        competitor = Competitor(
            name=payload.name,
            domain=payload.domain,
            status=payload.status,
            crawl_cadence=payload.crawl_cadence,
            created_at=datetime.now(timezone.utc),
        )
        db.add(competitor)
        db.commit()
        db.refresh(competitor)
        return CompetitorRead(
            id=competitor.id,
            name=competitor.name,
            domain=competitor.domain,
            status=competitor.status,
            crawl_cadence=competitor.crawl_cadence,
            created_at=competitor.created_at,
        )


@app.post("/competitors/discover")
def discover_competitor(domain: str | None = None, payload: dict | None = None) -> dict:
    candidate_source = payload or {}
    requested_domain = domain or candidate_source.get("domain")
    if not requested_domain:
        return {"domain": "", "candidates": []}

    if settings.demo_mode:
        normalized_domain = requested_domain.removeprefix("https://").removeprefix("http://").strip("/")
        return {
            "domain": normalized_domain,
            "candidates": [
                {"url": f"https://{normalized_domain}/pricing", "page_type": "pricing"},
                {"url": f"https://{normalized_domain}/product", "page_type": "product"},
                {"url": f"https://{normalized_domain}/careers", "page_type": "careers"},
            ],
        }

    return {
        "domain": requested_domain,
        "candidates": discover_urls(requested_domain),
    }


@app.post("/competitors/{competitor_id}/tracked-urls")
def create_tracked_url(competitor_id: int, payload: dict) -> dict:
    if settings.demo_mode:
        if not any(item["id"] == competitor_id for item in DEMO_COMPETITORS):
            raise HTTPException(status_code=404, detail="Competitor not found")
        tracked_url = {
            "id": max((item["id"] for item in DEMO_TRACKED_URLS), default=0) + 1,
            "competitor_id": competitor_id,
            "url": payload.get("url"),
            "page_type": payload.get("page_type", "product"),
            "exclude": bool(payload.get("exclude", False)),
        }
        DEMO_TRACKED_URLS.append(tracked_url)
        return tracked_url

    with SessionLocal() as db:
        competitor = db.get(Competitor, competitor_id)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")

        tracked_url = TrackedUrl(
            competitor_id=competitor.id,
            url=payload.get("url"),
            page_type=payload.get("page_type", "product"),
            exclude=bool(payload.get("exclude", False)),
        )
        db.add(tracked_url)
        db.commit()
        db.refresh(tracked_url)
        return {
            "id": tracked_url.id,
            "competitor_id": tracked_url.competitor_id,
            "url": tracked_url.url,
            "page_type": tracked_url.page_type,
            "exclude": tracked_url.exclude,
        }


@app.post("/competitors/{competitor_id}/tracked-urls/{tracked_url_id}/snapshots")
def create_snapshot(competitor_id: int, tracked_url_id: int, payload: dict) -> dict:
    if settings.demo_mode:
        if not any(item["id"] == tracked_url_id and item["competitor_id"] == competitor_id for item in DEMO_TRACKED_URLS):
            raise HTTPException(status_code=404, detail="Tracked URL not found")
        return {
            "id": tracked_url_id,
            "tracked_url_id": tracked_url_id,
            "text_content": payload.get("text_content", "Demo snapshot captured."),
            "screenshot_url": payload.get("screenshot_url"),
            "structured_data": payload.get("structured_data"),
        }

    with SessionLocal() as db:
        competitor = db.get(Competitor, competitor_id)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")

        tracked_url = db.get(TrackedUrl, tracked_url_id)
        if tracked_url is None or tracked_url.competitor_id != competitor_id:
            raise HTTPException(status_code=404, detail="Tracked URL not found")

        snapshot = Snapshot(
            tracked_url_id=tracked_url.id,
            fetched_at=datetime.now(timezone.utc),
            text_content=payload.get("text_content", ""),
            screenshot_url=payload.get("screenshot_url"),
            structured_data=payload.get("structured_data"),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return {
            "id": snapshot.id,
            "tracked_url_id": snapshot.tracked_url_id,
            "text_content": snapshot.text_content,
            "screenshot_url": snapshot.screenshot_url,
            "structured_data": snapshot.structured_data,
        }


@app.post("/competitors/{competitor_id}/tracked-urls/{tracked_url_id}/diffs")
def create_diff(competitor_id: int, tracked_url_id: int, payload: dict) -> dict:
    if settings.demo_mode:
        if not any(item["id"] == tracked_url_id and item["competitor_id"] == competitor_id for item in DEMO_TRACKED_URLS):
            raise HTTPException(status_code=404, detail="Tracked URL not found")
        return {
            "id": tracked_url_id,
            "tracked_url_id": tracked_url_id,
            "category": "product",
            "material_change": False,
            "summary": "Demo mode does not run live comparison jobs.",
            "confidence": 0.0,
            "change_item_id": None,
        }

    with SessionLocal() as db:
        competitor = db.get(Competitor, competitor_id)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")

        tracked_url = db.get(TrackedUrl, tracked_url_id)
        if tracked_url is None or tracked_url.competitor_id != competitor_id:
            raise HTTPException(status_code=404, detail="Tracked URL not found")

        previous_snapshot_id = payload.get("previous_snapshot_id")
        current_snapshot_id = payload.get("current_snapshot_id")
        previous_snapshot = db.get(Snapshot, previous_snapshot_id)
        current_snapshot = db.get(Snapshot, current_snapshot_id)

        if previous_snapshot is None or current_snapshot is None:
            raise HTTPException(status_code=404, detail="Snapshots not found")
        if previous_snapshot.tracked_url_id != tracked_url_id or current_snapshot.tracked_url_id != tracked_url_id:
            raise HTTPException(status_code=400, detail="Snapshots do not belong to this tracked URL")

        summary = build_change_summary(
            previous_snapshot.text_content,
            current_snapshot.text_content,
            tracked_url.url,
        )

        diff = Diff(
            tracked_url_id=tracked_url.id,
            snapshot_before_id=previous_snapshot.id,
            snapshot_after_id=current_snapshot.id,
            stage1_score=1.0 if summary["material_change"] else 0.0,
            passed_filter=summary["material_change"],
        )
        db.add(diff)
        db.commit()
        db.refresh(diff)

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
        db.commit()
        db.refresh(change_item)

        return {
            "id": diff.id,
            "tracked_url_id": diff.tracked_url_id,
            "category": summary["category"],
            "material_change": summary["material_change"],
            "summary": summary["summary"],
            "confidence": summary["confidence"],
            "change_item_id": change_item.id,
        }


@app.get("/competitors/{competitor_id}/digest")
def get_competitor_digest(competitor_id: int) -> dict:
    if settings.demo_mode:
        competitor = next((item for item in DEMO_COMPETITORS if item["id"] == competitor_id), None)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")
        return {
            "competitor_id": competitor_id,
            "competitor_name": competitor["name"],
            "highlights": [
                {"url": item["url"], "category": item["category"], "summary": item["summary"], "confidence": item["confidence"]}
                for item in DEMO_DIGEST_ITEMS
                if item["competitor_name"] == competitor["name"]
            ],
        }

    with SessionLocal() as db:
        competitor = db.get(Competitor, competitor_id)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")

        rows = (
            db.execute(
                select(ChangeItem, TrackedUrl)
                .join(Diff, Diff.id == ChangeItem.diff_id)
                .join(TrackedUrl, TrackedUrl.id == Diff.tracked_url_id)
                .where(TrackedUrl.competitor_id == competitor_id)
                .order_by(ChangeItem.confidence.desc())
            )
            .all()
        )

        highlights = []
        for change_item, tracked_url in rows:
            highlights.append(
                {
                    "url": tracked_url.url,
                    "category": change_item.category,
                    "summary": change_item.summary,
                    "confidence": change_item.confidence,
                }
            )

        return {
            "competitor_id": competitor.id,
            "competitor_name": competitor.name,
            "highlights": highlights,
        }


@app.post("/digests/weekly")
def post_weekly_digest(payload: dict | None = None) -> dict:
    if settings.demo_mode:
        return {
            "digest_id": 1,
            "item_count": len(DEMO_DIGEST_ITEMS),
            "candidate_count": len(DEMO_DIGEST_ITEMS),
            "minor_changes_overflow": 0,
            "delivery": {"status": "skipped", "reason": "Demo mode does not send notifications."},
            "items": DEMO_DIGEST_ITEMS,
        }

    candidate = payload or {}
    send = bool(candidate.get("send", False))
    with SessionLocal() as db:
        return generate_weekly_digest(db, send=send)


@app.get("/digests/weekly")
def get_weekly_digest() -> dict:
    """Return the most recent persisted weekly digest, with items ranked."""
    if settings.demo_mode:
        return demo_digest()

    with SessionLocal() as db:
        digest = db.scalar(select(Digest).order_by(Digest.id.desc()).limit(1))
        if digest is None:
            raise HTTPException(status_code=404, detail="No weekly digest generated yet; POST /digests/weekly first")

        rows = db.execute(
            select(DigestItem, ChangeItem, Competitor, TrackedUrl)
            .join(ChangeItem, ChangeItem.id == DigestItem.change_item_id)
            .join(Diff, Diff.id == ChangeItem.diff_id)
            .join(TrackedUrl, TrackedUrl.id == Diff.tracked_url_id)
            .join(Competitor, Competitor.id == TrackedUrl.competitor_id)
            .where(DigestItem.digest_id == digest.id)
            .order_by(DigestItem.rank.asc())
        ).all()

        digest_items = [
            {
                "rank": digest_item.rank,
                "change_item_id": change_item.id,
                "competitor_name": competitor.name,
                "url": tracked_url.url,
                "category": change_item.category,
                "magnitude": change_item.magnitude,
                "summary": change_item.summary,
                "confidence": change_item.confidence,
            }
            for digest_item, change_item, competitor, tracked_url in rows
        ]

        return {
            "digest_id": digest.id,
            "period_start": digest.period_start.isoformat(),
            "period_end": digest.period_end.isoformat(),
            "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
            "summary": f"{len(digest_items)} change items in this digest.",
            "digest_items": digest_items,
        }


@app.get("/digests")
def list_digests() -> dict:
    if settings.demo_mode:
        digest = demo_digest()
        return {
            "digests": [{
                "id": digest["digest_id"],
                "period_start": digest["period_start"],
                "period_end": digest["period_end"],
                "sent_at": None,
                "channel": "demo",
                "item_count": len(DEMO_DIGEST_ITEMS),
            }]
        }

    with SessionLocal() as db:
        rows = db.execute(
            select(Digest, func.count(DigestItem.id))
            .outerjoin(DigestItem, DigestItem.digest_id == Digest.id)
            .group_by(Digest.id)
            .order_by(Digest.id.desc())
        ).all()
        return {
            "digests": [
                {
                    "id": digest.id,
                    "period_start": digest.period_start.isoformat(),
                    "period_end": digest.period_end.isoformat(),
                    "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
                    "channel": digest.channel,
                    "item_count": count,
                }
                for digest, count in rows
            ]
        }


@app.post("/change-items/{change_item_id}/feedback")
def create_feedback(change_item_id: int, payload: FeedbackCreate) -> dict:
    if payload.label not in {"relevant", "not_relevant"}:
        raise HTTPException(status_code=422, detail="label must be 'relevant' or 'not_relevant'")

    if settings.demo_mode:
        item = next((entry for entry in DEMO_DIGEST_ITEMS if entry["change_item_id"] == change_item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Change item not found")
        return {
            "id": change_item_id,
            "change_item_id": change_item_id,
            "label": payload.label,
            "user_id": payload.user_id,
            "change_item_status": "shown" if payload.label == "relevant" else "dismissed",
        }

    with SessionLocal() as db:
        change_item = db.get(ChangeItem, change_item_id)
        if change_item is None:
            raise HTTPException(status_code=404, detail="Change item not found")

        feedback = Feedback(
            change_item_id=change_item.id,
            user_id=payload.user_id,
            label=payload.label,
            created_at=datetime.now(timezone.utc),
        )
        db.add(feedback)

        # PRD FR9: "not relevant" marks the item dismissed so future digests skip it.
        if payload.label == "not_relevant":
            change_item.status = "dismissed"

        db.commit()
        db.refresh(feedback)
        return {
            "id": feedback.id,
            "change_item_id": feedback.change_item_id,
            "label": feedback.label,
            "user_id": feedback.user_id,
            "change_item_status": change_item.status,
        }


@app.get("/change-items/{change_item_id}/evidence")
def get_change_item_evidence(change_item_id: int) -> dict:
    """Evidence view for a change item (PRD FR8).

    Returns the full before/after snapshot text behind the claim, the changed
    tokens the diff engine surfaced, and screenshot references when present,
    so every digest claim is traceable to stored raw snapshots.
    """
    if settings.demo_mode:
        evidence = demo_evidence(change_item_id)
        if not evidence:
            raise HTTPException(status_code=404, detail="Change item not found")
        return evidence

    with SessionLocal() as db:
        change_item = db.get(ChangeItem, change_item_id)
        if change_item is None:
            raise HTTPException(status_code=404, detail="Change item not found")

        diff = db.get(Diff, change_item.diff_id)
        tracked_url = db.get(TrackedUrl, diff.tracked_url_id)
        competitor = db.get(Competitor, tracked_url.competitor_id)
        before_snapshot = db.get(Snapshot, diff.snapshot_before_id) if diff.snapshot_before_id else None
        after_snapshot = db.get(Snapshot, diff.snapshot_after_id)

        from app.services.diffing import summarize_changed_tokens

        changed_tokens = summarize_changed_tokens(
            before_snapshot.text_content if before_snapshot else "",
            after_snapshot.text_content if after_snapshot else "",
        )

        return {
            "change_item_id": change_item.id,
            "status": change_item.status,
            "category": change_item.category,
            "magnitude": change_item.magnitude,
            "summary": change_item.summary,
            "why_it_matters": change_item.why_it_matters,
            "confidence": change_item.confidence,
            "competitor": {
                "id": competitor.id,
                "name": competitor.name,
                "domain": competitor.domain,
            },
            "tracked_url": {
                "id": tracked_url.id,
                "url": tracked_url.url,
                "page_type": tracked_url.page_type,
            },
            "diff": {
                "id": diff.id,
                "material_change": diff.passed_filter,
                "stage1_score": diff.stage1_score,
                "changed_tokens": changed_tokens[:20],
            },
            "before": (
                {
                    "snapshot_id": before_snapshot.id,
                    "fetched_at": before_snapshot.fetched_at.isoformat() if before_snapshot.fetched_at else None,
                    "text_content": before_snapshot.text_content,
                    "screenshot_url": before_snapshot.screenshot_url,
                }
                if before_snapshot
                else None
            ),
            "after": (
                {
                    "snapshot_id": after_snapshot.id,
                    "fetched_at": after_snapshot.fetched_at.isoformat() if after_snapshot.fetched_at else None,
                    "text_content": after_snapshot.text_content,
                    "screenshot_url": after_snapshot.screenshot_url,
                }
                if after_snapshot
                else None
            ),
        }


@app.get("/change-items/{change_item_id}/feedback")
def list_feedback(change_item_id: int) -> dict:
    if settings.demo_mode:
        if not any(entry["change_item_id"] == change_item_id for entry in DEMO_DIGEST_ITEMS):
            raise HTTPException(status_code=404, detail="Change item not found")
        return {"change_item_id": change_item_id, "change_item_status": "shown", "feedback": []}

    with SessionLocal() as db:
        change_item = db.get(ChangeItem, change_item_id)
        if change_item is None:
            raise HTTPException(status_code=404, detail="Change item not found")

        rows = db.scalars(
            select(Feedback).where(Feedback.change_item_id == change_item_id).order_by(Feedback.id)
        ).all()
        return {
            "change_item_id": change_item_id,
            "change_item_status": change_item.status,
            "feedback": [
                {
                    "id": row.id,
                    "label": row.label,
                    "user_id": row.user_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
        }


@app.get("/competitors/{competitor_id}/urgent-pricing")
def get_urgent_pricing(competitor_id: int) -> dict:
    if settings.demo_mode:
        competitor = next((item for item in DEMO_COMPETITORS if item["id"] == competitor_id), None)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")
        item = next(
            (entry for entry in DEMO_DIGEST_ITEMS if entry["competitor_name"] == competitor["name"] and entry["category"] == "pricing"),
            None,
        )
        if item is None:
            return {"urgent": False, "competitor_name": competitor["name"], "category": "pricing", "summary": "No pricing changes detected."}
        return {
            "urgent": True,
            "competitor_name": competitor["name"],
            "url": item["url"],
            "category": item["category"],
            "summary": item["summary"],
            "confidence": item["confidence"],
        }

    with SessionLocal() as db:
        competitor = db.get(Competitor, competitor_id)
        if competitor is None:
            raise HTTPException(status_code=404, detail="Competitor not found")

        row = (
            db.execute(
                select(ChangeItem, TrackedUrl)
                .join(Diff, Diff.id == ChangeItem.diff_id)
                .join(TrackedUrl, TrackedUrl.id == Diff.tracked_url_id)
                .where(TrackedUrl.competitor_id == competitor_id)
                .where(ChangeItem.category == "pricing")
                .order_by(ChangeItem.confidence.desc())
                .limit(1)
            )
            .first()
        )

        if row is None:
            return {"urgent": False, "competitor_name": competitor.name, "category": "pricing", "summary": "No pricing changes detected."}

        change_item, tracked_url = row
        return {
            "urgent": True,
            "competitor_name": competitor.name,
            "url": tracked_url.url,
            "category": change_item.category,
            "summary": change_item.summary,
            "confidence": change_item.confidence,
        }


@app.get("/workers/status")
def worker_status() -> dict:
    if settings.demo_mode:
        return {"running": False, "jobs": [], "mode": "demo"}
    return scheduler_status()


@app.get("/workers/queue-status")
def queue_status() -> dict:
    if settings.demo_mode:
        return {
            "available": False,
            "queue": settings.redis_queue_name,
            "queued": 0,
            "started": 0,
            "failed": 0,
            "jobs": [],
            "message": "Queue is disabled in demo mode.",
        }
    return get_queue_status()


@app.post("/workers/run-cycle")
def run_cycle(payload: dict | None = None) -> dict:
    if settings.demo_mode:
        return {
            "processed_competitors": len(DEMO_COMPETITORS),
            "material_changes": len(DEMO_DIGEST_ITEMS),
            "alerts_sent": 0,
            "last_alert": "Demo cycle complete. No websites were crawled and no data was persisted.",
            "failed_fetches": [],
        }

    candidate = payload or {}
    competitor_id = candidate.get("competitor_id")
    tracked_url_id = candidate.get("tracked_url_id")
    previous_snapshot_id = candidate.get("previous_snapshot_id")
    current_snapshot_id = candidate.get("current_snapshot_id")
    return run_monitoring_cycle(
        competitor_id=competitor_id,
        tracked_url_id=tracked_url_id,
        previous_snapshot_id=previous_snapshot_id,
        current_snapshot_id=current_snapshot_id,
    )


@app.post("/workers/enqueue-cycle")
def enqueue_cycle(payload: dict | None = None) -> dict:
    if settings.demo_mode:
        return {"queued": False, "reason": "Background queue is disabled in demo mode."}

    candidate = payload or {}
    return enqueue_monitoring_cycle(
        competitor_id=candidate.get("competitor_id"),
        tracked_url_id=candidate.get("tracked_url_id"),
        previous_snapshot_id=candidate.get("previous_snapshot_id"),
        current_snapshot_id=candidate.get("current_snapshot_id"),
    )
