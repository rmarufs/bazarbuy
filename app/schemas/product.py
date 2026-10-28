from pydantic import BaseModel, ConfigDict, Field

# PostgreSQL INTEGER upper bound; keeps the price storable.
MAX_PRICE = 2_147_483_647


class ProductInput(BaseModel):
    """Validated product fields coming from the admin form."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    price: int = Field(gt=0, le=MAX_PRICE)
    category_id: int


class ReorderRequest(BaseModel):
    """Product ids in the order the admin wants them, top to bottom."""

    ordered_ids: list[int]


def normalize_search_name(name: str) -> str:
    """Remove all whitespace and ignore case: 'Louis Vuitton' -> 'louisvuitton'."""
    return "".join(name.split()).casefold()
