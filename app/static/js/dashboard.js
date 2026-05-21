(function () {
  const gridEl = document.getElementById("grid");
  if (!gridEl) return;

  const grid = GridStack.init(
    {
      cellHeight: 80,
      margin: 8,
      column: 12,
      float: false,
    },
    gridEl
  );

  // Restore saved layout if present.
  try {
    const raw = gridEl.dataset.layout;
    const saved = raw ? JSON.parse(raw) : [];
    if (Array.isArray(saved) && saved.length > 0) {
      grid.load(saved);
    }
  } catch (e) {
    console.warn("could not parse saved layout", e);
  }

  // Debounced save on change.
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
  grid.on("added", persist);
  grid.on("removed", persist);
})();
