/*
 * Forge NPS — Hermes Command Center
 * app.js | NDJSON streaming, campaign runner, chat, settings
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let chatHistory = [];
let sessionId = "session_" + Date.now();
let campaignActive = false;
let campaignAbortController = null;
let campaignRecoveryTimer = null;
let configDirty = {}; // dot_key -> new_value
let currentConfig = {};

// Spark state
let sparkRenderResults = {};
let sparkWebSocket = null;
let sparkCampaignId = null;
let videoSelection = new Set();
let videoShotsById = {};
let dashboardSelection = new Set();
let currentCampaignId = "";
let identityAssets = [];
let identityAssetSelection = new Set();
const MAX_DASHBOARD_THUMBS = 180;
const MAX_VIDEO_THUMBS = 180;
let campaignSort = { key: "name", reverse: false };
let mediaSort = { key: "time", reverse: true }; // newest first
const shotFilters = {
    campaignId: "",
    renderedOnly: false,
    failedOnly: false,
    passedOnly: false,
    retriesOnly: false,
    importedOnly: false,
};

// Script / Director state
let director_shots = {};
let memoryGraphRaw = { nodes: [], edges: [] };
let memoryPlaybackTimer = null;
let memoryPlaybackRunning = false;
let memoryNexusOverlay = { nodes: [], edges: [] };

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $log = document.getElementById("log-panel");
const $filmstrip = document.getElementById("filmstrip");
const $chatInput = document.getElementById("chat-input");
const $chatStatus = document.getElementById("chat-status");
const $briefInput = document.getElementById("brief-input");
const $biblePath = document.getElementById("bible-path");
const $runBtn = document.getElementById("run-campaign-btn");
const $charList = document.getElementById("char-list");
const $lengthSelect = document.getElementById("length-select"); // may be null if removed
const $campaignList = document.getElementById("campaign-list");

// Spark DOM refs
const $videoSelectedCount = document.getElementById("video-selected-count");
const $dashboardSelectedCount = document.getElementById("dashboard-selected-count");
const $videoDuration = document.getElementById("video-duration");
const $videoFps = document.getElementById("video-fps");
const $videoPrompt = document.getElementById("video-prompt");
const $sparkGrid = document.getElementById("spark-grid");
const $sparkStatusText = document.getElementById("spark-status-text");
const $sparkProgress = document.getElementById("spark-progress");

function getSelectedVideoWorkflow() {
    const el = document.querySelector('input[name="video-workflow"]:checked');
    return el ? String(el.value || "").trim() : "02_ltx2.3_T2V_I2V_distilled";
}
const $startBatchBtn = document.getElementById("start-batch-btn");
const $lightboxModal = document.getElementById("lightbox-modal");
const $dashboardDivider = document.getElementById("dashboard-divider");
const $dashboardLeftPane = document.getElementById("dashboard-left-pane");

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
    loadCharacters();
    loadStats();
    loadShots();
    loadCampaignFolders();
    setInterval(loadStats, 10000);
    loadConfig();
    loadVideoLibrary();
    const csk = document.getElementById("campaign-sort-key");
    const csr = document.getElementById("campaign-sort-reverse");
    if (csk) campaignSort.key = csk.value || "name";
    if (csr) campaignSort.reverse = !!csr.checked;
    mediaSort = { key: "time", reverse: true };
    syncInlineMediaSortControls();
    initDashboardResizer();
    initVideoResizer();
    ["identity-type","identity-name","identity-tokens","identity-negatives"].forEach((k) => {
        const el = id(k);
        if (el) el.addEventListener("input", updateIdentityPreview);
        if (el) el.addEventListener("change", updateIdentityPreview);
    });
});

function id(s) { return document.getElementById(s); }

function _csvToList(v) {
    return String(v || "")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
}

function getIdentityPackFromUI() {
    const type = (id("identity-type")?.value || "").trim().toLowerCase();
    const name = (id("identity-name")?.value || "").trim();
    const anchor_image_ids = identityAssets.filter((a) => a.active).map((a) => a.asset_id);
    const identity_tokens = _csvToList(id("identity-tokens")?.value);
    const negative_tokens = _csvToList(id("identity-negatives")?.value);
    if (!type) return null;
    return { type, name, anchor_image_ids, identity_tokens, negative_tokens };
}

function setIdentityUI(identity) {
    const pack = identity || {};
    if (id("identity-type")) id("identity-type").value = pack.type || "";
    if (id("identity-name")) id("identity-name").value = pack.name || "";
    if (id("identity-tokens")) id("identity-tokens").value = Array.isArray(pack.identity_tokens) ? pack.identity_tokens.join(", ") : "";
    if (id("identity-negatives")) id("identity-negatives").value = Array.isArray(pack.negative_tokens) ? pack.negative_tokens.join(", ") : "";
    if (id("identity-campaign-readout")) id("identity-campaign-readout").value = shotFilters.campaignId || currentCampaignId || "";
    updateIdentityPreview();
}

function syncIdentityAnchorsFromAssets() {
    const anchors = identityAssets.filter((a) => a.active).map((a) => a.asset_id);
    if (id("identity-anchors")) id("identity-anchors").value = anchors.join(", ");
    updateIdentityPreview();
}

async function loadCampaignIdentity(campaignId) {
    if (!campaignId) {
        setIdentityUI(null);
        identityAssets = [];
        renderIdentityAssets([]);
        return;
    }
    try {
        const resp = await fetch("/api/campaigns/" + encodeURIComponent(campaignId) + "/identity");
        const data = await resp.json();
        if (resp.ok) setIdentityUI(data.identity_pack || null);
        await loadIdentityAssets(campaignId);
    } catch (_e) {}
}

async function saveCampaignIdentity() {
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    if (!cid) {
        addLogEntry("error", "Select a campaign folder first.");
        return;
    }
    const identity_pack = getIdentityPackFromUI() || { type: "", name: "", anchor_image_ids: [], identity_tokens: [], negative_tokens: [] };
    try {
        const resp = await fetch("/api/campaigns/identity", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ campaign_id: cid, identity_pack }),
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") {
            addLogEntry("error", "Identity save failed: " + (data.detail || data.error || resp.status));
            return;
        }
        addLogEntry("hermes", "Identity saved for campaign: " + cid);
        loadCampaignFolders();
        await loadCampaignIdentity(cid);
    } catch (e) {
        addLogEntry("error", "Identity save error: " + e.message);
    }
}

function renderIdentityAssets(assets) {
    const grid = id("identity-assets-grid");
    if (!grid) return;
    if (!assets || !assets.length) {
        grid.innerHTML = '<div class="grid-placeholder"><p>No identity assets uploaded for this campaign.</p></div>';
        return;
    }
    grid.innerHTML = "";
    assets.forEach((a) => {
        const cell = document.createElement("div");
        cell.className = "grid-cell rendered";
        const img = document.createElement("img");
        img.src = a.src;
        img.alt = a.asset_id;
        img.loading = "lazy";
        const label = document.createElement("div");
        label.className = "cell-label";
        const pick = document.createElement("input");
        pick.type = "checkbox";
        pick.checked = identityAssetSelection.has(a.asset_id);
        pick.addEventListener("change", () => {
            if (pick.checked) identityAssetSelection.add(a.asset_id);
            else identityAssetSelection.delete(a.asset_id);
        });
        const active = document.createElement("input");
        active.type = "checkbox";
        active.checked = !!a.active;
        active.addEventListener("change", () => updateIdentityAsset(a.asset_id, { active: active.checked }));
        const txt = document.createElement("span");
        txt.textContent = " " + a.asset_id;
        const role = document.createElement("select");
        role.style.marginLeft = "6px";
        role.innerHTML = '<option value="anchor">anchor</option><option value="sheet">sheet</option><option value="detail">detail</option>';
        role.value = a.role || "anchor";
        role.addEventListener("change", () => updateIdentityAsset(a.asset_id, { role: role.value }));
        const up = document.createElement("button");
        up.textContent = "↑";
        up.className = "btn btn-secondary";
        up.style.padding = "2px 6px";
        up.style.marginLeft = "6px";
        up.addEventListener("click", (e) => { e.stopPropagation(); updateIdentityAsset(a.asset_id, { priority: (a.priority || 1000) - 1 }); });
        const down = document.createElement("button");
        down.textContent = "↓";
        down.className = "btn btn-secondary";
        down.style.padding = "2px 6px";
        down.style.marginLeft = "4px";
        down.addEventListener("click", (e) => { e.stopPropagation(); updateIdentityAsset(a.asset_id, { priority: (a.priority || 1000) + 1 }); });
        label.appendChild(pick);
        label.appendChild(active);
        label.appendChild(txt);
        label.appendChild(role);
        label.appendChild(up);
        label.appendChild(down);
        cell.appendChild(img);
        cell.appendChild(label);
        grid.appendChild(cell);
    });
}

async function loadIdentityAssets(campaignId) {
    const cid = (campaignId || shotFilters.campaignId || currentCampaignId || "").trim();
    if (!cid) {
        identityAssets = [];
        renderIdentityAssets([]);
        syncIdentityAnchorsFromAssets();
        return;
    }
    try {
        const resp = await fetch("/api/campaigns/" + encodeURIComponent(cid) + "/assets");
        const data = await resp.json();
        identityAssets = Array.isArray(data.assets) ? data.assets : [];
        identityAssetSelection = new Set([...identityAssetSelection].filter((x) => identityAssets.some((a) => a.asset_id === x)));
        renderIdentityAssets(identityAssets);
        syncIdentityAnchorsFromAssets();
    } catch (_e) {
        identityAssets = [];
        renderIdentityAssets([]);
    }
}

async function uploadIdentityAsset() {
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    const fileInput = id("identity-upload-input");
    if (!cid || !fileInput || !fileInput.files || !fileInput.files.length) {
        addLogEntry("error", "Select a campaign and file first.");
        return;
    }
    const role = id("identity-upload-role")?.value || "anchor";
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    fd.append("role", role);
    try {
        const resp = await fetch("/api/campaigns/" + encodeURIComponent(cid) + "/assets/upload", {
            method: "POST",
            body: fd,
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") {
            addLogEntry("error", "Identity upload failed: " + (data.detail || data.error || resp.status));
            return;
        }
        addLogEntry("hermes", "Identity asset uploaded: " + data.asset.asset_id);
        fileInput.value = "";
        await loadIdentityAssets(cid);
    } catch (e) {
        addLogEntry("error", "Identity upload error: " + e.message);
    }
}

async function updateIdentityAsset(assetId, patch) {
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    if (!cid || !assetId) return;
    try {
        await fetch("/api/campaigns/" + encodeURIComponent(cid) + "/assets/" + encodeURIComponent(assetId), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        });
        await loadIdentityAssets(cid);
    } catch (_e) {}
}

async function loadIdentityTab() {
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    if (id("identity-campaign-readout")) id("identity-campaign-readout").value = cid;
    await loadCampaignIdentity(cid);
    await loadIdentityTemplates();
    await loadCampaignFolders();
    populateIdentityCloneOptions();
}

function populateIdentityCloneOptions() {
    const sel = id("identity-clone-source");
    if (!sel) return;
    sel.innerHTML = "";
    const rows = document.querySelectorAll("#campaign-list .campaign-row .campaign-btn");
    rows.forEach((btn) => {
        const cid = String(btn.textContent || "").trim();
        if (!cid || cid === "All") return;
        const opt = document.createElement("option");
        opt.value = cid;
        opt.textContent = cid;
        sel.appendChild(opt);
    });
}

async function cloneIdentityFromCampaign() {
    const dst = (shotFilters.campaignId || currentCampaignId || "").trim();
    const src = id("identity-clone-source")?.value || "";
    if (!dst || !src) return;
    try {
        const resp = await fetch("/api/campaigns/" + encodeURIComponent(dst) + "/identity/clone/" + encodeURIComponent(src), { method: "POST" });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") throw new Error(data.detail || "clone failed");
        await loadCampaignIdentity(dst);
        addLogEntry("hermes", "Identity cloned from " + src);
    } catch (e) {
        addLogEntry("error", "Identity clone failed: " + e.message);
    }
}

async function autoSelectIdentityAnchors() {
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    if (!cid) return;
    try {
        const resp = await fetch("/api/campaigns/" + encodeURIComponent(cid) + "/assets/auto-select", { method: "POST" });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "auto-select failed");
        await loadIdentityAssets(cid);
        addLogEntry("hermes", "Auto-selected " + (data.selected || 0) + " anchor assets.");
    } catch (e) {
        addLogEntry("error", "Auto-select failed: " + e.message);
    }
}

async function bulkSetIdentityRole() {
    const role = id("identity-bulk-role")?.value || "anchor";
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    if (!cid || !identityAssetSelection.size) return;
    for (const aid of identityAssetSelection) {
        await updateIdentityAsset(aid, { role });
    }
}

async function bulkSetIdentityActive(flag) {
    const cid = (shotFilters.campaignId || currentCampaignId || "").trim();
    if (!cid || !identityAssetSelection.size) return;
    for (const aid of identityAssetSelection) {
        await updateIdentityAsset(aid, { active: !!flag });
    }
}

async function loadIdentityTemplates() {
    const sel = id("identity-template-select");
    if (!sel) return;
    try {
        const resp = await fetch("/api/identity/templates");
        const data = await resp.json();
        sel.innerHTML = "";
        (data.templates || []).forEach((t) => {
            const opt = document.createElement("option");
            opt.value = t;
            opt.textContent = t;
            sel.appendChild(opt);
        });
    } catch (_e) {}
}

async function saveIdentityTemplateFromForm() {
    const name = (id("identity-template-name")?.value || "").trim();
    if (!name) return;
    const pack = getIdentityPackFromUI();
    if (!pack) return;
    try {
        const resp = await fetch("/api/identity/templates/" + encodeURIComponent(name), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(pack),
        });
        if (!resp.ok) throw new Error("save failed");
        await loadIdentityTemplates();
        addLogEntry("hermes", "Identity template saved: " + name);
    } catch (e) {
        addLogEntry("error", "Template save failed: " + e.message);
    }
}

async function loadIdentityTemplateIntoForm() {
    const name = id("identity-template-select")?.value || "";
    if (!name) return;
    try {
        const resp = await fetch("/api/identity/templates/" + encodeURIComponent(name));
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "load failed");
        setIdentityUI(data.identity_pack || {});
        addLogEntry("hermes", "Identity template loaded: " + name);
        updateIdentityPreview();
    } catch (e) {
        addLogEntry("error", "Template load failed: " + e.message);
    }
}

function updateIdentityPreview() {
    const el = id("identity-anchors");
    const out = id("identity-prompt-preview");
    if (!el) return;
    const pack = getIdentityPackFromUI();
    if (!pack) {
        if (out) out.value = "";
        return;
    }
    const preview = [
        pack.type ? ("identity lock " + pack.type + ": " + (pack.name || "unnamed")) : "",
        pack.identity_tokens.length ? ("traits: " + pack.identity_tokens.join(", ")) : "",
        pack.negative_tokens.length ? ("drift negatives: " + pack.negative_tokens.join(", ")) : "",
        pack.anchor_image_ids.length ? ("anchors: " + pack.anchor_image_ids.length) : "",
    ].filter(Boolean).join(" | ");
    el.title = preview;
    if (out) out.value = preview;
}

function onCampaignSortChange() {
    const key = document.getElementById("campaign-sort-key")?.value || "name";
    const reverse = !!document.getElementById("campaign-sort-reverse")?.checked;
    campaignSort = { key, reverse };
    loadCampaignFolders();
}

function onMediaSortChange() {
    mediaSort = { key: "time", reverse: !!mediaSort.reverse };
    syncInlineMediaSortControls();
    loadShots();
    loadVideoLibrary();
}

function syncInlineMediaSortControls() {
    const labels = mediaSort.reverse ? ["Newest", "↓"] : ["Oldest", "↑"];
    const sideBtn = document.getElementById("media-sort-toggle");
    const dockBtn = document.getElementById("media-sort-toggle-inline");
    if (sideBtn) {
        sideBtn.title = "Toggle media sort order";
        sideBtn.textContent = labels[1];
    }
    if (dockBtn) {
        dockBtn.title = "Sort: " + labels[0] + " first";
        dockBtn.textContent = labels[1];
    }
}

function toggleMediaSortOrder() {
    mediaSort = { key: "time", reverse: !mediaSort.reverse };
    syncInlineMediaSortControls();
    loadShots();
    loadVideoLibrary();
}

function _parseTs(v) {
    if (!v) return 0;
    const t = Date.parse(v);
    return Number.isFinite(t) ? t : 0;
}

function _sortCampaigns(list) {
    const arr = [...(list || [])];
    arr.sort((a, b) => {
        if (campaignSort.key === "time") {
            const ta = _parseTs(a.started_at || a.created_at);
            const tb = _parseTs(b.started_at || b.created_at);
            return ta - tb;
        }
        return String(a.campaign_id || "").localeCompare(String(b.campaign_id || ""));
    });
    if (campaignSort.reverse) arr.reverse();
    return arr;
}

function _sortShots(list) {
    const arr = [...(list || [])];
    arr.sort((a, b) => {
        if (mediaSort.key === "name") {
            return String(a.id || a.shot_id || "").localeCompare(String(b.id || b.shot_id || ""));
        }
        const ta = _parseTs(a.created_at) || _parseTs(a.audit_timestamp);
        const tb = _parseTs(b.created_at) || _parseTs(b.audit_timestamp);
        return ta - tb;
    });
    if (mediaSort.reverse) arr.reverse();
    return arr;
}

async function refreshShotViews() {
    // Keep filter state in sync with controls before reloading.
    shotFilters.campaignId = (document.getElementById("filter-campaign-id")?.value || "").trim();
    shotFilters.renderedOnly = !!document.getElementById("filter-rendered-only")?.checked;
    shotFilters.failedOnly = !!document.getElementById("filter-failed-only")?.checked;
    shotFilters.passedOnly = !!document.getElementById("filter-passed-only")?.checked;
    shotFilters.retriesOnly = !!document.getElementById("filter-retries-only")?.checked;
    shotFilters.importedOnly = !!document.getElementById("filter-imported-only")?.checked;
    try {
        await fetch("/api/shots/reindex-storage", { method: "POST" });
    } catch (_e) {
        // best effort
    }
    await loadShots();
    await loadVideoLibrary();
    await loadCampaignFolders();
}

function initDashboardResizer() {
    if (!$dashboardDivider || !$dashboardLeftPane) return;
    let dragging = false;

    const onMouseMove = (event) => {
        if (!dragging) return;
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        if (!viewportWidth) return;
        const leftPercent = (event.clientX / viewportWidth) * 100;
        const clamped = Math.max(28, Math.min(72, leftPercent));
        $dashboardLeftPane.style.width = clamped + "%";
    };

    const onMouseUp = () => {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove("dashboard-resizing");
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
    };

    $dashboardDivider.addEventListener("mousedown", (event) => {
        event.preventDefault();
        dragging = true;
        document.body.classList.add("dashboard-resizing");
        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
    });
}

function initVideoResizer() {
    const $divider = document.getElementById("video-divider");
    const $leftPane = document.getElementById("video-left-pane");
    if (!$divider || !$leftPane) return;
    let dragging = false;

    const onMouseMove = (event) => {
        if (!dragging) return;
        const workspace = $divider.parentElement;
        if (!workspace) return;
        const rect = workspace.getBoundingClientRect();
        const offsetX = event.clientX - rect.left;
        const percent = (offsetX / rect.width) * 100;
        const clamped = Math.max(28, Math.min(72, percent));
        $leftPane.style.width = clamped + "%";
    };

    const onMouseUp = () => {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove("dashboard-resizing");
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
    };

    $divider.addEventListener("mousedown", (event) => {
        event.preventDefault();
        dragging = true;
        document.body.classList.add("dashboard-resizing");
        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
    });
}

function applyShotFilters() {
    shotFilters.campaignId = (document.getElementById("filter-campaign-id")?.value || "").trim();
    shotFilters.renderedOnly = !!document.getElementById("filter-rendered-only")?.checked;
    shotFilters.failedOnly = !!document.getElementById("filter-failed-only")?.checked;
    shotFilters.passedOnly = !!document.getElementById("filter-passed-only")?.checked;
    shotFilters.retriesOnly = !!document.getElementById("filter-retries-only")?.checked;
    shotFilters.importedOnly = !!document.getElementById("filter-imported-only")?.checked;
    loadShots();
    loadVideoLibrary();
}

function shotMatchesFilters(s) {
    const isRetry = !!(s.retry_of || s.parent_shot_id || String(s.id).includes("__retry_"));
    const audit = (s.audit_status || "").toLowerCase();
    const campaign = String(s.campaign_id || "");
    const state = String(s.state || s.status || "").toLowerCase();
    const source = String(s.source || "");
    const effectiveAudit = audit || (state.includes("fail") ? "fail" : (state.includes("pass") ? "pass" : ""));

    if (shotFilters.campaignId && campaign !== shotFilters.campaignId) return false;
    if (shotFilters.renderedOnly && !(s.image_url || state.includes("rendered") || state.includes("audited") || state.includes("final"))) return false;
    if (shotFilters.failedOnly && effectiveAudit !== "fail") return false;
    if (shotFilters.passedOnly && effectiveAudit !== "pass") return false;
    if (shotFilters.retriesOnly && !isRetry) return false;
    if (shotFilters.importedOnly && source !== "import") return false;
    return true;
}

// ---------------------------------------------------------------------------
// Page Navigation
// ---------------------------------------------------------------------------
function switchPage(pageClass) {
    const prevActive = document.querySelector(".page-view.active");
    const prevClass = prevActive ? Array.from(prevActive.classList).find((c) => c.endsWith("-view")) : "";
    // Hide all page views
    document.querySelectorAll(".page-view").forEach(el => {
        el.classList.remove("active");
        el.style.display = "none";
    });

    // Show target page
    const target = document.querySelector("." + pageClass);
    if (target) {
        target.classList.add("active");
        target.style.display = "";
    }

    // Update nav tabs
    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.classList.toggle("active", tab.getAttribute("data-page") === pageClass);
    });

    // Tear down heavy graph resources when leaving Memory.
    if (prevClass === "memory-view" && pageClass !== "memory-view" && window._memoryCy) {
        try { window._memoryCy.destroy(); } catch (_e) {}
        window._memoryCy = null;
        const cy = document.getElementById("cy-canvas");
        if (cy) cy.innerHTML = "";
    }

    // Load config when switching to settings
    if (pageClass === "settings-view") {
        loadConfig();
    }
    if (pageClass === "spark-view") {
        loadVideoLibrary();
    }
    if (pageClass === "identity-view") {
        loadIdentityTab();
    }
    if (pageClass === "memory-view") {
        loadMemoryTab();
    }
}

async function loadCampaignFolders() {
    if (!$campaignList) return;
    try {
        const resp = await fetch("/api/campaigns");
        const data = await resp.json();
        const campaigns = _sortCampaigns(Array.isArray(data.campaigns) ? data.campaigns : []);
        $campaignList.innerHTML = "";

        // "All" option: clears campaign filter and shows every campaign.
        const allRow = document.createElement("div");
        allRow.className = "campaign-row";
        const allSelected = !shotFilters.campaignId;
        if (allSelected) allRow.classList.add("active");

        const allBtn = document.createElement("button");
        allBtn.className = "campaign-btn";
        allBtn.textContent = "All";
        allBtn.title = "Show all campaigns";
        allBtn.addEventListener("click", () => {
            const filter = document.getElementById("filter-campaign-id");
            if (filter) filter.value = "";
            shotFilters.campaignId = "";
            currentCampaignId = "";
            // Reset sidebar/media filters so "All" truly shows all shots.
            shotFilters.renderedOnly = false;
            shotFilters.failedOnly = false;
            shotFilters.passedOnly = false;
            shotFilters.retriesOnly = false;
            shotFilters.importedOnly = false;
            const ids = [
                "filter-rendered-only",
                "filter-failed-only",
                "filter-passed-only",
                "filter-retries-only",
                "filter-imported-only",
            ];
            ids.forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.checked = false;
            });
            loadCampaignIdentity("");
            loadShots();
            loadVideoLibrary();
            loadCampaignFolders();
        });
        allRow.appendChild(allBtn);

        const allMeta = document.createElement("span");
        allMeta.className = "campaign-meta";
        allMeta.textContent = String(data.count || campaigns.length || 0);
        allRow.appendChild(allMeta);
        $campaignList.appendChild(allRow);

        if (!campaigns.length) return;

        campaigns.forEach((c) => {
            const row = document.createElement("div");
            row.className = "campaign-row";
            if (shotFilters.campaignId && c.campaign_id === shotFilters.campaignId) row.classList.add("active");

            const campaignBtn = document.createElement("button");
            campaignBtn.className = "campaign-btn";
            campaignBtn.textContent = c.campaign_id;
            campaignBtn.title = c.campaign_id;
            campaignBtn.addEventListener("click", () => {
                const filter = document.getElementById("filter-campaign-id");
                if (filter) filter.value = c.campaign_id;
                shotFilters.campaignId = c.campaign_id;
                currentCampaignId = c.campaign_id;
                // Do not overwrite the creative brief with slug-derived fallbacks.
                // Older campaigns without persisted manifest briefs can return a
                // truncated humanized campaign id as "brief".
                if ($briefInput && c.brief && c.brief_source !== "humanized_id") {
                    $briefInput.value = c.brief;
                }
                loadCampaignIdentity(c.campaign_id);
                loadShots();
                loadVideoLibrary();
                loadCampaignFolders();
            });
            row.appendChild(campaignBtn);

            if (c.identity_type) {
                const idBadge = document.createElement("span");
                idBadge.className = "campaign-meta";
                idBadge.textContent = c.identity_type === "product" ? "PROD" : "CHAR";
                idBadge.title = c.identity_name || c.identity_type;
                row.appendChild(idBadge);
            }

            const meta = document.createElement("span");
            meta.className = "campaign-meta";
            meta.textContent = String(c.shot_count || 0);
            row.appendChild(meta);

            const renameBtn = document.createElement("button");
            renameBtn.className = "campaign-rename";
            renameBtn.textContent = "Rename";
            renameBtn.addEventListener("click", async (event) => {
                event.stopPropagation();
                const newName = window.prompt("Rename campaign folder", c.campaign_id);
                if (!newName || newName.trim() === c.campaign_id) return;
                try {
                    const renameResp = await fetch("/api/campaigns/rename", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            old_campaign_id: c.campaign_id,
                            new_campaign_name: newName.trim(),
                        }),
                    });
                    const result = await renameResp.json();
                    if (!renameResp.ok || result.status !== "ok") {
                        addLogEntry("error", "Campaign rename failed: " + (result.detail || result.error || renameResp.status));
                        return;
                    }
                    addLogEntry("system", "Campaign renamed: " + result.old_campaign_id + " -> " + result.new_campaign_id);
                    if (currentCampaignId === result.old_campaign_id) currentCampaignId = result.new_campaign_id;
                    const filter = document.getElementById("filter-campaign-id");
                    if (filter && filter.value === result.old_campaign_id) filter.value = result.new_campaign_id;
                    loadCampaignFolders();
                    loadShots();
                    loadVideoLibrary();
                } catch (err) {
                    addLogEntry("error", "Campaign rename error: " + err.message);
                }
            });
            row.appendChild(renameBtn);

            const deleteBtn = document.createElement("button");
            deleteBtn.className = "campaign-delete";
            deleteBtn.textContent = "Delete";
            deleteBtn.addEventListener("click", async (event) => {
                event.stopPropagation();
                const ok = window.confirm(`Delete campaign "${c.campaign_id}"?\n\nThis removes campaign shots and campaign folders from media storage.`);
                if (!ok) return;
                try {
                    const delResp = await fetch("/api/campaigns/" + encodeURIComponent(c.campaign_id), {
                        method: "DELETE",
                    });
                    const result = await delResp.json();
                    if (!delResp.ok || result.status !== "ok") {
                        addLogEntry("error", "Campaign delete failed: " + (result.detail || result.error || delResp.status));
                        return;
                    }
                    addLogEntry("system", "Campaign deleted: " + c.campaign_id + " (removed shots: " + String(result.removed_shots || 0) + ")");
                    if (currentCampaignId === c.campaign_id) currentCampaignId = "";
                    const filter = document.getElementById("filter-campaign-id");
                    if (filter && filter.value === c.campaign_id) filter.value = "";
                    shotFilters.campaignId = "";
                    loadCampaignIdentity("");
                    loadCampaignFolders();
                    loadShots();
                    loadVideoLibrary();
                } catch (err) {
                    addLogEntry("error", "Campaign delete error: " + err.message);
                }
            });
            row.appendChild(deleteBtn);

            $campaignList.appendChild(row);
        });
    } catch (e) {
        $campaignList.innerHTML = '<div style="color:#666; font-size:12px;">Failed to load campaigns</div>';
    }
}

// ---------------------------------------------------------------------------
// Settings: Load Config
// ---------------------------------------------------------------------------
async function loadConfig() {
    try {
        const resp = await fetch("/api/config");
        currentConfig = await resp.json();

        // Backend mode
        const backendMode = currentConfig.backend_mode || "local";
        document.getElementById("cfg-backend-mode").checked = backendMode === "remote";
        _updateBackendLabels(backendMode === "remote");

        // AI Provider (Nous / Kimi / OpenRouter)
        const kimi = currentConfig.kimi || {};
        const keyField = document.getElementById("cfg-kimi-api-key");
        keyField.value = "";
        keyField.placeholder = kimi.api_key_set ? "••••••••  (key saved — paste to replace)" : "Bearer token...";
        document.getElementById("cfg-kimi-endpoint").value = kimi.endpoint || "";

        // Models
        const models = currentConfig.models || {};

        // Director
        const director = models.director_kimi || {};
        document.getElementById("cfg-director-model").value = director.model_name || "";
        const directorEndpointEl = document.getElementById("cfg-director-endpoint");
        if (directorEndpointEl) directorEndpointEl.value = director.endpoint || "";
        const dApi1 = director.endpoint_api1 || director.endpoint || "";
        const dApi1El = document.getElementById("cfg-director-endpoint-api1");
        if (dApi1El) dApi1El.value = dApi1;

        // Vision / audit model
        const kimiVl = models.kimi_vl || {};
        const vApi1 = kimiVl.endpoint_api1 || kimiVl.endpoint || "";
        const vApi1El = document.getElementById("cfg-vision-endpoint-api1");
        if (vApi1El) vApi1El.value = vApi1;

        document.getElementById("cfg-visual-model").value = kimiVl.model_name || "";

        // LM Studio (Hermes 3)
        const hermes = models.hermes_3 || {};
        document.getElementById("cfg-lmstudio-host").value = hermes.host || "";
        document.getElementById("cfg-lmstudio-port").value = hermes.port || "";
        document.getElementById("cfg-lmstudio-model").value = hermes.model_name || "";

        // ComfyUI
        const comfyui = currentConfig.comfyui || {};
        const comfyPrimaryEl = document.getElementById("cfg-comfyui-primary");
        if (comfyPrimaryEl) comfyPrimaryEl.value = comfyui.primary || "";
        const comfySecondaryEl = document.getElementById("cfg-comfyui-secondary");
        if (comfySecondaryEl) comfySecondaryEl.value = comfyui.secondary || "";

        // Spark
        const spark = currentConfig.spark || {};
        const sparkPrimaryEl = document.getElementById("cfg-spark-primary");
        if (sparkPrimaryEl) sparkPrimaryEl.value = spark.primary || "";
        const sparkSecondaryEl = document.getElementById("cfg-spark-secondary");
        if (sparkSecondaryEl) sparkSecondaryEl.value = spark.secondary || "";
        const sparkWorkflowEl = document.getElementById("cfg-spark-workflow");
        if (sparkWorkflowEl) sparkWorkflowEl.value = spark.workflow_file || "";

    } catch (e) {
        console.error("Failed to load config:", e);
    }
}

function _updateBackendLabels(isRemote) {
    const local = document.getElementById("backend-label-local");
    const api = document.getElementById("backend-label-api");
    if (!local || !api) return;
    local.classList.toggle("active", !isRemote);
    api.classList.toggle("active", isRemote);
}

function onBackendModeToggle() {
    const isRemote = document.getElementById("cfg-backend-mode").checked;
    _updateBackendLabels(isRemote);
    markDirty('backend_mode');
}

// ---------------------------------------------------------------------------
// Settings: Track Changes
// ---------------------------------------------------------------------------
function markDirty(dotKey) {
    // Read the current value from the corresponding field
    const fieldMap = {
        'backend_mode': () => document.getElementById("cfg-backend-mode").checked ? "remote" : "local",
        'kimi.api_key': () => document.getElementById("cfg-kimi-api-key").value,
        'kimi.endpoint': () => document.getElementById("cfg-kimi-endpoint").value,
        'models.director_kimi.model_name': () => document.getElementById("cfg-director-model").value,
        'models.director_kimi.endpoint': () => document.getElementById("cfg-director-endpoint")?.value || "",
        'models.director_kimi.endpoint_api1': () => document.getElementById("cfg-director-endpoint-api1")?.value || "",
        'models.kimi_vl.model_name': () => document.getElementById("cfg-visual-model").value,
        'models.kimi_vl.endpoint': () => document.getElementById("cfg-vision-endpoint-api1")?.value || "",
        'models.kimi_vl.endpoint_api1': () => document.getElementById("cfg-vision-endpoint-api1")?.value || "",
        'models.hermes_3.host': () => document.getElementById("cfg-lmstudio-host").value,
        'models.hermes_3.port': () => parseInt(document.getElementById("cfg-lmstudio-port").value) || 0,
        'models.hermes_3.model_name': () => document.getElementById("cfg-lmstudio-model").value,
        'comfyui.primary': () => document.getElementById("cfg-comfyui-primary")?.value || "",
        'comfyui.secondary': () => document.getElementById("cfg-comfyui-secondary")?.value || "",
        'spark.primary': () => document.getElementById("cfg-spark-primary")?.value || "",
        'spark.secondary': () => document.getElementById("cfg-spark-secondary")?.value || "",
        'spark.workflow_file': () => document.getElementById("cfg-spark-workflow")?.value || "",
    };

    if (fieldMap[dotKey]) {
        configDirty[dotKey] = fieldMap[dotKey]();
    }
}

// ---------------------------------------------------------------------------
// Settings: Save All
// ---------------------------------------------------------------------------
async function saveAllSettings() {
    if (Object.keys(configDirty).length === 0) {
        showToast("No changes to save", "loading");
        return;
    }

    try {
        const resp = await fetch("/api/config/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ updates: configDirty }),
        });
        const result = await resp.json();

        if (result.status === "success") {
            // Update current config
            for (const [key, value] of Object.entries(configDirty)) {
                const parts = key.split(".");
                let obj = currentConfig;
                for (const part of parts.slice(0, -1)) {
                    if (!(part in obj)) obj[part] = {};
                    obj = obj[part];
                }
                obj[parts[parts.length - 1]] = value;
            }
            configDirty = {};
            showToast("Saved: " + result.saved.length + " field(s)", "ok");
        } else {
            showToast("Save failed: " + (result.error || "unknown"), "err");
        }
    } catch (e) {
        showToast("Save error: " + e.message, "err");
    }
}

// ---------------------------------------------------------------------------
// Settings: Toast Notifications
// ---------------------------------------------------------------------------
function showToast(msg, type) {
    const $toast = document.getElementById("settings-toast");
    $toast.textContent = msg;
    $toast.className = "test-result " + type;
    if (type === "ok" || type === "err") {
        setTimeout(() => { $toast.className = "test-result"; }, 3000);
    }
}

// ---------------------------------------------------------------------------
// Settings: Test Kimi
// ---------------------------------------------------------------------------
async function testProvider() {
    const $result = document.getElementById("kimi-test-result");
    const apiKey = document.getElementById("cfg-kimi-api-key").value;
    const endpoint = document.getElementById("cfg-kimi-endpoint").value;
    const hasSavedKey = !!(currentConfig && currentConfig.kimi && currentConfig.kimi.api_key_set);

    if ((!apiKey && !hasSavedKey) || !endpoint) {
        $result.textContent = "Please fill in endpoint and API key, or save an API key first";
        $result.className = "test-result err";
        return;
    }

    $result.textContent = "Testing connection...";
    $result.className = "test-result loading";

    try {
        const resp = await fetch("/api/test/nous", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, endpoint: endpoint }),
        });
        const data = await resp.json();

        if (data.status === "ok") {
            $result.textContent = "Connected! Latency: " + data.latency_ms + "ms";
            $result.className = "test-result ok";
        } else {
            $result.textContent = "Failed: " + (data.error || "unknown error");
            $result.className = "test-result err";
        }
    } catch (e) {
        $result.textContent = "Error: " + e.message;
        $result.className = "test-result err";
    }
}

async function testDirector() {
    const $result = document.getElementById("director-test-result");
    $result.textContent = "Testing Director...";
    $result.className = "test-result loading";
    try {
        const resp = await fetch("/api/test/director");
        const data = await resp.json();
        if (data.status === "ok") {
            $result.textContent = "Director OK: " + data.model + " (" + data.latency_ms + "ms)";
            $result.className = "test-result ok";
        } else {
            $result.textContent = "Director failed: " + (data.error || "unknown error");
            $result.className = "test-result err";
        }
    } catch (e) {
        $result.textContent = "Director error: " + e.message;
        $result.className = "test-result err";
    }
}

async function testVision() {
    const $result = document.getElementById("vision-test-result");
    $result.textContent = "Testing Vision...";
    $result.className = "test-result loading";
    try {
        const resp = await fetch("/api/test/vision");
        const data = await resp.json();
        if (data.status === "ok") {
            $result.textContent = "Vision OK: " + data.model + " (" + data.latency_ms + "ms)";
            $result.className = "test-result ok";
        } else {
            $result.textContent = "Vision failed: " + (data.error || "unknown error");
            $result.className = "test-result err";
        }
    } catch (e) {
        $result.textContent = "Vision error: " + e.message;
        $result.className = "test-result err";
    }
}

// ---------------------------------------------------------------------------
// Settings: Test LM Studio
// ---------------------------------------------------------------------------
async function testLMStudio() {
    const $result = document.getElementById("lmstudio-test-result");
    const $modelsList = document.getElementById("lmstudio-models-list");
    const $modelsSelect = document.getElementById("lmstudio-models-select");
    const host = document.getElementById("cfg-lmstudio-host").value;
    const port = document.getElementById("cfg-lmstudio-port").value;

    $result.textContent = "Connecting to " + host + ":" + port + "...";
    $result.className = "test-result loading";
    $modelsList.style.display = "none";

    try {
        const url = "/api/test/lmstudio?host=" + encodeURIComponent(host) + "&port=" + encodeURIComponent(port);
        const resp = await fetch(url);
        const data = await resp.json();

        if (data.status === "ok") {
            $result.textContent = "Connected! Latency: " + data.latency_ms + "ms | " + data.message;
            $result.className = "test-result ok";

            // Populate model dropdown
            if (data.models && data.models.length > 0) {
                $modelsSelect.innerHTML = data.models.map(m =>
                    '<option value="' + escapeHtml(m) + '">' + escapeHtml(m) + '</option>'
                ).join("");
                $modelsList.style.display = "block";
            }
        } else {
            $result.textContent = "Failed: " + (data.error || "unknown error");
            $result.className = "test-result err";
        }
    } catch (e) {
        $result.textContent = "Error: " + e.message;
        $result.className = "test-result err";
    }
}

// ---------------------------------------------------------------------------
// Settings: Test ComfyUI
// ---------------------------------------------------------------------------
async function testComfyUI(which) {
    const $result = document.getElementById("comfyui-test-result");
    const host = document.getElementById("cfg-comfyui-" + which).value;

    if (!host) {
        $result.textContent = "Please fill in the " + which + " host URL";
        $result.className = "test-result err";
        return;
    }

    $result.textContent = "Testing " + which + ": " + host + "...";
    $result.className = "test-result loading";

    try {
        const resp = await fetch("/api/test/comfyui", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ host: host }),
        });
        const data = await resp.json();

        if (data.status === "ok") {
            $result.textContent = which + " connected! Latency: " + data.latency_ms + "ms";
            $result.className = "test-result ok";
        } else {
            $result.textContent = which + " failed: " + (data.error || "unknown error");
            $result.className = "test-result err";
        }
    } catch (e) {
        $result.textContent = which + " error: " + e.message;
        $result.className = "test-result err";
    }
}

async function testComfyUIAll() {
    const $result = document.getElementById("comfyui-test-result");
    const primary = document.getElementById("cfg-comfyui-primary")?.value?.trim() || "";
    const secondary = document.getElementById("cfg-comfyui-secondary")?.value?.trim() || "";
    const sparkRaw = document.getElementById("cfg-spark-primary")?.value?.trim() || "";
    const setDot = (id, status) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove("ok", "err");
        if (status === "ok") el.classList.add("ok");
        if (status === "err") el.classList.add("err");
    };

    setDot("server-dot-primary", "");
    setDot("server-dot-secondary", "");
    setDot("server-dot-spark", "");

    if (!primary && !secondary && !sparkRaw) {
        $result.textContent = "Please fill in at least one ComfyUI/Spark URL";
        $result.className = "test-result err";
        return;
    }

    $result.textContent = "Testing ComfyUI + Spark...";
    $result.className = "test-result loading";

    const checkOne = async (label, host) => {
        if (!host) return { label, status: "skipped", msg: "not set" };
        try {
            const resp = await fetch("/api/test/comfyui", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ host }),
            });
            const data = await resp.json();
            if (data.status === "ok") return { label, status: "ok", msg: `${data.latency_ms}ms` };
            return { label, status: "err", msg: data.error || "unknown error" };
        } catch (e) {
            return { label, status: "err", msg: e.message };
        }
    };

    const p = await checkOne("primary", primary);
    const s = await checkOne("secondary", secondary);

    const normalizeSparkHttp = (url) => {
        const u = String(url || "").trim();
        if (!u) return "";
        if (u.startsWith("http://") || u.startsWith("https://")) return u;
        if (u.startsWith("ws://")) return "http://" + u.slice("ws://".length);
        if (u.startsWith("wss://")) return "https://" + u.slice("wss://".length);
        return u.startsWith("//") ? ("http:" + u) : ("http://" + u);
    };

    const checkSpark = async (raw) => {
        if (!raw) return { label: "spark", status: "skipped", msg: "not set" };
        const httpUrl = normalizeSparkHttp(raw);
        try {
            const u = new URL(httpUrl);
            const resp = await fetch(`/api/spark/test?url=${encodeURIComponent(u.origin)}`);
            if (!resp.ok) {
                let detail = "unknown error";
                try {
                    const body = await resp.json();
                    detail = body?.detail || detail;
                } catch (_e) {}
                return { label: "spark", status: "err", msg: detail };
            }
            return { label: "spark", status: "ok", msg: u.origin };
        } catch (e) {
            return { label: "spark", status: "err", msg: e.message };
        }
    };

    const sp = await checkSpark(sparkRaw);
    setDot("server-dot-primary", p.status === "ok" ? "ok" : (p.status === "err" ? "err" : ""));
    setDot("server-dot-secondary", s.status === "ok" ? "ok" : (s.status === "err" ? "err" : ""));
    setDot("server-dot-spark", sp.status === "ok" ? "ok" : (sp.status === "err" ? "err" : ""));
    const parts = [p, s, sp].filter(x => x.status !== "skipped").map(x => `${x.label}: ${x.status === "ok" ? "ok" : "fail"} (${x.msg})`);
    const anyFail = [p, s, sp].some(x => x.status === "err");
    $result.textContent = parts.join(" | ") || "No hosts to test";
    $result.className = "test-result " + (anyFail ? "err" : "ok");
}

// ---------------------------------------------------------------------------
// Script / Director
// ---------------------------------------------------------------------------
const $scriptBrief = document.getElementById("script-brief");
const $scriptStatusText = document.getElementById("script-status-text");
const $scriptProgress = document.getElementById("script-progress");
const $shotList = document.getElementById("shot-list");
const $shotListPlaceholder = document.getElementById("shot-list-placeholder");
const $sendToSparkBtn = document.getElementById("send-to-spark-btn");

let characterMap = {}; // id -> name for linking

async function uploadBrief() {
    const fileInput = document.getElementById("brief-file-input");
    const file = fileInput.files[0];
    if (!file) return;

    $scriptStatusText.textContent = "Uploading " + file.name + "...";

    const formData = new FormData();
    formData.append("file", file);

    try {
        const resp = await fetch("/api/brief/upload", {
            method: "POST",
            body: formData,
        });
        const data = await resp.json();

        if (data.status === "ok") {
            $scriptBrief.value = data.content;
            $scriptStatusText.textContent = "Uploaded: " + data.filename + " (" + data.char_count + " chars)";
            setTimeout(() => { $scriptStatusText.textContent = "Ready"; }, 3000);
        } else {
            $scriptStatusText.textContent = "Error: " + (data.error || "Upload failed");
        }
    } catch (e) {
        $scriptStatusText.textContent = "Error: " + e.message;
    }
}

async function generateShotList() {
    const brief = $scriptBrief.value.trim();
    if (!brief) {
        $scriptStatusText.textContent = "Please enter or upload a brief";
        return;
    }

    const $btn = document.getElementById("generate-shots-btn");
    $btn.disabled = true;
    $btn.textContent = "Generating...";
    $scriptStatusText.textContent = "Director is analyzing brief...";
    $scriptProgress.textContent = "";

    // Clear existing shots
    director_shots = {};
    $shotList.innerHTML = "";
    $shotList.style.display = "none";
    $shotListPlaceholder.style.display = "block";

    try {
        const resp = await fetch("/api/director/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ brief: brief }),
        });

        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const event = JSON.parse(line);
                    handleDirectorEvent(event);
                } catch (e) { /* skip */ }
            }
        }

        if (buffer.trim()) {
            try {
                const event = JSON.parse(buffer);
                handleDirectorEvent(event);
            } catch (e) { /* skip */ }
        }

    } catch (e) {
        $scriptStatusText.textContent = "Error: " + e.message;
    } finally {
        $btn.disabled = false;
        $btn.textContent = "Generate Shot List";
    }
}

