(function () {
  const gridEl = document.getElementById("grid");
  if (!gridEl) return;

  const grid = GridStack.init(
    {
      cellHeight: 80,
      margin: 8,
      column: 12,
      float: false,
      handle: ".widget-header",
    },
    gridEl
  );

  // Debounced save on layout change.
  let timer = null;
  function persist() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const layout = grid.save(false);
      try {
        await fetch("/layout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(layout),
        });
      } catch (e) {
        console.warn("layout save failed", e);
      }
    }, 500);
  }
  grid.on("change", persist);

  // Submit the focused widget form on Shift+Enter. Plain Enter still inserts
  // a newline in the textarea.
  document.addEventListener("keydown", (e) => {
    if (e.shiftKey && e.key === "Enter") {
      const ta = document.activeElement;
      if (ta && ta.tagName === "TEXTAREA") {
        const form = ta.closest("form");
        if (form && form.requestSubmit) {
          e.preventDefault();
          form.requestSubmit();
        }
      }
    }
  });

  // Auto-hide flashes after the duration in data-autohide (ms).
  function bindAutoHide(scope) {
    (scope || document).querySelectorAll(".flash[data-autohide]").forEach((el) => {
      if (el.dataset.bound === "1") return;
      el.dataset.bound = "1";
      const ms = parseInt(el.dataset.autohide, 10) || 3000;
      setTimeout(() => el.classList.add("fade-out"), ms);
      setTimeout(() => el.remove(), ms + 600);
    });
  }
  bindAutoHide();
  document.body.addEventListener("htmx:afterSwap", (e) => bindAutoHide(e.target));
})();
