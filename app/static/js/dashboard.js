(function () {
  const gridEl = document.getElementById("grid");
  if (gridEl) {
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
  }

  // ---- Shift+Enter submits the focused widget form ----------------------
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

  // ---- Flash auto-hide --------------------------------------------------
  function bindAutoHide(scope) {
    (scope || document).querySelectorAll(".flash[data-autohide]").forEach((el) => {
      if (el.dataset.bound === "1") return;
      el.dataset.bound = "1";
      const ms = parseInt(el.dataset.autohide, 10) || 3000;
      setTimeout(() => el.classList.add("fade-out"), ms);
      setTimeout(() => el.remove(), ms + 600);
    });
  }

  // ---- Dropzone (Inbox widget) ------------------------------------------
  function fmtBytes(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
  }

  function bindDropzones(scope) {
    (scope || document).querySelectorAll(".dropzone").forEach((zone) => {
      if (zone.dataset.bound === "1") return;
      zone.dataset.bound = "1";

      const input = zone.querySelector('input[type="file"]');
      const chips = zone.querySelector(".file-chips");

      function renderChips() {
        chips.innerHTML = "";
        Array.from(input.files).forEach((f, idx) => {
          const li = document.createElement("li");
          li.className = "file-chip";
          li.innerHTML =
            '<span class="name"></span> ' +
            '<span class="size muted"></span> ' +
            '<button type="button" class="remove" title="Remove">&times;</button>';
          li.querySelector(".name").textContent = f.name;
          li.querySelector(".size").textContent = fmtBytes(f.size);
          li.querySelector(".remove").addEventListener("click", (ev) => {
            ev.preventDefault();
            removeAt(idx);
          });
          chips.appendChild(li);
        });
      }

      function removeAt(removeIdx) {
        const dt = new DataTransfer();
        Array.from(input.files).forEach((f, i) => {
          if (i !== removeIdx) dt.items.add(f);
        });
        input.files = dt.files;
        renderChips();
      }

      function addFiles(fileList) {
        const dt = new DataTransfer();
        Array.from(input.files).forEach((f) => dt.items.add(f));
        Array.from(fileList).forEach((f) => dt.items.add(f));
        input.files = dt.files;
        renderChips();
      }

      // Click anywhere in the zone (but not on chips/removes) opens picker.
      zone.addEventListener("click", (e) => {
        if (e.target.closest(".file-chip")) return;
        input.click();
      });
      input.addEventListener("change", renderChips);

      ["dragenter", "dragover"].forEach((evt) =>
        zone.addEventListener(evt, (e) => {
          e.preventDefault();
          zone.classList.add("dragover");
        })
      );
      ["dragleave", "dragend", "drop"].forEach((evt) =>
        zone.addEventListener(evt, (e) => {
          if (evt === "dragleave" && zone.contains(e.relatedTarget)) return;
          zone.classList.remove("dragover");
        })
      );
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        if (e.dataTransfer && e.dataTransfer.files.length) {
          addFiles(e.dataTransfer.files);
        }
      });

      // Clear chips after successful submit (the form gets swapped, but we
      // wipe just in case).
      const form = zone.closest("form");
      if (form) {
        form.addEventListener("submit", () => {
          // leave files; HTMX will replace this widget on response
        });
      }
    });
  }

  // Global paste handler: if a textarea inside an inbox widget has focus
  // and the clipboard contains files (image paste), route them to that
  // widget's dropzone input.
  document.addEventListener("paste", (e) => {
    const active = document.activeElement;
    if (!active || active.tagName !== "TEXTAREA") return;
    const widget = active.closest(".widget.inbox");
    if (!widget) return;
    const items = e.clipboardData && e.clipboardData.files;
    if (!items || items.length === 0) return;
    e.preventDefault();
    const zone = widget.querySelector(".dropzone");
    if (!zone) return;
    const input = zone.querySelector('input[type="file"]');
    const dt = new DataTransfer();
    Array.from(input.files).forEach((f) => dt.items.add(f));
    Array.from(items).forEach((f) => dt.items.add(f));
    input.files = dt.files;
    // Trigger UI refresh
    input.dispatchEvent(new Event("change"));
  });

  bindAutoHide();
  bindDropzones();
  document.body.addEventListener("htmx:afterSwap", (e) => {
    bindAutoHide(e.target);
    bindDropzones(e.target);
  });
})();