function handleDirectorEvent(event) {
    switch (event.type) {
        case "status":
            $scriptStatusText.textContent = event.text;
            break;

        case "shot":
            $shotListPlaceholder.style.display = "none";
            $shotList.style.display = "flex";
            renderShotCard(event.shot, event.index, event.total);
            $scriptProgress.textContent = event.index + "/" + event.total;
            break;

        case "done":
            $scriptStatusText.textContent = event.text;
            updateSendToSparkBtn();
            break;

        case "error":
            $scriptStatusText.textContent = "Error: " + event.text;
            break;
    }
}

function renderShotCard(shot, index, total) {
    const card = document.createElement("div");
    card.className = "shot-card";
    card.id = "shot-card-" + shot.id;
    card.dataset.shotId = shot.id;

    const intentClass = shot.intent === "video" ? "video" : "image";
    const intentLabel = shot.intent === "video" ? "VIDEO" : "IMAGE";

    const charsHtml = (shot.characters || []).map(c =>
        '<span class="char-tag" data-char="' + escapeHtml(c) + '" onclick="onCharTagClick(\'' + escapeHtml(c) + '\')">' + escapeHtml(c) + "</span>"
    ).join("");

    card.innerHTML =
        '<div class="shot-header">' +
            '<input type="checkbox" class="shot-checkbox" data-shot-id="' + shot.id + '" onchange="toggleShotSelection()">' +
            '<span class="shot-id">' + escapeHtml(shot.id) + '</span>' +
            '<span class="shot-intent ' + intentClass + '">' + intentLabel + '</span>' +
            '<div class="shot-actions">' +
                '<button class="btn btn-secondary" onclick="toggleEditShot(\'' + shot.id + '\')">Edit</button>' +
                '<button class="btn btn-secondary" onclick="deleteShot(\'' + shot.id + '\')">Delete</button>' +
            '</div>' +
        '</div>' +
        '<div class="shot-description">' +
            '<div class="shot-text">' + escapeHtml(shot.description) + '</div>' +
            '<textarea class="shot-edit" style="display:none;" data-shot-id="' + shot.id + '">' + escapeHtml(shot.description) + '</textarea>' +
            '<div class="shot-edit-actions" style="display:none;gap:6px;margin-top:6px;">' +
                '<button class="btn btn-secondary" onclick="saveShotEdit(\'' + shot.id + '\')">Save</button>' +
                '<button class="btn btn-secondary" onclick="cancelShotEdit(\'' + shot.id + '\')">Cancel</button>' +
            '</div>' +
        '</div>' +
        (shot.mood ? '<div style="font-size:12px;color:#6C7278;"><em>Mood: ' + escapeHtml(shot.mood) + '</em></div>' : '') +
        (charsHtml ? '<div class="shot-meta"><div class="shot-characters">' + charsHtml + '</div></div>' : '');

    $shotList.appendChild(card);
}

