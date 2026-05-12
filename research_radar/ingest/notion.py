from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from research_radar.config import Settings, get_settings
from research_radar.models import NotionSnapshot

LOGGER = logging.getLogger(__name__)
NOTION_VERSION = "2022-06-28"


@dataclass
class NotionIngestResult:
    source: str = "notion"
    status: str = "ok"
    snapshots: int = 0
    message: str = ""


def ingest_notion(session: Session, settings: Settings | None = None) -> NotionIngestResult:
    settings = settings or get_settings()
    has_target = settings.notion_page_id_list or settings.notion_database_id
    if not settings.notion_token or not has_target:
        return NotionIngestResult(status="not_configured", message="Notion not configured")

    headers = {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    texts: list[tuple[str, str]] = []
    try:
        with httpx.Client(headers=headers, timeout=settings.http_timeout_seconds) as client:
            for page_id in settings.notion_page_id_list:
                text = _read_block_children(client, page_id)
                texts.append((page_id, text))
            if settings.notion_database_id:
                page_ids = _query_database_pages(client, settings.notion_database_id)
                for page_id in page_ids:
                    text = _read_block_children(client, page_id)
                    texts.append((page_id, text))
    except httpx.HTTPError as exc:
        LOGGER.warning("Notion ingestion failed: %s", exc)
        snapshot = NotionSnapshot(status="error", object_id="", text="", source="notion")
        session.add(snapshot)
        session.commit()
        return NotionIngestResult(status="error", message=f"Notion skipped: {exc}")

    for object_id, text in texts:
        session.add(NotionSnapshot(object_id=object_id, text=text, status="ok", source="notion"))
    session.commit()
    return NotionIngestResult(snapshots=len(texts), message=f"snapshots={len(texts)}")


def notion_status(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    has_target = settings.notion_page_id_list or settings.notion_database_id
    if not settings.notion_token or not has_target:
        return "Notion not configured"
    return "Notion configured"


def _query_database_pages(client: httpx.Client, database_id: str) -> list[str]:
    page_ids: list[str] = []
    has_more = True
    start_cursor: str | None = None
    while has_more:
        payload: dict[str, Any] = {"page_size": 25}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        response = client.post(
            f"https://api.notion.com/v1/databases/{database_id}/query", json=payload
        )
        response.raise_for_status()
        data = response.json()
        page_ids.extend(item["id"] for item in data.get("results", []) if item.get("id"))
        has_more = bool(data.get("has_more"))
        start_cursor = data.get("next_cursor")
    return page_ids


def _read_block_children(client: httpx.Client, block_id: str) -> str:
    lines: list[str] = []
    has_more = True
    start_cursor: str | None = None
    while has_more:
        params: dict[str, Any] = {"page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor
        response = client.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children", params=params
        )
        response.raise_for_status()
        data = response.json()
        for block in data.get("results", []):
            lines.extend(_plain_text_from_block(block))
        has_more = bool(data.get("has_more"))
        start_cursor = data.get("next_cursor")
    return "\n".join(line for line in lines if line).strip()


def _plain_text_from_block(block: dict[str, Any]) -> list[str]:
    block_type = block.get("type")
    content = block.get(block_type or "", {})
    texts: list[str] = []
    for rich_text in content.get("rich_text", []) or []:
        plain = rich_text.get("plain_text", "")
        if plain:
            texts.append(plain)
    title = content.get("title")
    if isinstance(title, list):
        for rich_text in title:
            plain = rich_text.get("plain_text", "")
            if plain:
                texts.append(plain)
    return [" ".join(texts).strip()] if texts else []
