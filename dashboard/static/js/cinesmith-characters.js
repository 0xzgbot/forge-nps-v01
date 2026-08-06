/* Characters polish — F2 multi-file drag-drop + F3 auto sheet from one photo (Hermes continuity). */
(function (global) {
  "use strict";

  const DROP_CLASS = "cinesmith-dropzone";
  const READY_ATTR = "data-cinesmith-multi-upload";
  const AUTO_SHEET_READY = "data-cinesmith-auto-sheet";

  function toast(msg, type) {
    if (global.CinesmithCore && typeof CinesmithCore.toast === "function") {
      CinesmithCore.toast(msg, type || "info");
      return;
    }
    if (typeof global.showToast === "function") {
      global.showToast(msg, type === "error" ? "err" : type === "success" ? "ok" : "info");
    }
  }

  function selectedCharacterId() {
    if (global.shellState && global.shellState.selectedCharacterId) {
      return global.shellState.selectedCharacterId;
    }
    if (global.characterCinesmithSelectedId) {
      return global.characterCinesmithSelectedId;
    }
    return "";
  }

  function characterIdFromPayload(payload) {
    if (!payload) return "";
    if (payload.id) return payload.id;
    if (payload.character_id) return payload.character_id;
    if (payload.character && payload.character.id) return payload.character.id;
    return "";
  }

  function setStatusLine(text, kind) {
    const el =
      document.getElementById("character-auto-sheet-status") ||
      document.getElementById("character-manager-status");
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("kimi-generating", "kimi-success", "kimi-fallback");
    if (kind === "working") el.classList.add("kimi-generating");
    if (kind === "ok") el.classList.add("kimi-success");
    if (kind === "warn" || kind === "partial") el.classList.add("kimi-fallback");
  }

  function ensureResultStrip() {
    let strip = document.getElementById("character-auto-sheet-result");
    if (strip) return strip;
    const host =
      document.getElementById("character-render-gallery") ||
      document.querySelector(".character-action-bar") ||
      document.getElementById("identity-view") ||
      document.getElementById("character-content");
    if (!host) return null;
    strip = document.createElement("div");
    strip.id = "character-auto-sheet-result";
    strip.className = "character-auto-sheet-result";
    strip.setAttribute("aria-live", "polite");
    if (host.id === "character-render-gallery") {
      host.parentNode.insertBefore(strip, host);
    } else if (host.classList && host.classList.contains("character-action-bar")) {
      host.parentNode.insertBefore(strip, host.nextSibling);
    } else {
      host.insertBefore(strip, host.firstChild);
    }
    return strip;
  }

  function renderResultStrip(data) {
    const strip = ensureResultStrip();
    if (!strip || !data) return;
    const status = data.status || "error";
    const imgs = Array.isArray(data.image_urls) ? data.image_urls : [];
    const sheetUrl = data.sheet_url || imgs[0] || "";
    const masterUrl =
      (data.master_reference && data.master_reference.url) ||
      (data.character && data.character.anchor_url) ||
      "";
    const panels = Array.isArray(data.panels) ? data.panels : [];
    const hint = data.recovery_hint || "";
    const msg = data.message || "";

    let thumbs = "";
    if (masterUrl) {
      thumbs +=
        '<figure class="character-auto-sheet-thumb">' +
        '<img src="' + escapeAttr(masterUrl) + '" alt="Master photo" loading="lazy">' +
        "<figcaption>Master</figcaption></figure>";
    }
    if (sheetUrl) {
      thumbs +=
        '<figure class="character-auto-sheet-thumb">' +
        '<img src="' + escapeAttr(sheetUrl) + '" alt="Character sheet" loading="lazy">' +
        "<figcaption>Sheet</figcaption></figure>";
    }
    panels.slice(0, 6).forEach(function (p, i) {
      if (!p || !p.url) return;
      thumbs +=
        '<figure class="character-auto-sheet-thumb">' +
        '<img src="' + escapeAttr(p.url) + '" alt="Panel ' + (i + 1) + '" loading="lazy">' +
        "<figcaption>P" + (i + 1) + "</figcaption></figure>";
    });

    strip.innerHTML =
      '<div class="character-auto-sheet-result-inner status-' + escapeAttr(status) + '">' +
        '<div class="character-auto-sheet-result-meta">' +
          "<strong>Sheet from photo</strong>" +
          '<span class="badge">' + escapeHtml(status) + "</span>" +
          (data.character_id
            ? '<span class="t-meta">' + escapeHtml(data.character_id) + "</span>"
            : "") +
          (data.prompt_id
            ? '<span class="t-meta">job ' + escapeHtml(data.prompt_id) + "</span>"
            : "") +
        "</div>" +
        (msg ? '<p class="t-meta">' + escapeHtml(msg) + "</p>" : "") +
        (hint && status !== "complete"
          ? '<p class="character-auto-sheet-hint">' + escapeHtml(hint) + "</p>"
          : "") +
        (thumbs ? '<div class="character-auto-sheet-thumbs">' + thumbs + "</div>" : "") +
      "</div>";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  async function refreshCharactersUi(data) {
    if (global.shellState && Array.isArray(global.shellState.characters) && data && data.character) {
      const cid = characterIdFromPayload(data) || characterIdFromPayload(data.character);
      if (cid) {
        global.shellState.selectedCharacterId = cid;
        const idx = global.shellState.characters.findIndex(function (c) {
          return (c.id || c.name) === cid;
        });
        const normalized = Object.assign({}, data.character, { id: cid });
        if (idx >= 0) global.shellState.characters[idx] = normalized;
        else global.shellState.characters.push(normalized);
      }
    }
    if (typeof global.renderCharactersContent === "function") {
      try { await global.renderCharactersContent(); } catch (_e) { /* ignore */ }
    } else if (typeof global.loadCharacterManager === "function") {
      try { await global.loadCharacterManager(); } catch (_e) { /* ignore */ }
    }
  }

  /**
   * Auto continuity pack from one photo.
   * opts: { charId, createNew, name, role, prompt, rows, cols, extractPanels, file }
   */
  async function autoSheetFromPhoto(fileOrFiles, opts) {
    opts = opts || {};
    const file = Array.isArray(fileOrFiles) || (global.FileList && fileOrFiles instanceof FileList)
      ? (fileOrFiles[0] || null)
      : fileOrFiles;
    if (!file) {
      toast("Choose one face or body photo first.", "warn");
      return null;
    }

    const createNew = !!opts.createNew || !opts.charId && !selectedCharacterId();
    const charId = opts.charId || selectedCharacterId();
    const form = new FormData();
    form.append("file", file, file.name || "photo.jpg");
    if (opts.prompt) form.append("prompt", opts.prompt);
    if (opts.name) form.append("name", opts.name);
    if (opts.role) form.append("role", opts.role);
    form.append("rows", String(opts.rows != null ? opts.rows : 2));
    form.append("cols", String(opts.cols != null ? opts.cols : 3));
    form.append("extract_panels", opts.extractPanels === false ? "false" : "true");
    if (opts.workflowId) form.append("workflow_id", opts.workflowId);

    let url;
    if (createNew || !charId) {
      url = "/api/characters/auto-sheet-from-photo";
      if (!opts.name) {
        const stem = (file.name || "character").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
        form.append("name", stem || "New Character");
      }
    } else {
      url = "/api/characters/" + encodeURIComponent(charId) + "/auto-sheet";
    }

    toast("Building continuity pack from photo…", "info");
    setStatusLine("Sheet from photo — locking identity and checking Spark…", "working");

    try {
      const resp = await fetch(url, { method: "POST", body: form });
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok && data.status !== "partial") {
        const detail = data.detail;
        const msg =
          (detail && detail.message) ||
          (typeof detail === "string" ? detail : null) ||
          data.error ||
          data.message ||
          "Auto sheet failed";
        throw new Error(msg);
      }

      // partial is a successful offline path (HTTP 200)
      renderResultStrip(data);
      await refreshCharactersUi(data);

      if (data.status === "complete") {
        toast(data.message || "Character sheet ready.", "success");
        setStatusLine(data.message || "Character sheet complete.", "ok");
      } else if (data.status === "partial") {
        toast(data.message || "Photo saved. Spark offline — sheet deferred.", "warn");
        setStatusLine(
          (data.message || "Partial") +
            (data.recovery_hint ? " — " + data.recovery_hint : ""),
          "partial"
        );
      } else {
        toast(data.message || data.error || "Auto sheet failed", "error");
        setStatusLine(data.message || data.error || "Auto sheet failed", "warn");
      }
      return data;
    } catch (err) {
      if (global.CinesmithCore && typeof CinesmithCore.reportError === "function") {
        CinesmithCore.reportError(err, "Sheet from photo failed");
      } else {
        toast((err && err.message) || "Sheet from photo failed", "error");
      }
      setStatusLine((err && err.message) || "Sheet from photo failed", "warn");
      return null;
    }
  }

  async function uploadCharacterFiles(files, opts) {
    opts = opts || {};
    const charId = opts.charId || selectedCharacterId();
    if (!charId) {
      toast("Select a character first.", "warn");
      return null;
    }
    const list = Array.from(files || []).filter(Boolean);
    if (!list.length) {
      toast("Drop or choose reference images first.", "warn");
      return null;
    }

    const form = new FormData();
    list.forEach(function (file) {
      form.append("files", file, file.name);
    });
    form.append("reference_type", opts.referenceType || "auto");
    form.append("notes", opts.notes || "");

    toast("Uploading " + list.length + " reference" + (list.length === 1 ? "" : "s") + "…", "info");
    try {
      const resp = await fetch(
        "/api/characters/" + encodeURIComponent(charId) + "/references/batch",
        { method: "POST", body: form }
      );
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        const detail = data.detail;
        const msg =
          (detail && detail.message) ||
          (typeof detail === "string" ? detail : null) ||
          data.error ||
          "Upload failed";
        throw new Error(msg);
      }

      const count = data.uploaded_count || (data.uploaded && data.uploaded.length) || list.length;
      const errCount = (data.errors && data.errors.length) || 0;
      toast(
        "Uploaded " + count + " reference" + (count === 1 ? "" : "s") +
          (errCount ? " (" + errCount + " skipped)" : ""),
        errCount ? "warn" : "success"
      );

      if (global.shellState && Array.isArray(global.shellState.characters) && data.character) {
        const cid = characterIdFromPayload(data.character) || charId;
        const idx = global.shellState.characters.findIndex(function (c) {
          return (c.id || c.name) === cid;
        });
        const normalized = Object.assign({}, data.character, { id: cid });
        if (idx >= 0) global.shellState.characters[idx] = normalized;
        else global.shellState.characters.push(normalized);
      }
      if (typeof global.renderCharactersContent === "function") {
        await global.renderCharactersContent();
      } else if (typeof global.loadCharacterManager === "function") {
        await global.loadCharacterManager();
      }
      return data;
    } catch (err) {
      if (global.CinesmithCore && typeof CinesmithCore.reportError === "function") {
        CinesmithCore.reportError(err, "Reference upload failed");
      } else {
        toast((err && err.message) || "Reference upload failed", "error");
      }
      return null;
    }
  }

  function bindDropzone(zone, fileInput, onFiles) {
    if (!zone || zone.getAttribute(READY_ATTR) === "1") return;
    zone.setAttribute(READY_ATTR, "1");

    function prevent(e) {
      e.preventDefault();
      e.stopPropagation();
    }

    ["dragenter", "dragover", "dragleave", "drop"].forEach(function (evt) {
      zone.addEventListener(evt, prevent);
    });
    zone.addEventListener("dragenter", function () {
      zone.classList.add("is-dragover");
    });
    zone.addEventListener("dragover", function () {
      zone.classList.add("is-dragover");
    });
    zone.addEventListener("dragleave", function () {
      zone.classList.remove("is-dragover");
    });
    zone.addEventListener("drop", function (e) {
      zone.classList.remove("is-dragover");
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) onFiles(files);
    });

    if (fileInput) {
      fileInput.setAttribute("multiple", "multiple");
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files.length) {
          onFiles(fileInput.files);
          try { fileInput.value = ""; } catch (_e) { /* ignore */ }
        }
      });
    }

    zone.addEventListener("click", function (e) {
      if (e.target && e.target.closest && e.target.closest("button, select, input, a, label")) {
        return;
      }
      if (fileInput) fileInput.click();
    });
  }

  function enhanceCharacterUploadForm(form) {
    if (!form || form.getAttribute(READY_ATTR) === "1") return;
    form.setAttribute(READY_ATTR, "1");

    const fileInput =
      form.querySelector('input[type="file"][name="reference_image"]') ||
      form.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.setAttribute("multiple", "multiple");
      fileInput.removeAttribute("required");
    }

    let zone = form.querySelector("." + DROP_CLASS);
    if (!zone) {
      zone = document.createElement("div");
      zone.className = DROP_CLASS + " character-ref-dropzone";
      zone.innerHTML =
        '<div class="cinesmith-dropzone-inner">' +
          "<strong>Drop reference images</strong>" +
          '<span class="t-meta">Multi-upload · PNG / JPG / WEBP · optional video clips</span>' +
          '<span class="t-meta cinesmith-dropzone-hint">or click to browse</span>' +
        "</div>";
      form.insertBefore(zone, form.firstChild);
    }

    const typeSelect = form.querySelector('select[name="reference_type"]');

    form.addEventListener(
      "submit",
      function (e) {
        e.preventDefault();
        e.stopPropagation();
        const files = fileInput && fileInput.files;
        if (!files || !files.length) {
          toast("Choose one or more reference files.", "warn");
          return;
        }
        uploadCharacterFiles(files, {
          referenceType: (typeSelect && typeSelect.value) || "auto",
        });
      },
      true
    );

    bindDropzone(zone, fileInput, function (files) {
      uploadCharacterFiles(files, {
        referenceType: (typeSelect && typeSelect.value) || "auto",
      });
    });
  }

  function injectAutoSheetControls(root) {
    root = root || document;
    // Design cinesmith action bar (identity-view)
    const actionBars = root.querySelectorAll
      ? root.querySelectorAll(".character-action-bar")
      : [];
    actionBars.forEach(function (bar) {
      if (bar.getAttribute(AUTO_SHEET_READY) === "1") return;
      // Prefer the first design-panel action bar that has generate character
      if (!bar.querySelector("#char-cinesmith-sheet-btn, [onclick*='renderCharacterOnSpark']") &&
          !bar.closest('[data-character-step-panel="design"]')) {
        // still allow inject into design panel only, or any bar missing controls
        if (!bar.closest("#identity-view") && !bar.closest("#character-content")) return;
      }
      bar.setAttribute(AUTO_SHEET_READY, "1");

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/png,image/jpeg,image/webp,image/gif";
      fileInput.id = fileInput.id || "char-auto-sheet-file";
      if (!document.getElementById("char-auto-sheet-file")) {
        fileInput.id = "char-auto-sheet-file";
      } else {
        fileInput.id = "char-auto-sheet-file-" + Math.random().toString(36).slice(2, 7);
      }
      fileInput.className = "character-auto-sheet-file";
      fileInput.hidden = true;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-primary character-auto-sheet-btn";
      btn.id = "char-auto-sheet-btn";
      btn.textContent = "Sheet from photo";
      btn.title =
        "Drop one face/body photo → lock master reference and generate multi-panel continuity sheet when Spark is up";

      const newBtn = document.createElement("button");
      newBtn.type = "button";
      newBtn.className = "btn btn-secondary character-auto-sheet-new-btn";
      newBtn.textContent = "New from photo";
      newBtn.title = "Create a new character continuity pack from one photo";

      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files[0]) {
          const mode = fileInput.getAttribute("data-mode") || "selected";
          autoSheetFromPhoto(fileInput.files[0], {
            createNew: mode === "new",
            charId: mode === "new" ? "" : selectedCharacterId(),
            name: (document.getElementById("char-cinesmith-name") || {}).value || "",
            role: (document.getElementById("char-cinesmith-role") || {}).value || "",
            prompt: (document.getElementById("char-cinesmith-sheet-prompt") || {}).value ||
              (document.getElementById("char-cinesmith-base-prompt") || {}).value || "",
          });
          try { fileInput.value = ""; } catch (_e) { /* ignore */ }
        }
      });

      btn.addEventListener("click", function () {
        fileInput.setAttribute("data-mode", "selected");
        fileInput.click();
      });
      newBtn.addEventListener("click", function () {
        fileInput.setAttribute("data-mode", "new");
        fileInput.click();
      });

      bar.appendChild(fileInput);
      bar.appendChild(btn);
      bar.appendChild(newBtn);
    });

    // Production actions grid in character detail (shell)
    root.querySelectorAll && root.querySelectorAll(".character-op-grid").forEach(function (grid) {
      if (grid.getAttribute(AUTO_SHEET_READY) === "1") return;
      grid.setAttribute(AUTO_SHEET_READY, "1");
      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/png,image/jpeg,image/webp";
      fileInput.hidden = true;
      fileInput.className = "character-auto-sheet-file";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn character-auto-sheet-btn";
      btn.textContent = "Sheet from photo";
      btn.title = "Lock this photo as master reference and build a multi-panel sheet when Spark is available";
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files[0]) {
          autoSheetFromPhoto(fileInput.files[0], { charId: selectedCharacterId() });
          try { fileInput.value = ""; } catch (_e) { /* ignore */ }
        }
      });
      btn.addEventListener("click", function () { fileInput.click(); });
      grid.appendChild(fileInput);
      grid.appendChild(btn);
    });

    // Static hook button in index.html (if present)
    const hookBtn = document.getElementById("char-sheet-from-photo-btn");
    const hookInput = document.getElementById("char-sheet-from-photo-file");
    if (hookBtn && hookInput && hookBtn.getAttribute(AUTO_SHEET_READY) !== "1") {
      hookBtn.setAttribute(AUTO_SHEET_READY, "1");
      hookBtn.addEventListener("click", function () {
        hookInput.click();
      });
      hookInput.addEventListener("change", function () {
        if (hookInput.files && hookInput.files[0]) {
          autoSheetFromPhoto(hookInput.files[0], {
            charId: selectedCharacterId(),
            createNew: !selectedCharacterId(),
            name: (document.getElementById("char-cinesmith-name") || {}).value || "",
            role: (document.getElementById("char-cinesmith-role") || {}).value || "",
            prompt: (document.getElementById("char-cinesmith-sheet-prompt") || {}).value || "",
          });
          try { hookInput.value = ""; } catch (_e) { /* ignore */ }
        }
      });
    }

    ensureResultStrip();
  }

  function scan() {
    document.querySelectorAll("form.character-reference-upload").forEach(enhanceCharacterUploadForm);
    injectAutoSheetControls(document);
  }

  function startObserver() {
    scan();
    if (!global.MutationObserver) return;
    const root =
      document.getElementById("identity-view") ||
      document.getElementById("characters-view") ||
      document.body;
    const obs = new MutationObserver(function () {
      scan();
    });
    obs.observe(root, { childList: true, subtree: true });
  }

  global.CinesmithCharacters = {
    uploadFiles: uploadCharacterFiles,
    autoSheetFromPhoto: autoSheetFromPhoto,
    enhance: scan,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver);
  } else {
    startObserver();
  }
})(window);
