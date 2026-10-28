(() => {
  const STORAGE_KEY = "bazarbuy_cart";

  function readCart() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .map((item) => ({
          id: Number(item.id),
          name: String(item.name || ""),
          price: Number(item.price),
          image: String(item.image || ""),
          qty: Number(item.qty),
        }))
        .filter(
          (item) =>
            Number.isInteger(item.id) &&
            item.id > 0 &&
            item.name.length > 0 &&
            Number.isFinite(item.price) &&
            item.price >= 0 &&
            Number.isInteger(item.qty) &&
            item.qty >= 1
        );
    } catch {
      return [];
    }
  }

  function writeCart(items) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      // Ignore storage quota errors in restricted environments.
    }
    renderAll(items);
  }

  function addProduct(product) {
    const items = readCart();
    const existing = items.find((item) => item.id === product.id);
    if (existing) {
      existing.qty += 1;
      existing.name = product.name;
      existing.price = product.price;
      existing.image = product.image;
    } else {
      items.push({
        id: product.id,
        name: product.name,
        price: product.price,
        image: product.image,
        qty: 1,
      });
    }
    writeCart(items);
  }

  function changeQty(productId, delta) {
    const items = readCart();
    const index = items.findIndex((item) => item.id === productId);
    if (index === -1) return;
    const nextQty = items[index].qty + delta;
    if (nextQty <= 0) {
      items.splice(index, 1);
    } else {
      items[index].qty = nextQty;
    }
    writeCart(items);
  }

  function clearCart() {
    writeCart([]);
  }

  function buildWhatsAppMessage(items) {
    const lines = items.map(
      (item, index) =>
        `${index + 1}. ${item.name}, ${item.qty} шт. × ${item.price} = ${item.qty * item.price} сомони`
    );
    const total = items.reduce((sum, item) => sum + item.qty * item.price, 0);
    return (
      "Здравствуйте! Это предзаказ с сайта Bazarbuy.tj:\n\n" +
      lines.join("\n") +
      `\n\nИтого: ${total} сомони`
    );
  }

  function renderBadge(items) {
    const totalQty = items.reduce((sum, item) => sum + item.qty, 0);
    document.querySelectorAll("[data-cart-count]").forEach((badge) => {
      badge.textContent = String(totalQty);
      badge.hidden = totalQty === 0;
    });
  }

  function ensureStepperForButton(button, productId) {
    const next = button.nextElementSibling;
    if (next && next.dataset && next.dataset.stepperFor === String(productId)) {
      return next;
    }
    const stepper = document.createElement("div");
    stepper.className = "qty-control";
    stepper.dataset.stepperFor = String(productId);

    const minusBtn = document.createElement("button");
    minusBtn.type = "button";
    minusBtn.className = "qty-btn";
    minusBtn.dataset.qtyMinus = "";
    minusBtn.setAttribute("aria-label", "Уменьшить количество");
    minusBtn.textContent = "−";
    minusBtn.addEventListener("click", () => changeQty(productId, -1));

    const valueSpan = document.createElement("span");
    valueSpan.className = "qty-value";
    valueSpan.dataset.stepperQty = "";

    const plusBtn = document.createElement("button");
    plusBtn.type = "button";
    plusBtn.className = "qty-btn";
    plusBtn.dataset.qtyPlus = "";
    plusBtn.setAttribute("aria-label", "Увеличить количество");
    plusBtn.textContent = "+";
    plusBtn.addEventListener("click", () => changeQty(productId, 1));

    stepper.append(minusBtn, valueSpan, plusBtn);
    button.after(stepper);
    return stepper;
  }

  function renderProductButtons(items) {
    const byId = new Map(items.map((item) => [item.id, item]));
    document.querySelectorAll("[data-add-to-cart]").forEach((button) => {
      const productId = Number(button.dataset.productId);
      if (!productId) return;
      const inCart = byId.get(productId);
      const stepper = ensureStepperForButton(button, productId);
      if (inCart) {
        button.hidden = true;
        stepper.hidden = false;
        const qtyEl = stepper.querySelector("[data-stepper-qty]");
        if (qtyEl) qtyEl.textContent = String(inCart.qty);
      } else {
        button.hidden = false;
        stepper.hidden = true;
      }
    });
  }

  function createCartItemRow(item) {
    const row = document.createElement("article");
    row.className = "card cart-item";
    row.dataset.cartItemId = String(item.id);

    const thumbLink = document.createElement("a");
    thumbLink.className = "cart-item-thumb";
    thumbLink.href = `/products/${item.id}`;
    if (item.image) {
      const img = document.createElement("img");
      img.src = item.image;
      img.alt = item.name;
      img.width = 72;
      img.height = 72;
      img.loading = "lazy";
      thumbLink.appendChild(img);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "cart-item-placeholder";
      placeholder.textContent = "Нет фото";
      thumbLink.appendChild(placeholder);
    }

    const info = document.createElement("div");
    info.className = "cart-item-info";

    const titleLink = document.createElement("a");
    titleLink.className = "cart-item-title";
    titleLink.href = `/products/${item.id}`;
    titleLink.textContent = item.name;

    const unitPrice = document.createElement("span");
    unitPrice.className = "cart-item-price";
    unitPrice.textContent = `${item.price} сомони / шт.`;

    info.append(titleLink, unitPrice);

    const actions = document.createElement("div");
    actions.className = "cart-item-actions";

    const stepper = document.createElement("div");
    stepper.className = "qty-control";

    const minusBtn = document.createElement("button");
    minusBtn.type = "button";
    minusBtn.className = "qty-btn";
    minusBtn.dataset.cartMinus = "";
    minusBtn.setAttribute("aria-label", "Уменьшить количество");
    minusBtn.textContent = "−";
    minusBtn.addEventListener("click", () => changeQty(item.id, -1));

    const qtySpan = document.createElement("span");
    qtySpan.className = "qty-value";
    qtySpan.dataset.cartQty = "";
    qtySpan.textContent = String(item.qty);

    const plusBtn = document.createElement("button");
    plusBtn.type = "button";
    plusBtn.className = "qty-btn";
    plusBtn.dataset.cartPlus = "";
    plusBtn.setAttribute("aria-label", "Увеличить количество");
    plusBtn.textContent = "+";
    plusBtn.addEventListener("click", () => changeQty(item.id, 1));

    stepper.append(minusBtn, qtySpan, plusBtn);

    const subtotal = document.createElement("strong");
    subtotal.className = "cart-item-subtotal";
    subtotal.dataset.cartSubtotal = "";
    subtotal.textContent = `${item.qty * item.price} сомони`;

    actions.append(stepper, subtotal);
    row.append(thumbLink, info, actions);
    return row;
  }

  function renderCartPage(items) {
    const container = document.getElementById("cart-container");
    if (!container) return;

    const emptyBlock = document.getElementById("cart-empty");
    const contentBlock = document.getElementById("cart-content");
    const itemsList = document.getElementById("cart-items");
    const totalEl = document.getElementById("cart-total");
    const clearBtn = document.getElementById("cart-clear-btn");
    const orderBtn = document.getElementById("whatsapp-order-btn");

    if (items.length === 0) {
      if (emptyBlock) emptyBlock.hidden = false;
      if (contentBlock) contentBlock.hidden = true;
      if (clearBtn) clearBtn.hidden = true;
      if (itemsList) itemsList.replaceChildren();
      if (totalEl) totalEl.textContent = "0 сомони";
      return;
    }

    if (emptyBlock) emptyBlock.hidden = true;
    if (contentBlock) contentBlock.hidden = false;
    if (clearBtn) clearBtn.hidden = false;

    if (itemsList) {
      itemsList.replaceChildren(...items.map(createCartItemRow));
    }

    const total = items.reduce((sum, item) => sum + item.qty * item.price, 0);
    if (totalEl) {
      totalEl.textContent = `${total} сомони`;
    }

    if (orderBtn) {
      const rawPhone = container.dataset.whatsappNumber || "";
      const cleanPhone = rawPhone.replace(/\D/g, "");
      if (cleanPhone) {
        const message = buildWhatsAppMessage(items);
        const url = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`;
        if (orderBtn.tagName === "A") {
          orderBtn.href = url;
        }
        orderBtn.dataset.whatsappUrl = url;
      } else {
        orderBtn.disabled = true;
      }
    }
  }

  function renderAll(items = readCart()) {
    renderBadge(items);
    renderProductButtons(items);
    renderCartPage(items);
  }

  async function syncCartWithServer() {
    const container = document.getElementById("cart-container");
    if (!container) return;
    const current = readCart();
    if (current.length === 0) return;
    const ids = current.map((item) => item.id).join(",");
    try {
      const response = await fetch(`/api/cart-items?ids=${encodeURIComponent(ids)}`);
      if (!response.ok) return;
      const freshItems = await response.json();
      if (!Array.isArray(freshItems)) return;
      const byId = new Map(freshItems.map((entry) => [Number(entry.id), entry]));
      const latest = readCart();
      const synced = [];
      for (const item of latest) {
        const fresh = byId.get(item.id);
        if (fresh) {
          synced.push({
            id: item.id,
            name: String(fresh.name),
            price: Number(fresh.price),
            image: String(fresh.image_url || ""),
            qty: item.qty,
          });
        }
      }
      writeCart(synced);
    } catch {
      // Keep local cart data if offline or request fails.
    }
  }

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-to-cart]");
    if (addButton) {
      event.preventDefault();
      addProduct({
        id: Number(addButton.dataset.productId),
        name: String(addButton.dataset.productName || ""),
        price: Number(addButton.dataset.productPrice),
        image: String(addButton.dataset.productImage || ""),
      });
    }
  });

  const clearBtn = document.getElementById("cart-clear-btn");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => clearCart());
  }

  renderAll();
  syncCartWithServer();
})();
