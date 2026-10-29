from app.schemas.product import normalize_search_name


def test_normalize_search_name_ignores_case_and_spaces() -> None:
    expected = "louisvuitton"
    for name in (
        "Louis Vuitton",
        "louis vuitton",
        "LOUISVUITTON",
        " Louis\u00a0 Vuitton\t",
    ):
        assert normalize_search_name(name) == expected
