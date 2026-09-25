from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    crawl_cadence: Mapped[str] = mapped_column(String(32), default="weekly")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tracked_urls: Mapped[list["TrackedUrl"]] = relationship(back_populates="competitor")


class TrackedUrl(Base):
    __tablename__ = "tracked_urls"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    page_type: Mapped[str] = mapped_column(String(64), default="product")
    exclude: Mapped[bool] = mapped_column(Boolean, default=False)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    competitor: Mapped[Competitor] = relationship(back_populates="tracked_urls")
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="tracked_url")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tracked_url_id: Mapped[int] = mapped_column(ForeignKey("tracked_urls.id"), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    text_content: Mapped[str] = mapped_column(Text)
    screenshot_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    tracked_url: Mapped[TrackedUrl] = relationship(back_populates="snapshots")
    diffs: Mapped[list["Diff"]] = relationship(
        back_populates="snapshot_after",
        foreign_keys="Diff.snapshot_after_id",
    )
    previous_diffs: Mapped[list["Diff"]] = relationship(
        back_populates="snapshot_before",
        foreign_keys="Diff.snapshot_before_id",
    )


class Diff(Base):
    __tablename__ = "diffs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tracked_url_id: Mapped[int] = mapped_column(ForeignKey("tracked_urls.id"), nullable=False)
    snapshot_before_id: Mapped[int | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True)
    snapshot_after_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"), nullable=False)
    stage1_score: Mapped[float] = mapped_column(Float, default=0.0)
    passed_filter: Mapped[bool] = mapped_column(Boolean, default=False)

    snapshot_before: Mapped[Snapshot | None] = relationship(
        foreign_keys=[snapshot_before_id],
        back_populates="previous_diffs",
    )
    snapshot_after: Mapped[Snapshot] = relationship(
        back_populates="diffs",
        foreign_keys=[snapshot_after_id],
    )
    change_items: Mapped[list["ChangeItem"]] = relationship(back_populates="diff")


class ChangeItem(Base):
    __tablename__ = "change_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    diff_id: Mapped[int] = mapped_column(ForeignKey("diffs.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="other")
    magnitude: Mapped[str] = mapped_column(String(32), default="minor")
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    diff: Mapped[Diff] = relationship(back_populates="change_items")
    digest_items: Mapped[list["DigestItem"]] = relationship(back_populates="change_item")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="change_item")


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    period_end: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="email")

    items: Mapped[list["DigestItem"]] = relationship(back_populates="digest")


class DigestItem(Base):
    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id"), nullable=False)
    change_item_id: Mapped[int] = mapped_column(ForeignKey("change_items.id"), nullable=False)
    rank: Mapped[int] = mapped_column(default=0)

    digest: Mapped[Digest] = relationship(back_populates="items")
    change_item: Mapped[ChangeItem] = relationship(back_populates="digest_items")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    change_item_id: Mapped[int] = mapped_column(ForeignKey("change_items.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str] = mapped_column(String(32), default="relevant")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    change_item: Mapped[ChangeItem] = relationship(back_populates="feedback")
