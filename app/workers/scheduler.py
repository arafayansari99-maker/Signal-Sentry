from __future__ import annotations

import structlog

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.workers.pipeline import run_monitoring_cycle

_logger = structlog.get_logger()

_scheduler: BackgroundScheduler | None = None


def run_scheduled_job() -> dict:
    """Scheduled entry point: monitoring cycle first, then digest composition.

    The digest runs only when the cycle actually surfaced change items, so an
    empty crawl doesn't create empty Digest rows every scheduled run. Digest
    failures never fail the cycle result — they're logged and reported.
    """
    cycle = run_monitoring_cycle()
    result: dict = {"cycle": cycle, "digest": None}

    if not cycle.get("diff_ids"):
        _logger.info("digest_skipped_no_changes")
        return result

    try:
        from app.db import SessionLocal
        from app.services.digests import generate_weekly_digest

        with SessionLocal() as db:
            result["digest"] = generate_weekly_digest(db, send=False)
        _logger.info("digest_generated", digest_id=(result["digest"] or {}).get("digest_id"))
    except Exception as exc:  # digest must never break the monitoring job
        _logger.error("digest_generation_failed", error=str(exc))
        result["digest_error"] = str(exc)

    return result


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    settings = get_settings()
    _scheduler = BackgroundScheduler()

    if settings.monitoring_cron_schedule.strip():
        trigger = CronTrigger.from_crontab(settings.monitoring_cron_schedule)
        job_kwargs = {"trigger": trigger}
        job_name = f"Run monitoring cycle ({settings.monitoring_cron_schedule})"
    else:
        job_kwargs = {"trigger": "interval", "minutes": settings.monitoring_interval_minutes}
        job_name = f"Run monitoring cycle every {settings.monitoring_interval_minutes} minutes"

    _scheduler.add_job(
        run_scheduled_job,
        id="monitoring_cycle",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        name=job_name,
        **job_kwargs,
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def scheduler_status() -> dict:
    running = _scheduler is not None and _scheduler.running
    jobs = []
    if _scheduler is not None:
        for job in _scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            })
    return {"running": running, "jobs": jobs}
