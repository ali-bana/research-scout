from __future__ import annotations

from typing import Any

from research_radar.llm.base import LLMProvider, PaperSummary
from research_radar.ranking.scorer import fallback_selection_reason


class MockLLMProvider(LLMProvider):
    name = "mock"

    def summarize_paper(self, title: str, abstract: str, profile_context: str) -> PaperSummary:
        del profile_context
        sentence = _first_sentence(abstract)
        if not sentence:
            sentence = f"{title} appears relevant based on the transparent ranking signals."
        return PaperSummary(short_explanation=_limit(sentence, 320))

    def explain_relevance(
        self, paper: Any, profile_context: str, score_breakdown: dict[str, Any]
    ) -> str:
        del paper, profile_context
        return fallback_selection_reason(score_breakdown)

    def generate_digest(self, digest_items: list[Any], profile_context: str) -> str:
        del profile_context
        if not digest_items:
            return "No papers were selected for this digest."
        lines = ["# Research Radar Digest", ""]
        for item in digest_items:
            reason = item.llm_selection_reason or item.selection_reason
            lines.append(f"{item.rank}. **{item.paper.title}**")
            lines.append(f"   - Score: {item.score:.2f}")
            lines.append(f"   - Reason: {reason}")
            lines.append(f"   - Link: {item.paper.url}")
        return "\n".join(lines)


def _first_sentence(text: str) -> str:
    cleaned = " ".join((text or "").split())
    for delimiter in [". ", "? ", "! "]:
        if delimiter in cleaned:
            return cleaned.split(delimiter, 1)[0].strip() + delimiter.strip()
    return cleaned


def _limit(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3].rstrip() + "..."
