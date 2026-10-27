from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_PATH = Path(settings.UPLOAD_DIR)
UPLOAD_PATH.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(BASE_DIR / "templates"),
        autoescape=True,
    )
)

app = FastAPI(title="Bazarbuy.tj")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_PATH), name="uploads")


@app.get("/health")
async def health() -> dict[str, str]:
    """Technical health check endpoint."""
    return {"status": "ok"}
