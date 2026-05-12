from __future__ import annotations

import re
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_radar.config import Settings, get_settings
from research_radar.models import NotionSnapshot

PROFILE_KEYS = [
    "current_projects",
    "high_priority_topics",
    "broader_watchlist",
    "negative_topics",
    "seed_papers_i_like",
    "authors_labs_to_watch",
]


def load_profile(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = settings.path(settings.profile_path)
    if not path.exists():
        return empty_profile()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    profile = empty_profile()
    profile.update({key: loaded.get(key, profile[key]) for key in PROFILE_KEYS})
    return profile


def save_profile_yaml(raw_yaml: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed = yaml.safe_load(raw_yaml) or {}
    if not isinstance(parsed, dict):
        raise ValueError("Profile YAML must be a mapping.")
    profile = empty_profile()
    for key in PROFILE_KEYS:
        value = parsed.get(key, profile[key])
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list.")
        profile[key] = value
    path = settings.path(settings.profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return profile


def profile_yaml(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    path = settings.path(settings.profile_path)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return yaml.safe_dump(empty_profile(), sort_keys=False)


def empty_profile() -> dict[str, list[Any]]:
    return {
        "current_projects": [],
        "high_priority_topics": [],
        "broader_watchlist": [],
        "negative_topics": [],
        "seed_papers_i_like": [],
        "authors_labs_to_watch": [],
    }


def latest_notion_text(session: Session) -> str:
    snapshot = session.scalars(
        select(NotionSnapshot).order_by(NotionSnapshot.created_at.desc()).limit(1)
    ).first()
    if not snapshot or snapshot.status != "ok":
        return ""
    return snapshot.text


def profile_context(profile: dict[str, Any], notion_text: str = "") -> str:
    sections: list[str] = []
    for key in PROFILE_KEYS:
        values = profile.get(key) or []
        if values:
            rendered = "; ".join(_render_profile_value(value) for value in values)
            sections.append(f"{key}: {rendered}")
    if notion_text:
        sections.append(f"notion_watchlist: {notion_text[:3000]}")
    return "\n".join(sections)


def profile_terms(profile: dict[str, Any], include_negative: bool = False) -> list[str]:
    keys = [
        "current_projects",
        "high_priority_topics",
        "broader_watchlist",
        "seed_papers_i_like",
        "authors_labs_to_watch",
    ]
    if include_negative:
        keys.append("negative_topics")
    terms: list[str] = []
    for key in keys:
        for value in profile.get(key, []) or []:
            terms.extend(extract_terms(_render_profile_value(value)))
    return sorted(set(terms))


def extract_terms(text: str, *, min_len: int = 3) -> list[str]:
    phrases = re.findall(r"[A-Za-z][A-Za-z0-9+.-]*(?:[ -][A-Za-z][A-Za-z0-9+.-]*){0,3}", text)
    terms: list[str] = []
    for phrase in phrases:
        normalized = normalize_text(phrase).strip()
        if len(normalized) >= min_len and not normalized.isdigit():
            terms.append(normalized)
    return terms


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9+.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _render_profile_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = [str(value.get("title", "")), str(value.get("note", ""))]
        return " ".join(part for part in parts if part)
    return str(value)
