from pydantic import BaseModel, ConfigDict, Field


class CategoryName(BaseModel):
    """Validated category name: trimmed, 1 to 100 characters."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class CategoryWithCount(BaseModel):
    """A category together with the number of products in it."""

    id: int
    name: str
    products_count: int
