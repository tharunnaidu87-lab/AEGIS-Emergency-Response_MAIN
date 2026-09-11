"""Minimal stateless authority authentication for the AEGIS Command Center.

The Command username/password/signing secret come only from backend environment
variables. Public reporting and responder flows remain unauthenticated for the
prototype; Command-only routes are enforced here at the API boundary.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


router = APIRouter(prefix="/auth/command", tags=["command-auth"])
TOKEN_TTL_SECONDS = 8 * 60 * 60


class CommandLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=300)


def _settings():
    return (
        os.getenv("AEGIS_COMMAND_USERNAME", "").strip(),
        os.getenv("AEGIS_COMMAND_PASSWORD", ""),
        os.getenv("AEGIS_COMMAND_AUTH_SECRET", ""),
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload_part: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def create_command_token(username: str) -> tuple[str, int]:
    _, _, secret = _settings()
    if not secret:
        raise HTTPException(503, "Command authentication is not configured.")

    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = {
        "sub": username,
        "role": "AUTHORITY",
        "exp": expires_at,
        "iat": int(time.time()),
    }
    payload_part = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{payload_part}.{_sign(payload_part, secret)}", expires_at


def validate_command_token(token: str) -> dict:
    _, _, secret = _settings()
    if not secret:
        raise ValueError("authentication unavailable")

    try:
        payload_part, signature = token.split(".", 1)
        expected = _sign(payload_part, secret)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(_b64decode(payload_part))
        if payload.get("role") != "AUTHORITY":
            raise ValueError("invalid role")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        username, _, _ = _settings()
        if not username or not hmac.compare_digest(str(payload.get("sub", "")), username):
            raise ValueError("invalid subject")
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error) as error:
        raise ValueError("invalid command session") from error


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise ValueError("missing bearer token")
    token = authorization[7:].strip()
    if not token:
        raise ValueError("missing bearer token")
    return token


def require_authority(request: Request) -> dict:
    return validate_command_token(_bearer_token(request))


@router.post("/login")
def command_login(credentials: CommandLoginRequest):
    username, password, secret = _settings()
    if not username or not password or not secret:
        raise HTTPException(503, "Command authentication is not configured.")

    username_ok = hmac.compare_digest(credentials.username, username)
    password_ok = hmac.compare_digest(credentials.password, password)
    if not (username_ok and password_ok):
        raise HTTPException(401, "Invalid authority credentials.")

    token, expires_at = create_command_token(username)
    return {
        "status": "AUTHENTICATED",
        "role": "AUTHORITY",
        "username": username,
        "token": token,
        "expires_at": expires_at,
        "expires_in": TOKEN_TTL_SECONDS,
    }


@router.get("/session")
def command_session(request: Request):
    payload = require_authority(request)
    return {
        "status": "AUTHENTICATED",
        "role": payload["role"],
        "username": payload["sub"],
        "expires_at": payload["exp"],
    }


def _is_command_only(method: str, path: str) -> bool:
    method = method.upper()

    exact = {
        ("POST", "/aegis-analyse"),
        ("POST", "/incident"),
        ("GET", "/resources"),
        ("GET", "/relocation-centres"),
        ("POST", "/relocation-plan"),
        ("POST", "/hazard-analysis"),
        ("GET", "/reports"),
        ("GET", "/audit-events"),
    }
    if (method, path) in exact:
        return True

    if method == "GET" and re.fullmatch(r"/fusion/[^/]+/reports", path):
        return True
    if method == "PATCH" and re.fullmatch(r"/reports/[^/]+/status", path):
        return True
    if method == "POST" and re.fullmatch(r"/reports/[^/]+/dispatch", path):
        return True

    return False


class CommandAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or not _is_command_only(request.method, request.url.path):
            return await call_next(request)

        try:
            require_authority(request)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authority authentication required."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
