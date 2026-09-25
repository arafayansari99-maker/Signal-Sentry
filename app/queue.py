from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.workers.pipeline import run_monitoring_cycle


def get_queue_client() -> Any:
    """Return an RQ queue if Redis is reachable, otherwise return a local fallback."""
    settings = get_settings()
    try:
        import redis
        from rq import Queue

        connection = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        connection.ping()
        return Queue(settings.redis_queue_name, connection=connection)
    except Exception:
        return None


def get_queue_status() -> dict[str, Any]:
    settings = get_settings()
    queue = get_queue_client()
    if queue is None:
        return {
            "available": False,
            "queue": settings.redis_queue_name,
            "queued": 0,
            "started": 0,
            "failed": 0,
            "jobs": [],
            "message": "Redis queue unavailable; requests are falling back to inline execution.",
        }

    queued_jobs = list(queue.get_jobs())
    started_jobs = []
    failed_jobs = []
    try:
        started_jobs = list(queue.started_job_registry.get_job_ids())
    except Exception:
        started_jobs = []
    try:
        failed_jobs = list(queue.failed_job_registry.get_job_ids())
    except Exception:
        failed_jobs = []

    job_map: dict[str, dict[str, Any]] = {}
    for job in queued_jobs:
        job_map[job.id] = {"id": job.id, "status": "queued", "description": job.description or "monitoring cycle"}
    for job_id in started_jobs:
        if job_id not in job_map:
            job_map[job_id] = {"id": job_id, "status": "started", "description": "monitoring cycle"}
        else:
            job_map[job_id]["status"] = "started"
    for job_id in failed_jobs:
        if job_id not in job_map:
            job_map[job_id] = {"id": job_id, "status": "failed", "description": "monitoring cycle"}
        else:
            job_map[job_id]["status"] = "failed"

    return {
        "available": True,
        "queue": settings.redis_queue_name,
        "queued": len(queued_jobs),
        "started": len(started_jobs),
        "failed": len(failed_jobs),
        "jobs": list(job_map.values()),
    }


def enqueue_monitoring_cycle(
    competitor_id: int | None = None,
    tracked_url_id: int | None = None,
    previous_snapshot_id: int | None = None,
    current_snapshot_id: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.background_queue_enabled:
        return {
            "queued": False,
            "reason": "background queue disabled",
            "result": run_monitoring_cycle(
                competitor_id=competitor_id,
                tracked_url_id=tracked_url_id,
                previous_snapshot_id=previous_snapshot_id,
                current_snapshot_id=current_snapshot_id,
            ),
        }

    queue = get_queue_client()
    if queue is None:
        return {
            "queued": False,
            "reason": "redis unavailable; executed inline",
            "result": run_monitoring_cycle(
                competitor_id=competitor_id,
                tracked_url_id=tracked_url_id,
                previous_snapshot_id=previous_snapshot_id,
                current_snapshot_id=current_snapshot_id,
            ),
        }

    job = queue.enqueue(
        run_monitoring_cycle,
        competitor_id=competitor_id,
        tracked_url_id=tracked_url_id,
        previous_snapshot_id=previous_snapshot_id,
        current_snapshot_id=current_snapshot_id,
    )
    return {
        "queued": True,
        "job_id": job.id,
        "queue": settings.redis_queue_name,
        "status": job.get_status(),
    }
