from __future__ import annotations

from typing import Any

import httpx

from research_radar.llm.base import LLMProvider, PaperSummary


class OpenAICompatibleProvider(LLMProvider):
    """Minimal OpenAI-compatible Chat Completions client.

    The official OpenAI OpenAPI spec exposes POST /chat/completions under /v1.
    Many local servers, including vLLM, mirror this shape.
    """

    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def summarize_paper(self, title: str, abstract: str, profile_context: str) -> PaperSummary:
        content = self._chat(
            "Write a concise, researcher-facing explanation of why this paper may matter. "
            "Keep it under 80 words.",
            f"Profile:\n{profile_context}\n\nTitle: {title}\nAbstract: {abstract}",
            max_tokens=180,
        )
        return PaperSummary(short_explanation=content)

    def explain_relevance(
        self, paper: Any, profile_context: str, score_breakdown: dict[str, Any]
    ) -> str:
        return self._chat(
            "Write one sentence beginning with 'Chosen because' that explains why this paper was "
            "selected. Mention the strongest concrete match. Keep it under 35 words.",
            f"Profile:\n{profile_context}\n\nTitle: {paper.title}\nAbstract: {paper.abstract}\n"
            f"Signals: {score_breakdown}",
            max_tokens=90,
        )

    def generate_digest(self, digest_items: list[Any], profile_context: str) -> str:
        papers = "\n".join(
            f"- {item.paper.title}: {item.llm_selection_reason or item.selection_reason}"
            for item in digest_items
        )
        return self._chat(
            "Create a compact research digest in Markdown for one researcher. "
            "Do not invent papers or links.",
            f"Profile:\n{profile_context}\n\nSelected papers:\n{papers}",
            max_tokens=700,
        )

    def _chat(self, system_prompt: str, user_prompt: str, *, max_tokens: int) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            return ""
        return " ".join((choices[0].get("message", {}).get("content") or "").split())
