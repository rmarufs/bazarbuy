from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent.parent

# Autoescape stays on for all templates.
templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(BASE_DIR / "templates"),
        autoescape=True,
    )
)
