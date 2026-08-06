/* Asset Vault polish — F2 multi-upload drag-drop + F4 package→campaign identity attach. */
(function (global) {
  "use strict";

  const READY_ATTR = "data-cinesmith-asset-polish";
  const DROP_CLASS = "cinesmith-dropzone";

  function toast(msg, type) {
    if (global.CinesmithCore && typeof CinesmithCore.toast === "function") {
      CinesmithCore.toast(msg, type || "info");
      return;
    }
    if (typeof global.showToast === "function") {
      global.showToast(msg, type === "error" ? "err" : type === "success" ? "ok" : "info");
    }
  }

  function selectedPackageId() {
    if (global.shellState && global.shellState.selectedProductId) {
      return global.shellState.selectedProductId;
    }
    if (typeof global.selectedAssetVaultPackage === "function") {
      const pkg = global.selectedAssetVaultPackage();
      return (pkg && pkg.id) || "";
    }
    return "";
  }

  function activeCampaignId() {
    if (typeof global.currentCampaignId === "string" && global.currentCampaignId) {
      return global.currentCampaignId;
    }
    if (global.shotFilters && global.shotFilters.campaignId) {
      return global.shotFilters.campaignId;
    }
    const readout = document.getElementById("identity-campaign-readout");
    if (readout && readout.value) return readout.value.trim();
    const filter = document.getElementById("campaign-filter") || document.querySelector("[data-campaign-filter]");
    if (filter && filter.value) return String(filter.value).trim();
    return "";
  }

  async function uploadAssetFiles(files, opts) {
    opts = opts || {};
    const packageId = opts.packageId || selectedPackageId();
    if (!packageId) {
      toast("Select an Asset Vault package first.", "warn");
      return null;
    }
    const list = Array.from(files || []).filter(Boolean);
    if (!list.length) {
      toast("Drop or choose asset files first.", "warn");
      return null;
    }

    const form = new FormData();
    list.forEach(function (file) {
      form.append("files", file, file.name);
    });
    form.append(
      "asset_type",
      opts.assetType ||
        (document.getElementById("asset-vault-upload-type") || {}).value ||
        "reference"
    );
    form.append(
      "name",
      opts.name ||
        (document.getElementById("asset-vault-upload-name") || {}).value ||
        ""
    );
    form.append(
      "prompt",
      opts.prompt ||
        (document.getElementById("asset-vault-upload-prompt") || {}).value ||
        ""
    );

    toast("Uploading " + list.length + " package asset" + (list.length === 1 ? "" : "s") + "…", "info");
    try {
      const resp = await fetch(
        "/api/asset-vault/packages/" + encodeURIComponent(packageId) + "/references/upload-batch",
        { method: "POST", body: form }
      );
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok || data.status !== "ok") {
        const detail = data.detail;
        throw new Error(
          (detail && detail.message) ||
            (typeof detail === "string" ? detail : null) ||
            data.error ||
            "Upload failed"
        );
      }
      const count = data.uploaded_count || list.length;
      const errCount = (data.errors && data.errors.length) || 0;
      toast(
        "Uploaded " + count + " asset" + (count === 1 ? "" : "s") +
          (errCount ? " (" + errCount + " skipped)" : ""),
        errCount ? "warn" : "success"
      );

      if (typeof global.fetchAssetVaultPackages === "function") {
        await global.fetchAssetVaultPackages();
      }
      if (typeof global.renderProductsContent === "function") {
        global.renderProductsContent();
      }
      if (typeof global.loadStoryboardAssetVaultPackages === "function") {
        await global.loadStoryboardAssetVaultPackages();
      }
      return data;
    } catch (err) {
      if (global.CinesmithCore && typeof CinesmithCore.reportError === "function") {
        CinesmithCore.reportError(err, "Asset upload failed");
      } else {
        toast((err && err.message) || "Asset upload failed", "error");
      }
      return null;
    }
  }

  async function attachPackageIdentity(opts) {
    opts = opts || {};
    const packageId = opts.packageId || selectedPackageId();
    if (!packageId) {
      toast("Select an Asset Vault package first.", "warn");
      return null;
    }
    const campaignId = (opts.campaignId || activeCampaignId() || "").trim();
    const body = {
      campaign_id: campaignId,
      copy_reference_assets: opts.copyReferenceAssets !== false,
    };

    toast(
      campaignId
        ? "Attaching package identity to campaign…"
        : "Attaching package identity (active campaign)…",
      "info"
    );
    try {
      const resp = await fetch(
        "/api/asset-vault/packages/" +
          encodeURIComponent(packageId) +
          "/attach-campaign-identity",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      );
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok || data.status !== "ok") {
        throw new Error(
          (typeof data.detail === "string" && data.detail) ||
            (data.detail && data.detail.message) ||
            data.error ||
            data.message ||
            "Attach failed"
        );
      }

      const cid = data.campaign_id || campaignId || "campaign";
      const name = data.package_name || packageId;
      const copied = data.copied_count || 0;
      if (global.CinesmithCore && typeof CinesmithCore.toast === "function") {
        CinesmithCore.toast(
          "Attached “" + name + "” → " + cid +
            (copied ? " · " + copied + " asset" + (copied === 1 ? "" : "s") + " copied" : ""),
          "success",
          4800
        );
      } else {
        toast(
          "Attached “" + name + "” → " + cid +
            (copied ? " · " + copied + " asset" + (copied === 1 ? "" : "s") + " copied" : ""),
          "success"
        );
      }

      if (typeof global.loadCampaignIdentity === "function" && cid) {
        await global.loadCampaignIdentity(cid);
      }
      if (typeof global.loadCampaignFolders === "function") {
        global.loadCampaignFolders();
      }
      return data;
    } catch (err) {
      if (global.CinesmithCore && typeof CinesmithCore.reportError === "function") {
        CinesmithCore.reportError(err, "Identity attach failed");
      } else {
        toast((err && err.message) || "Identity attach failed", "error");
      }
      return null;
    }
  }

  function bindDropzone(zone, fileInput, onFiles) {
    if (!zone || zone.getAttribute(READY_ATTR + "-dz") === "1") return;
    zone.setAttribute(READY_ATTR + "-dz", "1");

    function prevent(e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ["dragenter", "dragover", "dragleave", "drop"].forEach(function (evt) {
      zone.addEventListener(evt, prevent);
    });
    zone.addEventListener("dragenter", function () { zone.classList.add("is-dragover"); });
    zone.addEventListener("dragover", function () { zone.classList.add("is-dragover"); });
    zone.addEventListener("dragleave", function () { zone.classList.remove("is-dragover"); });
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

  function enhanceReferenceUploadRow(row) {
    if (!row || row.getAttribute(READY_ATTR) === "1") return;
    row.setAttribute(READY_ATTR, "1");

    const fileInput = row.querySelector("#asset-vault-upload-file") || row.querySelector('input[type="file"]');
    if (fileInput) fileInput.setAttribute("multiple", "multiple");

    let zone = row.parentElement && row.parentElement.querySelector("." + DROP_CLASS + ".asset-ref-dropzone");
    if (!zone) {
      zone = document.createElement("div");
      zone.className = DROP_CLASS + " asset-ref-dropzone";
      zone.innerHTML =
        '<div class="cinesmith-dropzone-inner">' +
          "<strong>Drop package references</strong>" +
          '<span class="t-meta">Multi-upload · product photos, logos, style boards</span>' +
          '<span class="t-meta cinesmith-dropzone-hint">or click to browse</span>' +
        "</div>";
      row.parentElement.insertBefore(zone, row);
    }

    bindDropzone(zone, fileInput, function (files) {
      uploadAssetFiles(files);
    });

    // Rebind Upload button to multi-upload when present
    const uploadBtn = Array.from(row.querySelectorAll("button")).find(function (b) {
      return /upload/i.test(b.textContent || "");
    });
    if (uploadBtn && !uploadBtn.getAttribute(READY_ATTR)) {
      uploadBtn.setAttribute(READY_ATTR, "1");
      uploadBtn.addEventListener(
        "click",
        function (e) {
          e.preventDefault();
          e.stopPropagation();
          const files = fileInput && fileInput.files;
          if (!files || !files.length) {
            toast("Choose one or more files to upload.", "warn");
            return;
          }
          uploadAssetFiles(files);
        },
        true
      );
    }
  }

  function enhancePackageActions() {
    const actions = document.querySelector(
      ".product-identity-card .product-recipe-actions, .product-form-stack .product-recipe-actions"
    );
    if (!actions || actions.querySelector(".cinesmith-attach-identity-btn")) return;
    if (!selectedPackageId()) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-primary cinesmith-attach-identity-btn";
    btn.title =
      "Apply this package’s continuity lock to the active Hermes campaign identity pack";
    btn.textContent = "Attach to Campaign Identity";
    btn.addEventListener("click", function () {
      attachPackageIdentity({});
    });
    actions.appendChild(btn);

    const hint = document.createElement("span");
    hint.className = "t-meta cinesmith-attach-identity-hint";
    hint.textContent = "One-click continuity → active campaign";
    actions.appendChild(hint);
  }

  function scan() {
    document
      .querySelectorAll(".asset-reference-upload-row")
      .forEach(enhanceReferenceUploadRow);
    enhancePackageActions();
  }

  function startObserver() {
    scan();
    if (!global.MutationObserver) return;
    const root =
      document.getElementById("products-view") ||
      document.getElementById("asset-vault-live-root") ||
      document.body;
    const obs = new MutationObserver(function () {
      scan();
    });
    obs.observe(root, { childList: true, subtree: true });
  }

  global.CinesmithAssets = {
    uploadFiles: uploadAssetFiles,
    attachPackageIdentity: attachPackageIdentity,
    enhance: scan,
  };

  // Global helpers for inline onclick if needed
  global.attachAssetVaultPackageIdentity = function (packageId, campaignId) {
    return attachPackageIdentity({ packageId: packageId, campaignId: campaignId });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver);
  } else {
    startObserver();
  }
})(window);
