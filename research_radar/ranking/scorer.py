from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_radar.models import Feedback, Paper, utcnow
from research_radar.ranking.profile import extract_terms, normalize_text

DISCOVERY_KEYWORDS = [
    "benchmark",
    "survey",
    "reasoning",
    "agent",
    "agents",
    "post-training",
    "retrieval",
    "evaluation",
    "tool use",
    "tool-use",
    "long-context",
    "multimodal",
    "alignment",
]


@dataclass
class ScoredPaper:
    paper: Paper
    score: float
    breakdown: dict[str, Any]
    fallback_reason: str


def score_and_rank(
    session: Session,
    papers: list[Paper],
    profile: dict[str, Any],
    notion_text: str = "",
    *,
    discovery_mode: bool = False,
) -> list[ScoredPaper]:
    feedback_terms = _feedback_terms(session)
    scored = [
        _score_one(paper, profile, notion_text, feedback_terms, discovery_mode=discovery_mode)
        for paper in papers
    ]
    scored.sort(key=_sort_key, reverse=True)
    _apply_diversity_penalty(scored)
    scored.sort(key=_sort_key, reverse=True)
    for item in scored:
        item.paper.final_score = item.score
        item.paper.signal_breakdown = item.breakdown
        item.paper.selection_reason = item.fallback_reason
    return scored


def fallback_selection_reason(breakdown: dict[str, Any]) -> str:
    matched = breakdown.get("matched_terms") or []
    notion_terms = breakdown.get("notion_terms") or []
    author_matches = breakdown.get("author_matches") or []
    signals: list[str] = []
    if matched:
        signals.append(f"matches your interest in {matched[0]}")
    if notion_terms:
        signals.append(f"connects to your Notion watchlist item {notion_terms[0]}")
    if author_matches:
        signals.append(f"comes from your watchlist author/lab {author_matches[0]}")
    if breakdown.get("discovery_terms"):
        signals.append(f"contains discovery signal {breakdown['discovery_terms'][0]}")
    if breakdown.get("recency", 0) > 0.5:
        signals.append("is recent")
    if not signals:
        signals.append("has the strongest remaining transparent score for your profile")
    if len(signals) == 1:
        return f"Chosen because it {signals[0]}."
    return f"Chosen because it {signals[0]} and {signals[1]}."


def _score_one(
    paper: Paper,
    profile: dict[str, Any],
    notion_text: str,
    feedback_terms: dict[str, Counter[str]],
    *,
    discovery_mode: bool,
) -> ScoredPaper:
    text = normalize_text(
        " ".join([paper.title or "", paper.abstract or "", paper.categories or ""])
    )
    authors = normalize_text(paper.authors or "")

    high_terms = _terms(profile, "high_priority_topics") + _terms(profile, "current_projects")
    broad_terms = _terms(profile, "broader_watchlist") + _terms(profile, "seed_papers_i_like")
    negative_terms = _terms(profile, "negative_topics")
    author_terms = _terms(profile, "authors_labs_to_watch")
    notion_terms = extract_terms(notion_text[:5000]) if notion_text else []

    high_matches = _matches(text, high_terms)
    broad_matches = _matches(text, broad_terms)
    negative_matches = _matches(text, negative_terms)
    notion_matches = _matches(text, notion_terms)
    author_matches = _matches(authors, author_terms)
    discovery_matches = _matches(text, DISCOVERY_KEYWORDS) if discovery_mode else []
    liked_matches = _matches(text, list(feedback_terms["liked"].keys()))
    disliked_matches = _matches(text, list(feedback_terms["disliked"].keys()))

    recency = _recency_score(paper.published_at or paper.seen_at)
    keyword_score = min(4.0, len(high_matches) * 1.2 + len(broad_matches) * 0.55)
    notion_score = min(2.0, len(notion_matches) * 0.45)
    author_score = min(1.5, len(author_matches) * 0.75)
    feedback_boost = min(1.2, sum(feedback_terms["liked"][term] for term in liked_matches) * 0.2)
    feedback_penalty = min(
        1.5, sum(feedback_terms["disliked"][term] for term in disliked_matches) * 0.25
    )
    negative_penalty = min(3.0, len(negative_matches) * 1.0)
    discovery_score = min(2.0, len(discovery_matches) * 0.45)

    final_score = (
        keyword_score
        + notion_score
        + author_score
        + recency
        + feedback_boost
        + discovery_score
        - feedback_penalty
        - negative_penalty
    )
    breakdown: dict[str, Any] = {
        "keyword_topic_match": round(keyword_score, 3),
        "notion_watchlist_match": round(notion_score, 3),
        "negative_topic_penalty": round(-negative_penalty, 3),
        "recency": round(recency, 3),
        "author_lab_bonus": round(author_score, 3),
        "feedback_boost": round(feedback_boost, 3),
        "feedback_penalty": round(-feedback_penalty, 3),
        "diversity_penalty": 0.0,
        "discovery_keyword_bonus": round(discovery_score, 3),
        "matched_terms": (high_matches + broad_matches)[:8],
        "notion_terms": notion_matches[:5],
        "negative_terms": negative_matches[:5],
        "author_matches": author_matches[:5],
        "discovery_terms": discovery_matches[:5],
        "liked_feedback_terms": liked_matches[:5],
        "disliked_feedback_terms": disliked_matches[:5],
    }
    return ScoredPaper(
        paper=paper,
        score=round(final_score, 3),
        breakdown=breakdown,
        fallback_reason=fallback_selection_reason(breakdown),
    )


