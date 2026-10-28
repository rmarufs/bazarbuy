(() => {
  const mainImage = document.getElementById("gallery-main-image");
  const thumbs = document.querySelectorAll("[data-gallery-thumb]");
  if (!mainImage || thumbs.length === 0) return;

  thumbs.forEach((thumb) => {
    thumb.addEventListener("click", (event) => {
      event.preventDefault();
      mainImage.src = thumb.href;
      thumbs.forEach((other) => {
        const isActive = other === thumb;
        other.classList.toggle("is-active", isActive);
        if (isActive) other.setAttribute("aria-current", "true");
        else other.removeAttribute("aria-current");
      });
    });
  });
})();