function toggleEditShot(shotId) {
    const card = document.getElementById("shot-card-" + shotId);
    if (!card) return;

    const shotText = card.querySelector(".shot-text");
    const shotEdit = card.querySelector(".shot-edit");
    const editActions = card.querySelector(".shot-edit-actions");

    if (shotEdit.style.display === "none") {
        shotText.style.display = "none";
        shotEdit.style.display = "block";
        editActions.style.display = "flex";
        shotEdit.focus();
    } else {
        cancelShotEdit(shotId);
    }
}

async function saveShotEdit(shotId) {
    const card = document.getElementById("shot-card-" + shotId);
    if (!card) return;

    const shotEdit = card.querySelector(".shot-edit");
    const newDesc = shotEdit.value.trim();

    try {
        const resp = await fetch("/api/shots/" + shotId, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ description: newDesc }),
        });
        const data = await resp.json();

        if (data.status === "ok") {
            // Update display
            const shotText = card.querySelector(".shot-text");
            shotText.textContent = newDesc;
            shotText.style.display = "block";
            shotEdit.style.display = "none";
            card.querySelector(".shot-edit-actions").style.display = "none";

            // Update in-memory store
            if (director_shots[shotId]) {
                director_shots[shotId].description = newDesc;
            }
        }
    } catch (e) {
        alert("Failed to save: " + e.message);
    }
}

