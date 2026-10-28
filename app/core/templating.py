from pathlib import Path
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent.parent


def catalog_url(category_id: int | None = None, q: str | None = None) -> str:
    """Catalog link that keeps the chosen category and/or search query."""
    params: dict[str, str | int] = {}
    if category_id is not None:
        params["category_id"] = category_id
    if q:
        params["q"] = q
    return f"/?{urlencode(params)}" if params else "/"


# Autoescape stays on for all templates.
templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(BASE_DIR / "templates"),
        autoescape=True,
    )
)
templates.env.globals["catalog_url"] = catalog_url
