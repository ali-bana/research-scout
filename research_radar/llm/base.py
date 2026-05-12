from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from research_radar.config import Settings


@dataclass
class PaperSummary:
    short_explanation: str


class LLMProvider(ABC):
    name: str = "base"

    @property
    def configured(self) -> bool:
        return True

    @abstractmethod
    def summarize_paper(self, title: str, abstract: str, profile_context: str) -> PaperSummary:
        raise NotImplementedError

    @abstractmethod
    def explain_relevance(
        self, paper: Any, profile_context: str, score_breakdown: dict[str, Any]
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_digest(self, digest_items: list[Any], profile_context: str) -> str:
        raise NotImplementedError


def provider_from_settings(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        from research_radar.llm.ollama import OllamaProvider

        candidate = OllamaProvider(settings.ollama_base_url, settings.ollama_model)
        return candidate if candidate.configured else _mock()
    if provider in {"openai", "openai-compatible", "openai_compatible"}:
        from research_radar.llm.openai_compatible import OpenAICompatibleProvider

        candidate = OpenAICompatibleProvider(
            settings.openai_base_url, settings.openai_api_key, settings.openai_model
        )
        return candidate if candidate.configured else _mock()
    return _mock()


def _mock() -> LLMProvider:
    from research_radar.llm.mock import MockLLMProvider

    return MockLLMProvider()
