# Bazarbuy.tj

Catalog website with WhatsApp preorder (no payments). Read `docs/SPEC.md` before any task: it is the single source of truth for functionality.

## Stack
Python, FastAPI, Pydantic, async SQLAlchemy + asyncpg, PostgreSQL, Alembic, Jinja2 templates, plain HTML/CSS/JS (no frontend framework), Pillow for images, pytest + Playwright for tests.

## Structure and layering
- `app/routers`: only HTTP handling, call services. No business logic here.
- `app/services`: all business logic.
- `app/models`: SQLAlchemy tables. `app/schemas`: Pydantic.
- `app/templates`, `app/static`: UI. `uploads/`: user photos (git-ignored).
- `tests/api`: pytest. `tests/e2e`: Playwright.

## Rules
1. Implement only what is in `docs/SPEC.md` and only the stage you are given. Do not add features, pages or dependencies on your own.
2. If something is unclear or missing, stop and ask. Do not guess.
3. Never create, change or delete: `.env`, databases, DB roles, running services. If something is missing, stop and report what is needed.
4. Schema changes only through Alembic migrations.
5. Everything async. Load related data explicitly (no lazy loading).
6. Mobile-first UI. Jinja autoescape stays on.
7. Security: hashed admin password, session cookie (HttpOnly, SameSite), validate image type and size, all admin routes require login.
8. Code in English, type hints, small functions, no dead code.
9. Every stage ends with tests that pass.

## Commands
- Run: `uvicorn app.main:app --reload`
- Tests: `pytest`
- Migrate: `alembic upgrade head`
- New migration: `alembic revision --autogenerate -m "message"`

## When you finish a task, report
What changed, how to run/check it, what is not done.