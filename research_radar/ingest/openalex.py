from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from research_radar.config import Settings, get_settings


@dataclass
class OpenAlexResult:
    status: str
    data: dict[str, Any] | list[Any] | None = None
    message: str = ""


class OpenAlexConnector:
    base_url = "https://api.openalex.org"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.openalex_email
            or self.settings.openalex_api_key
            or self.settings.openalex_token
        )

    def get_paper_metadata(self, paper_id: str) -> OpenAlexResult:
        if not self.configured:
            return OpenAlexResult(status="not_configured", message="OpenAlex not configured")
        return self._get(f"/works/{paper_id}", params={})

    def get_recommendations(self, paper_ids: list[str]) -> OpenAlexResult:
        if not self.configured:
            return OpenAlexResult(status="not_configured", message="OpenAlex not configured")
        filter_value = "|".join(paper_ids[:20])
        return self._get("/works", params={"filter": f"cites:{filter_value}", "per-page": "10"})

    def get_citation_context(self, paper_id: str) -> OpenAlexResult:
        if not self.configured:
            return OpenAlexResult(status="not_configured", message="OpenAlex not configured")
        return self._get("/works", params={"filter": f"cites:{paper_id}", "per-page": "25"})

    def _get(self, path: str, params: dict[str, str]) -> OpenAlexResult:
        request_params = dict(params)
        if self.settings.openalex_email:
            request_params["mailto"] = self.settings.openalex_email
        headers: dict[str, str] = {}
        token = self.settings.openalex_token or self.settings.openalex_api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                params=request_params,
                headers=headers,
                timeout=self.settings.http_timeout_seconds,
            )
            response.raise_for_status()
            return OpenAlexResult(status="ok", data=response.json())
        except httpx.HTTPError as exc:
            return OpenAlexResult(status="error", message=str(exc))
