from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from research_radar.auth import csrf_token, deployment_warnings, validate_csrf, verify_password
from research_radar.config import get_settings
from research_radar.db import SessionLocal
from research_radar.digest.daily import generate_daily_digest
from research_radar.digest.emailer import send_latest_digest
from research_radar.digest.weekly import generate_weekly_discovery
from research_radar.ingest.arxiv import ingest_arxiv
from research_radar.ingest.notion import ingest_notion, notion_status
from research_radar.ingest.rss import ingest_rss
from research_radar.ingest.x_placeholder import XReadOnlyConnector
from research_radar.jobs.runner import run_job
from research_radar.llm.base import provider_from_settings
from research_radar.llm.mock import MockLLMProvider
from research_radar.models import (
    Digest,
    DigestItem,
    Feedback,
    JobLog,
    NotionSnapshot,
    Paper,
    RssItem,
)
from research_radar.ranking.profile import (
    extract_terms,
    latest_notion_text,
    load_profile,
    profile_context,
    profile_yaml,
)
from research_radar.ranking.profile import save_profile_yaml as persist_profile_yaml

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return _render(request, "login.html")


@router.post("/login")
async def login(request: Request):
    form = await request.form()
    validate_csrf(request, str(form.get("csrf_token", "")))
    settings = get_settings()
    password = str(form.get("password", ""))
    if settings.admin_password_hash and verify_password(password, settings.admin_password_hash):
        request.session["admin_authenticated"] = True
        _flash(request, "Signed in.")
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", error="Invalid password.")


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    form = await request.form()
    validate_csrf(request, str(form.get("csrf_token", "")))
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        latest_daily = _latest_digest(session, "daily")
        latest_weekly = _latest_digest(session, "weekly")
        counts = {
            "papers": session.scalar(select(func.count(Paper.id))) or 0,
            "rss": session.scalar(select(func.count(RssItem.id))) or 0,
            "digests": session.scalar(select(func.count(Digest.id))) or 0,
            "feedback": session.scalar(select(func.count(Feedback.id))) or 0,
        }
        jobs = list(session.scalars(select(JobLog).order_by(JobLog.started_at.desc()).limit(5)))
    return _render(
        request,
        "dashboard.html",
        latest_daily=latest_daily,
        latest_weekly=latest_weekly,
        counts=counts,
        jobs=jobs,
        notion_status=notion_status(),
        x_status=XReadOnlyConnector().status(),
    )