function cancelShotEdit(shotId) {
    const card = document.getElementById("shot-card-" + shotId);
    if (!card) return;

    const shotText = card.querySelector(".shot-text");
    const shotEdit = card.querySelector(".shot-edit");
    const editActions = card.querySelector(".shot-edit-actions");

    shotText.style.display = "block";
    shotEdit.style.display = "none";
    editActions.style.display = "none";
}

async function deleteShot(shotId) {
    if (!confirm("Delete shot " + shotId + "?")) return;

    try {
        const resp = await fetch("/api/director/shots/" + shotId, {
            method: "DELETE",
        });
        const data = await resp.json();

        if (data.status === "ok") {
            const card = document.getElementById("shot-card-" + shotId);
            if (card) card.remove();
            delete director_shots[shotId];
            updateSendToSparkBtn();

            if ($shotList.children.length === 0) {
                $shotList.style.display = "none";
                $shotListPlaceholder.style.display = "block";
            }
        }
    } catch (e) {
        alert("Failed to delete: " + e.message);
    }
}

function onCharTagClick(charName) {
    // If character exists in sidebar, highlight it
    const charCards = document.querySelectorAll(".char-card");
    charCards.forEach(card => {
        const nameEl = card.querySelector(".char-name");
        if (nameEl && nameEl.textContent.toLowerCase().includes(charName.toLowerCase())) {
            card.style.background = "#2a2a3e";
            setTimeout(() => { card.style.background = ""; }, 2000);
        }
    });
}

function toggleShotSelection() {
    updateSendToSparkBtn();
}

function updateSendToSparkBtn() {
    const checked = document.querySelectorAll(".shot-checkbox:checked");
    $sendToSparkBtn.disabled = checked.length === 0;
    $sendToSparkBtn.textContent = checked.length > 0
        ? "Send " + checked.length + " Shot(s) to Spark"
        : "Send Selected to Spark";
}

async function sendToSpark() {
    const checked = document.querySelectorAll(".shot-checkbox:checked");
    if (checked.length === 0) return;

    const shotsToSend = [];
    checked.forEach(cb => {
        const shotId = cb.dataset.shotId;
        if (director_shots[shotId]) {
            shotsToSend.push(director_shots[shotId]);
        }
    });

    if (shotsToSend.length === 0) return;

    // Switch to Video page
    switchPage("spark-view");
    await loadVideoLibrary();

    videoSelection.clear();
    shotsToSend.forEach(s => {
        if (s && s.id) videoSelection.add(s.id);
    });
    updateVideoSelectionUI();
    shotsToSend.forEach(s => {
        const cell = document.querySelector('.grid-cell[data-shot-id="' + CSS.escape(s.id) + '"]');
        if (!cell) return;
        cell.classList.add("selected");
        const cb = cell.querySelector('input[type="checkbox"]');
        if (cb) cb.checked = true;
    });

    $scriptStatusText.textContent = "Selected " + shotsToSend.length + " shot(s) in Video tab";
}

function clearShotList() {
    director_shots = {};
    $shotList.innerHTML = "";
    $shotList.style.display = "none";
    $shotListPlaceholder.style.display = "block";
    $scriptStatusText.textContent = "Ready";
    $scriptProgress.textContent = "";
    updateSendToSparkBtn();
}

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------
let __systemLogSideRight = false;
let __lastLogSpeaker = null;
let __profileLogQueueDelayMs = 0;
let __profileLogQueueTimer = null;
function addLogEntry(type, text) {
    const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
    const row = document.createElement("div");
    if (__lastLogSpeaker !== type) {
        __systemLogSideRight = !__systemLogSideRight;
        __lastLogSpeaker = type;
    }
    row.className = "log-row " + type + " " + (__systemLogSideRight ? "right" : "left");

    const tags = {
        user: "YOU",
        kimi: "[KIMI \u270D]",
        hermes: "[HERMES \uD83E\uDDE0]",
        spark: "[SPARK \u26A1]",
        memory: "[MEM \uD83D\uDCBE]",
        system: "[SYS]",
        error: "[ERR]",
        profile_director_kimi: "[Kimi / Director Planner]",
        profile_critic_kimi: "[Kimi / Coverage Critic]",
        profile_compiler_lmstudio: "[Hermes / Prompt Compiler]",
        profile_continuity_lmstudio: "[Hermes / Continuity Guard]",
        profile_remediation_lmstudio: "[Hermes / Remediation Reprompter]",
        profile_audit_kimi: "[Kimi / Audit Judge]",
    };

    row.innerHTML =
        '<div class="log-bubble">' +
            '<div class="meta">' +
                '<span class="tag">' + escapeHtml((tags[type] || "[" + type.toUpperCase() + "]").replace(/^\[|\]$/g, "")) + "</span>" +
                '<span class="ts">' + ts + "</span>" +
            "</div>" +
            '<div class="msg">' + escapeHtml(text) + "</div>" +
        "</div>";

    $log.appendChild(row);
    $log.scrollTop = $log.scrollHeight;
}

function addQueuedProfileLogEntry(type, text) {
    const delay = __profileLogQueueDelayMs;
    __profileLogQueueDelayMs += 220;
    setTimeout(() => addLogEntry(type, text), delay);
    if (__profileLogQueueTimer) clearTimeout(__profileLogQueueTimer);
    __profileLogQueueTimer = setTimeout(() => {
        __profileLogQueueDelayMs = 0;
        __profileLogQueueTimer = null;
    }, __profileLogQueueDelayMs + 50);
}

function clearLog() {
    $log.innerHTML = "";
    __lastLogSpeaker = null;
    addLogEntry("system", "Log cleared");
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Campaign Runner (NDJSON streaming)
// ---------------------------------------------------------------------------
async function cancelCampaign() {
    if (campaignAbortController) campaignAbortController.abort();
    await fetch("/api/hermes/cancel", { method: "POST" }).catch(() => {});
    addLogEntry("system", "Campaign cancelled.");
}

async function runCampaign() {
    const brief = $briefInput.value.trim();
    if (!brief) {
        addLogEntry("error", "Please enter a creative brief");
        return;
    }

    const biblePath = $biblePath ? $biblePath.value.trim() : "";
    const length = $lengthSelect ? $lengthSelect.value : "";
    const klein = document.getElementById("model-klein")?.checked;
    const flux2 = document.getElementById("model-flux2")?.checked;
    const turbo = document.getElementById("model-turbo")?.checked;
    const appendToCampaign = !!document.getElementById("append-campaign")?.checked;
    const selectedCampaignId =
        (document.getElementById("filter-campaign-id")?.value || "").trim() ||
        (currentCampaignId || "").trim();
    const workflowMap = {
        flux2: {
            standard: "01_flux2_text_to_image",
            turbo: "01_flux2_text_to_image",
        },
        klein: "08_flux2_klein_9b_text_to_image",
    };
    const workflow_ids = [];
    if (klein) workflow_ids.push(workflowMap.klein);
    if (flux2) workflow_ids.push(turbo ? workflowMap.flux2.turbo : workflowMap.flux2.standard);
    if (turbo) {
        if (flux2) {
            addLogEntry("system", "Turbo mode enabled for Flux2.Dev.");
        } else {
            addLogEntry("system", "Turbo is only applied to Flux2.Dev.");
        }
    }
    // De-dupe in case multiple toggles currently map to the same numbered workflow.
    const dedupedWorkflows = [...new Set(workflow_ids)];
    if (!dedupedWorkflows.length) {
        addLogEntry("error", "Select at least one base model: Flux2 Klein and/or Flux2.Dev");
        return;
    }
    if (appendToCampaign && !selectedCampaignId) {
        addLogEntry("error", "Append is enabled, but no campaign is selected. Pick a campaign in the sidebar or disable append.");
        return;
    }
    const identity_pack = getIdentityPackFromUI();

    $runBtn.disabled = true;
    $runBtn.textContent = "Running...";
    campaignActive = true;
    campaignAbortController = new AbortController();
    const $cancelBtn = document.getElementById("cancel-campaign-btn");
    if ($cancelBtn) $cancelBtn.style.display = "inline-flex";

    addLogEntry("system", "Campaign started: " + brief);

    try {
        const resp = await fetch("/api/hermes/run-campaign", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                brief: brief,
                bible_path: biblePath,
                length: length,
                workflow_ids: dedupedWorkflows,
                identity_pack: identity_pack,
                campaign_id: selectedCampaignId,
                append_to_campaign: appendToCampaign,
            }),
            signal: campaignAbortController.signal,
        });

        if (!resp.ok) {
            throw new Error("HTTP " + resp.status);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete lines
            const lines = buffer.split("\n");
            buffer = lines.pop(); // keep incomplete line in buffer

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const event = JSON.parse(line);
                    handleCampaignEvent(event);
                } catch (e) {
                    addLogEntry("error", "Failed to parse event: " + line);
                }
            }
        }

        // Process any remaining buffer
        if (buffer.trim()) {
            try {
                const event = JSON.parse(buffer);
                handleCampaignEvent(event);
            } catch (e) {
                // ignore trailing partial
            }
        }

    } catch (e) {
        if (e.name !== "AbortError") {
            addLogEntry("warning", "Campaign stream disconnected: " + e.message);
            addLogEntry("system", "Backend may still be processing. Auto-refreshing media for 45s.");
            if (campaignRecoveryTimer) clearInterval(campaignRecoveryTimer);
            let ticks = 0;
            campaignRecoveryTimer = setInterval(async () => {
                ticks += 1;
                await refreshShotViews();
                if (ticks >= 9) {
                    clearInterval(campaignRecoveryTimer);
                    campaignRecoveryTimer = null;
                    addLogEntry("system", "Recovery refresh complete.");
                }
            }, 5000);
        }
    } finally {
        $runBtn.disabled = false;
        $runBtn.textContent = "Run Campaign";
        campaignActive = false;
        campaignAbortController = null;
        const $cancelBtn = document.getElementById("cancel-campaign-btn");
        if ($cancelBtn) $cancelBtn.style.display = "none";
    }
}

function handleCampaignEvent(event) {
    const type = event.type;
    const text = event.text || "";
    const shotId = event.shot_id || "";
    if (event.campaign_id) {
        currentCampaignId = event.campaign_id;
        loadCampaignFolders();
    }

    switch (type) {
        case "kimi":
            addLogEntry("kimi", text);
            break;

        case "kimi_raw":
            addLogEntry("kimi", "Raw preview: " + text + (event.campaign_id ? " — full exchange: /api/campaigns/" + event.campaign_id + "/agent-exchanges" : ""));
            break;

        case "kimi_plan":
            addLogEntry("kimi", text || ("Structured plan received (" + (event.count || 0) + " shots)"));
            break;

        case "kimi_review": {
            const score = event.score !== undefined ? event.score : "n/a";
            const status = event.status || "unknown";
            addLogEntry("kimi", "[review] status=" + status + " score=" + score);
            if (Array.isArray(event.coverage_gaps) && event.coverage_gaps.length) {
                addLogEntry("memory", "Kimi coverage gaps: " + event.coverage_gaps.slice(0, 3).join("; "));
            }
            if (event.director_notes) {
                addLogEntry("hermes", "Director notes: " + event.director_notes);
            }
            break;
        }

        case "hermes":
            addLogEntry("hermes", text);
            break;

        case "compiler":
            addLogEntry("hermes", "[compiler] " + text);
            break;

        case "spark":
            addLogEntry("spark", text);
            if (event.status === "queued" && event.prompt_id) {
                addLogEntry("memory", "Shot " + shotId + " stored (prompt_id: " + event.prompt_id + ")");
            }
            break;

        case "audit":
            addLogEntry("memory", text);
            break;

        case "remediation":
            addLogEntry("hermes", text);
            break;

        case "memory":
            addLogEntry("memory", text);
            break;

        case "error":
            addLogEntry("error", text);
            break;

        case "warning":
            addLogEntry("system", "Warning: " + text);
            break;
        case "profile":
            addQueuedProfileLogEntry(event.profile_color_key || "profile_compiler_lmstudio", text || "Profile event");
            break;

        case "done":
            addLogEntry("system", text);
            loadShots();
            break;

        default:
            addLogEntry("system", JSON.stringify(event));
    }
}

