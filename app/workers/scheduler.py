from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.workers.pipeline import run_monitoring_cycle

_scheduler: BackgroundScheduler | None = None


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
        run_monitoring_cycle,
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
