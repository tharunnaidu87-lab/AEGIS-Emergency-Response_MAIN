"""Minimal stateless authority authentication for the AEGIS Command Center.

The Command username/password/signing secret come only from backend environment
variables. Public intake remains open. Authority and resource-scoped responder sessions
are enforced at the API boundary; all resources are local simulations.
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


router = APIRouter(tags=["staff-auth"])
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


def create_command_token(username: str, role="AUTHORITY") -> tuple[str, int]:
    _, _, secret = _settings()
    if not secret:
        raise HTTPException(503, "Command authentication is not configured.")

    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = {
        "sub": username,
        "role": role,
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
        if not isinstance(payload, dict) or payload.get("role") not in {"AUTHORITY", "RESPONDER"}:
            raise ValueError("invalid role")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        username, _, _ = _settings()
        if payload["role"] == "RESPONDER":
            username = str(payload.get("sub", "")) if str(payload.get("sub", "")) in responder_accounts() else ""
        if not username or not _equal(str(payload.get("sub", "")), username):
            raise ValueError("invalid subject")
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error, AttributeError, UnicodeError) as error:
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
    payload = validate_command_token(_bearer_token(request))
    if payload["role"] != "AUTHORITY":
        raise ValueError("Authority required")
    return payload


@router.post("/auth/command/login")
def command_login(credentials: CommandLoginRequest):
    username, password, secret = _settings()
    if not username or not password or not secret:
        raise HTTPException(503, "Command authentication is not configured.")

    username_ok = _equal(credentials.username, username)
    password_ok = _equal(credentials.password, password)
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


@router.get("/auth/command/session")
def command_session(request: Request):
    try:
        payload = require_authority(request)
    except ValueError:
        raise HTTPException(401, "Sign in to continue.") from None
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
        ("POST", "/demo/reset"),
        ("GET", "/distress"),
    }
    if (method, path) in exact:
        return True

    if method == "GET" and re.fullmatch(r"/fusion/[^/]+/reports", path):
        return True
    if method == "PATCH" and re.fullmatch(r"/reports/[^/]+/status", path):
        return True
    if method == "POST" and re.fullmatch(r"/reports/[^/]+/dispatch", path):
        return True

    if path.startswith("/distress/") and method == "PATCH":
        return True
    if path.endswith("/reassign") and path.startswith("/assignments/"):
        return True
    return False


class CommandAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if request.method == "OPTIONS":
            return await call_next(request)
        try:
            if request.method == "POST" and path in {"/reports", "/distress", "/intake/parse", "/voice/transcribe"} and request.headers.get("authorization"):
                staff = validate_command_token(_bearer_token(request))
                if staff["role"] == "RESPONDER":
                    return JSONResponse(status_code=403, content={"detail": "Use the citizen reporting interface to create a report."})
            if _is_command_only(request.method, path):
                require_authority(request)
            elif path.startswith("/assignments"):
                payload = validate_command_token(_bearer_token(request))
                request.state.staff = payload
                if payload["role"] == "RESPONDER":
                    import db
                    if path == "/assignments":
                        if request.query_params.get("resource_id") != payload["sub"]:
                            return JSONResponse(status_code=403, content={"detail": "Only your assigned unit is accessible."})
                    else:
                        assignment = db.get_assignment(path.split("/")[2])
                        if not assignment or assignment["resource_id"] != payload["sub"]:
                            return JSONResponse(status_code=403, content={"detail": "Only your missions are accessible."})
            elif request.method == "GET" and re.fullmatch(r"/reports/[^/]+", path):
                import intake_delivery
                intake_delivery.authorize_report(request, path.split("/")[2])
        except (ValueError, HTTPException):
            return JSONResponse(status_code=401, content={"detail": "Sign in or open the report from your saved receipt."},
                                headers={"WWW-Authenticate": "Bearer"})
        response = await call_next(request)
        if path.startswith(("/auth/", "/reports", "/assignments", "/distress", "/media/")):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def _equal(left, right):
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def responder_accounts():
    # Map demo resource IDs to passwords. Never ship a production default.
    try:
        accounts = json.loads(os.getenv("AEGIS_RESPONDER_ACCOUNTS", "{}"))
        from engines.resource_engine import load_resources
        ids = {r["id"] for r in load_resources()}
        return {k: v for k, v in accounts.items() if k in ids and isinstance(v, str) and v}
    except (ValueError, AttributeError):
        return {}


@router.post("/auth/responder/login")
def responder_login(credentials: CommandLoginRequest):
    accounts = responder_accounts()
    if not accounts:
        raise HTTPException(503, "Responder access needs local administrator configuration.")
    if not _equal(credentials.password, accounts.get(credentials.username, "")) or credentials.username not in accounts:
        raise HTTPException(401, "Check your unit ID and password.")
    token, expires = create_command_token(credentials.username, "RESPONDER")
    return {"token": token, "expires_at": expires, "role": "RESPONDER", "username": credentials.username}


@router.get("/auth/responder/session")
def responder_session(request: Request):
    try:
        payload = validate_command_token(_bearer_token(request))
        if payload["role"] != "RESPONDER":
            raise ValueError("wrong role")
        return {"role": payload["role"], "username": payload["sub"], "expires_at": payload["exp"]}
    except ValueError:
        raise HTTPException(401, "Sign in to your responder unit.") from None