// ---------------------------------------------------------------------------
// Hermes Chat (NDJSON streaming)
// ---------------------------------------------------------------------------
async function sendChat() {
    const msg = $chatInput.value.trim();
    if (!msg || campaignActive) return;

    $chatInput.value = "";
    $chatStatus.textContent = "Hermes is thinking...";

    addLogEntry("user", msg);

    try {
        const resp = await fetch("/api/hermes/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: msg,
                history: chatHistory,
                session_id: sessionId,
            }),
        });

        if (!resp.ok) {
            throw new Error("HTTP " + resp.status);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullResponse = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            $chatStatus.textContent = "Hermes: " + fullResponse;

            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    if (data.token) {
                        fullResponse += data.token;
                        // Live update last hermes log entry
                        const entries = $log.querySelectorAll(".log-row.hermes .msg");
                        if (entries.length) {
                            entries[entries.length - 1].textContent = fullResponse;
                            $log.scrollTop = $log.scrollHeight;
                        }
                    }
                    if (data.done) {
                        // Store in history
                        chatHistory.push({ role: "user", content: msg });
                        chatHistory.push({ role: "assistant", content: fullResponse });
                        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
                    }
                    if (data.error) {
                        addLogEntry("error", data.error);
                    }
                } catch (e) {
                    // skip
                }
            }
        }

        // Final log entry
        if (fullResponse) {
            addLogEntry("hermes", fullResponse);
        }
        $chatStatus.textContent = "";

    } catch (e) {
        addLogEntry("error", "Chat failed: " + e.message);
        $chatStatus.textContent = "Error: " + e.message;
    }
}

// ---------------------------------------------------------------------------
// Characters
// ---------------------------------------------------------------------------
async function loadCharacters() {
    try {
        const resp = await fetch("/api/characters");
        const data = await resp.json();
        const chars = data.characters || [];

        if (!chars.length) {
            $charList.innerHTML = '<div style="color:#666; font-size:12px;">No anchors yet</div>';
            return;
        }

        $charList.innerHTML = chars.map(c =>
            '<div class="char-card">' +
            '<img src="' + c.anchor_src + '" alt="' + escapeHtml(c.name) + '">' +
            '<span class="char-name">' + escapeHtml(c.name) + "</span>" +
            "</div>"
        ).join("");
    } catch (e) {
        $charList.innerHTML = '<div style="color:#666; font-size:12px;">Failed to load</div>';
    }
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
async function loadStats() {
    try {
        const resp = await fetch("/api/stats");
        const data = await resp.json();
        document.getElementById("stat-shots").textContent = data.shots_in_store || 0;
        document.getElementById("stat-sessions").textContent = data.chat_sessions || 0;
        if (data.ram_percent != null) {
            document.getElementById("stat-ram").textContent = data.ram_percent + "%";
        }
    } catch (e) {
        // silent
    }
}

// ---------------------------------------------------------------------------
// Shots
// ---------------------------------------------------------------------------
async function loadShots() {
    try {
        const resp = await fetch("/api/shots");
        const data = await resp.json();
        const rawShots = Array.isArray(data) ? data : (data.shots || []);
        if (data.active_campaign_id) currentCampaignId = data.active_campaign_id;
        let shots = _sortShots(rawShots.filter(shotMatchesFilters));
        const hasRealMedia = shots.some(s => !!s.image_url);
        if (hasRealMedia) {
            shots = shots.filter(s => !!s.image_url || !s.id || String(s.id).includes("__retry_"));
        }
        const totalBeforeCap = shots.length;
        if (shots.length > MAX_DASHBOARD_THUMBS) shots = shots.slice(-MAX_DASHBOARD_THUMBS);
        $filmstrip.innerHTML = "";
        shots.forEach((s) => {
            const isRetry = !!(s.retry_of || s.parent_shot_id || String(s.id).includes("__retry_"));
            const state = String(s.state || s.status || "").toLowerCase();
            const audit = String(s.audit_status || "").toLowerCase() || (state.includes("fail") ? "fail" : (state.includes("pass") ? "pass" : ""));

            const item = document.createElement("div");
            item.className = "filmstrip-item";
            if (audit === "pass") item.classList.add("audit-pass");
            if (audit === "fail") item.classList.add("audit-fail");
            if (isRetry) item.classList.add("retry-cell");

            if (s.image_url) {
                const img = document.createElement("img");
                img.src = s.image_url;
                img.alt = s.id || "shot";
                img.loading = "lazy";
                img.decoding = "async";
                item.appendChild(img);

                item.addEventListener("click", () => toggleDashboardSelect(s.id, item));
                item.addEventListener("dblclick", (event) => {
                    event.preventDefault();
                    openLightbox({
                        image_url: s.image_url,
                        status: s.status || "complete",
                        prompt: s.prompt || "",
                        negative_prompt: s.negative_prompt || "",
                        workflow: s.workflow || s.workflow_id || "-",
                        workflow_profile: s.workflow_profile || "",
                        model_standard_name: s.model_standard_name || "",
                        model_standard_version: s.model_standard_version || "",
                        identity_type: s.identity_type || "",
                        identity_name: s.identity_name || "",
                        identity_expected_traits: s.identity_expected_traits || [],
                        identity_detected_notes: s.identity_detected_notes || [],
                        seed: s.seed || "Random",
                        kimi_plan: s.kimi_plan || null,
                        kimi_rationale: s.kimi_rationale || "",
                        skills_used: s.skills_used || [],
                        prompt_id: s.prompt_id || "",
                        audit_status: s.audit_status || "",
                        audit_score: s.audit_score ?? "",
                        audit_issues: s.audit_issues || [],
                        retry_of: s.retry_of || s.parent_shot_id || "",
                        video_prompt: s.video_prompt || "",
                        video_prompt_source: s.video_prompt_source || "",
                        variant: "-",
                    });
                });
            } else {
                const placeholder = document.createElement("div");
                placeholder.style.display = "flex";
                placeholder.style.alignItems = "center";
                placeholder.style.justifyContent = "center";
                placeholder.style.height = "100%";
                placeholder.style.color = "#555";
                placeholder.style.fontSize = "11px";
                placeholder.textContent = "Rendering...";
                item.appendChild(placeholder);
            }

            const label = document.createElement("div");
            label.className = "shot-label";
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "shot-select";
            checkbox.checked = dashboardSelection.has(s.id);
            checkbox.addEventListener("click", (event) => {
                event.stopPropagation();
                toggleDashboardSelect(s.id, item);
            });
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode((s.id || "-") + " — " + (s.status || "-")));
            if (s.state) {
                const stateBadge = document.createElement("span");
                stateBadge.className = "shot-badge";
                stateBadge.textContent = String(s.state).toUpperCase();
                label.appendChild(stateBadge);
            }

            if (audit === "pass" || audit === "fail") {
                const badge = document.createElement("span");
                badge.className = "shot-badge " + audit;
                badge.textContent = audit.toUpperCase();
                label.appendChild(badge);
            }
            if (s.video_prompt) {
                const vb = document.createElement("span");
                vb.className = "shot-badge vprompt";
                vb.textContent = videoPromptBadgeLabel(s);
                vb.title = videoPromptBadgeTitle(s);
                label.appendChild(vb);

                const dot = document.createElement("span");
                dot.className = "video-prompt-dot";
                dot.title = "Video prompt attached";
                item.appendChild(dot);
            }
            if (s.identity_type && s.identity_status) {
                const idb = document.createElement("span");
                idb.className = "shot-badge " + (s.identity_status === "pass" ? "pass" : "fail");
                idb.textContent = "ID " + String(s.identity_status).toUpperCase();
                label.appendChild(idb);
            }
            if (isRetry) {
                const retryBadge = document.createElement("span");
                retryBadge.className = "shot-badge retry";
                retryBadge.textContent = "RETRY";
                label.appendChild(retryBadge);
            }

            item.appendChild(label);
            $filmstrip.appendChild(item);
            item.classList.toggle("selected", dashboardSelection.has(s.id));
        });
        updateDashboardSelectionUI();
        if (totalBeforeCap > MAX_DASHBOARD_THUMBS) {
            addLogEntry("system", "Dashboard showing latest " + MAX_DASHBOARD_THUMBS + " of " + totalBeforeCap + " shots for stability.");
        }
        loadCampaignFolders();
    } catch (e) {
        addLogEntry("error", "Failed to refresh dashboard shots: " + (e?.message || e));
    }
}

function toggleDashboardSelect(shotId, itemEl) {
    if (!shotId) return;
    if (dashboardSelection.has(shotId)) dashboardSelection.delete(shotId);
    else dashboardSelection.add(shotId);
    if (itemEl) itemEl.classList.toggle("selected", dashboardSelection.has(shotId));
    updateDashboardSelectionUI();
}

function updateDashboardSelectionUI() {
    if ($dashboardSelectedCount) {
        $dashboardSelectedCount.value = dashboardSelection.size + " selected";
    }
}

async function reprocessSelectedFromDashboard() {
    await reprocessSelectedShots(Array.from(dashboardSelection), "dashboard");
}

async function reprocessSelectedFromVideo() {
    await reprocessSelectedShots(Array.from(videoSelection), "video");
}

async function reprocessSelectedShots(shotIds, source) {
    if (!shotIds || !shotIds.length) {
        alert("Select one or more images first");
        return;
    }

    addLogEntry("system", "Vision re-audit started for " + shotIds.length + " selected image(s)");
    if ($sparkStatusText) $sparkStatusText.textContent = "Vision re-auditing " + shotIds.length + " image(s)...";

    let ok = false;
    let usedEndpoint = "";
    let backendSupportsReprocess = false;
    try {
        // Preferred endpoint for selected-shot audit reprocess.
        const r1 = await fetch("/api/audit/reprocess", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shot_ids: shotIds }),
        });
        if (r1.ok) {
            const d1 = await r1.json();
            ok = d1 && (d1.status === "ok" || d1.status === "started");
            if (ok) {
                backendSupportsReprocess = true;
                usedEndpoint = "/api/audit/reprocess";
                addLogEntry("hermes", "Vision re-audit request accepted via /api/audit/reprocess");
                if (Array.isArray(d1.results)) {
                    const done = d1.results.filter(r => r && (r.status === "ok" || r.status === "complete")).length;
                    addLogEntry("memory", "Vision re-audit immediate results: " + done + "/" + d1.results.length + " updated");
                }
            }
        }

        // No legacy fallback: canonical endpoint only.
    } catch (e) {
        addLogEntry("error", "Vision re-audit failed: " + e.message);
        if ($sparkStatusText) $sparkStatusText.textContent = "Vision re-audit failed: " + e.message;
        return;
    }

    if (!ok || !backendSupportsReprocess) {
        addLogEntry("error", "Vision re-audit unavailable: canonical endpoint /api/audit/reprocess is required");
        if ($sparkStatusText) $sparkStatusText.textContent = "Vision re-audit unavailable (missing canonical endpoint)";
        return;
    }

    if (source === "dashboard") dashboardSelection.clear();
    if (source === "video") videoSelection.clear();
    updateDashboardSelectionUI();
    updateVideoSelectionUI();

    addLogEntry("spark", "Vision re-audit in progress for " + shotIds.length + " image(s) [" + usedEndpoint + "]");
    if ($sparkStatusText) $sparkStatusText.textContent = "Vision re-audit queued for " + shotIds.length + " image(s)";

    // Lightweight progress polling to surface status changes in the Hermes log panel.
    let polls = 0;
    const maxPolls = 8;
    const poll = async () => {
        polls += 1;
        try {
            const resp = await fetch("/api/shots");
            const data = await resp.json();
            const shots = data.shots || [];
            const selectedSet = new Set(shotIds);
            const subset = shots.filter(s => selectedSet.has(s.id));
            const withAudit = subset.filter(s => (s.audit_status === "pass" || s.audit_status === "fail")).length;
            addLogEntry("memory", "Vision re-audit status: " + withAudit + "/" + shotIds.length + " have audit labels");

            if (withAudit === shotIds.length || polls >= maxPolls) {
                const pass = subset.filter(s => s.audit_status === "pass").length;
                const fail = subset.filter(s => s.audit_status === "fail").length;
                addLogEntry("system", "Vision re-audit complete: " + pass + " pass, " + fail + " fail");
                await loadShots();
                await loadVideoLibrary();
                return;
            }
        } catch (_e) {
            // no-op
        }
        setTimeout(poll, 1500);
    };
    setTimeout(poll, 1000);
}

