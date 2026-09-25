from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import ChangeItem, Competitor, Diff, Snapshot, TrackedUrl
from app.schemas import CompetitorCreate, CompetitorRead
from app.services.diffing import build_change_summary
from app.services.discovery import discover_urls
from app.workers.pipeline import run_monitoring_cycle
from app.workers.scheduler import scheduler_status, start_scheduler, stop_scheduler
from app.queue import enqueue_monitoring_cycle, get_queue_status

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.mount("/ui-static", StaticFiles(directory=BASE_DIR / "static"), name="ui_static")
init_db()


@app.get("/", response_class=HTMLResponse)
def landing_page() -> HTMLResponse:
    html_path = BASE_DIR / "templates" / "landing.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> HTMLResponse:
    html_path = BASE_DIR / "templates" / "dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/ui", response_class=HTMLResponse)
def ui_page() -> HTMLResponse:
    html_path = BASE_DIR / "templates" / "ui.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/api")
def root() -> dict[str, str]:
    return {"message": "Competitive Intelligence Agent is running."}


@app.get("/competitors", response_model=list[CompetitorRead])
def list_competitors() -> list[CompetitorRead]:
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

    return {
        "domain": requested_domain,
        "candidates": discover_urls(requested_domain),
    }


@app.post("/competitors/{competitor_id}/tracked-urls")
def create_tracked_url(competitor_id: int, payload: dict) -> dict:
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


@app.get("/digests/weekly")
def get_weekly_digest() -> dict:
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(Competitor.name, TrackedUrl.url, ChangeItem.category, ChangeItem.summary, ChangeItem.confidence)
                .join(TrackedUrl, TrackedUrl.competitor_id == Competitor.id)
                .join(Diff, Diff.tracked_url_id == TrackedUrl.id)
                .join(ChangeItem, ChangeItem.diff_id == Diff.id)
                .order_by(ChangeItem.confidence.desc())
            )
            .all()
        )

        digest_items = [
            {
                "competitor_name": competitor_name,
                "url": url,
                "category": category,
                "summary": summary,
                "confidence": confidence,
            }
            for competitor_name, url, category, summary, confidence in rows
        ]

        return {
            "summary": f"{len(digest_items)} change items surfaced this week.",
            "digest_items": digest_items,
        }


@app.get("/competitors/{competitor_id}/urgent-pricing")
def get_urgent_pricing(competitor_id: int) -> dict:
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
    return scheduler_status()


@app.get("/workers/queue-status")
def queue_status() -> dict:
    return get_queue_status()


@app.post("/workers/run-cycle")
def run_cycle(payload: dict | None = None) -> dict:
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
    candidate = payload or {}
    return enqueue_monitoring_cycle(
        competitor_id=candidate.get("competitor_id"),
        tracked_url_id=candidate.get("tracked_url_id"),
        previous_snapshot_id=candidate.get("previous_snapshot_id"),
        current_snapshot_id=candidate.get("current_snapshot_id"),
    )
