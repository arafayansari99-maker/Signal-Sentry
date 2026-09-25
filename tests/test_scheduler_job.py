import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./scheduler_job_test.db")

from app.db import SessionLocal
from app.main import app  # noqa: F401  (ensures models/tables init)
from app.models import Digest, DigestItem
from app.workers import scheduler as scheduler_module
from app.workers.scheduler import run_scheduled_job


@pytest.fixture()
def clean_db():
    from app.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_scheduled_job_composes_digest_after_material_cycle(clean_db, monkeypatch):
    fake_cycle = {
        "processed_competitors": 1,
        "material_changes": 1,
        "diff_ids": [101],
        "alerts_sent": 0,
        "last_alert": "alert text",
        "failed_fetches": [],
    }
    monkeypatch.setattr(scheduler_module, "run_monitoring_cycle", lambda: fake_cycle)

    result = run_scheduled_job()

    assert result["cycle"] == fake_cycle
    digest = result["digest"]
    # The diff IDs are fake, so no real candidates: no digest row is created.
    assert digest is not None and digest["digest_id"] is None
    assert digest["item_count"] == 0

    # Now with a real change item flowing through the pipeline:
    from datetime import datetime, timezone

    from app.models import ChangeItem, Competitor, Diff, Snapshot, TrackedUrl

    with SessionLocal() as db:
        competitor = Competitor(name="Acme", domain="acme-sched.com")
        db.add(competitor)
        db.flush()
        tracked = TrackedUrl(competitor_id=competitor.id, url="https://acme-sched.com/pricing", page_type="pricing")
        db.add(tracked)
        db.flush()
        snapshot = Snapshot(tracked_url_id=tracked.id, fetched_at=datetime.now(timezone.utc), text_content="text")
        db.add(snapshot)
        db.flush()
        diff = Diff(tracked_url_id=tracked.id, snapshot_after_id=snapshot.id, passed_filter=True, stage1_score=1.0)
        db.add(diff)
        db.flush()
        db.add(ChangeItem(diff_id=diff.id, category="pricing", magnitude="major", summary="Price cut", confidence=0.9))
        db.commit()

        def real_cycle_with_existing_diff(**kwargs):
            # Simulate a cycle that "found" the diff we just stored.
            return dict(fake_cycle, diff_ids=[diff.id])

        monkeypatch.setattr(scheduler_module, "run_monitoring_cycle", real_cycle_with_existing_diff)
        result = run_scheduled_job()

    assert result["digest"] is not None
    assert result["digest"]["item_count"] == 1
    with SessionLocal() as check:
        assert check.query(Digest).count() == 1
        assert check.query(DigestItem).count() == 1


def test_scheduled_job_skips_digest_when_no_changes(clean_db, monkeypatch):
    from app.models import Digest

    monkeypatch.setattr(
        scheduler_module,
        "run_monitoring_cycle",
        lambda: {"processed_competitors": 0, "material_changes": 0, "diff_ids": [], "alerts_sent": 0, "last_alert": None, "failed_fetches": []},
    )

    result = run_scheduled_job()

    assert result["digest"] is None
    with SessionLocal() as check:
        assert check.query(Digest).count() == 0


def test_scheduled_job_survives_digest_failure(clean_db, monkeypatch):
    monkeypatch.setattr(
        scheduler_module,
        "run_monitoring_cycle",
        lambda: {"processed_competitors": 1, "material_changes": 1, "diff_ids": [1], "alerts_sent": 0, "last_alert": None, "failed_fetches": []},
    )

    def boom(db, *, send=False):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr("app.services.digests.generate_weekly_digest", boom)

    result = run_scheduled_job()

    assert result["cycle"]["diff_ids"] == [1]  # cycle result intact
    assert result["digest"] is None
    assert "smtp exploded" in result["digest_error"]


def test_scheduler_registers_digest_wired_job():
    sched = scheduler_module.start_scheduler()
    try:
        jobs = sched.get_jobs()
        assert any(job.id == "monitoring_cycle" for job in jobs)
        assert any("cycle" in job.name.lower() for job in jobs)
    finally:
        scheduler_module.stop_scheduler()
