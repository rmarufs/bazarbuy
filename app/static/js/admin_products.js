(() => {
  const list = document.getElementById("product-list");
  const bulkForm = document.getElementById("bulk-form");
  if (!list || !bulkForm) return;

  const selectAll = document.getElementById("select-all");
  const counter = document.getElementById("selected-count");
  const deleteButton = document.getElementById("bulk-delete-button");
  const status = document.getElementById("reorder-status");
  const rowSelector = ".product-row";
  const EDGE = 70; // px from the viewport edge where the page auto-scrolls
  const SCROLL_STEP = 14;

  const checks = () => [...list.querySelectorAll(".product-check")];
  const rows = () => [...list.querySelectorAll(rowSelector)];

  /* ---------- Bulk selection ---------- */

  function updateSelection() {
    const all = checks();
    const selected = all.filter((box) => box.checked).length;
    counter.textContent = `Выбрано: ${selected}`;
    deleteButton.disabled = selected === 0;
    selectAll.checked = selected > 0 && selected === all.length;
    selectAll.indeterminate = selected > 0 && selected < all.length;
  }

  selectAll.addEventListener("change", () => {
    checks().forEach((box) => { box.checked = selectAll.checked; });
    updateSelection();
  });
  list.addEventListener("change", (event) => {
    if (event.target.matches(".product-check")) updateSelection();
  });
  bulkForm.addEventListener("submit", (event) => {
    const selected = checks().filter((box) => box.checked).length;
    if (selected === 0 || !confirm(`Удалить выбранные товары (${selected})?`)) {
      event.preventDefault();
    }
  });
  updateSelection();

  /* ---------- Reordering ---------- */

  const currentOrder = () => rows().map((row) => Number(row.dataset.id));

  function showStatus(message, isError) {
    status.textContent = message;
    status.classList.toggle("is-error", isError);
    status.hidden = false;
  }

  async function saveOrder(order) {
    try {
      const response = await fetch(list.dataset.reorderUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ordered_ids: order }),
      });
      if (!response.ok) throw new Error(String(response.status));
      showStatus("Порядок сохранён", false);
    } catch {
      showStatus("Не удалось сохранить порядок. Страница будет обновлена.", true);
      setTimeout(() => location.reload(), 1500);
    }
  }

  const middleOf = (element) => {
    const box = element.getBoundingClientRect();
    return box.top + box.height / 2;
  };

  // Moves the neighbours around the dragged row (not the row itself),
  // so the row that holds the pointer capture stays attached to the page.
  function moveRowToPointer(row, pointerY) {
    let previous = row.previousElementSibling;
    while (previous && pointerY < middleOf(previous)) {
      row.after(previous);
      previous = row.previousElementSibling;
    }
    let next = row.nextElementSibling;
    while (next && pointerY > middleOf(next)) {
      row.before(next);
      next = row.nextElementSibling;
    }
  }

  function autoScroll(pointerY) {
    if (pointerY < EDGE) window.scrollBy(0, -SCROLL_STEP);
    else if (pointerY > window.innerHeight - EDGE) window.scrollBy(0, SCROLL_STEP);
  }

  function startDrag(event, grip) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const row = grip.closest(rowSelector);
    const startOrder = currentOrder();
    event.preventDefault();
    grip.setPointerCapture(event.pointerId);
    row.classList.add("is-dragging");
    document.body.classList.add("is-dragging");

    const onMove = (moveEvent) => {
      moveRowToPointer(row, moveEvent.clientY);
      autoScroll(moveEvent.clientY);
    };
    const onEnd = () => {
      grip.removeEventListener("pointermove", onMove);
      grip.removeEventListener("pointerup", onEnd);
      grip.removeEventListener("pointercancel", onEnd);
      row.classList.remove("is-dragging");
      document.body.classList.remove("is-dragging");
      const order = currentOrder();
      if (order.join() !== startOrder.join()) saveOrder(order);
    };
    grip.addEventListener("pointermove", onMove);
    grip.addEventListener("pointerup", onEnd);
    grip.addEventListener("pointercancel", onEnd);
  }

  // Keyboard alternative: arrow keys on the focused handle move the row.
  function moveWithKeyboard(event, grip) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const row = grip.closest(rowSelector);
    const neighbour = event.key === "ArrowUp"
      ? row.previousElementSibling
      : row.nextElementSibling;
    if (!neighbour) return;
    if (event.key === "ArrowUp") neighbour.before(row);
    else neighbour.after(row);
    grip.focus();
    saveOrder(currentOrder());
  }

  list.addEventListener("pointerdown", (event) => {
    const grip = event.target.closest(".grip");
    if (grip) startDrag(event, grip);
  });
  list.addEventListener("keydown", (event) => {
    const grip = event.target.closest(".grip");
    if (grip) moveWithKeyboard(event, grip);
  });
})();
