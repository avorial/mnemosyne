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

  // ---- Drop a URL onto the Bookmark widget -----------------------------
  function bindBookmarkDrops(scope) {
    (scope || document).querySelectorAll(".widget.bookmark").forEach((widget) => {
      if (widget.dataset.urlDropBound === "1") return;
      widget.dataset.urlDropBound = "1";

      const form = widget.querySelector("form.bookmark-form");
      if (!form) return;
      const input = form.querySelector('input[name="url"]');
      if (!input) return;

      ["dragenter", "dragover"].forEach((evt) =>
        widget.addEventListener(evt, (e) => {
          // Only react to URL/text drags, not file drags.
          const types = e.dataTransfer && Array.from(e.dataTransfer.types || []);
          if (!types) return;
          if (
            types.includes("text/uri-list") ||
            types.includes("text/x-moz-url") ||
            types.includes("text/plain")
          ) {
            e.preventDefault();
            widget.classList.add("url-dragover");
          }
        })
      );
      ["dragleave", "dragend", "drop"].forEach((evt) =>
        widget.addEventListener(evt, (e) => {
          if (evt === "dragleave" && widget.contains(e.relatedTarget)) return;
          widget.classList.remove("url-dragover");
        })
      );
      widget.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        if (!dt) return;
        let raw =
          dt.getData("text/uri-list") ||
          dt.getData("text/x-moz-url") ||
          dt.getData("text/plain");
        if (!raw) return;
        // text/uri-list and text/x-moz-url can have multiple lines; take the
        // first non-empty, non-comment line.
        const url = raw
          .split(/\r?\n/)
          .map((s) => s.trim())
          .find((s) => s && !s.startsWith("#"));
        if (!url) return;
        e.preventDefault();
        input.value = url;
        if (form.requestSubmit) form.requestSubmit();
        else form.submit();
      });
    });
  }

  bindAutoHide();
  bindDropzones();
  bindBookmarkDrops();
  document.body.addEventListener("htmx:afterSwap", (e) => {
    bindAutoHide(e.target);
    bindDropzones(e.target);
    bindBookmarkDrops(e.target);
  });
})();