// ---------------------------------------------------------------------------
// Video Studio
// ---------------------------------------------------------------------------
async function loadVideoLibrary() {
    const gridEl = document.getElementById("spark-grid");
    const statusEl = document.getElementById("spark-status-text");
    if (!gridEl) {
        if (statusEl) statusEl.textContent = "Video grid container not found (spark-grid).";
        return;
    }
    try {
        const resp = await fetch("/api/shots");
        const data = await resp.json();
        const allShots = Array.isArray(data) ? data : (data.shots || []);
        let shots = _sortShots(allShots.filter(s => !!s.image_url).filter(shotMatchesFilters));
        const totalBeforeCap = shots.length;
        if (shots.length > MAX_VIDEO_THUMBS) shots = shots.slice(-MAX_VIDEO_THUMBS);
        videoShotsById = {};
        shots.forEach(s => { videoShotsById[s.id] = s; });
        if (!shots.length) {
            gridEl.innerHTML = '<div class="grid-placeholder"><p>No photos available yet.</p></div>';
            if (statusEl) statusEl.textContent = "Ready — no photos found in /api/shots";
            return;
        }
        gridEl.innerHTML = "";
        shots.forEach(s => {
            const selected = videoSelection.has(s.id);
            const cell = document.createElement("div");
            const isRetry = !!(s.retry_of || s.parent_shot_id || String(s.id).includes("__retry_"));
            const state = String(s.state || s.status || "").toLowerCase();
            const auditStatus = String(s.audit_status || "").toLowerCase() || (state.includes("fail") ? "fail" : (state.includes("pass") ? "pass" : ""));
            const cls = ["grid-cell", "rendered"];
            if (selected) cls.push("selected");
            if (auditStatus === "pass") cls.push("audit-pass");
            if (auditStatus === "fail") cls.push("audit-fail");
            if (isRetry) cls.push("retry-cell");
            cell.className = cls.join(" ");
            cell.dataset.shotId = s.id;

            const img = document.createElement("img");
            img.src = s.image_url;
            img.alt = s.id;
            img.loading = "lazy";
            img.decoding = "async";

            const label = document.createElement("div");
            label.className = "cell-label";
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = selected;
            checkbox.addEventListener("click", (event) => {
                event.stopPropagation();
                toggleVideoSelect(s.id);
            });
            label.appendChild(checkbox);
            const idText = document.createTextNode(" " + s.id);
            label.appendChild(idText);
            if (s.state) {
                const st = document.createElement("span");
                st.className = "audit-badge";
                st.textContent = String(s.state).toUpperCase();
                label.appendChild(st);
            }
            if (auditStatus === "pass" || auditStatus === "fail") {
                const b = document.createElement("span");
                b.className = "audit-badge " + auditStatus;
                b.textContent = auditStatus.toUpperCase();
                label.appendChild(b);
            }
            if (s.identity_type && s.identity_status) {
                const idb = document.createElement("span");
                idb.className = "audit-badge " + (s.identity_status === "pass" ? "pass" : "fail");
                idb.textContent = "ID " + String(s.identity_status).toUpperCase();
                label.appendChild(idb);
            }
            if (isRetry) {
                const b2 = document.createElement("span");
                b2.className = "audit-badge retry";
                b2.textContent = "RETRY";
                label.appendChild(b2);
            }
            const verdict = evaluateShotForVideo(s);
            const vBadge = document.createElement("span");
            vBadge.className = "audit-badge " + (verdict.eligible ? "pass" : "fail");
            vBadge.textContent = verdict.eligible ? "VIDEO_OK" : "BLOCKED";
            if (!verdict.eligible) vBadge.title = verdict.reasons.join(", ");
            label.appendChild(vBadge);
            if (s.video_prompt) {
                const vp = document.createElement("span");
                vp.className = "audit-badge vprompt";
                vp.textContent = videoPromptBadgeLabel(s);
                vp.title = videoPromptBadgeTitle(s);
                label.appendChild(vp);
            }

            if (s.video_prompt) {
                const dot = document.createElement("span");
                dot.className = "video-prompt-dot";
                dot.title = "Video prompt attached";
                cell.appendChild(dot);
            }

            cell.appendChild(img);
            cell.appendChild(label);
            cell.addEventListener("click", () => toggleVideoSelect(s.id));
            cell.addEventListener("dblclick", (event) => {
                event.preventDefault();
                openLightbox({
                    image_url: s.image_url,
                    status: s.status || "complete",
                    prompt: s.prompt || "",
                    negative_prompt: s.negative_prompt || "",
                    workflow: s.workflow || s.workflow_id || "-",
                    workflow_profile: s.workflow_profile || "",
                    model_standard_name: s.model_standard_name || "",
                    model_standard_version: s.model_standard_version || "",
                    identity_type: s.identity_type || "",
                    identity_name: s.identity_name || "",
                    identity_expected_traits: s.identity_expected_traits || [],
                    identity_detected_notes: s.identity_detected_notes || [],
                    seed: s.seed || "Random",
                    kimi_plan: s.kimi_plan || null,
                    kimi_rationale: s.kimi_rationale || "",
                    skills_used: s.skills_used || [],
                    prompt_id: s.prompt_id || "",
                    audit_status: s.audit_status || "",
                    audit_score: s.audit_score ?? "",
                    audit_issues: s.audit_issues || [],
                    retry_of: s.retry_of || s.parent_shot_id || "",
                    video_prompt: s.video_prompt || "",
                    video_prompt_source: s.video_prompt_source || "",
                    variant: "-",
                });
            });
            gridEl.appendChild(cell);
        });
        if (statusEl) {
            statusEl.textContent = "Ready — loaded " + shots.length + " photo(s)" +
                (totalBeforeCap > MAX_VIDEO_THUMBS ? (" (latest " + MAX_VIDEO_THUMBS + " of " + totalBeforeCap + ")") : "");
        }
        updateVideoSelectionUI();
    } catch (e) {
        if (statusEl) statusEl.textContent = "Failed to load photos: " + e.message;
    }
}

function toggleVideoSelect(shotId) {
    if (videoSelection.has(shotId)) videoSelection.delete(shotId);
    else videoSelection.add(shotId);
    updateVideoSelectionUI();
    const cell = document.querySelector('.grid-cell[data-shot-id="' + CSS.escape(shotId) + '"]');
    if (cell) cell.classList.toggle("selected", videoSelection.has(shotId));
}

function clearVideoSelection() {
    videoSelection.clear();
    updateVideoSelectionUI();
    document.querySelectorAll('#spark-grid .grid-cell.selected').forEach(el => el.classList.remove('selected'));
    document.querySelectorAll('#spark-grid .grid-cell input[type="checkbox"]').forEach(el => el.checked = false);
}

function evaluateShotForVideo(shot) {
    const reasons = [];
    if (!shot) return { eligible: false, reasons: ["shot_missing"] };
    if (!shot.image_path && !shot.image_url) reasons.push("image_missing");
    return { eligible: reasons.length === 0, reasons };
}

function updateVideoSelectionUI() {
    if ($videoSelectedCount) {
        let blockedCount = 0;
        videoSelection.forEach(id => {
            const s = videoShotsById[id];
            const verdict = evaluateShotForVideo(s);
            if (!verdict.eligible) blockedCount += 1;
        });
        $videoSelectedCount.value = videoSelection.size + " selected" +
            (blockedCount ? (" (" + blockedCount + " missing images)") : "");
    }
}

async function remediateFailedSelected() {
    const selected = Array.from(videoSelection);
    if (!selected.length) {
        alert("Select one or more failed images first");
        return;
    }
    const failedOnly = selected.filter(id => (videoShotsById[id] || {}).audit_status === "fail");
    if (!failedOnly.length) {
        alert("No failed images selected");
        return;
    }
    $sparkStatusText.textContent = "Remediating " + failedOnly.length + " failed shot(s)...";
    try {
        const resp = await fetch("/api/audit/remediate", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({ shot_ids: failedOnly }),
        });
        const data = await resp.json();
        if (data.status !== "ok") throw new Error(data.error || "Remediation failed");
        const ok = (data.results || []).filter(r => r.status === "ok").length;
        $sparkStatusText.textContent = "Remediation complete: " + ok + "/" + failedOnly.length + " retried";
        await loadVideoLibrary();
        videoSelection.clear();
        updateVideoSelectionUI();
    } catch (e) {
        $sparkStatusText.textContent = "Remediation error: " + e.message;
    }
}

async function sendVideoChat() {
    const input = document.getElementById("video-chat-input");
    const msg = (input?.value || "").trim();
    if (!msg) return;
    input.value = "";
    const $chatLog = document.getElementById("video-chat-log");
    const $chatStatus = document.getElementById("video-chat-status");

    function addEntry(agent, text) {
        const wrapper = document.createElement("div");
        wrapper.style.marginBottom = "10px";
        wrapper.style.display = "flex";
        wrapper.style.flexDirection = "column";
        wrapper.style.alignItems = agent === "You" ? "flex-end" : "flex-start";

        const label = document.createElement("div");
        label.style.fontSize = "10px";
        label.style.color = "#888";
        label.style.marginBottom = "2px";
        label.textContent = agent;
        wrapper.appendChild(label);

        const bubble = document.createElement("div");
        bubble.style.maxWidth = "90%";
        bubble.style.padding = "10px 14px";
        bubble.style.borderRadius = agent === "You" ? "14px 14px 4px 14px" : "14px 14px 14px 4px";
        bubble.style.fontSize = "12px";
        bubble.style.lineHeight = "1.5";
        bubble.style.wordBreak = "break-word";
        const colors = {
            "You": { bg: "#1e1e1e", border: "#333", text: "#ddd" },
            "Hermes": { bg: "#1a1a2e", border: "#2a2a4e", text: "#c8c8f0" },
            "Error": { bg: "#2b0d0d", border: "#4d1a1a", text: "#f0a8a8" },
        };
        const c = colors[agent] || { bg: "#151515", border: "#2a2a2a", text: "#ccc" };
        bubble.style.background = c.bg;
        bubble.style.border = "1px solid " + c.border;
        bubble.style.color = c.text;
        bubble.textContent = text;
        wrapper.appendChild(bubble);
        $chatLog.appendChild(wrapper);
        $chatLog.scrollTop = $chatLog.scrollHeight;
    }

    addEntry("You", msg);
    $chatStatus.textContent = "Hermes is thinking...";

    try {
        const resp = await fetch("/api/hermes/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg, history: [], session_id: "video_tab" }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullResponse = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    if (data.token) fullResponse += data.token;
                    if (data.done) {
                        addEntry("Hermes", fullResponse);
                        $chatStatus.textContent = "Ready";
                    }
                    if (data.error) addEntry("Error", data.error);
                } catch (e) {}
            }
        }
    } catch (e) {
        addEntry("Error", e.message);
        $chatStatus.textContent = "Error";
    }
}

async function generateVideoPrompts() {
    if (!videoSelection.size) {
        alert("Select at least one image");
        return;
    }
    const duration = parseInt(document.getElementById("video-duration")?.value || "4", 10);
    const fps = parseInt(document.getElementById("video-fps")?.value || "24", 10);
    const $chatLog = document.getElementById("video-chat-log");
    const $chatStatus = document.getElementById("video-chat-status");
    const $btn = document.getElementById("generate-prompts-btn");

    $btn.disabled = true;
    $btn.textContent = "Generating...";
    $chatStatus.textContent = "Agents running...";
    $chatLog.innerHTML = "";

    function addChatBubble(agent, text, isStatus) {
        const wrapper = document.createElement("div");
        wrapper.style.marginBottom = "10px";
        wrapper.style.display = "flex";
        wrapper.style.flexDirection = "column";
        wrapper.style.alignItems = agent === "You" ? "flex-end" : "flex-start";

        const label = document.createElement("div");
        label.style.fontSize = "10px";
        label.style.color = "#888";
        label.style.marginBottom = "2px";
        label.style.paddingLeft = agent === "You" ? "0" : "6px";
        label.style.paddingRight = agent === "You" ? "6px" : "0";
        label.textContent = agent;
        wrapper.appendChild(label);

        const bubble = document.createElement("div");
        bubble.style.maxWidth = "90%";
        bubble.style.padding = isStatus ? "6px 10px" : "10px 14px";
        bubble.style.borderRadius = agent === "You" ? "14px 14px 4px 14px" : "14px 14px 14px 4px";
        bubble.style.fontSize = "12px";
        bubble.style.lineHeight = "1.5";
        bubble.style.wordBreak = "break-word";

        const colors = {
            "Vision Analyst": { bg: "#0d2b25", border: "#1a4d3e", text: "#a8f0d8" },
            "Hermes / Duration Planner": { bg: "#2b250d", border: "#4d3e1a", text: "#f0e6a8" },
            "Hermes / LTX Prompt Engineer": { bg: "#1a0d2b", border: "#3e1a4d", text: "#d8a8f0" },
            "Hermes": { bg: "#1a1a2e", border: "#2a2a4e", text: "#c8c8f0" },
            "Error": { bg: "#2b0d0d", border: "#4d1a1a", text: "#f0a8a8" },
            "You": { bg: "#1e1e1e", border: "#333", text: "#ddd" },
        };
        const c = colors[agent] || { bg: "#151515", border: "#2a2a2a", text: "#ccc" };
        bubble.style.background = c.bg;
        bubble.style.border = "1px solid " + c.border;
        bubble.style.color = c.text;

        if (isStatus) {
            bubble.style.fontStyle = "italic";
            bubble.style.opacity = "0.7";
        }

        bubble.textContent = text;
        wrapper.appendChild(bubble);
        $chatLog.appendChild(wrapper);
        $chatLog.scrollTop = $chatLog.scrollHeight;
    }

    try {
        const resp = await fetch("/api/video/generate-prompts", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                shot_ids: Array.from(videoSelection),
                duration,
                fps,
            }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    if (data.error) {
                        addChatBubble("Error", data.error, false);
                    } else if (data.status === "thinking") {
                        $chatStatus.textContent = data.agent + " is analyzing...";
                        addChatBubble(data.agent, "💭 Thinking...", true);
                    } else if (data.result) {
                        addChatBubble(data.agent, data.result, false);
                    } else if (data.done) {
                        const saved = Number(data.saved || 0);
                        const selected = Number(data.selected || 0);
                        $chatStatus.textContent = "✅ Done — " + saved + " prompts saved" + (selected ? (" / " + selected + " selected") : "");
                        if (Array.isArray(data.unmapped_prompt_keys) && data.unmapped_prompt_keys.length) {
                            addChatBubble("Error", "Unmapped prompt keys: " + data.unmapped_prompt_keys.join(", "), false);
                        }
                        addChatBubble("Hermes / LTX Prompt Engineer", "All prompts generated and saved.", true);
                        if (data.prompts) {
                            Object.entries(data.prompts).forEach(([sid, prompt]) => {
                                if (videoShotsById[sid]) {
                                    videoShotsById[sid].video_prompt = prompt;
                                    videoShotsById[sid].video_prompt_source = data.video_prompt_source || "vision_prompt_agent";
                                }
                            });
                            loadVideoLibrary();
                        }
                    }
                } catch (e) {
                    // skip malformed lines
                }
            }
        }
    } catch (e) {
        $chatStatus.textContent = "Error: " + e.message;
        addChatEntry("Error", e.message);
    } finally {
        $btn.disabled = false;
        $btn.textContent = "Generate Prompts";
    }
}

async function processSelectedVideos() {
    if (!videoSelection.size) {
        alert("Select at least one image");
        return;
    }
    const duration = parseInt($videoDuration?.value || "4", 10);
    const fps = parseInt($videoFps?.value || "24", 10);
    const workflowId = getSelectedVideoWorkflow();
    const videoPrompt = ($videoPrompt?.value || "").trim();
    $startBatchBtn.disabled = true;
    $startBatchBtn.textContent = "Processing...";
    $sparkStatusText.textContent = "Processing " + videoSelection.size + " image(s) into videos via " + workflowId + "...";
    try {
        const resp = await fetch("/api/video/process", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
                shot_ids: Array.from(videoSelection),
                duration,
                fps,
                workflow_id: workflowId,
                prompt: videoPrompt,
                min_audit_score: 0,
                min_audit_confidence: 0,
                require_audit_pass: false,
                allow_failed_override: true,
            }),
        });
        const data = await resp.json();
        if (data.status !== "ok") throw new Error(data.error || "Video processing failed");
        const done = (data.results || []).filter(r => r.status === "ok").length;
        const blocked = (data.results || []).filter(r => r.status === "blocked").length;
        const errs = (data.results || []).filter(r => r.status === "error").length;
        $sparkStatusText.textContent = "Video processing complete (" + workflowId + "): " + done + " queued, " + blocked + " blocked, " + errs + " errors";
        $sparkProgress.textContent = (data.output_dir || "");
    } catch (e) {
        $sparkStatusText.textContent = "Error: " + e.message;
    } finally {
        $startBatchBtn.disabled = false;
        $startBatchBtn.textContent = "Process";
    }
}

function clearComfyUIQueue() {
    // no-op in video mode
}
function handleSparkMessage(_data) {}

async function startBatchRender() {
    return processSelectedVideos();
}

