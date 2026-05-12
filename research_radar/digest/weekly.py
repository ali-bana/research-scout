from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from research_radar.config import Settings, get_settings
from research_radar.digest.daily import _build_item, _generate_digest_markdown, _select
from research_radar.digest.formatting import markdown_to_html
from research_radar.llm.base import provider_from_settings
from research_radar.llm.mock import MockLLMProvider
from research_radar.models import Digest, DigestItem, Paper, utcnow
from research_radar.ranking.profile import latest_notion_text, load_profile, profile_context
from research_radar.ranking.scorer import score_and_rank


def generate_weekly_discovery(session: Session, settings: Settings | None = None) -> Digest:
    settings = settings or get_settings()
    now = utcnow()
    cutoff = now - timedelta(days=settings.weekly_discovery_window_days)
    papers = _weekly_candidates(session, cutoff)
    profile = load_profile(settings)
    notion_text = latest_notion_text(session)
    context = profile_context(profile, notion_text)
    scored = score_and_rank(session, papers, profile, notion_text, discovery_mode=True)
    selected = _select(scored, settings.daily_max_papers)

    digest = Digest(
        digest_type="weekly",
        title=f"Weekly Discovery - {now:%Y-%m-%d}",
        generated_at=now,
        period_start=cutoff,
        period_end=now,
    )
    session.add(digest)
    session.flush()

    provider = provider_from_settings(settings)
    mock = MockLLMProvider()
    items: list[DigestItem] = []
    for rank, scored_paper in enumerate(selected, start=1):
        with session.no_autoflush:
            item = _build_item(rank, scored_paper, provider, mock, context)
            digest.items.append(item)
        items.append(item)
    digest.item_count = len(items)
    digest.summary_markdown = _generate_digest_markdown(provider, mock, items, context)
    digest.summary_html = markdown_to_html(digest.summary_markdown)
    session.commit()
    return _load_digest(session, digest.id)


def _weekly_candidates(session: Session, cutoff: datetime) -> list[Paper]:
    recent_daily_items = (
        select(DigestItem.paper_id)
        .join(Digest, DigestItem.digest_id == Digest.id)
        .where(Digest.digest_type == "daily", Digest.generated_at >= cutoff)
    )
    statement = (
        select(Paper)
        .where(or_(Paper.published_at >= cutoff, Paper.seen_at >= cutoff))
        .where(Paper.id.not_in(recent_daily_items))
        .order_by(Paper.final_score.desc(), Paper.published_at.desc().nullslast())
        .limit(500)
    )
    return list(session.scalars(statement))


def _load_digest(session: Session, digest_id: int) -> Digest:
    digest = session.scalar(
        select(Digest)
        .where(Digest.id == digest_id)
        .options(selectinload(Digest.items).selectinload(DigestItem.paper))
    )
    if digest is None:
        raise RuntimeError(f"Digest {digest_id} disappeared after generation")
    return digest
