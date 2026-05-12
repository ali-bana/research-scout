from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from research_radar.config import Settings, get_settings
from research_radar.digest.formatting import markdown_to_html
from research_radar.llm.base import LLMProvider, provider_from_settings
from research_radar.llm.mock import MockLLMProvider
from research_radar.models import Digest, DigestItem, Paper, utcnow
from research_radar.ranking.profile import latest_notion_text, load_profile, profile_context
from research_radar.ranking.scorer import ScoredPaper, score_and_rank

LOGGER = logging.getLogger(__name__)


def generate_daily_digest(
    session: Session,
    settings: Settings | None = None,
    *,
    max_papers: int | None = None,
) -> Digest:
    settings = settings or get_settings()
    max_papers = max_papers or settings.daily_max_papers
    now = utcnow()
    cutoff = now - timedelta(days=settings.arxiv_days_back)
    papers = _daily_candidates(session, cutoff)

    profile = load_profile(settings)
    notion_text = latest_notion_text(session)
    context = profile_context(profile, notion_text)
    scored = score_and_rank(session, papers, profile, notion_text)
    selected = _select(scored, max_papers)

    digest = Digest(
        digest_type="daily",
        title=f"Daily Research Radar - {now:%Y-%m-%d}",
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
    session.refresh(digest)
    return _load_digest(session, digest.id)


def _daily_candidates(session: Session, cutoff: datetime) -> list[Paper]:
    included_daily = (
        select(DigestItem.paper_id)
        .join(Digest, DigestItem.digest_id == Digest.id)
        .where(Digest.digest_type == "daily")
    )
    base_filter = or_(Paper.published_at >= cutoff, Paper.seen_at >= cutoff)
    statement: Select[tuple[Paper]] = (
        select(Paper)
        .where(base_filter)
        .where(Paper.id.not_in(included_daily))
        .order_by(Paper.published_at.desc().nullslast(), Paper.seen_at.desc())
        .limit(250)
    )
    papers = list(session.scalars(statement))
    if papers:
        return papers
    fallback = (
        select(Paper)
        .where(Paper.id.not_in(included_daily))
        .order_by(Paper.published_at.desc().nullslast(), Paper.seen_at.desc())
        .limit(250)
    )
    return list(session.scalars(fallback))


def _select(scored: list[ScoredPaper], max_papers: int) -> list[ScoredPaper]:
    positive = [item for item in scored if item.score > 0]
    if positive:
        return positive[:max_papers]
    return scored[: min(max_papers, 3)]


def _build_item(
    rank: int,
    scored_paper: ScoredPaper,
    provider: LLMProvider,
    mock: MockLLMProvider,
    context: str,
) -> DigestItem:
    paper = scored_paper.paper
    fallback_reason = scored_paper.fallback_reason
    short_explanation = mock.summarize_paper(paper.title, paper.abstract, context).short_explanation
    llm_reason = ""
    if provider.name != "mock":
        try:
            short_explanation = provider.summarize_paper(
                paper.title, paper.abstract, context
            ).short_explanation
            llm_reason = provider.explain_relevance(paper, context, scored_paper.breakdown)
        except Exception as exc:
            LOGGER.warning("LLM provider failed for paper %s: %s", paper.id, exc)
    paper.short_explanation = short_explanation
    paper.selection_reason = fallback_reason
    paper.llm_selection_reason = llm_reason
    return DigestItem(
        paper=paper,
        rank=rank,
        score=scored_paper.score,
        score_breakdown=scored_paper.breakdown,
        selection_reason=fallback_reason,
        llm_selection_reason=llm_reason,
        short_explanation=short_explanation,
    )


def _generate_digest_markdown(
    provider: LLMProvider, mock: MockLLMProvider, items: list[DigestItem], context: str
) -> str:
    if provider.name != "mock":
        try:
            return provider.generate_digest(items, context)
        except Exception as exc:
            LOGGER.warning("LLM digest generation failed: %s", exc)
    return mock.generate_digest(items, context)


def _load_digest(session: Session, digest_id: int) -> Digest:
    digest = session.scalar(
        select(Digest)
        .where(Digest.id == digest_id)
        .options(selectinload(Digest.items).selectinload(DigestItem.paper))
    )
    if digest is None:
        raise RuntimeError(f"Digest {digest_id} disappeared after generation")
    return digest