function createGridCell(variant, total, status, result) {
    const cell = document.createElement("div");
    cell.className = "grid-cell " + status;
    cell.id = "cell-v" + variant;

    if (status === "rendered" && result && result.image_url) {
        cell.innerHTML =
            '<img src="' + result.image_url + '" alt="Variant ' + variant + '">' +
            '<div class="cell-label">v' + variant + ' | seed: ' + (result.seed || "rand") + "</div>";
        cell.onclick = () => openLightbox(result);
    } else if (status === "error") {
        cell.innerHTML =
            '<div class="cell-overlay">' +
            '<div style="font-size:24px;">&#9888;</div>' +
            '<div>ERROR</div>' +
            (result && result.error ? '<div style="font-size:10px;max-width:160px;text-align:center;">' + escapeHtml(result.error).substring(0, 60) + '</div>' : "") +
            "</div>" +
            '<div class="cell-label">v' + variant + " | ERROR</div>";
        cell.onclick = () => openLightbox(result);
    } else if (status === "rendering") {
        cell.innerHTML =
            '<div class="cell-overlay">' +
            '<div style="font-size:24px;">&#9203;</div>' +
            '<div>Rendering...</div>' +
            "</div>" +
            '<div class="cell-label">v' + variant + " | rendering</div>";
    } else {
        cell.innerHTML =
            '<div class="cell-overlay">' +
            '<div style="font-size:24px;">&#9208;</div>' +
            '<div>QUEUED</div>' +
            "</div>" +
            '<div class="cell-label">v' + variant + " | queued</div>";
    }

    $sparkGrid.appendChild(cell);
}

function updateRenderCell(data) {
    const variantId = data.variant_id;
    const status = data.status;
    const variant = data.variant;
    const total = data.total;

    // Store result
    sparkRenderResults[variantId] = {
        id: variantId,
        variant: variant,
        status: status,
        image_url: data.image_url || null,
        seed: data.seed || null,
        prompt: data.prompt || "",
        workflow: data.workflow || "",
        error: data.error || null,
    };

    // Update or create cell
    const existingCell = document.getElementById("cell-v" + variant);
    if (existingCell) {
        existingCell.remove();
    }

    createGridCell(variant, total, status, sparkRenderResults[variantId]);

    // Update progress
    const completed = Object.values(sparkRenderResults).filter(r => r.status === "rendered" || r.status === "error").length;
    $sparkProgress.textContent = completed + "/" + total;

    if (completed >= total) {
        $sparkStatusText.textContent = "Batch complete";
        $startBatchBtn.disabled = false;
        $startBatchBtn.textContent = "Start Batch";
    }
}

function onBatchComplete(data) {
    $sparkStatusText.textContent = "Batch complete: " + data.total + " variants";
    $startBatchBtn.disabled = false;
    $startBatchBtn.textContent = "Start Batch";
    $sparkProgress.textContent = data.total + "/" + data.total;
}

function clearRenderGrid() {
    sparkRenderResults = {};
    sparkCampaignId = null;
    $sparkGrid.innerHTML =
        '<div class="grid-placeholder">' +
        '<p>Configure your settings and click <strong>Start Batch</strong> to begin rendering.</p>' +
        "</div>";
    $sparkStatusText.textContent = "Ready";
    $sparkProgress.textContent = "";
}

