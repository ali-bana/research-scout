from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from research_radar.config import Settings, get_settings


@dataclass
class ConnectorResult:
    status: str
    data: dict[str, Any] | list[Any] | None = None
    message: str = ""


class SemanticScholarConnector:
    base_url = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.semantic_scholar_api_key)

    def get_paper_metadata(self, paper_id: str) -> ConnectorResult:
        if not self.configured:
            return _not_configured()
        fields = "title,authors,abstract,year,citationCount,externalIds,url"
        return self._get(f"/paper/{paper_id}", params={"fields": fields})

    def get_recommendations(self, paper_ids: list[str]) -> ConnectorResult:
        if not self.configured:
            return _not_configured()
        payload = {"positivePaperIds": paper_ids[:20]}
        try:
            response = httpx.post(
                f"{self.base_url}/recommendations/v1/papers",
                headers=self._headers(),
                json=payload,
                timeout=self.settings.http_timeout_seconds,
            )
            response.raise_for_status()
            return ConnectorResult(status="ok", data=response.json())
        except httpx.HTTPError as exc:
            return ConnectorResult(status="error", message=str(exc))

    def get_citation_context(self, paper_id: str) -> ConnectorResult:
        if not self.configured:
            return _not_configured()
        return self._get(
            f"/paper/{paper_id}/citations", params={"fields": "contexts,intents,title"}
        )

    def _get(self, path: str, params: dict[str, str]) -> ConnectorResult:
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
                timeout=self.settings.http_timeout_seconds,
            )
            response.raise_for_status()
            return ConnectorResult(status="ok", data=response.json())
        except httpx.HTTPError as exc:
            return ConnectorResult(status="error", message=str(exc))

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.settings.semantic_scholar_api_key}


def _not_configured() -> ConnectorResult:
    return ConnectorResult(status="not_configured", message="Semantic Scholar API key missing")