@router.get("/digests/latest", response_class=HTMLResponse)
def latest_digest(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        digest = _latest_digest(session, "daily")
    return _render(request, "digest.html", digest=digest, title="Latest Daily Digest")


@router.get("/weekly", response_class=HTMLResponse)
def weekly_digest(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        digest = _latest_digest(session, "weekly")
    return _render(request, "digest.html", digest=digest, title="Weekly Discovery")


@router.get("/digests/history", response_class=HTMLResponse)
def digest_history(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        digests = list(
            session.scalars(select(Digest).order_by(Digest.generated_at.desc()).limit(100))
        )
    return _render(request, "history.html", digests=digests)


@router.get("/digests/{digest_id}", response_class=HTMLResponse)
def digest_detail(request: Request, digest_id: int):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        digest = _digest_by_id(session, digest_id)
    title = digest.title if digest else "Digest"
    return _render(request, "digest.html", digest=digest, title=title)


@router.get("/papers", response_class=HTMLResponse)
def papers(request: Request, q: str = ""):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        statement = select(Paper).order_by(
            Paper.published_at.desc().nullslast(), Paper.seen_at.desc()
        )
        if q:
            like = f"%{q}%"
            statement = statement.where(
                or_(Paper.title.ilike(like), Paper.abstract.ilike(like), Paper.authors.ilike(like))
            )
        results = list(session.scalars(statement.limit(100)))
    return _render(request, "papers.html", papers=results, q=q)


@router.get("/rss", response_class=HTMLResponse)
def rss_items(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        items = list(
            session.scalars(select(RssItem).order_by(RssItem.published_at.desc().nullslast()).limit(100))
        )
    return _render(request, "rss.html", items=items)


@router.get("/notion", response_class=HTMLResponse)
def notion(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        snapshots = list(
            session.scalars(select(NotionSnapshot).order_by(NotionSnapshot.created_at.desc()).limit(20))
        )
    return _render(request, "notion.html", snapshots=snapshots, status=notion_status())


@router.get("/feedback", response_class=HTMLResponse)
def feedback_dashboard(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        counts = dict(
            session.execute(select(Feedback.label, func.count()).group_by(Feedback.label)).all()
        )
        recent = list(
            session.scalars(
                select(Feedback)
                .options(selectinload(Feedback.paper))
                .order_by(Feedback.created_at.desc())
                .limit(30)
            )
        )
        boosted, penalized = _feedback_topic_counters(session)
    return _render(
        request,
        "feedback.html",
        counts=counts,
        recent=recent,
        boosted=boosted.most_common(12),
        penalized=penalized.most_common(12),
    )


@router.post("/feedback/{digest_item_id}")
async def record_feedback(
    request: Request,
    digest_item_id: int,
    label: str = Form(...),
    notes: str = Form(""),
    csrf_token_value: str = Form(..., alias="csrf_token"),
) -> RedirectResponse:
    validate_csrf(request, csrf_token_value)
    guard = _guard(request)
    if guard:
        return guard
    allowed = {"very_relevant", "relevant", "not_relevant", "already_knew", "read_later"}
    if label not in allowed:
        _flash(request, "Unknown feedback label.")
        return RedirectResponse("/feedback", status_code=303)
    with SessionLocal() as session:
        item = session.get(DigestItem, digest_item_id)
        if item:
            session.add(
                Feedback(
                    digest_item_id=item.id,
                    paper_id=item.paper_id,
                    label=label,
                    notes=notes,
                )
            )
            session.commit()
            _flash(request, "Feedback recorded.")
    return _back(request)


@router.get("/settings/profile", response_class=HTMLResponse)
def profile_editor(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    return _render(request, "profile.html", profile_text=profile_yaml())


@router.post("/settings/profile")
async def save_profile(request: Request):
    form = await request.form()
    validate_csrf(request, str(form.get("csrf_token", "")))
    guard = _guard(request)
    if guard:
        return guard
    raw_yaml = str(form.get("profile_text", ""))
    try:
        persist_profile_yaml(raw_yaml)
    except ValueError as exc:
        return _render(request, "profile.html", profile_text=raw_yaml, error=str(exc))
    _flash(request, "Profile saved.")
    return RedirectResponse("/settings/profile", status_code=303)


@router.get("/jobs", response_class=HTMLResponse)
def jobs(request: Request):
    guard = _guard(request)
    if guard:
        return guard
    with SessionLocal() as session:
        logs = list(session.scalars(select(JobLog).order_by(JobLog.started_at.desc()).limit(100)))
    return _render(request, "jobs.html", logs=logs)


@router.post("/actions/ingest")
async def action_ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    csrf_token_value: str = Form(..., alias="csrf_token"),
) -> RedirectResponse:
    validate_csrf(request, csrf_token_value)
    guard = _guard(request)
    if guard:
        return guard
    background_tasks.add_task(run_job, "manual_ingest", _ingest_sources)
    _flash(request, "Ingestion job started.")
    return RedirectResponse("/", status_code=303)


@router.post("/actions/generate-daily")
async def action_generate_daily(
    request: Request,
    background_tasks: BackgroundTasks,
    csrf_token_value: str = Form(..., alias="csrf_token"),
) -> RedirectResponse:
    validate_csrf(request, csrf_token_value)
    guard = _guard(request)
    if guard:
        return guard
    background_tasks.add_task(run_job, "manual_generate_daily", _generate_daily)
    _flash(request, "Daily digest job started.")
    return RedirectResponse("/", status_code=303)


@router.post("/actions/discover-weekly")
async def action_discover_weekly(
    request: Request,
    background_tasks: BackgroundTasks,
    csrf_token_value: str = Form(..., alias="csrf_token"),
) -> RedirectResponse:
    validate_csrf(request, csrf_token_value)
    guard = _guard(request)
    if guard:
        return guard
    background_tasks.add_task(run_job, "manual_discover_weekly", _generate_weekly)
    _flash(request, "Weekly discovery job started.")
    return RedirectResponse("/", status_code=303)


@router.post("/actions/send-latest-email")
async def action_send_latest_email(
    request: Request,
    background_tasks: BackgroundTasks,
    csrf_token_value: str = Form(..., alias="csrf_token"),
) -> RedirectResponse:
    validate_csrf(request, csrf_token_value)
    guard = _guard(request)
    if guard:
        return guard
    background_tasks.add_task(run_job, "manual_send_latest_email", _send_latest_email)
    _flash(request, "Email job started.")
    return RedirectResponse("/", status_code=303)


@router.post("/digest-items/{digest_item_id}/refresh-explanation")
async def refresh_explanation(
    request: Request,
    background_tasks: BackgroundTasks,
    digest_item_id: int,
    csrf_token_value: str = Form(..., alias="csrf_token"),
) -> RedirectResponse:
    validate_csrf(request, csrf_token_value)
    guard = _guard(request)
    if guard:
        return guard
    background_tasks.add_task(
        run_job, "manual_refresh_explanation", lambda: _refresh_item(digest_item_id)
    )
    _flash(request, "Explanation refresh started.")
    return _back(request)


def _guard(request: Request) -> RedirectResponse | None:
    if not request.session.get("admin_authenticated"):
        return RedirectResponse("/login", status_code=303)
    return None


def _back(request: Request) -> RedirectResponse:
    target = str(request.headers.get("referer") or "/digests/latest")
    return RedirectResponse(target, status_code=303)


def _render(request: Request, template: str, **context: Any) -> HTMLResponse:
    settings = get_settings()
    base = {
        "request": request,
        "csrf_token": csrf_token(request),
        "authenticated": bool(request.session.get("admin_authenticated")),
        "flash": request.session.pop("flash", None),
        "warnings": deployment_warnings(
            settings.app_secret_key, settings.admin_password_hash, settings.app_host
        ),
        "settings": settings,
    }
    base.update(context)
    return templates.TemplateResponse(request, template, base)


def _flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def _latest_digest(session, digest_type: str) -> Digest | None:
    return session.scalar(
        select(Digest)
        .where(Digest.digest_type == digest_type)
        .options(selectinload(Digest.items).selectinload(DigestItem.paper))
        .order_by(Digest.generated_at.desc())
        .limit(1)
    )


def _digest_by_id(session, digest_id: int) -> Digest | None:
    return session.scalar(
        select(Digest)
        .where(Digest.id == digest_id)
        .options(selectinload(Digest.items).selectinload(DigestItem.paper))
    )


def _ingest_sources() -> str:
    with SessionLocal() as session:
        arxiv = ingest_arxiv(session)
        rss = ingest_rss(session)
        notion_result = ingest_notion(session)
        return " | ".join([arxiv.message, rss.message, notion_result.message])


def _generate_daily() -> Digest:
    with SessionLocal() as session:
        return generate_daily_digest(session)


def _generate_weekly() -> Digest:
    with SessionLocal() as session:
        return generate_weekly_discovery(session)


def _send_latest_email() -> str:
    with SessionLocal() as session:
        return send_latest_digest(session).message


def _refresh_item(digest_item_id: int) -> str:
    settings = get_settings()
    with SessionLocal() as session:
        item = session.scalar(
            select(DigestItem)
            .where(DigestItem.id == digest_item_id)
            .options(selectinload(DigestItem.paper))
        )
        if not item:
            return "digest item not found"
        profile = load_profile(settings)
        context = profile_context(profile, latest_notion_text(session))
        provider = provider_from_settings(settings)
        mock = MockLLMProvider()
        try:
            summary = provider.summarize_paper(item.paper.title, item.paper.abstract, context)
            reason = provider.explain_relevance(item.paper, context, item.score_breakdown)
            if provider.name == "mock":
                item.selection_reason = reason
                item.paper.selection_reason = reason
            else:
                item.llm_selection_reason = reason
                item.paper.llm_selection_reason = reason
            item.short_explanation = summary.short_explanation
            item.paper.short_explanation = summary.short_explanation
        except Exception:
            summary = mock.summarize_paper(item.paper.title, item.paper.abstract, context)
            item.short_explanation = summary.short_explanation
        session.commit()
        return "refreshed explanation"


def _feedback_topic_counters(session) -> tuple[Counter[str], Counter[str]]:
    boosted: Counter[str] = Counter()
    penalized: Counter[str] = Counter()
    rows = session.execute(select(Feedback, Paper).join(Paper, Feedback.paper_id == Paper.id)).all()
    for feedback, paper in rows:
        terms = extract_terms(f"{paper.title} {paper.abstract}")[:20]
        if feedback.label in {"very_relevant", "relevant", "read_later"}:
            boosted.update(terms)
        elif feedback.label == "not_relevant":
            penalized.update(terms)
    return boosted, penalized
