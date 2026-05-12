from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_radar.config import Settings, get_settings
from research_radar.models import RssItem

LOGGER = logging.getLogger(__name__)


@dataclass
class RssIngestResult:
    source: str = "rss"
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    message: str = ""


def ingest_rss(session: Session, settings: Settings | None = None) -> RssIngestResult:
    settings = settings or get_settings()
    feeds = _load_feeds(settings)
    result = RssIngestResult()
    if not feeds:
        result.message = "no RSS feeds configured"
        return result

    for feed in feeds:
        name = str(feed.get("name") or feed.get("url") or "RSS")
        url = str(feed.get("url") or "")
        if not url:
            result.skipped += 1
            continue
        parsed = feedparser.parse(url)
        if parsed.bozo:
            LOGGER.warning("RSS feed parse issue for %s: %s", url, parsed.bozo_exception)
        for entry in parsed.entries:
            result.fetched += 1
            item_url = entry.get("link", "")
            if not item_url:
                result.skipped += 1
                continue
            existing = session.scalar(select(RssItem).where(RssItem.url == item_url))
            data = {
                "title": _clean(entry.get("title", "")),
                "url": item_url,
                "source": name,
                "summary": _clean(entry.get("summary", entry.get("description", ""))),
                "published_at": _entry_date(entry),
            }
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                result.updated += 1
            else:
                session.add(RssItem(**data))
                result.created += 1
    session.commit()
    result.message = f"fetched={result.fetched} created={result.created} updated={result.updated}"
    return result


def _load_feeds(settings: Settings) -> list[dict[str, Any]]:
    path = settings.path(settings.rss_feeds_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    feeds = loaded.get("feeds", [])
    return feeds if isinstance(feeds, list) else []


def _entry_date(entry: Any) -> datetime | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            try:
                return parsedate_to_datetime(value).replace(tzinfo=None)
            except (TypeError, ValueError, AttributeError):
                return None
    return None


def _clean(text: str) -> str:
    return " ".join((text or "").split())
