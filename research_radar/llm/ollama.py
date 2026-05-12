from __future__ import annotations

from typing import Any

import httpx

from research_radar.llm.base import LLMProvider, PaperSummary


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def summarize_paper(self, title: str, abstract: str, profile_context: str) -> PaperSummary:
        prompt = (
            "Write a concise, researcher-facing explanation of why this paper may matter. "
            "Keep it under 80 words.\n\n"
            f"Profile:\n{profile_context}\n\nTitle: {title}\nAbstract: {abstract}"
        )
        return PaperSummary(short_explanation=self._chat(prompt))

    def explain_relevance(
        self, paper: Any, profile_context: str, score_breakdown: dict[str, Any]
    ) -> str:
        prompt = (
            "Write one sentence beginning with 'Chosen because' that explains why this paper was "
            "selected. Mention the strongest concrete match. Keep it under 35 words.\n\n"
            f"Profile:\n{profile_context}\n\nTitle: {paper.title}\nAbstract: {paper.abstract}\n"
            f"Signals: {score_breakdown}"
        )
        return _one_line(self._chat(prompt))

    def generate_digest(self, digest_items: list[Any], profile_context: str) -> str:
        papers = "\n".join(
            f"- {item.paper.title}: {item.llm_selection_reason or item.selection_reason}"
            for item in digest_items
        )
        prompt = (
            "Create a compact daily research digest in Markdown for one researcher. "
            "Do not invent papers or links.\n\n"
            f"Profile:\n{profile_context}\n\nSelected papers:\n{papers}"
        )
        return self._chat(prompt)

    def _chat(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return _one_line(payload.get("message", {}).get("content", "").strip())


def _one_line(text: str) -> str:
    return " ".join((text or "").split())
