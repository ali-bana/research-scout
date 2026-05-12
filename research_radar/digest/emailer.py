from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from research_radar.config import Settings, get_settings
from research_radar.digest.formatting import digest_email_html
from research_radar.models import Digest, DigestItem, utcnow

LOGGER = logging.getLogger(__name__)


@dataclass
class EmailResult:
    status: str
    message: str


def send_latest_digest(session: Session, settings: Settings | None = None) -> EmailResult:
    settings = settings or get_settings()
    digest = session.scalar(
        select(Digest)
        .options(selectinload(Digest.items).selectinload(DigestItem.paper))
        .order_by(Digest.generated_at.desc())
        .limit(1)
    )
    if digest is None:
        return EmailResult(status="skipped", message="email skipped: no digest exists")
    return send_digest(session, digest, settings)


def send_digest(session: Session, digest: Digest, settings: Settings | None = None) -> EmailResult:
    settings = settings or get_settings()
    missing = [
        name
        for name, value in {
            "SMTP_HOST": settings.smtp_host,
            "SMTP_FROM": settings.smtp_from,
            "DIGEST_TO_EMAIL": settings.digest_to_email,
        }.items()
        if not value
    ]
    if missing:
        message = f"email skipped: missing {', '.join(missing)}"
        LOGGER.info(message)
        return EmailResult(status="skipped", message=message)

    message = EmailMessage()
    message["Subject"] = digest.title
    message["From"] = settings.smtp_from
    message["To"] = settings.digest_to_email
    plain = _plain_digest(digest)
    html = digest_email_html(digest)
    message.set_content(plain)
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except OSError as exc:
        LOGGER.warning("SMTP send failed: %s", exc)
        return EmailResult(status="error", message=str(exc))

    digest.email_sent_at = utcnow()
    session.commit()
    return EmailResult(status="sent", message=f"sent to {settings.digest_to_email}")


def _plain_digest(digest: Digest) -> str:
    lines = [digest.title, ""]
    if digest.summary_markdown:
        lines.extend([digest.summary_markdown, ""])
    for item in digest.items:
        reason = item.llm_selection_reason or item.selection_reason
        lines.extend(
            [
                f"{item.rank}. {item.paper.title}",
                f"Score: {item.score:.2f}",
                f"Reason: {reason}",
                item.short_explanation,
                item.paper.url,
                "",
            ]
        )
    return "\n".join(lines)
