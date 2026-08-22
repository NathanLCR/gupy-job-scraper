from datetime import datetime, timedelta
import hashlib
import logging
import secrets
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from config import settings
from database import SessionLocal
from entities import AdminSession

router = APIRouter(prefix="/admin", tags=["Admin & Authentication"])
audit_logger = logging.getLogger("skillpulse.audit")


def audit_operator_event(
    event: str,
    request: Request,
    *,
    result: str,
    actor: str = "anonymous",
    action: Optional[str] = None,
) -> None:
    """Emit a credential-free, body-free operator audit event."""
    request_id = getattr(request.state, "request_id", "unassigned")
    message = (
        f"event={event} result={result} actor={actor} "
        f"request_id={request_id}"
    )
    if action:
        message += f" action={action}"
    message += f" method={request.method} path={request.url.path}"
    audit_logger.info(message)


# ─────────────────────────────────────────────────────────────────────────────
# Session & Rate Limit Store (Spec 08 §4, §7)
# ─────────────────────────────────────────────────────────────────────────────

class AdminSessionStore:
    """
    Durable operator session store (Spec 08 §4), backed by the
    `admin_sessions` relation rather than an in-process dictionary.

    An in-memory dict loses every session on restart and is invisible to
    any other worker/instance serving `/api/v1/admin/*` — this store uses
    the same PostgreSQL/SQLite database already used elsewhere in this
    repository so a session is durable and shared regardless of how many
    processes are handling requests. Only the SHA-256 hash of the token is
    ever written here; the raw token lives solely in the HttpOnly cookie.
    """

    def create_session(self, raw_token: str, duration_hours: int = 8) -> str:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
        db = SessionLocal()
        try:
            db.add(AdminSession(token_hash=token_hash, expires_at=expires_at))
            db.commit()
        finally:
            db.close()
        return token_hash

    def validate_session(self, raw_token: str) -> bool:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        db = SessionLocal()
        try:
            record = db.execute(
                select(AdminSession).where(AdminSession.token_hash == token_hash)
            ).scalar_one_or_none()
            if record is None or record.revoked_at is not None or record.expires_at <= datetime.utcnow():
                return False
            record.last_seen_at = datetime.utcnow()
            db.commit()
            return True
        finally:
            db.close()

    def revoke_session(self, raw_token: str) -> bool:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        db = SessionLocal()
        try:
            record = db.execute(
                select(AdminSession).where(AdminSession.token_hash == token_hash)
            ).scalar_one_or_none()
            if record is None:
                return False
            record.revoked_at = datetime.utcnow()
            db.commit()
            return True
        finally:
            db.close()

    def clear(self) -> None:
        """Test-only: wipes every session row. Never called from request handling."""
        db = SessionLocal()
        try:
            db.execute(delete(AdminSession))
            db.commit()
        finally:
            db.close()


session_store = AdminSessionStore()

# Rate limit store for failed login attempts (5 failures / 15 minutes per IP)
_FAILED_LOGINS: Dict[str, List[float]] = {}


def _check_login_rate_limit(client_ip: str) -> None:
    now = time.time()
    window = 15 * 60.0  # 15 minutes
    attempts = [t for t in _FAILED_LOGINS.get(client_ip, []) if now - t < window]
    if len(attempts) >= 5:
        retry_after = max(1, int(window - (now - attempts[0])) + 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in 15 minutes.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )
    _FAILED_LOGINS[client_ip] = attempts


def _record_login_failure(client_ip: str) -> None:
    now = time.time()
    if client_ip not in _FAILED_LOGINS:
        _FAILED_LOGINS[client_ip] = []
    _FAILED_LOGINS[client_ip].append(now)


def _record_login_success(client_ip: str) -> None:
    if client_ip in _FAILED_LOGINS:
        del _FAILED_LOGINS[client_ip]


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    key: Optional[str] = Field(default=None, description="Admin secret key")
    admin_key: Optional[str] = Field(default=None, description="Admin secret key alias")

    def get_key(self) -> str:
        return (self.key or self.admin_key or "").strip()


class AdminLoginResponse(BaseModel):
    status: str = "authenticated"
    authenticated: bool = True
    message: str = "Operator session established."


# ─────────────────────────────────────────────────────────────────────────────
# Origin Validation for Cookie-Authenticated Requests (Spec 08 §7)
# ─────────────────────────────────────────────────────────────────────────────

