from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from research_radar.auth import deployment_warnings
from research_radar.config import Settings, get_settings
from research_radar.db import init_db
from research_radar.web.routes import router

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    _validate_runtime_settings(settings)
    init_db()
    app = FastAPI(title="Research Radar")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_secret_key,
        same_site="lax",
        https_only=settings.session_https_only,
        session_cookie="research_radar_session",
    )
    app.mount("/static", StaticFiles(directory="research_radar/web/static"), name="static")
    app.include_router(router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline';",
        )
        return response

    return app


def _validate_runtime_settings(settings: Settings) -> None:
    if not settings.app_secret_key:
        raise RuntimeError("APP_SECRET_KEY must be configured before starting the web app.")
    for warning in deployment_warnings(
        settings.app_secret_key, settings.admin_password_hash, settings.app_host
    ):
        LOGGER.warning("Deployment warning: %s", warning.message)
