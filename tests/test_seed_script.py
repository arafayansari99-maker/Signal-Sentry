import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./seed_test.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Base, SessionLocal, engine
from app.models import ChangeItem, Competitor, Diff, Digest, Snapshot, TrackedUrl
from scripts.seed_demo_data import seed


def setup_function(_):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function(_):
    Base.metadata.drop_all(bind=engine)


def test_seed_creates_full_demo_dataset():
    counts = seed()
    assert counts == {"competitors": 4, "tracked_urls": 7, "snapshots": 14, "diffs": 7, "change_items": 4}

    with SessionLocal() as db:
        assert db.query(Competitor).count() == 4
        assert db.query(Snapshot).count() == 14
        items = db.query(ChangeItem).all()
        assert len(items) == 4
        # Seeded items carry hand-written business framing, not the heuristic fallback.
        assert all(item.why_it_matters != item.summary for item in items)
        assert all(item.status == "pending" for item in items)


def test_seed_is_idempotent():
    first = seed()
    second = seed()
    assert first == second, "re-running the seeder reproduces the same dataset"

    with SessionLocal() as db:
        assert db.query(Competitor).count() == 4
        assert db.query(Snapshot).count() == 14
        assert db.query(Digest).count() == 0  # seeder never touches digests


def test_seeded_diffs_line_up_with_change_items():
    seed()
    with SessionLocal() as db:
        material_diffs = db.query(Diff).filter(Diff.passed_filter.is_(True)).count()
        assert material_diffs == 4
        # Every material diff has exactly one change item.
        for diff in db.query(Diff).filter(Diff.passed_filter.is_(True)).all():
            assert db.query(ChangeItem).filter(ChangeItem.diff_id == diff.id).count() == 1
