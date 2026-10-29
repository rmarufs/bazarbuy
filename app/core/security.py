from typing import Any

import bcrypt
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings

LOGIN_URL = "/admin/login"
SESSION_COOKIE_NAME = "admin_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days, in seconds
BCRYPT_MAX_PASSWORD_BYTES = 72

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="admin-session")


def _password_bytes(password: str) -> bytes:
    # bcrypt uses at most 72 bytes and newer versions raise ValueError on longer inputs.
    return password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session_token(admin_id: int) -> str:
    return _serializer.dumps(admin_id)


def read_session_token(token: str) -> int | None:
    """Return the admin id from a valid, unexpired token, otherwise None."""
    try:
        value = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    return value if isinstance(value, int) else None


def session_cookie_params() -> dict[str, Any]:
    """Keyword arguments for `Response.set_cookie` of the session cookie."""
    return {
        "max_age": SESSION_MAX_AGE,
        "httponly": True,
        "samesite": "lax",
        "secure": settings.APP_ENV == "production",
    }


def get_session_admin_id(request: Request) -> int | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return read_session_token(token) if token else None


def get_current_admin_id(request: Request) -> int:
    """Dependency for admin routes: redirect to the login page if not signed in."""
    admin_id = get_session_admin_id(request)
    if admin_id is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": LOGIN_URL},
        )
    return admin_id
