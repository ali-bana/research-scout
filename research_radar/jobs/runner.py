from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from research_radar.db import SessionLocal
from research_radar.models import JobLog, utcnow

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


def run_job(job_name: str, work: Callable[[], T]) -> T:
    started_at = utcnow()
    with SessionLocal() as session:
        log = JobLog(job_name=job_name, status="running", started_at=started_at)
        session.add(log)
        session.commit()
        log_id = log.id
    try:
        result = work()
    except Exception as exc:
        LOGGER.exception("Job failed: %s", job_name)
        with SessionLocal() as session:
            log = session.get(JobLog, log_id)
            if log:
                log.status = "error"
                log.message = str(exc)
                log.finished_at = utcnow()
                session.commit()
        raise
    with SessionLocal() as session:
        log = session.get(JobLog, log_id)
        if log:
            log.status = "ok"
            log.message = _message(result)
            log.details = _details(result)
            log.finished_at = utcnow()
            session.commit()
    return result


def record_job(
    job_name: str, status: str, message: str, details: dict[str, Any] | None = None
) -> None:
    with SessionLocal() as session:
        session.add(
            JobLog(
                job_name=job_name,
                status=status,
                message=message,
                details=details or {},
                finished_at=utcnow(),
            )
        )
        session.commit()


def _message(result: Any) -> str:
    if hasattr(result, "message"):
        return str(result.message)
    if hasattr(result, "title"):
        return str(result.title)
    return str(result)


def _details(result: Any) -> dict[str, Any]:
    if hasattr(result, "__dict__"):
        return {
            key: value
            for key, value in result.__dict__.items()
            if isinstance(value, str | int | float | bool | type(None))
        }
    return {}