_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _validate_operator_origin(request: Request) -> None:
    """
    State-changing cookie-authenticated requests must validate `Origin` and
    reject missing or unexpected origins in production (Spec 08 §7).

    The operator origin is not a separately configured value: the selected
    architecture (§3.1) authorizes the same session cookie for both the
    console and `/api/v1/admin/*` on one origin, so the only legitimate
    caller is this application itself. That is derived per-request from the
    request's own scheme + Host header rather than hardcoded, so it holds
    under any deployment hostname without extra configuration.

    This check is independent of the CORS policy: CORS only controls
    whether a browser lets JavaScript on another origin *read* a response,
    not whether it can *send* a simple or cookie-carrying request in the
    first place, which is what actually matters for a state-changing
    request authenticated by an ambient cookie.
    """
    if request.method not in _STATE_CHANGING_METHODS:
        return

    origin = request.headers.get("origin")
    if origin is None:
        if settings.ENVIRONMENT.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: missing Origin header on a cookie-authenticated request.",
                headers={"Cache-Control": "no-store"},
            )
        return

    expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if origin.rstrip("/") != expected_origin.rstrip("/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: unexpected Origin for a cookie-authenticated request.",
            headers={"Cache-Control": "no-store"},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Dependency: Require Admin Authorization (Spec 08 §3.2, §3.3)
# ─────────────────────────────────────────────────────────────────────────────

def require_admin_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=settings.ADMIN_SESSION_COOKIE),
) -> bool:
    """
    Fail-closed operator authorization dependency.
    Accepts:
    1. HttpOnly session cookie (validated against active session store)
    2. Authorization: Bearer <secret> (validated via secrets.compare_digest)

    Explicitly rejects:
    - Query parameter credentials (token, admin_key, key)
    - Legacy X-Admin-Key headers
    """
    if not settings.ADMIN_AUTH_ENABLED:
        return True

    expected_key = settings.ADMIN_API_KEY
    if not expected_key:
        # If no key configured, fail closed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Operator API key is unconfigured or disabled.",
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
        )

    # 1. Check Session Cookie
    if admin_cookie and session_store.validate_session(admin_cookie):
        _validate_operator_origin(request)
        request.state.operator_actor_id = (
            "session:" + hashlib.sha256(admin_cookie.encode("utf-8")).hexdigest()[:12]
        )
        return True

    # 2. Check Authorization Bearer header
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            bearer_token = parts[1]
            if secrets.compare_digest(bearer_token.encode("utf-8"), expected_key.encode("utf-8")):
                request.state.operator_actor_id = "automation"
                return True

    # Query params and X-Admin-Key are intentionally rejected per Spec 08
    audit_operator_event(
        "authorization_failure",
        request,
        result="denied",
        action=f"{request.method} {request.url.path}",
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid operator session or Bearer token required.",
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=AdminLoginResponse)
def admin_login(request: Request, body: AdminLoginRequest, response: Response):
    """
    Authenticate administrator session with API key.
    Enforces rate limits, sets an opaque HttpOnly SameSite=Strict session cookie,
    and never echoes credentials to the client.
    """
    client_ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "127.0.0.1")
    )

    try:
        _check_login_rate_limit(client_ip)
    except HTTPException:
        audit_operator_event("operator_login", request, result="rate_limited")
        raise

    expected_key = settings.ADMIN_API_KEY
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin secret key.",
            headers={"Cache-Control": "no-store"},
        )

    provided_key = body.get_key()
    if not provided_key or not secrets.compare_digest(provided_key.encode("utf-8"), expected_key.encode("utf-8")):
        _record_login_failure(client_ip)
        audit_operator_event("operator_login", request, result="failure")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin secret key.",
            headers={"Cache-Control": "no-store"},
        )

    _record_login_success(client_ip)
    audit_operator_event("operator_login", request, result="success", actor="operator")

    # Generate opaque session token
    raw_token = secrets.token_urlsafe(32)
    session_store.create_session(raw_token, duration_hours=8)

    # Set secure HttpOnly session cookie
    is_prod = settings.ENVIRONMENT.lower() == "production"
    response.set_cookie(
        key=settings.ADMIN_SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=is_prod,
        path="/",
        max_age=8 * 3600,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"

    return AdminLoginResponse(
        status="authenticated",
        authenticated=True,
        message="Operator session established.",
    )


@router.get("/verify")
def verify_admin_session(response: Response, authenticated: bool = Depends(require_admin_auth)):
    """Verify validity of current admin authentication session."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return {"status": "authenticated", "authenticated": True, "role": "operator"}


@router.post("/logout")
def admin_logout(request: Request, response: Response):
    """Invalidate server session and clear administrator session cookie."""
    cookie_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE)
    if cookie_token:
        # Logout acts on whatever session the cookie identifies, so it is
        # cookie-authenticated in the sense Spec 08 §7 means even though it
        # has no Depends(require_admin_auth) of its own (an already-invalid
        # cookie must still be able to log out). Validate Origin whenever a
        # cookie is actually present, to reject a forged cross-origin
        # logout of someone else's active session.
        _validate_operator_origin(request)
        session_store.revoke_session(cookie_token)
        actor = "session:" + hashlib.sha256(cookie_token.encode("utf-8")).hexdigest()[:12]
    else:
        actor = "anonymous"

    response.delete_cookie(
        key=settings.ADMIN_SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=(settings.ENVIRONMENT.lower() == "production"),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    audit_operator_event("operator_logout", request, result="success", actor=actor)
    return {"status": "logged_out", "message": "Admin session terminated."}
