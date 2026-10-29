from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, expect

from tests.e2e.conftest import (
    CATEGORY_NAME,
    SECOND_CATEGORY_NAME,
    WHATSAPP_NUMBER,
    LiveServer,
    save_screenshot,
)


def catalog_card_titles(page: Page) -> list[str]:
    return page.locator(".product-card-title").all_text_contents()


def test_catalog_filter_and_search(
    page: Page,
    live_server: LiveServer,
    seed_public_catalog: Callable[[], dict[str, int]],
) -> None:
    seed_public_catalog()

    page.goto(live_server.url("/"))
    expect(page.locator(".product-card")).to_have_count(2)
    assert catalog_card_titles(page) == ["Сумка Louis Vuitton", "Кроссовки Nike"]
    prices = page.locator(".product-card-price").all_text_contents()
    assert prices == ["250 сомони", "400 сомони"]
    save_screenshot(page, "05_public_catalog.png")

    page.locator(".chips").get_by_role("link", name=CATEGORY_NAME).click()
    expect(page.locator(".product-card")).to_have_count(1)
    assert catalog_card_titles(page) == ["Сумка Louis Vuitton"]

    page.locator(".chips").get_by_role("link", name=SECOND_CATEGORY_NAME).click()
    expect(page.locator(".product-card")).to_have_count(1)
    assert catalog_card_titles(page) == ["Кроссовки Nike"]

    page.locator(".chips").get_by_role("link", name="Все категории").click()
    expect(page.locator(".product-card")).to_have_count(2)

    page.fill("#search", "louisvuitton")
    page.get_by_role("button", name="Найти").click()
    expect(page.locator(".product-card")).to_have_count(1)
    assert catalog_card_titles(page) == ["Сумка Louis Vuitton"]


def test_product_detail_and_photo_gallery(
    page: Page,
    live_server: LiveServer,
    seed_public_catalog: Callable[[], dict[str, int]],
) -> None:
    ids = seed_public_catalog()

    page.goto(live_server.url(f"/products/{ids['bag_id']}"))
    expect(page.locator(".detail-title")).to_have_text("Сумка Louis Vuitton")
    expect(page.locator(".detail-category")).to_have_text(CATEGORY_NAME)
    expect(page.locator(".detail-price")).to_have_text("250 сомони")
    expect(page.locator(".preorder-badge")).to_contain_text("Товар под предзаказ")
    expect(page.locator(".detail-description")).to_contain_text(
        "Кожаная сумка премиум-класса под предзаказ."
    )

    thumbs = page.locator("[data-gallery-thumb]")
    main_image = page.locator("#gallery-main-image")
    expect(thumbs).to_have_count(3)

    first_href = thumbs.nth(0).get_attribute("href")
    second_href = thumbs.nth(1).get_attribute("href")
    assert first_href is not None and second_href is not None
    assert first_href != second_href
    expect(main_image).to_have_attribute("src", first_href)

    thumbs.nth(1).click()
    expect(main_image).to_have_attribute("src", second_href)
    expect(thumbs.nth(1)).to_have_class("thumb is-active")
    gallery_box = page.locator(".gallery-main").bounding_box()
    image_box = main_image.bounding_box()
    assert gallery_box is not None and image_box is not None
    assert abs(gallery_box["height"] - image_box["height"]) <= 2
    save_screenshot(page, "06_product_detail.png")


