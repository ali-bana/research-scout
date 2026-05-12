from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
CSRF_SESSION_KEY = "csrf_token"


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode("ascii").rstrip("="),
            base64.b64encode(digest).decode("ascii").rstrip("="),
        ]
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(raw_iterations)
        salt = _b64decode(raw_salt)
        expected = _b64decode(raw_digest)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding)


def csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, submitted_token: str | None) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected or not submitted_token or not hmac.compare_digest(expected, submitted_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def require_login(request: Request) -> None:
    if not request.session.get("admin_authenticated"):
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})


@dataclass(frozen=True)
class SecurityWarning:
    code: str
    message: str


def deployment_warnings(
    app_secret_key: str, admin_password_hash: str, host: str
) -> list[SecurityWarning]:
    warnings: list[SecurityWarning] = []
    if not app_secret_key:
        warnings.append(SecurityWarning("missing-secret", "APP_SECRET_KEY is not configured."))
    elif app_secret_key.startswith("change-me"):
        warnings.append(
            SecurityWarning("placeholder-secret", "APP_SECRET_KEY still uses the example value.")
        )
    if not admin_password_hash:
        warnings.append(
            SecurityWarning("missing-password", "ADMIN_PASSWORD_HASH is not configured.")
        )
    if host != "127.0.0.1":
        warnings.append(
            SecurityWarning("public-bind", "The app is not bound to 127.0.0.1. Use TLS/VPN.")
        )
    return warnings
