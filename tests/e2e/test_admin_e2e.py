from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    CATEGORY_NAME,
    LiveServer,
    make_image,
    save_screenshot,
)

NOT_EMPTY_MESSAGE = "Нельзя удалить категорию, пока в ней есть товары"


def titles(page: Page) -> list[str]:
    return page.locator(".product-row .list-item-title").all_text_contents()


def make_photo(directory: Path) -> str:
    path = directory / "photo.png"
    path.write_bytes(make_image("PNG", "blue"))
    return str(path)


def add_product(
    page: Page, server: LiveServer, name: str, price: int, photo: str
) -> None:
    page.goto(server.url("/admin/products/new"))
    page.fill("#name", name)
    page.select_option("#category_id", label=CATEGORY_NAME)
    page.fill("#price", str(price))
    page.set_input_files("#photos", photo)
    page.get_by_role("button", name="Сохранить").click()
    page.wait_for_url("**/admin/products")


def test_login_and_settings(page: Page, live_server: LiveServer) -> None:
    page.goto(live_server.url("/admin/login"))
    save_screenshot(page, "01_login.png")

    page.fill("#username", ADMIN_USERNAME)
    page.fill("#password", ADMIN_PASSWORD)
    page.get_by_role("button", name="Войти").click()
    page.wait_for_url("**/admin/products")

    page.get_by_role("link", name="Настройки").click()
    page.wait_for_url("**/admin/settings")
    page.fill("#whatsapp_number", "+992900112233")
    page.get_by_role("button", name="Сохранить").click()

    page.wait_for_url("**/admin/settings?saved=1")
    expect(page.get_by_role("status")).to_have_text("Сохранено")
    expect(page.locator("#whatsapp_number")).to_have_value("+992900112233")


def test_wrong_password_shows_error(page: Page, live_server: LiveServer) -> None:
    page.goto(live_server.url("/admin/login"))
    page.fill("#username", ADMIN_USERNAME)
    page.fill("#password", "wrong")
    page.get_by_role("button", name="Войти").click()

    expect(page.get_by_role("alert")).to_have_text("Неверный логин или пароль")


def test_admin_pages_require_login(page: Page, live_server: LiveServer) -> None:
    page.goto(live_server.url("/admin/products"))
    expect(page).to_have_url(live_server.url("/admin/login"))


def test_create_category_and_products(
    admin_page: Page, live_server: LiveServer, tmp_path: Path
) -> None:
    page = admin_page
    page.goto(live_server.url("/admin/categories"))
    page.fill("#new-category", CATEGORY_NAME)
    page.get_by_role("button", name="Добавить").click()
    expect(page.locator(".list-item-title")).to_have_text(CATEGORY_NAME)
    expect(page.locator(".badge")).to_have_text("0 товаров")
    save_screenshot(page, "02_categories.png")

    page.goto(live_server.url("/admin/products/new"))
    save_screenshot(page, "04_product_form.png")

    photo = make_photo(tmp_path)
    for index, name in enumerate(["Товар 1", "Товар 2", "Товар 3"]):
        add_product(page, live_server, name, 100 * (index + 1), photo)

    expect(page.locator(".product-row")).to_have_count(3)
    assert titles(page) == ["Товар 3", "Товар 2", "Товар 1"]
    prices = page.locator(".product-price").all_text_contents()
    assert prices == ["300 сомони", "200 сомони", "100 сомони"]
    expect(page.locator(".product-row img").first).to_be_visible()
    save_screenshot(page, "03_products_list.png")


def test_non_empty_category_cannot_be_deleted(
    admin_page: Page, live_server: LiveServer, seed_products
) -> None:
    seed_products(["Товар 1"])
    page = admin_page
    page.on("dialog", lambda dialog: dialog.accept())

    page.goto(live_server.url("/admin/categories"))
    expect(page.locator(".badge")).to_have_text("1 товар")
    page.get_by_role("button", name="Удалить категорию").click()

    expect(page.get_by_role("alert")).to_have_text(NOT_EMPTY_MESSAGE)
    expect(page.locator(".list-item-title")).to_have_text(CATEGORY_NAME)


def drag_first_row_to_bottom(page: Page) -> None:
    rows = page.locator(".product-row")
    grip = rows.nth(0).locator(".grip").bounding_box()
    last = rows.nth(rows.count() - 1).bounding_box()
    assert grip is not None and last is not None
    start_x = grip["x"] + grip["width"] / 2
    start_y = grip["y"] + grip["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, last["y"] + last["height"] - 4, steps=25)
    with page.expect_response("**/admin/products/reorder") as response:
        page.mouse.up()
    assert response.value.status == 200


def test_reorder_products_by_dragging_handle(
    admin_page: Page, live_server: LiveServer, seed_products
) -> None:
    seed_products(["A", "B", "C"])
    page = admin_page
    page.goto(live_server.url("/admin/products"))
    assert titles(page) == ["C", "B", "A"]

    drag_first_row_to_bottom(page)
    assert titles(page) == ["B", "A", "C"]

    page.reload()
    assert titles(page) == ["B", "A", "C"]


def test_reorder_products_with_keyboard(
    admin_page: Page, live_server: LiveServer, seed_products
) -> None:
    seed_products(["A", "B", "C"])
    page = admin_page
    page.goto(live_server.url("/admin/products"))

    page.locator(".product-row").nth(2).locator(".grip").focus()
    with page.expect_response("**/admin/products/reorder") as response:
        page.keyboard.press("ArrowUp")
    assert response.value.status == 200
    assert titles(page) == ["C", "A", "B"]

    page.reload()
    assert titles(page) == ["C", "A", "B"]


def test_bulk_delete_with_checkboxes(
    admin_page: Page, live_server: LiveServer, seed_products
) -> None:
    seed_products(["A", "B", "C"])
    page = admin_page
    page.goto(live_server.url("/admin/products"))
    delete_button = page.get_by_role("button", name="Удалить выбранные")
    counter = page.locator("#selected-count")
    checks = page.locator(".product-check")
    expect(delete_button).to_be_disabled()
    expect(counter).to_have_text("Выбрано: 0")

    page.locator("#select-all").check()
    expect(counter).to_have_text("Выбрано: 3")
    page.locator("#select-all").uncheck()
    expect(counter).to_have_text("Выбрано: 0")
    expect(delete_button).to_be_disabled()

    checks.nth(0).check()
    checks.nth(1).check()
    expect(counter).to_have_text("Выбрано: 2")
    expect(delete_button).to_be_enabled()

    page.on("dialog", lambda dialog: dialog.accept())
    delete_button.click()

    expect(page.locator(".product-row")).to_have_count(1)
    assert titles(page) == ["A"]
    expect(delete_button).to_be_disabled()
