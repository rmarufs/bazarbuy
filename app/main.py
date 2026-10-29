from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.templating import BASE_DIR
from app.routers import (
    admin_auth,
    admin_categories,
    admin_products,
    admin_settings,
    public,
)

app = FastAPI(title="Bazarbuy.tj")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
if not settings.use_cloudinary:
    upload_path = Path(settings.UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")
app.include_router(admin_auth.router)
app.include_router(admin_settings.router)
app.include_router(admin_categories.router)
app.include_router(admin_products.router)
app.include_router(public.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Technical health check endpoint."""
    return {"status": "ok"}
