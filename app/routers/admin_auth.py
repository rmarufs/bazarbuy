from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    LOGIN_URL,
    SESSION_COOKIE_NAME,
    create_session_token,
    get_session_admin_id,
    session_cookie_params,
)
from app.core.templating import templates
from app.services import auth_service
from app.services.auth_service import TooManyLoginAttemptsError

router = APIRouter(prefix="/admin")

PRODUCTS_URL = "/admin/products"


def _get_client_ip(request: Request) -> str:
    # X-Forwarded-For is intentionally ignored: without a trusted reverse proxy
    # overwriting client headers, an attacker could spoof X-Forwarded-For on every
    # request and bypass per-IP rate limiting.
    return request.client.host if request.client else "unknown"


@router.get("")
async def admin_index() -> RedirectResponse:
    return RedirectResponse(PRODUCTS_URL, status_code=303)


@router.get("/login")
async def login_page(request: Request) -> Response:
    if get_session_admin_id(request) is not None:
        return RedirectResponse(PRODUCTS_URL, status_code=303)
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/login")
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    try:
        admin = await auth_service.login_admin(
            db, username, password, _get_client_ip(request)
        )
    except TooManyLoginAttemptsError as error:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": str(error), "username": username},
            status_code=429,
        )
    if admin is None:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "Неверный логин или пароль", "username": username},
            status_code=401,
        )
    response = RedirectResponse(PRODUCTS_URL, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, create_session_token(admin.id), **session_cookie_params()
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(LOGIN_URL, status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
