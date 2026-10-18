/* Tiny DOM helpers shared by the docs/pages tools (續領名單比對, 申請人數統計). */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /** Build an element; children may be nodes, strings, or falsy (skipped). */
  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === false) return;
      if (key === "text") node.textContent = value;
      else if (key === "className") node.className = value;
      else if (key === "checked" || key === "disabled") node[key] = Boolean(value);
      else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
      else node.setAttribute(key, value === true ? "" : value);
    });
    (children || []).filter(Boolean).forEach((child) => node.append(child));
    return node;
  }

  /**
   * Make a <label class="dropzone"> wrapping a file input accept drag & drop.
   * onFiles receives an array of File; the input is reset so re-picking the
   * same file fires again.
   */
  function bindDropZone(zone, input, onFiles) {
    const emit = (fileList) => {
      const files = [...fileList];
      if (files.length > 0) onFiles(input.multiple ? files : files.slice(0, 1));
    };
    input.addEventListener("change", () => {
      emit(input.files);
      input.value = "";
    });
    ["dragenter", "dragover"].forEach((type) =>
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add("dragging");
      }),
    );
    ["dragleave", "drop"].forEach((type) =>
      zone.addEventListener(type, () => zone.classList.remove("dragging")),
    );
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      emit(event.dataTransfer.files);
    });
  }

  /** Hand a generated file to the browser's download (no network involved). */
  function saveBlob(blob, fileName) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  window.RenewalDom = { $, el, bindDropZone, saveBlob };
})();