async function clearComfyUIQueue() {
    try {
        const resp = await fetch("/api/comfyui/clear", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await resp.json();

        if (data.status === "ok") {
            $sparkStatusText.textContent = "Queue cleared";
            setTimeout(() => {
                $sparkStatusText.textContent = "Ready";
            }, 2000);
        } else {
            $sparkStatusText.textContent = "Error: " + (data.error || "Failed");
        }
    } catch (e) {
        $sparkStatusText.textContent = "Error: " + e.message;
    }
}

function videoPromptBadgeLabel(shot) {
    const source = String(shot?.video_prompt_source || "").trim();
    if (source === "auto_default") return "V_DEFAULT";
    if (source === "prompt_agent") return "V_AGENT";
    if (source === "vision_prompt_agent") return "V_VISION";
    if (source === "auto_compiler") return "V_COMPILER";
    return "V_PROMPT";
}

function videoPromptBadgeTitle(shot) {
    const prompt = String(shot?.video_prompt || "");
    const source = String(shot?.video_prompt_source || "").trim() || "unknown";
    const preview = prompt.substring(0, 180) + (prompt.length > 180 ? "..." : "");
    return `Source: ${source}\n${preview}`;
}

// Lightbox
function openLightbox(result) {
    if (!result) return;

    document.getElementById("lightbox-image").src = result.image_url || "";
    document.getElementById("lightbox-variant").textContent = "v" + (result.variant || "-");
    document.getElementById("lightbox-seed").textContent = result.seed || "Random";
    document.getElementById("lightbox-workflow").textContent = result.workflow || "-";
    document.getElementById("lightbox-status").textContent = result.status || "-";
    document.getElementById("lightbox-prompt").textContent = result.prompt || "-";
    const videoPromptEl = document.getElementById("lightbox-video-prompt");
    if (videoPromptEl) videoPromptEl.textContent = result.video_prompt || "-";
    const videoPromptSourceEl = document.getElementById("lightbox-video-prompt-source");
    if (videoPromptSourceEl) videoPromptSourceEl.textContent = result.video_prompt_source || "-";
    document.getElementById("lightbox-negative-prompt").textContent = result.negative_prompt || "-";
    document.getElementById("lightbox-kimi-plan").textContent = result.kimi_plan ? JSON.stringify(result.kimi_plan) : "-";
    document.getElementById("lightbox-kimi-rationale").textContent = result.kimi_rationale || "-";
    document.getElementById("lightbox-skills-used").textContent = Array.isArray(result.skills_used) ? result.skills_used.join(", ") : "-";
    document.getElementById("lightbox-workflow-profile").textContent = result.workflow_profile || "-";
    const standardLabel = result.model_standard_name
        ? (result.model_standard_name + (result.model_standard_version ? " @" + result.model_standard_version : ""))
        : "-";
    document.getElementById("lightbox-model-standard").textContent = standardLabel;
    const identityLabel = result.identity_type
        ? ((String(result.identity_type).toUpperCase()) + (result.identity_name ? (": " + result.identity_name) : ""))
        : "-";
    const identityEl = document.getElementById("lightbox-identity");
    if (identityEl) identityEl.textContent = identityLabel;
    const expEl = document.getElementById("lightbox-identity-expected");
    if (expEl) expEl.textContent = Array.isArray(result.identity_expected_traits) && result.identity_expected_traits.length
        ? result.identity_expected_traits.join(", ")
        : "-";
    const detEl = document.getElementById("lightbox-identity-detected");
    if (detEl) detEl.textContent = Array.isArray(result.identity_detected_notes) && result.identity_detected_notes.length
        ? result.identity_detected_notes.join("; ")
        : "-";
    document.getElementById("lightbox-prompt-id").textContent = result.prompt_id || "-";
    const audit = result.audit_status
        ? (String(result.audit_status).toUpperCase() + (result.audit_score !== undefined && result.audit_score !== "" ? " (" + result.audit_score + ")" : ""))
        : "-";
    document.getElementById("lightbox-audit").textContent = audit;
    document.getElementById("lightbox-retry-of").textContent = result.retry_of || "-";

    $lightboxModal.classList.add("active");
}

function closeLightbox(event) {
    if (event && event.target !== $lightboxModal && event.target.className !== "lightbox-close") {
        return;
    }
    $lightboxModal.classList.remove("active");
}

// ---------------------------------------------------------------------------
// Memory Tab
// ---------------------------------------------------------------------------
const MEM_TYPE_COLOR = {
  session: '#f0c040', attempt: '#00BCD4', outcome: '#4CAF50',
  insight: '#7C4DFF', concept: '#e91e8c',
};
const TL_TYPE_COLOR = {
  shot_planned: '#90A4AE',
  render_attempt: '#00BCD4',
  render_result: '#4CAF50',
  audit_started: '#FFB74D',
  audit_result: '#FF9800',
  remediation_started: '#7C4DFF',
  remediation_result: '#7C4DFF',
  retry_linked: '#CE93D8',
  final_outcome: '#4CAF50',
  import_completed: '#607D8B',
};

async function loadMemoryTab() {
  const cyEl = document.getElementById('cy-canvas');
  if (cyEl) cyEl.innerHTML = "";
  try {
    const s = await fetch('/api/memory/stats').then(r => r.json());
    document.getElementById('mg-events').textContent = s.events ?? '—';
    document.getElementById('mg-insights').textContent = s.insights ?? '—';
    document.getElementById('mg-sessions').textContent = s.sessions ?? '—';
    document.getElementById('mg-rules').textContent = s.rules ?? '—';
  } catch(e) {
    addLogEntry("error", "Memory stats failed: " + (e?.message || e));
  }

  try {
    await ensureCytoscapeLoaded();
    const g = await fetch('/api/memory/graph').then(r => r.json());
    memoryGraphRaw = {
      nodes: Array.isArray(g.nodes) ? g.nodes : [],
      edges: Array.isArray(g.edges) ? g.edges : [],
    };
    populateMemoryCampaignFilter(memoryGraphRaw.nodes);
    bindMemoryControls();
    const filtered = buildMemoryFilteredGraph();
    const nodes = filtered.nodes;
    const edges = filtered.edges;
    if (!nodes.length && cyEl) {
      cyEl.innerHTML = '<div style="padding:14px;color:#888;font-size:12px;">No memory graph data yet.</div>';
    } else {
      initMemoryGraph(nodes, edges);
    }
  } catch(e) {
    if (cyEl) {
      cyEl.innerHTML = '<div style="padding:14px;color:#ff8a80;font-size:12px;">Memory graph failed to load.</div>';
    }
    addLogEntry("error", "Memory graph failed: " + (e?.message || e));
  }

  try {
    const rules = await fetch('/api/memory/insights').then(r => r.json());
    const el = document.getElementById('rulebook-list');
    if (!el) return;
    if (!rules.length) {
      el.innerHTML = '<span style="color:#888;font-size:12px;">No rules learned yet.</span>';
    } else {
      el.innerHTML = rules.map(r => `
        <div class="rule-entry">
          <div class="rule-text">${r.text || r.rule || '-'}</div>
          <div class="conf-bar"><div class="conf-fill" style="width:${Math.round((r.confidence||0.5)*100)}%"></div></div>
          <div class="rule-meta">${r.confirmations || 0}× confirmed · ${r.source || 'semantic'}</div>
        </div>`).join('');
    }
  } catch(e) {
    addLogEntry("error", "Memory insights failed: " + (e?.message || e));
  }

  try {
    const tl = await fetch('/api/memory/timeline').then(r => r.json());
    const el = document.getElementById('tl-list');
    if (!el) return;
    el.innerHTML = tl.map(e => {
      const col = TL_TYPE_COLOR[e.type] || '#888';
      const ts = e.ts ? new Date(e.ts).toLocaleTimeString() : '';
      return `<div class="tl-event">
        <div class="tl-dot" style="background:${col}"></div>
        <div>
          <div class="tl-body">${e.shot || e.type}</div>
          <div class="tl-time">${e.type} · ${ts}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    addLogEntry("error", "Memory timeline failed: " + (e?.message || e));
  }
}

async function ensureCytoscapeLoaded() {
  if (window.cytoscape) return;
  const sources = [
    "https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js",
    "https://cdn.jsdelivr.net/npm/cytoscape@3.26.0/dist/cytoscape.min.js",
  ];
  for (const src of sources) {
    await new Promise((resolve) => {
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = () => resolve(true);
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    });
    if (window.cytoscape) return;
  }
  throw new Error("cytoscape_script_unavailable");
}

function mapMemoryActorFromEventType(eventType) {
  const t = String(eventType || "").toLowerCase();
  if (t === "shot_planned") return "kimi";
  if (t.startsWith("render_")) return "spark";
  if (t.startsWith("audit_")) return "audit";
  if (t.startsWith("remediation_") || t === "retry_linked" || t === "final_outcome") return "hermes";
  if (t === "import_completed") return "memory";
  return "memory";
}

function populateMemoryCampaignFilter(nodes) {
  const el = document.getElementById("mem-filter-campaign");
  if (!el) return;
  const set = new Set(["all"]);
  for (const n of (nodes || [])) {
    const cid = String(n?.data?.campaign_id || "").trim();
    if (cid) set.add(cid);
  }
  const list = [...set];
  el.innerHTML = list.map((c) => `<option value="${c}">${c === "all" ? "All Campaigns" : c}</option>`).join("");
  if (shotFilters.campaignId && set.has(shotFilters.campaignId)) {
    el.value = shotFilters.campaignId;
  }
}

function bindMemoryControls() {
  const bindings = [
    "mem-filter-campaign",
    "mem-filter-fail",
    "mem-filter-retry",
    "mem-filter-audit",
    "mem-filter-current",
    "mem-filter-contribution",
    "mem-view-heat",
    "mem-view-lanes",
  ];
  bindings.forEach((id) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.bound === "1") return;
    el.dataset.bound = "1";
    el.addEventListener("change", memoryApplyFilters);
  });

  const slider = document.getElementById("mem-playback-range");
  if (slider && slider.dataset.bound !== "1") {
    slider.dataset.bound = "1";
    slider.addEventListener("input", () => {
      const r = document.getElementById("mem-playback-readout");
      if (r) r.value = `${slider.value}%`;
      memoryApplyFilters();
    });
  }
}

function buildMemoryFilteredGraph() {
  const campaignSel = document.getElementById("mem-filter-campaign")?.value || "all";
  const failOnly = !!document.getElementById("mem-filter-fail")?.checked;
  const retryOnly = !!document.getElementById("mem-filter-retry")?.checked;
  const auditOnly = !!document.getElementById("mem-filter-audit")?.checked;
  const currentOnly = !!document.getElementById("mem-filter-current")?.checked;
  const contribution = document.getElementById("mem-filter-contribution")?.value || "all";
  const playbackPct = Math.max(0, Math.min(100, Number(document.getElementById("mem-playback-range")?.value || 100)));

  const nodes = [...(memoryGraphRaw.nodes || [])];
  const edges = [...(memoryGraphRaw.edges || [])];
  const maxTs = Math.max(
    ...nodes.map((n) => {
      const t = Date.parse(String(n?.data?.timestamp || ""));
      return Number.isFinite(t) ? t : 0;
    }),
    0
  );
  const minTs = Math.min(
    ...nodes.map((n) => {
      const t = Date.parse(String(n?.data?.timestamp || ""));
      return Number.isFinite(t) ? t : maxTs;
    }),
    maxTs
  );
  const cutoff = minTs + ((maxTs - minTs) * (playbackPct / 100));
  const activeCampaign = (shotFilters.campaignId || currentCampaignId || "").trim();

  const keepNode = (n) => {
    const d = n?.data || {};
    const eventType = String(d.event_type || "");
    const actor = mapMemoryActorFromEventType(eventType);
    const ts = Date.parse(String(d.timestamp || ""));
    if (Number.isFinite(ts) && ts > cutoff) return false;
    const cid = String(d.campaign_id || "").trim();
    if (campaignSel !== "all" && cid !== campaignSel) return false;
    if (currentOnly && activeCampaign && cid !== activeCampaign) return false;
    if (contribution !== "all" && actor !== contribution) return false;
    if (failOnly) {
      const success = d.success;
      const fail = success === false || String(d.audit_status || "").toLowerCase() === "fail" || String(eventType).includes("fail");
      if (!fail) return false;
    }
    if (retryOnly) {
      const isRetry = String(d.retry_of || "").trim() || String(eventType) === "retry_linked" || String(d.shot_id || "").includes("__retry_");
      if (!isRetry) return false;
    }
    if (auditOnly && !String(eventType).startsWith("audit_")) return false;
    return true;
  };

  const keptNodes = nodes.filter(keepNode);
  const keptIds = new Set(keptNodes.map((n) => n.id));
  const keptEdges = edges.filter((e) => keptIds.has(e.source) && keptIds.has(e.target));
  return { nodes: keptNodes, edges: keptEdges };
}

function initMemoryGraph(nodes, edges) {
  const el = document.getElementById('cy-canvas');
  if (!el || !window.cytoscape) return;
  if (window._memoryCy) { window._memoryCy.destroy(); }
  const overlayNodes = Array.isArray(memoryNexusOverlay.nodes) ? memoryNexusOverlay.nodes : [];
  const overlayEdges = Array.isArray(memoryNexusOverlay.edges) ? memoryNexusOverlay.edges : [];
  const mergedNodes = [...(nodes || []), ...overlayNodes];
  const mergedEdges = [...(edges || []), ...overlayEdges];
  const MAX_NODES = 220;
  const useNodes = mergedNodes.slice(-MAX_NODES);
  const allowedNodeIds = new Set(useNodes.map((n) => n.id));
  const useEdges = mergedEdges.filter((e) => allowedNodeIds.has(e.source) && allowedNodeIds.has(e.target));
  const cyNodes = (useNodes || []).map((n) => {
    const cls = [];
    if (n.layer === "nexus") cls.push("nexus-node");
    if (n.type === "query") cls.push("nexus-root");
    return {
      data: {
        id: n.id,
        label: n.label || n.id,
        type: n.type || "event",
        size: n.size || 20,
        ...(n.data || {}),
      },
      classes: cls.join(" "),
    };
  });
  const cyEdges = (useEdges || []).map((e) => ({
    data: {
      id: e.id || (e.source + "->" + e.target),
      source: e.source,
      target: e.target,
      type: e.type || "link",
      label: e.label || "",
      weight: Number(e.weight || 1),
    },
    classes: e.layer === "nexus" ? "nexus-edge" : "",
  }));
  window._memoryCy = cytoscape({
    container: el,
    elements: [...cyNodes, ...cyEdges],
    style: [
      {
        selector: 'node',
        style: {
          'background-color': (n) => MEM_TYPE_COLOR[n.data('type')] || '#555',
          'label': 'data(label)',
          'color': '#e0e0e0',
          'font-size': '9px',
          'text-valign': 'bottom',
          'text-halign': 'center',
          'width': (n) => {
            const base = Number(n.data('size') || (n.data('type') === 'session' ? 28 : 18));
            const conf = Number(n.data('confidence') || 0.5);
            const imp = Number(n.data('importance') || 1);
            return Math.max(14, Math.min(56, base + (conf * 8) + (imp * 3)));
          },
          'height': (n) => {
            const base = Number(n.data('size') || (n.data('type') === 'session' ? 28 : 18));
            const conf = Number(n.data('confidence') || 0.5);
            const imp = Number(n.data('importance') || 1);
            return Math.max(14, Math.min(56, base + (conf * 8) + (imp * 3)));
          },
          'shape': (n) => ({ session: 'diamond', insight: 'star', concept: 'rectangle' }[n.data('type')] || 'ellipse'),
          'border-width': (n) => {
            const et = String(n.data('event_type') || "");
            if (et === "retry_linked" || String(n.data('retry_of') || "")) return 3;
            if (n.data('success') === false) return 3;
            if (n.data('success') === true) return 2;
            return 1;
          },
          'border-color': (n) => {
            const et = String(n.data('event_type') || "");
            if (et === "retry_linked" || String(n.data('retry_of') || "")) return '#ab47bc';
            if (n.data('success') === false) return '#d32f2f';
            if (n.data('success') === true) return '#2e7d32';
            return '#323232';
          },
        }
      },
      {
        selector: '.nexus-node',
        style: {
          'background-color': '#00bcd4',
          'border-color': '#80deea',
          'border-width': 2,
          'shape': 'round-rectangle',
          'font-size': '10px',
          'color': '#dffbff',
        }
      },
      {
        selector: '.nexus-root',
        style: {
          'background-color': '#7C4DFF',
          'border-color': '#d1c4e9',
          'shape': 'hexagon',
          'color': '#f3ecff',
        }
      },
      {
        selector: 'edge',
        style: {
          'line-color': '#2a2a2a',
          'width': (e) => Math.min(7, 1 + Number(e.data('weight') || 1)),
          'target-arrow-color': '#333', 'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
        }
      },
      {
        selector: '.nexus-edge',
        style: {
          'line-color': '#26c6da',
          'target-arrow-color': '#26c6da',
          'line-style': 'dashed',
          'opacity': 0.85,
        }
      },
      { selector: ':selected', style: { 'border-width': 2, 'border-color': '#fff' } },
      { selector: '.memory-dim', style: { 'opacity': 0.12 } },
    ],
    layout: { name: 'cose', padding: 20, animate: false },
    userPanningEnabled: true,
    userZoomingEnabled: true,
  });
  const lanesEnabled = !!document.getElementById("mem-view-lanes")?.checked;
  if (lanesEnabled) applyMemoryLaneLayout();
  attachMemorySelectionHandlers();
  updateMemoryHeatOverlay();
}

function memoryCyLayout(name) {
  if (!window._memoryCy) return;
  window._memoryCy.layout({ name, padding: 20, animate: true, animationDuration: 400 }).run();
}

function flashEdges(edges) {
  if (!edges || !edges.length) return;
  edges.forEach((edge, i) => {
    setTimeout(() => {
      edge
        .animate({ style: { 'line-color': '#ffffff', 'width': 4, 'target-arrow-color': '#ffffff' }, duration: 200 })
        .animate({ style: { 'line-color': '#BD00FF', 'width': 1.5, 'target-arrow-color': '#BD00FF' }, duration: 400 })
        .animate({ style: { 'line-color': '#2a2a2a', 'width': Math.min(7, 1 + Number(edge.data('weight') || 1)), 'target-arrow-color': '#333' }, duration: 220 });
    }, i * 100);
  });
}

function flashTargetNodes(edges) {
  if (!edges || !edges.length) return;
  const seen = new Set();
  edges.forEach((edge, i) => {
    const target = edge.target();
    if (!target || seen.has(target.id())) return;
    seen.add(target.id());
    const baseBorder = target.style("border-color") || "#323232";
    const baseWidth = Number(target.style("border-width") || 1);
    setTimeout(() => {
      target
        .animate({ style: { 'border-color': '#ffffff', 'border-width': 4 }, duration: 180 })
        .animate({ style: { 'border-color': '#00E5FF', 'border-width': 3 }, duration: 260 })
        .animate({ style: { 'border-color': baseBorder, 'border-width': baseWidth }, duration: 240 });
    }, 120 + (i * 100));
  });
}

function flashLatestInsight() {
  if (!window._memoryCy) return;
  const insightNodes = window._memoryCy.nodes().filter((n) => String(n.data("event_type") || "") === "insight");
  if (!insightNodes.length) return;
  const newest = insightNodes.max((n) => Number(n.data("confirmations") || 0));
  if (!newest) return;
  const learnedEdges = newest.connectedEdges().filter((e) => String(e.data("type") || "") === "learned_from");
  if (!learnedEdges.length) return;
  newest.animate({ style: { 'background-color': '#ffffff', 'border-color': '#ffffff' }, duration: 180 })
        .animate({ style: { 'background-color': '#7C4DFF', 'border-color': '#d1c4e9' }, duration: 350 });
  flashEdges(learnedEdges);
  flashTargetNodes(learnedEdges);
}

function applyMemoryLaneLayout() {
  if (!window._memoryCy) return;
  const phaseX = { kimi: 80, hermes: 320, spark: 560, audit: 800, memory: 1040 };
  const nodes = window._memoryCy.nodes();
  const sorted = [...nodes].sort((a, b) => {
    const ta = Date.parse(String(a.data("timestamp") || "")) || 0;
    const tb = Date.parse(String(b.data("timestamp") || "")) || 0;
    return ta - tb;
  });
  const spacing = 38;
  sorted.forEach((n, i) => {
    const actor = mapMemoryActorFromEventType(n.data("event_type"));
    const x = phaseX[actor] || 1120;
    n.position({ x, y: 30 + (i * spacing) });
  });
  window._memoryCy.fit(window._memoryCy.elements(), 30);
}

function attachMemorySelectionHandlers() {
  if (!window._memoryCy) return;
  const target = document.getElementById("mem-selection-insights");
  if (!target) return;
  window._memoryCy.off("tap");
  window._memoryCy.off("tap", "node");
  window._memoryCy.on("tap", "node", (evt) => {
    const n = evt.target;
    const neighborhood = n.neighborhood().add(n);
    window._memoryCy.elements().not(neighborhood).animate({ style: { opacity: 0.1 }, duration: 300 });
    neighborhood.animate({ style: { opacity: 1 }, duration: 300 });
  });
  window._memoryCy.on("tap", (evt) => {
    if (evt.target !== window._memoryCy) return;
    window._memoryCy.elements().removeClass("memory-dim");
    window._memoryCy.elements().animate({ style: { opacity: 1 }, duration: 300 });
    if (target) target.innerHTML = '<span style="color:var(--text-secondary);font-size:12px;">Select a node to inspect lineage.</span>';
  });

  window._memoryCy.off("select");
  window._memoryCy.on("select", "node", (evt) => {
    const n = evt.target;
    const d = n.data() || {};
    const out = [];
    out.push(`<div class="selection-line"><b>${d.label || d.id}</b></div>`);
    out.push(`<div class="selection-line">Type: <small>${d.event_type || d.type || "unknown"}</small></div>`);
    out.push(`<div class="selection-line">Actor: <small>${mapMemoryActorFromEventType(d.event_type)}</small></div>`);
    out.push(`<div class="selection-line">Campaign: <small>${d.campaign_id || "n/a"}</small></div>`);
    out.push(`<div class="selection-line">Workflow: <small>${d.workflow_id || "n/a"}</small></div>`);
    out.push(`<div class="selection-line">Shot: <small>${d.shot_id || "n/a"}</small></div>`);
    out.push(`<div class="selection-line">Result: <small>${d.success === true ? "pass" : d.success === false ? "fail" : "unknown"}</small></div>`);
    out.push(`<div class="selection-line">Risk: <small>${d.error_category || "none"}</small></div>`);
    out.push(`<div class="selection-line">Source: <small>${d.source || "n/a"}</small></div>`);
    if (d.retry_of) out.push(`<div class="selection-line">Retry of: <small>${d.retry_of}</small></div>`);
    target.innerHTML = out.join("");
    highlightRetryLineage(d.shot_id);
  });
}

function highlightRetryLineage(shotId) {
  if (!window._memoryCy || !shotId) return;
  window._memoryCy.elements().removeClass("memory-dim");
  const nodes = window._memoryCy.nodes().filter((n) => {
    const sid = String(n.data("shot_id") || "");
    const ro = String(n.data("retry_of") || "");
    return sid === shotId || ro === shotId || sid.includes(shotId) || shotId.includes(sid);
  });
  if (!nodes.length) return;
  const neighborhood = nodes.union(nodes.connectedEdges()).union(nodes.connectedEdges().connectedNodes());
  window._memoryCy.elements().difference(neighborhood).addClass("memory-dim");
  window._memoryCy.fit(neighborhood, 40);
}

function updateMemoryHeatOverlay() {
  const heat = document.getElementById("memory-heat-overlay");
  if (!heat) return;
  const on = !!document.getElementById("mem-view-heat")?.checked;
  heat.style.display = on ? "block" : "none";
}

function memoryApplyFilters() {
  if (!memoryGraphRaw.nodes.length) return;
  document.querySelectorAll(".memory-chip input").forEach((inp) => {
    const p = inp.parentElement;
    if (!p) return;
    p.classList.toggle("active", !!inp.checked);
  });
  const r = document.getElementById("mem-playback-readout");
  const slider = document.getElementById("mem-playback-range");
  if (r && slider) r.value = `${slider.value}%`;
  const filtered = buildMemoryFilteredGraph();
  initMemoryGraph(filtered.nodes, filtered.edges);
  updateMemoryHeatOverlay();
}

async function runNexusQuery() {
  const input = document.getElementById("nexus-query-input");
  const status = document.getElementById("nexus-query-status");
  if (!input || !status) return;
  const query = String(input.value || "").trim();
  if (!query) {
    status.textContent = "Enter a question first.";
    return;
  }
  status.textContent = "Querying Forge Nexus…";
  try {
    const resp = await fetch("/api/nexus/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_n: 8, include_impact: true }),
    });
    const data = await resp.json();
    if (!resp.ok || data.status !== "ok") {
      const err = data.detail || data.error || resp.statusText || "query_failed";
      status.textContent = "Nexus query failed: " + err;
      return;
    }
    const ov = data.overlay || { nodes: [], edges: [] };
    memoryNexusOverlay = {
      nodes: (ov.nodes || []).map((n) => ({
        id: "nexus::" + String(n.id || ""),
        label: String(n.label || n.id || ""),
        type: String(n.type || "asset"),
        size: 22,
        layer: "nexus",
        data: {
          event_type: "nexus_" + String(n.type || "asset"),
          campaign_id: "",
          workflow_id: "",
          shot_id: "",
          success: null,
          source: "nexus",
          confidence: Number(n.score || 0.5),
          importance: n.type === "query" ? 3 : 2,
        },
      })),
      edges: (ov.edges || []).map((e) => ({
        id: "nexus::" + String(e.id || `${e.source}->${e.target}`),
        source: "nexus::" + String(e.source || ""),
        target: "nexus::" + String(e.target || ""),
        type: String(e.type || "link"),
        weight: Number(e.weight || 1),
        layer: "nexus",
      })),
    };
    memoryApplyFilters();
    const first = (data.results || [])[0];
    const top = first ? String(first.id || "") : "none";
    status.textContent = `Nexus: ${data.count || 0} hits. Top asset: ${top}`;
  } catch (e) {
    status.textContent = "Nexus query error: " + (e?.message || e);
  }
}

function toggleMemoryPlayback() {
  const btn = event.currentTarget;
  const slider = document.getElementById("mem-playback-range");
  if (!slider) return;
  if (memoryPlaybackRunning) {
    memoryPlaybackRunning = false;
    if (memoryPlaybackTimer) clearInterval(memoryPlaybackTimer);
    memoryPlaybackTimer = null;
    if (btn) btn.textContent = "Play";
    return;
  }
  memoryPlaybackRunning = true;
  if (btn) btn.textContent = "Stop";
  if (Number(slider.value) >= 100) slider.value = "0";
  memoryApplyFilters();
  memoryPlaybackTimer = setInterval(() => {
    const next = Math.min(100, Number(slider.value) + 2);
    slider.value = String(next);
    memoryApplyFilters();
    if (next >= 100) {
      memoryPlaybackRunning = false;
      if (memoryPlaybackTimer) clearInterval(memoryPlaybackTimer);
      memoryPlaybackTimer = null;
      if (btn) btn.textContent = "Play";
    }
  }, 250);
}

async function triggerConsolidate() {
  const btn = event.currentTarget;
  btn.textContent = '⏳ Consolidating…';
  btn.disabled = true;
  try { await fetch('/api/memory/consolidate', { method: 'POST' }); } catch(e) {}
  btn.textContent = '✓ Done';
  setTimeout(() => { btn.textContent = '⚡ Consolidate Memory'; btn.disabled = false; }, 2000);
  await loadMemoryTab();
  setTimeout(() => flashLatestInsight(), 250);
}

// Close lightbox on Escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $lightboxModal.classList.contains("active")) {
        closeLightbox();
    }
});
