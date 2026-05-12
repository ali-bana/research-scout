from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_radar.config import Settings, get_settings
from research_radar.models import Paper, utcnow

LOGGER = logging.getLogger(__name__)
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


@dataclass
class IngestResult:
    source: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    message: str = ""


def ingest_arxiv(session: Session, settings: Settings | None = None) -> IngestResult:
    settings = settings or get_settings()
    categories = settings.arxiv_category_list
    if not categories:
        return IngestResult(source="arxiv", message="no categories configured")
    query = "+OR+".join(f"cat:{quote_plus(category)}" for category in categories)
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={query}&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={settings.arxiv_max_results}"
    )
    try:
        response = httpx.get(url, timeout=settings.http_timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        LOGGER.warning("arXiv ingestion failed: %s", exc)
        return IngestResult(source="arxiv", message=f"arXiv skipped: {exc}")

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        LOGGER.warning("arXiv response parse failed: %s", exc)
        return IngestResult(source="arxiv", message=f"arXiv parse skipped: {exc}")

    result = IngestResult(source="arxiv")
    for entry in root.findall(f"{ATOM}entry"):
        result.fetched += 1
        paper_data = _entry_to_paper(entry)
        if not paper_data["title"] or not paper_data["url"]:
            result.skipped += 1
            continue
        existing = None
        if paper_data["arxiv_id"]:
            existing = session.scalar(select(Paper).where(Paper.arxiv_id == paper_data["arxiv_id"]))
        if existing is None:
            existing = session.scalar(select(Paper).where(Paper.url == paper_data["url"]))
        if existing:
            for key, value in paper_data.items():
                setattr(existing, key, value)
            existing.seen_at = utcnow()
            result.updated += 1
        else:
            session.add(Paper(**paper_data))
            result.created += 1
    session.commit()
    result.message = f"fetched={result.fetched} created={result.created} updated={result.updated}"
    return result


def _entry_to_paper(entry: ET.Element) -> dict[str, object]:
    entry_id = _text(entry, f"{ATOM}id")
    arxiv_id = entry_id.rsplit("/", 1)[-1] if entry_id else None
    url = entry_id
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("type") == "text/html" or link.attrib.get("rel") == "alternate":
            url = link.attrib.get("href", url)
    authors = ", ".join(_text(author, f"{ATOM}name") for author in entry.findall(f"{ATOM}author"))
    categories = ", ".join(
        category.attrib.get("term", "") for category in entry.findall(f"{ATOM}category")
    )
    return {
        "source": "arxiv",
        "title": _clean(_text(entry, f"{ATOM}title")),
        "authors": authors,
        "abstract": _clean(_text(entry, f"{ATOM}summary")),
        "arxiv_id": arxiv_id,
        "categories": categories,
        "published_at": _parse_dt(_text(entry, f"{ATOM}published")),
        "updated_at": _parse_dt(_text(entry, f"{ATOM}updated")),
        "url": url or "",
    }


def _text(element: ET.Element, path: str) -> str:
    found = element.find(path)
    if found is None or found.text is None:
        return ""
    return found.text


def _clean(text: str) -> str:
    return " ".join(text.split())


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None