def _apply_diversity_penalty(scored: list[ScoredPaper]) -> None:
    accepted_titles: list[str] = []
    for item in scored:
        normalized_title = normalize_text(item.paper.title)
        penalty = 0.0
        for previous in accepted_titles[:20]:
            similarity = SequenceMatcher(a=normalized_title, b=previous).ratio()
            if similarity >= 0.82:
                penalty = max(penalty, 0.75)
        if penalty:
            item.score = round(item.score - penalty, 3)
            item.breakdown["diversity_penalty"] = -penalty
            item.fallback_reason = fallback_selection_reason(item.breakdown)
        accepted_titles.append(normalized_title)


def _feedback_terms(session: Session) -> dict[str, Counter[str]]:
    liked: Counter[str] = Counter()
    disliked: Counter[str] = Counter()
    rows = session.execute(select(Feedback, Paper).join(Paper, Feedback.paper_id == Paper.id)).all()
    for feedback, paper in rows:
        terms = extract_terms(f"{paper.title} {paper.abstract}")[:40]
        if feedback.label in {"very_relevant", "relevant", "read_later"}:
            liked.update(terms)
        elif feedback.label == "not_relevant":
            disliked.update(terms)
    return {"liked": liked, "disliked": disliked}


def _sort_key(item: ScoredPaper) -> tuple[float, datetime]:
    return item.score, item.paper.published_at or datetime.min


def _terms(profile: dict[str, Any], key: str) -> list[str]:
    terms: list[str] = []
    for value in profile.get(key, []) or []:
        if isinstance(value, dict):
            raw = " ".join(str(value.get(field, "")) for field in ("title", "note"))
        else:
            raw = str(value)
        terms.extend(extract_terms(raw))
    return sorted(set(terms))


def _matches(text: str, terms: list[str]) -> list[str]:
    matches: list[str] = []
    padded = f" {text} "
    for term in terms:
        normalized = normalize_text(term)
        if not normalized or len(normalized) < 3:
            continue
        if f" {normalized} " in padded or normalized in text:
            matches.append(term)
    return sorted(set(matches), key=lambda item: (-len(item), item))


def _recency_score(published_at: datetime | None) -> float:
    if not published_at:
        return 0.0
    age_days = max(0, (utcnow() - published_at).days)
    if age_days <= 2:
        return 1.0
    if age_days <= 7:
        return 0.75
    if age_days <= 30:
        return 0.45
    if age_days <= 180:
        return 0.2
    return 0.0
