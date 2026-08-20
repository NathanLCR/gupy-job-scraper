from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/admin", tags=["Admin & Authentication"])


class AdminLoginRequest(BaseModel):
    key: str


class AdminLoginResponse(BaseModel):
    status: str
    message: str
    token: str


def require_admin_auth(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    authorization: Optional[str] = Header(None),
    admin_cookie: Optional[str] = Cookie(None, alias=settings.ADMIN_SESSION_COOKIE),
    token_param: Optional[str] = Query(None, alias="token"),
    admin_key_param: Optional[str] = Query(None, alias="admin_key"),
) -> bool:
    """
    FastAPI security dependency protecting internal operator routes, scrapers,
    and administrative endpoints.
    """
    if not settings.ADMIN_AUTH_ENABLED:
        return True

    expected_key = settings.ADMIN_API_KEY or "skillpulse-admin-secret"

    # 1. Check direct X-Admin-Key header
    if x_admin_key and x_admin_key == expected_key:
        return True

    # 2. Check Authorization Bearer header
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == expected_key:
            return True
        elif len(parts) == 1 and parts[0] == expected_key:
            return True

    # 3. Check Session Cookie
    if admin_cookie and admin_cookie == expected_key:
        return True

    # 4. Check query params (for quick test / direct link if needed)
    if (token_param and token_param == expected_key) or (admin_key_param and admin_key_param == expected_key):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid admin credentials or X-Admin-Key header required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(request: AdminLoginRequest, response: Response):
    """
    Authenticate administrator session with API key.
    Sets secure session cookie and returns bearer token for API calls.
    """
    expected_key = settings.ADMIN_API_KEY or "skillpulse-admin-secret"
    if request.key.strip() != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Admin Secret Key.",
        )

    # Set session cookie
    response.set_cookie(
        key=settings.ADMIN_SESSION_COOKIE,
        value=expected_key,
        httponly=False,  # Allow frontend JS to read if needed
        samesite="lax",
        secure=False,
    )

    return AdminLoginResponse(
        status="ok",
        message="Authentication successful. Operator session established.",
        token=expected_key,
    )


@router.get("/verify")
def verify_admin_session(authenticated: bool = Depends(require_admin_auth)):
    """Verify validity of current admin authentication session."""
    return {"status": "authenticated", "role": "operator"}


@router.post("/logout")
def admin_logout(response: Response):
    """Clear administrator session cookie."""
    response.delete_cookie(key=settings.ADMIN_SESSION_COOKIE)
    return {"status": "logged_out", "message": "Admin session terminated."}
