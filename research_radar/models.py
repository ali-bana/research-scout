from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), default="arxiv", index=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    arxiv_id: Mapped[str | None] = mapped_column(String(80), unique=True, index=True, nullable=True)
    categories: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    signal_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    selection_reason: Mapped[str] = mapped_column(Text, default="")
    llm_selection_reason: Mapped[str] = mapped_column(Text, default="")
    short_explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    digest_items: Mapped[list[DigestItem]] = relationship(back_populates="paper")
    feedback: Mapped[list[Feedback]] = relationship(back_populates="paper")


class RssItem(Base):
    __tablename__ = "rss_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, unique=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotionSnapshot(Base):
    __tablename__ = "notion_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), default="notion")
    object_id: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(80), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest_type: Mapped[str] = mapped_column(String(30), default="daily", index=True)
    title: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary_markdown: Mapped[str] = mapped_column(Text, default="")
    summary_html: Mapped[str] = mapped_column(Text, default="")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    items: Mapped[list[DigestItem]] = relationship(
        back_populates="digest", cascade="all, delete-orphan", order_by="DigestItem.rank"
    )


class DigestItem(Base):
    __tablename__ = "digest_items"
    __table_args__ = (UniqueConstraint("digest_id", "paper_id", name="uq_digest_item_paper"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    selection_reason: Mapped[str] = mapped_column(Text, default="")
    llm_selection_reason: Mapped[str] = mapped_column(Text, default="")
    short_explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    digest: Mapped[Digest] = relationship(back_populates="items")
    paper: Mapped[Paper] = relationship(back_populates="digest_items")
    feedback: Mapped[list[Feedback]] = relationship(back_populates="digest_item")

    @property
    def displayed_reason(self) -> str:
        return self.llm_selection_reason or self.selection_reason


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digest_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("digest_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    digest_item: Mapped[DigestItem | None] = relationship(back_populates="feedback")
    paper: Mapped[Paper] = relationship(back_populates="feedback")


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=func.now(), index=True
    )


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