def test_cart_quantity_controls_and_whatsapp_order(
    page: Page,
    live_server: LiveServer,
    seed_public_catalog: Callable[[], dict[str, int]],
) -> None:
    ids = seed_public_catalog()
    badge = page.locator("[data-cart-count]")

    page.goto(live_server.url("/"))
    expect(badge).to_be_hidden()

    bag_card = page.locator(".product-card").filter(has_text="Сумка Louis Vuitton")
    bag_card.get_by_role("button", name="В корзину").click()
    expect(badge).to_be_visible()
    expect(badge).to_have_text("1")
    expect(bag_card.locator("[data-stepper-qty]")).to_have_text("1")

    page.goto(live_server.url(f"/products/{ids['sneakers_id']}"))
    page.get_by_role("button", name="В корзину").click()
    expect(badge).to_have_text("2")
    expect(page.locator(".detail-info [data-stepper-qty]")).to_have_text("1")

    page.locator(".cart-link").click()
    page.wait_for_url("**/cart")
    items = page.locator(".cart-item")
    expect(items).to_have_count(2)
    expect(page.locator("#cart-total")).to_have_text("650 сомони")

    first_item = items.nth(0)
    first_item.locator("[data-cart-plus]").click()
    expect(first_item.locator("[data-cart-qty]")).to_have_text("2")
    expect(first_item.locator("[data-cart-subtotal]")).to_have_text("500 сомони")
    expect(badge).to_have_text("3")
    expect(page.locator("#cart-total")).to_have_text("900 сомони")
    save_screenshot(page, "07_cart_page.png")

    order_btn = page.locator("#whatsapp-order-btn")
    href = order_btn.get_attribute("href")
    assert href is not None
    assert href.startswith("https://wa.me/992900112233?text=")
    parsed = urlparse(href)
    text = parse_qs(parsed.query)["text"][0]
    assert "Здравствуйте! Это предзаказ с сайта Bazarbuy.tj:" in text
    assert "1. Сумка Louis Vuitton, 2 шт. × 250 = 500 сомони" in text
    assert "2. Кроссовки Nike, 1 шт. × 400 = 400 сомони" in text
    assert "Итого: 900 сомони" in text

    first_item.locator("[data-cart-minus]").click()
    expect(first_item.locator("[data-cart-qty]")).to_have_text("1")
    expect(first_item.locator("[data-cart-subtotal]")).to_have_text("250 сомони")
    expect(page.locator("#cart-total")).to_have_text("650 сомони")

    second_item = items.nth(1)
    second_item.locator("[data-cart-minus]").click()
    expect(items).to_have_count(1)
    expect(page.locator(".cart-item-title")).to_have_text("Сумка Louis Vuitton")
    expect(page.locator("#cart-total")).to_have_text("250 сомони")

    items.nth(0).locator("[data-cart-minus]").click()
    expect(items).to_have_count(0)
    expect(page.locator("#cart-empty")).to_be_visible()
    expect(badge).to_be_hidden()


def test_cart_syncs_with_server_when_products_change(
    page: Page,
    live_server: LiveServer,
    seed_public_catalog: Callable[[], dict[str, int]],
) -> None:
    ids = seed_public_catalog()

    page.goto(live_server.url("/"))
    page.evaluate(
        """(bagId) => {
            localStorage.setItem("bazarbuy_cart", JSON.stringify([
                { id: bagId, name: "Старое имя", price: 100, image: "", qty: 2 },
                { id: 999999, name: "Удалённый товар", price: 500, image: "", qty: 1 }
            ]));
        }""",
        ids["bag_id"],
    )

    page.goto(live_server.url("/cart"))
    items = page.locator(".cart-item")
    expect(items).to_have_count(1)
    expect(page.locator(".cart-item-title")).to_have_text("Сумка Louis Vuitton")
    expect(page.locator("[data-cart-subtotal]")).to_have_text("500 сомони")
    expect(page.locator("#cart-total")).to_have_text("500 сомони")


def test_static_pages_about_and_contacts(
    page: Page,
    live_server: LiveServer,
    seed_public_catalog: Callable[[], dict[str, int]],
) -> None:
    seed_public_catalog()

    page.goto(live_server.url("/"))
    page.locator(".site-nav").get_by_role("link", name="О нас").click()
    page.wait_for_url("**/about")
    expect(page.locator("main")).to_contain_text("предзаказ")
    expect(page.locator("main")).to_contain_text("WhatsApp")

    page.locator(".site-nav").get_by_role("link", name="Контакты").click()
    page.wait_for_url("**/contacts")
    expect(page.locator(".contact-number")).to_contain_text(WHATSAPP_NUMBER)
    whatsapp_link = page.get_by_role("link", name="Написать в WhatsApp")
    expect(whatsapp_link).to_have_attribute("href", "https://wa.me/992900112233")
