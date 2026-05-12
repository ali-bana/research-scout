from __future__ import annotations

import logging
from typing import Annotated

import typer
import uvicorn
from rich.console import Console

from research_radar.auth import deployment_warnings, hash_password
from research_radar.config import get_settings
from research_radar.db import SessionLocal, init_db
from research_radar.digest.daily import generate_daily_digest
from research_radar.digest.emailer import send_latest_digest
from research_radar.digest.weekly import generate_weekly_discovery
from research_radar.ingest.arxiv import ingest_arxiv
from research_radar.ingest.notion import ingest_notion
from research_radar.ingest.rss import ingest_rss
from research_radar.jobs.runner import run_job

app = typer.Typer(help="Research Radar CLI")
console = Console()


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command("init-db")
def init_db_command() -> None:
    """Create SQLite tables if they do not exist."""
    configure_logging()
    init_db()
    console.print("Database initialized.")


@app.command("ingest")
def ingest_command() -> None:
    """Fetch arXiv, RSS, and Notion inputs."""
    configure_logging()
    init_db()

    def work() -> str:
        with SessionLocal() as session:
            arxiv = ingest_arxiv(session)
            rss = ingest_rss(session)
            notion = ingest_notion(session)
            return " | ".join([arxiv.message, rss.message, notion.message])

    message = run_job("ingest", work)
    console.print(message)


@app.command("generate-daily")
def generate_daily_command() -> None:
    """Generate and store the daily digest."""
    configure_logging()
    init_db()

    def work():
        with SessionLocal() as session:
            return generate_daily_digest(session)

    digest = run_job("generate_daily", work)
    console.print(f"Generated {digest.title} with {digest.item_count} item(s).")


@app.command("send-daily")
def send_daily_command() -> None:
    """Send the latest digest by SMTP if SMTP is configured."""
    configure_logging()
    init_db()

    def work():
        with SessionLocal() as session:
            return send_latest_digest(session)

    result = run_job("send_daily", work)
    console.print(result.message)


@app.command("discover-weekly")
def discover_weekly_command() -> None:
    """Generate and store a weekly discovery digest."""
    configure_logging()
    init_db()

    def work():
        with SessionLocal() as session:
            return generate_weekly_discovery(session)

    digest = run_job("discover_weekly", work)
    console.print(f"Generated {digest.title} with {digest.item_count} item(s).")


@app.command("run-all")
def run_all_command() -> None:
    """Run init-db, ingest, daily digest generation, and email send."""
    init_db_command()
    ingest_command()
    generate_daily_command()
    send_daily_command()


@app.command("hash-password")
def hash_password_command(
    password: Annotated[
        str,
        typer.Option(prompt=True, confirmation_prompt=True, hide_input=True, help="Admin password"),
    ],
) -> None:
    """Hash an admin password for ADMIN_PASSWORD_HASH."""
    console.print(hash_password(password))


@app.command("web")
def web_command() -> None:
    """Start the local FastAPI web app."""
    configure_logging()
    init_db()
    settings = get_settings()
    for warning in deployment_warnings(
        settings.app_secret_key, settings.admin_password_hash, settings.app_host
    ):
        console.print(f"[yellow]Warning:[/] {warning.message}")
    uvicorn.run(
        "research_radar.app:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )
