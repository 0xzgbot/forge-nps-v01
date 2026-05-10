/*
 * Forge NPS — Hermes Command Center
 * app.js | NDJSON streaming, campaign runner, chat, settings
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let chatHistory = [];
let sessionId = "session_" + Date.now();
let scriptChatHistory = [];
let scriptSessionId = "script_" + Date.now();
let scriptPackage = null;
let storyboardPlan = null;
let storyboardPanelJobs = {};
let storyboardCharacterSheetJob = null;
let campaignActive = false;
let campaignAbortController = null;
let campaignRecoveryTimer = null;
let campaignMediaRefreshTimer = null;
let configDirty = {}; // dot_key -> new_value
let currentConfig = {};
let currentPlatformSkill = { active: false, id: "", label: "No platform skill", constraints: {} };
let platformDetectTimer = null;
let targetCountManualOverride = false;

// Spark state
let sparkRenderResults = {};
let sparkWebSocket = null;
let sparkCampaignId = null;
let videoSelection = new Set();
let videoShotsById = {};
let pendingVideoJobs = [];
let videoJobPollTimer = null;
const VIDEO_JOBS_KEY = "forge_pending_video_jobs";
let dashboardSelection = new Set();
let currentCampaignId = "";
let identityAssets = [];
let identityAssetSelection = new Set();
const MAX_DASHBOARD_THUMBS = 180;
const MAX_VIDEO_THUMBS = 180;
const MEDIA_THUMB_SIZE_KEY = "forge_media_thumb_size";
const DEFAULT_MEDIA_THUMB_SIZE = 200;
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
let ideaBoardState = { campaignOptionsLoaded: false };

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $log = document.getElementById("log-panel");
const $filmstrip = document.getElementById("filmstrip");
const $chatInput = document.getElementById("chat-input");
const $chatStatus = document.getElementById("chat-status");
let $scriptChatInput = document.getElementById("script-chat-input");
let $scriptChatStatus = document.getElementById("script-chat-status");
let $scriptChatLog = document.getElementById("script-chat-log");
let $scriptChatSendBtn = document.getElementById("script-chat-send-btn");
const $briefInput = document.getElementById("brief-input");
const $runBtn = document.getElementById("run-campaign-btn");
const $campaignStatusBox = document.getElementById("campaign-status-box");
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
const DEFAULT_VIDEO_WORKFLOW_ID = "04_ltx2.3_image_to_video";

function getSelectedVideoWorkflow() {
    const select = document.getElementById("video-model-select");
    if (select?.value) return String(select.value || "").trim();
    return DEFAULT_VIDEO_WORKFLOW_ID;
}

function setDefaultVideoWorkflow() {
    const select = document.getElementById("video-model-select");
    if (select && !select.value) select.value = DEFAULT_VIDEO_WORKFLOW_ID;
}

function getVideoGenerationOptions() {
    const modelEl = document.getElementById("video-model-select");
    const durationEl = document.getElementById("video-duration-select");
    const resolutionEl = document.getElementById("video-resolution-select");
    const aspectEl = document.getElementById("video-aspect-select");
    const workflowId = String(modelEl?.value || getSelectedVideoWorkflow() || DEFAULT_VIDEO_WORKFLOW_ID);
    return {
        mode: "videos",
        workflowId,
        duration: parseInt(durationEl?.value || $videoDuration?.value || "5", 10),
        resolution: String(resolutionEl?.value || "540p"),
        aspectRatio: String(aspectEl?.value || "16:9"),
        modelLabel: modelEl?.selectedOptions?.[0]?.textContent?.trim() || "LTX 2.3 Fast",
    };
}

function syncVideoQuickOptions() {
    const options = getVideoGenerationOptions();
    if ($videoDuration && Number.isFinite(options.duration)) $videoDuration.value = String(options.duration);
    const summary = document.getElementById("video-option-summary");
    if (summary) {
        summary.textContent = [
            options.modelLabel,
            options.duration + " Sec",
            options.resolution,
            options.aspectRatio,
        ].join(" / ");
    }
    return options;
}

function initVideoQuickOptions() {
    ["video-model-select", "video-duration-select", "video-resolution-select", "video-aspect-select"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("change", syncVideoQuickOptions);
    });
    syncVideoQuickOptions();
}

function inferImageTargetCount(text, fallback) {
    const clean = String(text || "").toLowerCase();
    const units = "(?:images?|shots?|frames?|renders?|stills?|assets?|variations?)";
    const patterns = [
        new RegExp("\\b(\\d{1,3})\\s*[- ]?\\s*" + units + "\\b"),
        new RegExp("\\b" + units + "\\s*[:=]?\\s*(\\d{1,3})\\b"),
        /\b(?:make|create|generate|render|produce|need|needs|want|wants|requested|requesting)\s+(\d{1,3})\b/,
        /\b(\d{1,3})\s*x\b/,
    ];
    for (const pattern of patterns) {
        const match = clean.match(pattern);
        if (!match) continue;
        const n = parseInt(match[1], 10);
        if (Number.isFinite(n)) return Math.max(1, Math.min(n, 120));
    }
    const words = {
        one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
        eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17,
        eighteen: 18, nineteen: 19, twenty: 20, thirty: 30,
    };
    for (const [word, n] of Object.entries(words)) {
        if (new RegExp("\\b" + word + "\\s+" + units + "\\b").test(clean)) return n;
    }
    return fallback || 5;
}

function clampImageTargetCount(value, fallback = 5) {
    const parsed = parseInt(value, 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(1, Math.min(parsed, 120));
}

function updateTargetCountPill() {
    const input = document.getElementById("target-count-input");
    const unit = document.getElementById("target-count-unit");
    const inferred = inferImageTargetCount($briefInput?.value || "", 5);
    const count = input && targetCountManualOverride
        ? clampImageTargetCount(input.value, inferred)
        : inferred;
    if (input && document.activeElement !== input) input.value = String(count);
    if (unit) unit.textContent = count === 1 ? "image" : "images";
    return count;
}

function onTargetCountInput() {
    const input = document.getElementById("target-count-input");
    if (!input) return;
    if (!String(input.value || "").trim()) {
        targetCountManualOverride = false;
        updateTargetCountPill();
        return;
    }
    targetCountManualOverride = true;
    const count = clampImageTargetCount(input.value, 5);
    const unit = document.getElementById("target-count-unit");
    if (unit) unit.textContent = count === 1 ? "image" : "images";
}
const $startBatchBtn = document.getElementById("start-batch-btn");
const $lightboxModal = document.getElementById("lightbox-modal");
const $dashboardDivider = document.getElementById("dashboard-divider");
const $dashboardLeftPane = document.getElementById("dashboard-left-pane");

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
    setDefaultVideoWorkflow();
    initVideoQuickOptions();
    switchScriptFlowStep("idea");
    const scriptBriefEl = document.getElementById("script-brief");
    if (scriptBriefEl) scriptBriefEl.addEventListener("input", updateScriptFlowState);
    const scriptPackageEl = document.getElementById("script-package-json");
    if (scriptPackageEl) scriptPackageEl.addEventListener("input", updateScriptFlowState);
    if ($briefInput) $briefInput.addEventListener("input", updateTargetCountPill);
    updateTargetCountPill();
    loadCharacters();
    loadStats();
    loadShots();
    loadCampaignFolders();
    setInterval(loadStats, 10000);
    loadVideoLibrary();
    const csk = document.getElementById("campaign-sort-key");
    const csr = document.getElementById("campaign-sort-reverse");
    if (csk) campaignSort.key = csk.value || "name";
    if (csr) campaignSort.reverse = !!csr.checked;
    mediaSort = { key: "time", reverse: true };
    initModelControls();
    initPlatformControls();
    syncInlineMediaSortControls();
    initMediaThumbSizeControl();
    initDashboardResizer();
    initVideoResizer();
    loadPendingVideoJobs();
    if (pendingVideoJobs.length) scheduleVideoJobPoll(1200);
    ["identity-type","identity-name","identity-tokens","identity-negatives"].forEach((k) => {
        const el = id(k);
        if (el) el.addEventListener("input", updateIdentityPreview);
        if (el) el.addEventListener("change", updateIdentityPreview);
    });
});

function id(s) { return document.getElementById(s); }

function initPlatformControls() {
    const briefEl = document.getElementById("brief-input");
    if (briefEl) {
        briefEl.addEventListener("input", () => {
            if (platformDetectTimer) clearTimeout(platformDetectTimer);
            platformDetectTimer = setTimeout(updatePlatformDetection, 250);
        });
    }
    updatePlatformDetection();
}

async function updatePlatformDetection() {
    const brief = ($briefInput?.value || "").trim();
    const mode = document.getElementById("platform-mode")?.value || "auto";
    const seriesEl = document.getElementById("series-continuity");
    const seriesContinuity = seriesEl?.checked ? true : null;
    const pill = document.getElementById("platform-status-pill");
    if (!pill) return;
    if (!brief && mode === "auto") {
        currentPlatformSkill = { active: false, id: "", label: "No platform skill", constraints: {} };
        pill.textContent = "Platform skill: Auto";
        pill.className = "platform-status-pill off";
        return;
    }
    try {
        const resp = await fetch("/api/platform/detect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ brief, platform_mode: mode, series_continuity: seriesContinuity }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentPlatformSkill = data.platform || { active: false, id: "", label: "No platform skill", constraints: {} };
        renderPlatformPill(currentPlatformSkill);
        if (currentPlatformSkill.active && currentPlatformSkill.constraints) {
            const vd = document.getElementById("video-duration");
            const vds = document.getElementById("video-duration-select");
            if (vd && Number(vd.value || 0) < Number(currentPlatformSkill.constraints.duration_min_sec || 8)) {
                vd.value = String(currentPlatformSkill.constraints.duration_default_sec || 12);
            }
            if (vds && Number(vds.value || 0) < Number(currentPlatformSkill.constraints.duration_min_sec || 8)) {
                const target = String(currentPlatformSkill.constraints.duration_default_sec || 12);
                if (Array.from(vds.options).some((opt) => opt.value === target)) vds.value = target;
                syncVideoQuickOptions();
            }
        }
    } catch (e) {
        pill.textContent = "Platform skill: detection unavailable";
        pill.className = "platform-status-pill off";
    }
}

function renderPlatformPill(platform) {
    const pill = document.getElementById("platform-status-pill");
    if (!pill) return;
    if (platform && platform.active) {
        const constraints = platform.constraints || {};
        const series = platform.series_continuity ? " · series lock" : "";
        pill.textContent = "TikTok Vertical Active · " + (constraints.width || 1080) + "x" + (constraints.height || 1920) + " · 8-15s" + series;
        pill.className = "platform-status-pill active";
    } else {
        pill.textContent = "Platform skill: Auto";
        pill.className = "platform-status-pill off";
    }
}

function initModelControls() {
    const flux2El = document.getElementById("model-flux2");
    const turboEl = document.getElementById("model-turbo");
    if (flux2El) flux2El.addEventListener("change", syncTurboModelControl);
    if (turboEl) turboEl.addEventListener("change", syncTurboModelControl);
    syncTurboModelControl();
}

function syncTurboModelControl() {
    const flux2El = document.getElementById("model-flux2");
    const turboEl = document.getElementById("model-turbo");
    if (!flux2El || !turboEl) return;

    const enabled = !!flux2El.checked;
    if (!enabled) turboEl.checked = false;
    turboEl.disabled = !enabled;

    const label = turboEl.closest(".model-inline-option") || turboEl.closest(".model-checkbox");
    if (label) {
        label.classList.toggle("disabled", !enabled);
        label.title = enabled ? "Use Flux2.Dev turbo mode" : "Enable Flux2.Dev to use Turbo";
    }
}

function clampMediaThumbSize(value) {
    const parsed = parseInt(value, 10);
    if (!Number.isFinite(parsed)) return DEFAULT_MEDIA_THUMB_SIZE;
    return Math.max(120, Math.min(320, parsed));
}

function setMediaThumbSize(value) {
    const size = clampMediaThumbSize(value);
    document.documentElement.style.setProperty("--media-thumb-size", size + "px");
    document.querySelectorAll(".thumbnail-size-slider").forEach((slider) => {
        if (slider.value !== String(size)) slider.value = String(size);
    });
    document.querySelectorAll(".thumbnail-size-value").forEach((label) => {
        label.textContent = size + "px";
    });
    try {
        localStorage.setItem(MEDIA_THUMB_SIZE_KEY, String(size));
    } catch (_e) {
        // localStorage may be unavailable in restricted browser contexts.
    }
}

function initMediaThumbSizeControl() {
    let saved = DEFAULT_MEDIA_THUMB_SIZE;
    try {
        saved = localStorage.getItem(MEDIA_THUMB_SIZE_KEY) || DEFAULT_MEDIA_THUMB_SIZE;
    } catch (_e) {
        saved = DEFAULT_MEDIA_THUMB_SIZE;
    }
    setMediaThumbSize(saved);
}

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
        role.innerHTML = '<option value="anchor">character</option><option value="sheet">sheet</option><option value="detail">detail</option>';
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
        addLogEntry("hermes", "Auto-selected " + (data.selected || 0) + " character assets.");
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
        pack.anchor_image_ids.length ? ("characters: " + pack.anchor_image_ids.length) : "",
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
    syncShotFiltersFromControls();
    try {
        await fetch("/api/shots/reindex-storage", { method: "POST" });
    } catch (_e) {
        // best effort
    }
    await loadShots();
    await loadVideoLibrary();
    await loadCampaignFolders();
}

async function refreshPhotos() {
    const campaignId = (document.getElementById("filter-campaign-id")?.value || "").trim();
    if (campaignId) {
        try {
            const resp = await fetch("/api/comfy/recover-history", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ campaign_id: campaignId }),
            });
            const result = await resp.json();
            if (resp.ok && result.recovered_count) {
                addLogEntry("system", "Recovered " + result.recovered_count + " completed Comfy render(s) for " + campaignId + ".");
            } else if (!resp.ok) {
                addLogEntry("warning", "Comfy history recovery skipped: " + (result.detail || result.error || resp.status));
            }
        } catch (e) {
            addLogEntry("warning", "Comfy history recovery skipped: " + (e?.message || e));
        }
    }
    await refreshShotViews();
}

function syncShotFiltersFromControls() {
    shotFilters.campaignId = (document.getElementById("filter-campaign-id")?.value || "").trim();
    shotFilters.renderedOnly = !!document.getElementById("filter-rendered-only")?.checked;
    shotFilters.failedOnly = !!document.getElementById("filter-failed-only")?.checked;
    shotFilters.passedOnly = !!document.getElementById("filter-passed-only")?.checked;
    shotFilters.retriesOnly = !!document.getElementById("filter-retries-only")?.checked;
    shotFilters.importedOnly = !!document.getElementById("filter-imported-only")?.checked;
}

function scheduleCampaignMediaRefresh() {
    if (campaignMediaRefreshTimer) clearTimeout(campaignMediaRefreshTimer);
    campaignMediaRefreshTimer = setTimeout(async () => {
        campaignMediaRefreshTimer = null;
        await loadShots();
        await loadVideoLibrary();
        await loadCampaignFolders();
    }, 250);
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
    syncShotFiltersFromControls();
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
    if (pageClass === "ideas-view") {
        loadIdeaBoard();
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
            const append = document.getElementById("append-campaign");
            if (append) append.checked = false;
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
                const append = document.getElementById("append-campaign");
                if (append) append.checked = true;
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
            const mediaCount = Number.isFinite(Number(c.media_count)) ? Number(c.media_count) : Number(c.shot_count || 0);
            const totalCount = Number.isFinite(Number(c.total_shot_count)) ? Number(c.total_shot_count) : mediaCount;
            meta.textContent = String(mediaCount || 0);
            meta.title = "Media: " + String(mediaCount || 0) + (totalCount !== mediaCount ? " / total records: " + String(totalCount || 0) : "");
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
// Hermes Idea Board
// ---------------------------------------------------------------------------
async function syncIdeaBoardCampaignOptions(selectedCampaignId) {
    const select = document.getElementById("idea-board-filter");
    if (!select) return;
    const selected = selectedCampaignId ?? select.value ?? "";
    try {
        const resp = await fetch("/api/campaigns");
        const data = await resp.json();
        const campaigns = _sortCampaigns(Array.isArray(data.campaigns) ? data.campaigns : []);
        const options = ['<option value="">All campaigns</option>'].concat(
            campaigns.map((c) => {
                const cid = String(c.campaign_id || "");
                return '<option value="' + escapeHtml(cid) + '">' + escapeHtml(cid) + '</option>';
            })
        );
        select.innerHTML = options.join("");
        if (selected && campaigns.some((c) => String(c.campaign_id || "") === selected)) {
            select.value = selected;
        }
        ideaBoardState.campaignOptionsLoaded = true;
    } catch (_e) {
        if (!select.options.length) {
            select.innerHTML = '<option value="">All campaigns</option>';
        }
    }
}

async function loadIdeaBoard() {
    const boardEl = document.getElementById("idea-board");
    const statusEl = document.getElementById("idea-board-status");
    const subtitleEl = document.getElementById("idea-board-subtitle");
    const filterEl = document.getElementById("idea-board-filter");
    if (!boardEl) return;

    if (!ideaBoardState.campaignOptionsLoaded) {
        await syncIdeaBoardCampaignOptions(filterEl ? filterEl.value : "");
    }

    const campaignId = filterEl ? String(filterEl.value || "") : "";
    if (statusEl) statusEl.textContent = "Loading idea board...";
    try {
        const url = "/api/ideas/board" + (campaignId ? "?campaign_id=" + encodeURIComponent(campaignId) : "");
        const resp = await fetch(url);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const board = await resp.json();
        renderIdeaBoard(board);
        const count = Number(board.count || 0);
        if (statusEl) statusEl.textContent = "Loaded " + count + " idea" + (count === 1 ? "" : "s") + ".";
        if (subtitleEl) {
            subtitleEl.textContent = campaignId ? "Filtered to campaign " + campaignId + "." : "Creative concepts grouped by stage.";
        }
    } catch (e) {
        boardEl.innerHTML = '<div class="grid-placeholder"><p>Idea board unavailable.</p></div>';
        if (statusEl) statusEl.textContent = "Idea board failed: " + (e?.message || e);
        addLogEntry("error", "Idea board failed: " + (e?.message || e));
    }
}

const IDEA_BOARD_COLUMNS = [
    { id: "inbox", label: "Inbox" },
    { id: "spark", label: "Spark" },
    { id: "story", label: "Story" },
    { id: "visual", label: "Visual" },
    { id: "ready", label: "Ready" },
];

function renderIdeaBoard(board) {
    const boardEl = document.getElementById("idea-board");
    if (!boardEl) return;
    const columns = Array.isArray(board?.columns) ? board.columns : [];
    if (!columns.length) {
        boardEl.innerHTML = '<div class="grid-placeholder"><p>No idea columns returned.</p></div>';
        return;
    }
    boardEl.innerHTML = columns.map((column) => {
        const cards = Array.isArray(column.cards) ? column.cards : [];
        return (
            '<section class="idea-column" data-stage="' + escapeHtml(column.id || "") + '">' +
                '<header><span class="idea-column-title">' + escapeHtml(column.label || column.id || "Stage") + '</span><span class="idea-column-count">' + String(cards.length) + '</span></header>' +
                '<div class="idea-card-list">' +
                    (cards.length ? cards.map(renderIdeaCard).join("") : '<div class="idea-empty">No cards</div>') +
                '</div>' +
            '</section>'
        );
    }).join("");
}

function renderIdeaCard(card) {
    const stage = String(card.stage || "inbox");
    const tags = Array.isArray(card.tags) ? card.tags.slice(0, 4) : [];
    const previous = getAdjacentIdeaStage(stage, -1);
    const next = getAdjacentIdeaStage(stage, 1);
    return (
        '<article class="idea-card">' +
            '<div class="idea-card-meta"><span>' + escapeHtml(card.type || "idea") + '</span><span>' + escapeHtml(card.campaign_id || "unscoped") + '</span></div>' +
            '<h3>' + escapeHtml(card.title || card.id || "Untitled idea") + '</h3>' +
            '<p>' + escapeHtml(card.body || "No notes yet.") + '</p>' +
            '<div class="idea-tags">' + tags.map((tag) => '<span>' + escapeHtml(tag) + '</span>').join("") + '</div>' +
            '<div class="idea-card-actions">' +
                '<button type="button" class="idea-mini-btn" ' + (previous ? '' : 'disabled ') + 'onclick="moveIdeaCard(\'' + escapeJsString(card.id || "") + '\', \'' + escapeJsString(previous || "") + '\')">Back</button>' +
                '<button type="button" class="idea-mini-btn" ' + (next ? '' : 'disabled ') + 'onclick="moveIdeaCard(\'' + escapeJsString(card.id || "") + '\', \'' + escapeJsString(next || "") + '\')">Promote</button>' +
                '<button type="button" class="idea-mini-btn danger" onclick="deleteIdeaCard(\'' + escapeJsString(card.id || "") + '\')">Delete</button>' +
            '</div>' +
        '</article>'
    );
}

function getAdjacentIdeaStage(stage, offset) {
    const index = IDEA_BOARD_COLUMNS.findIndex((column) => column.id === stage);
    if (index < 0) return "";
    return IDEA_BOARD_COLUMNS[index + offset]?.id || "";
}

async function createIdeaCard(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const statusEl = document.getElementById("idea-board-status");
    const campaignId = document.getElementById("idea-board-filter")?.value || currentCampaignId || "";
    const data = new FormData(form);
    const payload = {
        title: String(data.get("title") || "").trim(),
        body: String(data.get("body") || "").trim(),
        type: String(data.get("type") || "concept"),
        stage: "inbox",
        campaign_id: campaignId,
        tags: String(data.get("tags") || "").split(",").map((tag) => tag.trim()).filter(Boolean),
    };
    if (!payload.title) return;
    if (statusEl) statusEl.textContent = "Saving idea...";
    const resp = await fetch("/api/ideas/cards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        if (statusEl) statusEl.textContent = "Idea save failed.";
        return;
    }
    form.reset();
    await loadIdeaBoard();
}

async function generateHookIdeas(saveToBoard) {
    const statusEl = document.getElementById("idea-board-status");
    const hookInput = document.getElementById("hook-brief-input");
    const campaignId = document.getElementById("idea-board-filter")?.value || currentCampaignId || "";
    const brief = (hookInput?.value || $briefInput?.value || "").trim();
    if (!brief) {
        if (statusEl) statusEl.textContent = "Enter a hook brief or write a prompt on Images.";
        return;
    }
    if (statusEl) statusEl.textContent = saveToBoard ? "Generating and saving TikTok hooks..." : "Generating hook preview...";
    try {
        const resp = await fetch("/api/ideas/hooks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                brief,
                campaign_id: campaignId,
                platform_mode: "tiktok",
                save_to_board: !!saveToBoard,
            }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        const hooks = Array.isArray(data.hooks) ? data.hooks : [];
        if (saveToBoard) {
            if (statusEl) statusEl.textContent = "Saved " + hooks.length + " TikTok hook idea(s).";
            await loadIdeaBoard();
        } else {
            if (statusEl) {
                statusEl.textContent = hooks.map((h) => (h.caption || h.hook || "Hook") + " / " + (h.audio || "audio direction")).join("  |  ");
            }
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = "Hook generation failed: " + (e?.message || e);
        addLogEntry("error", "Hook generation failed: " + (e?.message || e));
    }
}

async function moveIdeaCard(cardId, stage) {
    if (!cardId || !stage) return;
    const resp = await fetch("/api/ideas/cards/" + encodeURIComponent(cardId), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage }),
    });
    if (!resp.ok) {
        addLogEntry("error", "Idea move failed: HTTP " + resp.status);
        return;
    }
    await loadIdeaBoard();
}

async function deleteIdeaCard(cardId) {
    if (!cardId) return;
    const ok = window.confirm("Delete this idea card?");
    if (!ok) return;
    const resp = await fetch("/api/ideas/cards/" + encodeURIComponent(cardId), { method: "DELETE" });
    if (!resp.ok) {
        addLogEntry("error", "Idea delete failed: HTTP " + resp.status);
        return;
    }
    await loadIdeaBoard();
}

function escapeJsString(str) {
    return String(str || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

// ---------------------------------------------------------------------------
// Settings: Load Config
// ---------------------------------------------------------------------------
async function loadConfig() {
    if (!document.getElementById("cfg-backend-mode")) return;
    try {
        const resp = await fetch("/api/config");
        currentConfig = await resp.json();

        // Backend mode
        const backendMode = currentConfig.backend_mode || "local";
        document.getElementById("cfg-backend-mode").checked = backendMode === "remote";
        _updateBackendLabels(backendMode === "remote");

        // AI Provider (Nous / Kimi / OpenRouter / NVIDIA)
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
        loadSettingsBanks();

    } catch (e) {
        console.error("Failed to load config:", e);
    }
}

const SETTINGS_BANK_FIELDS = {
    pose: "cfg-bank-pose",
    view: "cfg-bank-view",
    lighting: "cfg-bank-lighting",
    background: "cfg-bank-background",
};

async function loadSettingsBanks() {
    const hasBankEditor = Object.values(SETTINGS_BANK_FIELDS).some((id) => document.getElementById(id));
    if (!hasBankEditor) return;
    try {
        const resp = await fetch("/api/banks?mode=character");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const banks = await resp.json();
        Object.entries(SETTINGS_BANK_FIELDS).forEach(([name, id]) => {
            const el = document.getElementById(id);
            if (el && Array.isArray(banks[name])) el.value = banks[name].join("\n");
        });
    } catch (e) {
        const status = document.getElementById("settings-bank-result");
        if (status) {
            status.textContent = "Bank load failed: " + (e?.message || e);
            status.className = "test-result err";
        }
    }
}

function collectSettingsBanks() {
    const banks = {};
    Object.entries(SETTINGS_BANK_FIELDS).forEach(([name, id]) => {
        const el = document.getElementById(id);
        if (el) banks[name] = el.value;
    });
    return banks;
}

async function savePromptBanks() {
    const status = document.getElementById("settings-bank-result");
    if (status) {
        status.textContent = "Saving banks...";
        status.className = "test-result loading";
    }
    try {
        const resp = await fetch("/api/banks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: "character", banks: collectSettingsBanks() }),
        });
        const result = await resp.json().catch(() => ({}));
        if (!resp.ok || result.status !== "success") {
            throw new Error(result.error || ("HTTP " + resp.status));
        }
        if (status) {
            const count = Object.keys(result.saved || {}).length;
            status.textContent = "Saved " + count + " bank(s)";
            status.className = "test-result ok";
        }
    } catch (e) {
        if (status) {
            status.textContent = "Bank save failed: " + (e?.message || e);
            status.className = "test-result err";
        }
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
    const fieldValue = (id) => {
        const el = document.getElementById(id);
        return el ? el.value : null;
    };
    const fieldMap = {
        'backend_mode': () => document.getElementById("cfg-backend-mode")?.checked ? "remote" : "local",
        'kimi.api_key': () => fieldValue("cfg-kimi-api-key"),
        'kimi.endpoint': () => fieldValue("cfg-kimi-endpoint"),
        'models.director_kimi.model_name': () => fieldValue("cfg-director-model"),
        'models.director_kimi.endpoint_api1': () => fieldValue("cfg-director-endpoint-api1"),
        'models.kimi_vl.model_name': () => fieldValue("cfg-visual-model"),
        'models.kimi_vl.endpoint_api1': () => fieldValue("cfg-vision-endpoint-api1"),
        'models.hermes_3.host': () => fieldValue("cfg-lmstudio-host"),
        'models.hermes_3.port': () => {
            const value = fieldValue("cfg-lmstudio-port");
            return value === null ? null : (parseInt(value) || 0);
        },
        'models.hermes_3.model_name': () => fieldValue("cfg-lmstudio-model"),
        'comfyui.primary': () => fieldValue("cfg-comfyui-primary"),
        'comfyui.secondary': () => fieldValue("cfg-comfyui-secondary"),
        'spark.primary': () => fieldValue("cfg-spark-primary"),
        'spark.secondary': () => fieldValue("cfg-spark-secondary"),
        'spark.workflow_file': () => fieldValue("cfg-spark-workflow"),
    };

    if (fieldMap[dotKey]) {
        const value = fieldMap[dotKey]();
        if (value !== null) configDirty[dotKey] = value;
    }
}

function collectAllSettings() {
    const keys = [
        'backend_mode',
        'kimi.api_key',
        'kimi.endpoint',
        'models.director_kimi.model_name',
        'models.director_kimi.endpoint_api1',
        'models.kimi_vl.model_name',
        'models.kimi_vl.endpoint_api1',
        'models.hermes_3.host',
        'models.hermes_3.port',
        'models.hermes_3.model_name',
        'comfyui.primary',
        'comfyui.secondary',
        'spark.primary',
        'spark.secondary',
        'spark.workflow_file',
    ];
    const previous = { ...configDirty };
    configDirty = {};
    keys.forEach(markDirty);
    configDirty = { ...configDirty, ...previous };
    return { ...configDirty };
}

// ---------------------------------------------------------------------------
// Settings: Save All
// ---------------------------------------------------------------------------
async function saveAllSettings() {
    const updates = collectAllSettings();

    try {
        const resp = await fetch("/api/config/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ updates }),
        });
        const result = await resp.json();

        if (result.status === "success") {
            // Update current config
            for (const [key, value] of Object.entries(updates)) {
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
        const resp = await fetch("/api/test/director", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                endpoint: document.getElementById("cfg-director-endpoint-api1")?.value || "",
                model: document.getElementById("cfg-director-model")?.value || "",
                api_key: document.getElementById("cfg-kimi-api-key")?.value || "",
            }),
        });
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
        const resp = await fetch("/api/test/vision", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                endpoint: document.getElementById("cfg-vision-endpoint-api1")?.value || "",
                model: document.getElementById("cfg-visual-model")?.value || "",
                api_key: document.getElementById("cfg-kimi-api-key")?.value || "",
                host: document.getElementById("cfg-lmstudio-host")?.value || "",
                port: document.getElementById("cfg-lmstudio-port")?.value || "",
            }),
        });
        const data = await resp.json();
        if (data.status === "ok") {
            const endpoint = data.endpoint ? " via " + data.endpoint : "";
            $result.textContent = "Vision OK: " + data.model + " (" + data.latency_ms + "ms)" + endpoint;
            $result.className = "test-result ok";
        } else {
            $result.textContent = "Vision failed: " + formatEndpointError(data);
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
    const displayTarget = [host || "localhost", port].filter(Boolean).join(":");

    $result.textContent = "Connecting to " + displayTarget + "...";
    $result.className = "test-result loading";
    if ($modelsList) $modelsList.style.display = "none";

    try {
        const params = new URLSearchParams();
        if (host) params.set("host", host);
        if (port) params.set("port", port);
        const url = "/api/lmstudio/status" + (params.toString() ? "?" + params.toString() : "");
        const resp = await fetch(url);
        const data = await resp.json();

        if (data.status === "ok") {
            const loaded = data.loaded_models || [];
            const available = data.available_models || [];
            const base = data.base_url ? " at " + data.base_url : "";
            $result.textContent = "Reachable" + base + ": " + loaded.length + " loaded / " + available.length + " available (" + data.latency_ms + "ms)";
            $result.className = loaded.length ? "test-result ok" : "test-result loading";

            // Populate model dropdown
            if ($modelsSelect && $modelsList && available.length > 0) {
                $modelsSelect.innerHTML = available.map(m =>
                    '<option value="' + escapeHtml(m.key) + '">' + escapeHtml((m.vision ? "VISION " : "") + (m.display_name || m.key) + " - " + m.key) + '</option>'
                ).join("");
                const current = document.getElementById("cfg-lmstudio-model")?.value || "";
                if (current) $modelsSelect.value = current;
                $modelsList.style.display = "block";
            }
        } else {
            $result.textContent = "Failed: " + formatEndpointError(data);
            $result.className = "test-result err";
        }
    } catch (e) {
        $result.textContent = "Error: " + e.message;
        $result.className = "test-result err";
    }
}

function formatEndpointError(data) {
    if (!data) return "unknown error";
    const parts = [];
    if (data.error) parts.push(data.error);
    if (data.base_url) parts.push("base: " + data.base_url);
    if (Array.isArray(data.attempted) && data.attempted.length) {
        parts.push("tried: " + data.attempted.join(", "));
    }
    if (Array.isArray(data.errors) && data.errors.length) {
        const tail = data.errors.slice(-3).map((e) => {
            if (typeof e === "string") return e;
            return (e.url || e.base_url || e.endpoint || "endpoint") + " -> " + (e.error || "failed");
        });
        parts.push(tail.join(" | "));
    }
    return parts.filter(Boolean).join(" | ") || "unknown error";
}

function getLMStudioLoadPayload() {
    return {
        host: document.getElementById("cfg-lmstudio-host")?.value || "",
        port: parseInt(document.getElementById("cfg-lmstudio-port")?.value || "0") || 0,
        model: document.getElementById("cfg-lmstudio-model")?.value || "",
    };
}

async function loadLMStudioModel() {
    const $result = document.getElementById("lmstudio-test-result");
    const payload = getLMStudioLoadPayload();
    if (!payload.model) {
        $result.textContent = "Choose or enter a model key first";
        $result.className = "test-result err";
        return null;
    }
    $result.textContent = "Loading " + payload.model + "...";
    $result.className = "test-result loading";
    try {
        const resp = await fetch("/api/lmstudio/load", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (data.status === "ok") {
            const seconds = data.load_time_seconds ?? Math.round((data.elapsed_ms || 0) / 1000);
            $result.textContent = "Loaded " + data.model + " in " + seconds + "s";
            $result.className = "test-result ok";
            configDirty = {};
            await loadConfig();
            await testLMStudio();
            return data;
        }
        $result.textContent = "Load failed: " + (data.error || data.detail || "unknown error");
        $result.className = "test-result err";
        return null;
    } catch (e) {
        $result.textContent = "Load error: " + e.message;
        $result.className = "test-result err";
        return null;
    }
}

async function reloadHermesVision() {
    const $result = document.getElementById("lmstudio-test-result");
    const loaded = await loadLMStudioModel();
    if (!loaded) return;
    $result.textContent = "Loaded. Testing Hermes and Vision...";
    $result.className = "test-result loading";
    await testLMStudio();
    await testVision();
    $result.textContent = "Reload complete: Hermes/Vision model loaded and Vision test triggered.";
    $result.className = "test-result ok";
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
let $scriptBrief = document.getElementById("script-brief");
let $scriptStatusText = document.getElementById("script-status-text");
let $scriptProgress = document.getElementById("script-progress");
let $shotList = document.getElementById("shot-list");
let $shotListPlaceholder = document.getElementById("shot-list-placeholder");
let $sendToSparkBtn = document.getElementById("send-to-spark-btn");
let currentScriptFlowStep = "idea";

let characterMap = {}; // id -> name for linking

function refreshScriptDomRefs() {
    $scriptChatInput = document.getElementById("script-chat-input");
    $scriptChatStatus = document.getElementById("script-chat-status");
    $scriptChatLog = document.getElementById("script-chat-log");
    $scriptChatSendBtn = document.getElementById("script-chat-send-btn");
    $scriptBrief = document.getElementById("script-brief");
    $scriptStatusText = document.getElementById("script-status-text");
    $scriptProgress = document.getElementById("script-progress");
    $shotList = document.getElementById("shot-list");
    $shotListPlaceholder = document.getElementById("shot-list-placeholder");
    $sendToSparkBtn = document.getElementById("send-to-spark-btn");
}

function scriptInputValue(idName, fallback) {
    const el = document.getElementById(idName);
    return (el?.value || fallback || "").trim();
}

function setScriptStatus(text, progress) {
    refreshScriptDomRefs();
    if ($scriptStatusText) $scriptStatusText.textContent = text || "";
    if ($scriptProgress && progress !== undefined) $scriptProgress.textContent = progress || "";
    updateScriptFlowState();
}

function scriptFlowCountShots() {
    return Object.keys(director_shots || {}).length;
}

function setScriptStepStatus(step, text) {
    const el = document.getElementById("script-step-status-" + step);
    if (el) el.textContent = text;
}

function updateScriptVideoHandoff() {
    const title = document.getElementById("script-video-handoff-title");
    const copy = document.getElementById("script-video-handoff-copy");
    const selected = videoSelection?.size || 0;
    const shots = scriptFlowCountShots();
    const boards = Array.isArray(storyboardPlan?.boards) ? storyboardPlan.boards.length : 0;
    if (title) {
        title.textContent = selected
            ? selected + " start frame" + (selected === 1 ? "" : "s") + " selected for video."
            : boards
                ? "Storyboard ready for video export."
                : shots
                    ? shots + " coverage shot" + (shots === 1 ? "" : "s") + " ready."
                    : "No video frames selected yet.";
    }
    if (copy) {
        copy.textContent = selected
            ? "Open the Videos tab to choose duration, resolution, aspect ratio, and generate LTX clips."
            : boards
                ? "Render storyboard panels, assemble them, then export the panel frames to Videos."
                : shots
                    ? "Render selected coverage shots first, then use those images as video start frames."
                    : "Build a script package and storyboard before generating videos.";
    }
}

function updateScriptFlowState() {
    const hasBrief = !!($scriptBrief?.value || "").trim();
    const hasPackage = !!getScriptPackageFromEditor();
    const shotCount = scriptFlowCountShots();
    const boardCount = Array.isArray(storyboardPlan?.boards) ? storyboardPlan.boards.length : 0;
    const selectedVideos = videoSelection?.size || 0;

    setScriptStepStatus("idea", hasBrief ? "Brief set" : "Ready");
    setScriptStepStatus("script", hasPackage ? "Package ready" : "Waiting");
    setScriptStepStatus("storyboard", boardCount ? boardCount + " board" + (boardCount === 1 ? "" : "s") : "Waiting");
    setScriptStepStatus("videos", selectedVideos ? selectedVideos + " selected" : shotCount ? "Coverage ready" : "Waiting");

    document.querySelectorAll(".script-flow-step[data-script-step]").forEach((el) => {
        const step = el.dataset.scriptStep;
        el.classList.toggle("active", step === currentScriptFlowStep);
        el.classList.toggle("complete",
            (step === "idea" && hasBrief) ||
            (step === "script" && hasPackage) ||
            (step === "storyboard" && boardCount > 0) ||
            (step === "videos" && selectedVideos > 0)
        );
    });
    updateScriptVideoHandoff();
}

function switchScriptFlowStep(step) {
    refreshScriptDomRefs();
    currentScriptFlowStep = step || "idea";
    document.querySelectorAll("[data-script-step-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.scriptStepPanel === currentScriptFlowStep);
    });
    updateScriptFlowState();
}

function getScriptPackageFromEditor() {
    const editor = document.getElementById("script-package-json");
    if (!editor || !editor.value.trim()) return scriptPackage;
    try {
        return JSON.parse(editor.value);
    } catch (_e) {
        return scriptPackage;
    }
}

function scriptPackageShotlistBrief() {
    const pkg = getScriptPackageFromEditor();
    const rawBrief = ($scriptBrief?.value || "").trim();
    if (!pkg) return rawBrief;
    return [
        "LOCKED SCRIPT PACKAGE FOR SHOTLIST GENERATION:",
        JSON.stringify(pkg, null, 2),
        "",
        "Generate coverage from the locked package. Preserve scene_id, beat_id, continuity, screen direction, edit role, duration, transition intent, audio cue, character wardrobe, prop state, and location state. Do not invent unrelated scenes.",
        rawBrief ? "\nORIGINAL USER BRIEF:\n" + rawBrief : "",
    ].join("\n");
}

function getStoryboardSourcePackage() {
    return getScriptPackageFromEditor();
}

function getStoryboardSourceText() {
    const pkg = getStoryboardSourcePackage();
    if (pkg) return JSON.stringify(pkg, null, 2);
    return ($scriptBrief?.value || "").trim();
}

const STORYBOARD_STYLE_PRESETS = {
    comic: {
        style: "classic American comic book style, bold ink lines, halftone dots, vibrant colors",
        panels: 9,
        target: "",
        resolution: "3840x2160",
    },
    anime: {
        style: "detailed anime style, clean line art, vibrant colors, dynamic angles",
        panels: 9,
        target: "",
        resolution: "3840x2160",
    },
    realistic: {
        style: "photorealistic cinematic stills, 35mm lens, anamorphic bokeh, dramatic lighting",
        panels: 9,
        target: "",
        resolution: "3840x2160",
    },
    four: {
        style: "cinematic storyboard frames, clean readable compositions, highly consistent character design",
        panels: 4,
        target: 4,
        resolution: "2048x2048",
    },
};

function setStoryboardPreset(name) {
    const preset = STORYBOARD_STYLE_PRESETS[name];
    if (!preset) return;
    const set = (idName, value) => {
        const el = document.getElementById(idName);
        if (el) el.value = value;
    };
    set("storyboard-style", preset.style);
    set("storyboard-panels-per-board", String(preset.panels));
    set("storyboard-target-panels", preset.target === "" ? "" : String(preset.target));
    set("storyboard-resolution", preset.resolution);
    setScriptStatus("Storyboard preset applied: " + name + ".", "Storyboard");
}

function storyboardSleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function storyboardCharacterSheetPrompt() {
    const title = scriptInputValue("script-title", "Storyboard Character") || "Storyboard Character";
    const consistency = scriptInputValue("storyboard-character-consistency", "");
    const style = scriptInputValue("storyboard-style", "cinematic");
    return [
        "professional production character reference turnaround sheet for " + title,
        consistency || "main character, consistent face, consistent wardrobe, full body, portrait close-up, side profile, three-quarter view",
        "4K horizontal 16:9 reference sheet, 3840x2160 composition, clean two-row production layout on a neutral studio background, thin light-gray divider lines, no square canvas, no overlapping panels, no giant central portrait overlay",
        "six large panels only, not nine, generous space around each figure",
        "top row three full-body turnaround panels: front view, left side profile, back view",
        "bottom row three detail panels: sharp front face portrait neutral expression, sharp warm smile portrait, sharp hands and forearms detail with visible skin texture, eyelashes, flyaway hair, fabric weave",
        "same person, same age, same face, same hair, same body proportions, same outfit, same lighting in every panel",
        style,
        "sharp eyelashes and hair strands, clean blank layout, crisp divider lines, no barcode artifacts, no labels, no captions, no typography, no letters, no numbers, no watermark, no duplicate identities, no faded ghost image, no collage overlay",
    ].join(", ");
}

function renderScriptPackage(pkg) {
    const treatmentEl = document.getElementById("script-treatment-output");
    const continuityEl = document.getElementById("script-continuity-output");
    const editEl = document.getElementById("script-edit-output");
    const scenesEl = document.getElementById("script-scenes-output");
    const jsonEl = document.getElementById("script-package-json");
    if (!pkg) {
        [treatmentEl, continuityEl, editEl, scenesEl].forEach((el) => { if (el) el.innerHTML = '<div class="script-empty-mini">No package generated.</div>'; });
        if (jsonEl) jsonEl.value = "";
        return;
    }

    const treatment = pkg.treatment || {};
    if (treatmentEl) {
        treatmentEl.innerHTML =
            '<h3>' + escapeHtml(pkg.title || "Untitled") + '</h3>' +
            '<p><strong>Logline</strong><br>' + escapeHtml(treatment.logline || "") + '</p>' +
            '<p><strong>Synopsis</strong><br>' + escapeHtml(treatment.synopsis || "") + '</p>' +
            '<p><strong>Visual Language</strong><br>' + escapeHtml(treatment.visual_language || "") + '</p>';
    }

    const acts = Array.isArray(pkg.script?.acts) ? pkg.script.acts : [];
    const scenes = acts.flatMap((act) => Array.isArray(act.scenes) ? act.scenes : []);
    if (scenesEl) {
        scenesEl.innerHTML = scenes.length ? scenes.map((scene) => {
            const beats = Array.isArray(scene.beats) ? scene.beats : [];
            return (
                '<article class="script-scene-card">' +
                    '<div class="script-scene-head"><span>' + escapeHtml(scene.scene_id || "") + '</span><strong>' + escapeHtml(scene.title || "Scene") + '</strong><em>' + escapeHtml(String(scene.duration_sec || "")) + 's</em></div>' +
                    '<p>' + escapeHtml(scene.emotional_turn || scene.location || "") + '</p>' +
                    '<div class="script-beat-list">' + beats.map((beat) => (
                        '<div class="script-beat"><span>' + escapeHtml(beat.beat_id || "") + '</span><p>' + escapeHtml(beat.action || "") + '</p></div>'
                    )).join("") + '</div>' +
                '</article>'
            );
        }).join("") : '<div class="script-empty-mini">No scenes returned.</div>';
    }

    const continuity = pkg.continuity || {};
    if (continuityEl) {
        const groups = [
            ["Characters", continuity.characters],
            ["Locations", continuity.locations],
            ["Props", continuity.props],
            ["Motifs", continuity.motifs],
        ];
        continuityEl.innerHTML = groups.map(([label, items]) => {
            const arr = Array.isArray(items) ? items : [];
            return '<div class="script-lock-group"><h3>' + label + '</h3>' + (arr.length ? arr.map((item) => {
                if (typeof item === "string") return '<p>' + escapeHtml(item) + '</p>';
                return '<p><strong>' + escapeHtml(item.name || item.title || "Lock") + '</strong><br>' + escapeHtml(item.visual_lock || item.wardrobe || item.state || item.performance || JSON.stringify(item)) + '</p>';
            }).join("") : '<p>No locks.</p>') + '</div>';
        }).join("");
    }

    const edit = pkg.edit_plan || {};
    if (editEl) {
        editEl.innerHTML =
            '<p><strong>Pacing</strong><br>' + escapeHtml(edit.pacing || "") + '</p>' +
            '<p><strong>Audio</strong><br>' + escapeHtml(edit.audio_strategy || "") + '</p>' +
            '<p><strong>Transitions</strong><br>' + escapeHtml(edit.transition_strategy || "") + '</p>';
    }

    if (jsonEl) jsonEl.value = JSON.stringify(pkg, null, 2);
}

function renderStoryboardPlan(plan) {
    const target = document.getElementById("storyboard-output");
    if (!target) return;
    if (!plan || !Array.isArray(plan.boards) || !plan.boards.length) {
        target.innerHTML = '<div class="script-empty-shot"><p>No storyboard generated yet.</p></div>';
        return;
    }
    target.innerHTML = plan.boards.map((board) => {
        const panels = Array.isArray(board.panels) ? board.panels : [];
        return (
            '<article class="storyboard-board" data-board-id="' + escapeHtml(board.board_id || "") + '">' +
                '<div class="storyboard-board-head">' +
                    '<div><strong>' + escapeHtml(board.board_id || "Storyboard") + '</strong><span>' + escapeHtml(String(board.panel_count || panels.length)) + ' panel(s) / ' + escapeHtml(board.layout || "") + ' / ' + escapeHtml(board.resolution || "3840x2160") + '</span></div>' +
                    '<div class="storyboard-copy-row">' +
                        '<button class="btn btn-secondary" onclick="renderStoryboardBoard(' + Number(board.index || 1) + ')">Render Page</button>' +
                        '<button class="btn btn-secondary" onclick="renderStoryboardPanels(' + Number(board.index || 1) + ')">Render Panels</button>' +
                        '<button class="btn" onclick="assembleStoryboardPanels(' + Number(board.index || 1) + ')">Assemble</button>' +
                        '<button class="btn" onclick="renderAssembleExportStoryboardPanels(' + Number(board.index || 1) + ')">Render + Export Frames</button>' +
                    '</div>' +
                '</div>' +
                '<div class="storyboard-panel-grid">' + panels.map((panel, idx) => (
                    '<div class="storyboard-panel">' +
                        '<span>' + String(idx + 1) + '</span>' +
                        '<p>' + escapeHtml(panel.caption || panel.visual_prompt || "") + '</p>' +
                    '</div>'
                )).join("") + '</div>' +
                '<textarea class="storyboard-prompt" readonly>' + escapeHtml(board.image_prompt || "") + '</textarea>' +
                '<div class="storyboard-copy-row"><button class="btn btn-secondary" onclick="copyStoryboardPrompt(' + Number(board.index || 1) + ')">Copy FLUX Prompt</button></div>' +
                '<div class="storyboard-panel-jobs" id="storyboard-panel-jobs-' + Number(board.index || 1) + '"></div>' +
                '<div class="storyboard-render-result" id="storyboard-render-' + Number(board.index || 1) + '"></div>' +
            '</article>'
        );
    }).join("");
    plan.boards.forEach((board) => renderStoryboardPanelJobList(Number(board.index || 1)));
}

async function copyStoryboardPrompt(boardIndex) {
    if (!storyboardPlan || !Array.isArray(storyboardPlan.boards)) return;
    const board = storyboardPlan.boards.find((b) => Number(b.index) === Number(boardIndex));
    if (!board || !board.image_prompt) return;
    try {
        await navigator.clipboard.writeText(board.image_prompt);
        const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
        if (resultEl) resultEl.textContent = "Prompt copied.";
    } catch (_e) {
        const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
        if (resultEl) resultEl.textContent = "Copy failed; select the prompt text manually.";
    }
}

async function generateStoryboard() {
    refreshScriptDomRefs();
    const sourceText = getStoryboardSourceText();
    const sourcePackage = getStoryboardSourcePackage();
    if (!sourceText) {
        setScriptStatus("Enter a script or develop a script package before storyboarding.", "");
        return;
    }
    const btn = document.getElementById("generate-storyboard-btn");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Building...";
    }
    setScriptStatus("Building storyboard board(s)...", "Storyboard");
    try {
        const targetPanelsRaw = scriptInputValue("storyboard-target-panels", "");
        const resp = await fetch("/api/script/storyboard", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                script: sourceText,
                package: sourcePackage || null,
                panels_per_board: parseInt(scriptInputValue("storyboard-panels-per-board", "9"), 10) || 9,
                target_panels: targetPanelsRaw ? parseInt(targetPanelsRaw, 10) : null,
                resolution: scriptInputValue("storyboard-resolution", "3840x2160") || "3840x2160",
                title: scriptInputValue("script-title", ""),
                style: scriptInputValue("storyboard-style", "cinematic"),
                character_consistency: scriptInputValue("storyboard-character-consistency", ""),
                negative_prompt: scriptInputValue("storyboard-negative-prompt", "blurry, deformed, extra limbs, text errors, inconsistent characters, merged panels"),
                reference_image_url: scriptInputValue("storyboard-reference-image", ""),
                include_captions: !!document.getElementById("storyboard-include-captions")?.checked,
            }),
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") {
            throw new Error(data.detail || data.error || "storyboard failed");
        }
        storyboardPlan = data;
        storyboardPanelJobs = {};
        renderStoryboardPlan(data);
        switchScriptFlowStep("storyboard");
        setScriptStatus("Storyboard ready: " + data.board_count + " board image(s), " + data.panel_count + " panel(s).", "Storyboard");
    } catch (e) {
        setScriptStatus("Storyboard failed: " + e.message, "");
        addLogEntry("error", "Storyboard failed: " + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Build Storyboard";
        }
    }
}

function getStoryboardBoard(boardIndex) {
    if (!storyboardPlan || !Array.isArray(storyboardPlan.boards)) return null;
    return storyboardPlan.boards.find((b) => Number(b.index) === Number(boardIndex)) || null;
}

function storyboardJobResultUrl(job) {
    const firstJob = Array.isArray(job?.jobs) ? job.jobs[0] : null;
    return firstJob?.results?.raw?.url || firstJob?.results?.min?.url || firstJob?.results?.all?.[0]?.url || "";
}

function renderStoryboardPanelJobList(boardIndex) {
    const holder = document.getElementById("storyboard-panel-jobs-" + Number(boardIndex));
    if (!holder) return;
    const jobs = storyboardPanelJobs[String(boardIndex)] || [];
    if (!jobs.length) {
        holder.innerHTML = "";
        return;
    }
    holder.innerHTML =
        '<div class="storyboard-copy-row">' +
            '<button class="btn btn-secondary" onclick="pollStoryboardPanelJobs(' + Number(boardIndex) + ')">Refresh Panel Jobs</button>' +
        '</div>' +
        '<div class="storyboard-panel-grid">' + jobs.map((job, idx) => {
            const status = job.status || "queued";
            const thumb = job.url ? '<img src="' + escapeHtml(job.url) + '" alt="Panel ' + String(idx + 1) + '">' : "";
            return (
                '<div class="storyboard-panel">' +
                    '<span>' + String(idx + 1) + '</span>' +
                    thumb +
                    '<p>' + escapeHtml(status) + (job.job_set_id ? ' / ' + escapeHtml(job.job_set_id.slice(0, 8)) : "") + '</p>' +
                '</div>'
            );
        }).join("") + '</div>';
}

async function renderStoryboardPanels(boardIndex) {
    const board = getStoryboardBoard(boardIndex);
    if (!board) return;
    const panels = Array.isArray(board.panels) ? board.panels : [];
    const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
    storyboardPanelJobs[String(boardIndex)] = panels.map((panel, idx) => ({
        index: idx + 1,
        status: "submitting",
        job_set_id: "",
        url: "",
    }));
    renderStoryboardPanelJobList(boardIndex);
    if (resultEl) resultEl.textContent = "Submitting " + panels.length + " individual panel render(s) to Spark...";
    try {
        for (let idx = 0; idx < panels.length; idx += 1) {
            const panel = panels[idx];
            const resp = await fetch("/api/local-higgsfield/generate-image", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: panel.single_panel_prompt || panel.visual_prompt || panel.caption || "",
                    width_and_height: panel.width_and_height || board.panel_width_and_height || "1280x720",
                    quality: "720p",
                    batch_size: 1,
                    enhance_prompt: false,
                    wait_for_output: false,
                    image_reference_url: board.reference_image_url || undefined,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.error || "panel render failed");
            storyboardPanelJobs[String(boardIndex)][idx] = {
                index: idx + 1,
                status: data.status || "queued",
                job_set_id: data.job_set_id || data.id || "",
                url: storyboardJobResultUrl(data),
            };
            renderStoryboardPanelJobList(boardIndex);
        }
        if (resultEl) resultEl.textContent = "Panel jobs submitted. Refresh until all panels show completed, then assemble.";
        return storyboardPanelJobs[String(boardIndex)] || [];
    } catch (e) {
        if (resultEl) resultEl.textContent = "Panel render failed: " + e.message;
        addLogEntry("error", "Storyboard panel render failed: " + e.message);
        return [];
    }
}

async function pollStoryboardPanelJobs(boardIndex) {
    const jobs = storyboardPanelJobs[String(boardIndex)] || [];
    const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
    if (!jobs.length) {
        if (resultEl) resultEl.textContent = "No individual panel jobs submitted yet.";
        return [];
    }
    for (let idx = 0; idx < jobs.length; idx += 1) {
        const job = jobs[idx];
        if (!job.job_set_id || job.url) continue;
        try {
            const resp = await fetch("/api/local-higgsfield/jobs/" + encodeURIComponent(job.job_set_id));
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.error || "status failed");
            job.status = data.status || job.status || "queued";
            job.url = storyboardJobResultUrl(data) || job.url || "";
        } catch (e) {
            job.status = "status error: " + e.message;
        }
    }
    renderStoryboardPanelJobList(boardIndex);
    const completed = jobs.filter((job) => job.url).length;
    if (resultEl) resultEl.textContent = "Panel jobs: " + completed + " / " + jobs.length + " image(s) ready.";
    return jobs;
}

async function assembleStoryboardPanels(boardIndex) {
    const board = getStoryboardBoard(boardIndex);
    if (!board) return;
    const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
    const jobs = await pollStoryboardPanelJobs(boardIndex);
    const urls = jobs.map((job) => job.url).filter(Boolean);
    if (!urls.length || urls.length !== (Array.isArray(board.panels) ? board.panels.length : 0)) {
        if (resultEl) resultEl.textContent = "Assemble blocked: all individual panel renders must be completed first.";
        return null;
    }
    if (resultEl) resultEl.textContent = "Assembling completed panels into a storyboard page...";
    try {
        const resp = await fetch("/api/script/storyboard/assemble", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                panel_image_urls: urls,
                title: storyboardPlan?.title || "Storyboard",
                resolution: board.resolution || "3840x2160",
                columns: board.layout_columns || 3,
                rows: board.layout_rows || 3,
                include_panel_numbers: true,
                captions: [],
            }),
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") throw new Error(data.detail || data.error || "assemble failed");
        if (resultEl) {
            resultEl.innerHTML = '<span>Assembled storyboard page.</span><br><img src="' + escapeHtml(data.url) + '" alt="Assembled storyboard">';
        }
        board.assembled_url = data.url || "";
        board.assembled_path = data.path || "";
        if (typeof loadVideoLibrary === "function") loadVideoLibrary();
        return data;
    } catch (e) {
        if (resultEl) resultEl.textContent = "Assemble failed: " + e.message;
        addLogEntry("error", "Storyboard assembly failed: " + e.message);
        return null;
    }
}

async function exportStoryboardVideoShots(boardIndex) {
    const board = getStoryboardBoard(boardIndex);
    if (!board) return null;
    const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
    const jobs = storyboardPanelJobs[String(boardIndex)] || [];
    const urls = jobs.map((job) => job.url).filter(Boolean);
    const expected = Array.isArray(board.panels) ? board.panels.length : 0;
    if (!expected || urls.length !== expected) {
        if (resultEl) resultEl.textContent = "Export blocked: all panel images must be ready before creating video start-frame shots.";
        return null;
    }
    try {
        const resp = await fetch("/api/script/storyboard/export-video-shots", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                board,
                panel_image_urls: urls,
                title: storyboardPlan?.title || scriptInputValue("script-title", "Storyboard"),
                campaign_id: "",
                duration_seconds: 4,
                replace_existing: true,
            }),
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") throw new Error(data.detail || data.error || "export failed");
        if (Array.isArray(data.shot_ids)) {
            data.shot_ids.forEach((id) => videoSelection.add(id));
        }
        if (resultEl) {
            resultEl.innerHTML =
                '<span>Exported ' + Number(data.count || 0) + ' ordered start-frame shot(s) to the Video tab.</span>' +
                (board.assembled_url ? '<br><img src="' + escapeHtml(board.assembled_url) + '" alt="Assembled storyboard">' : "");
        }
        setScriptStatus("Storyboard exported to Video tab: " + Number(data.count || 0) + " start-frame shot(s).", "Storyboard");
        if (typeof loadVideoLibrary === "function") await loadVideoLibrary();
        if (typeof updateVideoSelectionUI === "function") updateVideoSelectionUI();
        switchScriptFlowStep("videos");
        return data;
    } catch (e) {
        if (resultEl) resultEl.textContent = "Video shot export failed: " + e.message;
        addLogEntry("error", "Storyboard video shot export failed: " + e.message);
        return null;
    }
}

async function generateStoryboardCharacterSheet() {
    const btn = document.getElementById("storyboard-character-sheet-btn");
    const sheetEl = document.getElementById("storyboard-character-sheet-output");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Sheet...";
    }
    if (sheetEl) sheetEl.textContent = "Submitting character sheet to Spark...";
    try {
        const resp = await fetch("/api/local-higgsfield/generate-image", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                prompt: storyboardCharacterSheetPrompt(),
                width_and_height: "3840x2160",
                quality: "1080p",
                batch_size: 1,
                enhance_prompt: false,
                wait_for_output: false,
            }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.error || "character sheet failed");
        storyboardCharacterSheetJob = {
            job_set_id: data.job_set_id || data.id || "",
            status: data.status || "queued",
            url: storyboardJobResultUrl(data),
        };
        if (storyboardCharacterSheetJob.url) {
            const refEl = document.getElementById("storyboard-reference-image");
            if (refEl) refEl.value = storyboardCharacterSheetJob.url;
        }
        renderStoryboardCharacterSheetStatus();
    } catch (e) {
        if (sheetEl) sheetEl.textContent = "Character sheet failed: " + e.message;
        addLogEntry("error", "Storyboard character sheet failed: " + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Generate Character Sheet";
        }
    }
}

async function pollStoryboardCharacterSheet() {
    const sheetEl = document.getElementById("storyboard-character-sheet-output");
    if (!storyboardCharacterSheetJob?.job_set_id) {
        if (sheetEl) sheetEl.textContent = "No character sheet job submitted yet.";
        return null;
    }
    try {
        const resp = await fetch("/api/local-higgsfield/jobs/" + encodeURIComponent(storyboardCharacterSheetJob.job_set_id));
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.error || "status failed");
        storyboardCharacterSheetJob.status = data.status || storyboardCharacterSheetJob.status;
        storyboardCharacterSheetJob.url = storyboardJobResultUrl(data) || storyboardCharacterSheetJob.url || "";
        if (storyboardCharacterSheetJob.url) {
            const refEl = document.getElementById("storyboard-reference-image");
            if (refEl) refEl.value = storyboardCharacterSheetJob.url;
        }
        renderStoryboardCharacterSheetStatus();
        return storyboardCharacterSheetJob;
    } catch (e) {
        if (sheetEl) sheetEl.textContent = "Character sheet status failed: " + e.message;
        return null;
    }
}

function renderStoryboardCharacterSheetStatus() {
    const sheetEl = document.getElementById("storyboard-character-sheet-output");
    if (!sheetEl || !storyboardCharacterSheetJob) return;
    const status = storyboardCharacterSheetJob.status || "queued";
    const id = storyboardCharacterSheetJob.job_set_id || "";
    const img = storyboardCharacterSheetJob.url ? '<img src="' + escapeHtml(storyboardCharacterSheetJob.url) + '" alt="Storyboard character sheet">' : "";
    sheetEl.innerHTML =
        '<span>Character sheet: ' + escapeHtml(status) + (id ? ' / ' + escapeHtml(id.slice(0, 8)) : "") + '</span>' +
        img;
}

async function renderAssembleExportStoryboardPanels(boardIndex) {
    const board = getStoryboardBoard(boardIndex);
    if (!board) return;
    const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
    const expected = Array.isArray(board.panels) ? board.panels.length : 0;
    if (!expected) return;
    if (resultEl) resultEl.textContent = "Auto workflow: submitting panel renders...";
    await renderStoryboardPanels(boardIndex);
    const maxPolls = 180;
    for (let attempt = 0; attempt < maxPolls; attempt += 1) {
        const jobs = await pollStoryboardPanelJobs(boardIndex);
        const ready = jobs.filter((job) => job.url).length;
        if (resultEl) resultEl.textContent = "Auto workflow: " + ready + " / " + expected + " panel image(s) ready.";
        if (ready === expected) break;
        await storyboardSleep(10000);
    }
    const jobs = storyboardPanelJobs[String(boardIndex)] || [];
    if (jobs.filter((job) => job.url).length !== expected) {
        if (resultEl) resultEl.textContent = "Auto workflow timed out before all panel renders completed. Refresh jobs and assemble manually.";
        return;
    }
    const assembled = await assembleStoryboardPanels(boardIndex);
    if (!assembled) return;
    await exportStoryboardVideoShots(boardIndex);
}

async function renderStoryboardBoard(boardIndex) {
    const board = getStoryboardBoard(boardIndex);
    if (!board) return;
    const resultEl = document.getElementById("storyboard-render-" + Number(boardIndex));
    if (resultEl) resultEl.textContent = "Submitting storyboard board to Spark...";
    try {
        const resp = await fetch("/api/local-higgsfield/generate-image", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                prompt: board.image_prompt,
                width_and_height: board.width_and_height || "3840x2160",
                quality: "4k",
                batch_size: 1,
                enhance_prompt: false,
                wait_for_output: false,
                image_reference_url: board.reference_image_url || undefined,
            }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.error || "render failed");
        if (resultEl) {
            resultEl.innerHTML = '<span>Submitted.</span><code>' + escapeHtml(data.job_set_id || data.prompt_id || data.status || "queued") + '</code>';
        }
        if (typeof loadVideoLibrary === "function") loadVideoLibrary();
    } catch (e) {
        if (resultEl) resultEl.textContent = "Render failed: " + e.message;
        addLogEntry("error", "Storyboard render failed: " + e.message);
    }
}

async function developScriptPackage() {
    refreshScriptDomRefs();
    const brief = ($scriptBrief?.value || "").trim();
    if (!brief) {
        setScriptStatus("Enter a brief before developing the script package.", "");
        return;
    }
    const btn = document.getElementById("develop-script-btn");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Developing...";
    }
    setScriptStatus("Hermes is building treatment, script, continuity, and edit plan...", "Script");
    try {
        const resp = await fetch("/api/script/develop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                brief,
                title: scriptInputValue("script-title", ""),
                runtime_seconds: parseInt(scriptInputValue("script-runtime", "60"), 10) || 60,
                target_scenes: parseInt(scriptInputValue("script-scenes", "4"), 10) || 4,
                tone: scriptInputValue("script-tone", ""),
            }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.package) {
            throw new Error(data.detail || data.error || "script package failed");
        }
        scriptPackage = data.package;
        renderScriptPackage(scriptPackage);
        switchScriptFlowStep("script");
        setScriptStatus((data.status === "fallback" ? "Fallback script package ready" : "Script package ready") + ". Review locks, then generate coverage.", "Locked");
    } catch (e) {
        setScriptStatus("Script package failed: " + e.message, "");
        addLogEntry("error", "Script package failed: " + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Build Package";
        }
    }
}

async function uploadBrief() {
    refreshScriptDomRefs();
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
            updateScriptFlowState();
            setTimeout(() => { $scriptStatusText.textContent = "Ready"; }, 3000);
        } else {
            $scriptStatusText.textContent = "Error: " + (data.error || "Upload failed");
        }
    } catch (e) {
        $scriptStatusText.textContent = "Error: " + e.message;
    }
}

async function generateShotList() {
    refreshScriptDomRefs();
    const brief = scriptPackageShotlistBrief();
    if (!brief) {
        $scriptStatusText.textContent = "Develop a script package or enter a brief first";
        return;
    }

    const $btn = document.getElementById("generate-shots-btn");
    $btn.disabled = true;
    $btn.textContent = "Building...";
        $scriptStatusText.textContent = scriptPackage ? "Director is converting locked script into coverage..." : "Director is analyzing brief...";
        $scriptProgress.textContent = "";
        switchScriptFlowStep("script");

    // Clear existing shots
    director_shots = {};
    $shotList.innerHTML = "";
    $shotList.style.display = "none";
    $shotListPlaceholder.style.display = "block";

    try {
        const resp = await fetch("/api/director/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                brief: brief,
                length: scriptInputValue("script-runtime", ""),
                target_shots: parseInt(scriptInputValue("script-target-shots", ""), 10) || null,
            }),
        });

        if (!resp.ok) {
            const body = await resp.text();
            throw new Error("HTTP " + resp.status + (body ? ": " + body : ""));
        }

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
        $btn.textContent = "Build Shotlist";
    }
}

function handleDirectorEvent(event) {
    refreshScriptDomRefs();
    switch (event.type) {
        case "status":
            $scriptStatusText.textContent = event.text;
            break;

        case "shot":
            $shotListPlaceholder.style.display = "none";
            $shotList.style.display = "flex";
            director_shots[event.shot.id] = event.shot;
            renderShotCard(event.shot, event.index, event.total);
            $scriptProgress.textContent = event.index + "/" + event.total;
            break;

        case "done":
            $scriptStatusText.textContent = event.text;
            updateSendToSparkBtn();
            updateScriptFlowState();
            break;

        case "error":
            $scriptStatusText.textContent = "Error: " + event.text;
            break;
    }
}

function renderShotCard(shot, index, total) {
    refreshScriptDomRefs();
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
            '<span class="shot-id">' + escapeHtml(shot.shot_id || shot.id) + '</span>' +
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
    refreshScriptDomRefs();
    const checked = document.querySelectorAll(".shot-checkbox:checked");
    $sendToSparkBtn.disabled = checked.length === 0;
    $sendToSparkBtn.textContent = checked.length > 0
        ? "Send " + checked.length + " Shot(s) to Spark"
        : "Send Selected to Spark";
}

async function sendToSpark() {
    refreshScriptDomRefs();
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
    const missingMedia = [];
    shotsToSend.forEach(s => {
        if (!s || !s.id) return;
        if (videoShotsById[s.id] && evaluateShotForVideo(videoShotsById[s.id]).eligible) {
            videoSelection.add(s.id);
        } else {
            missingMedia.push(s.shot_id || s.id);
        }
    });
    updateVideoSelectionUI();
    shotsToSend.forEach(s => {
        const cell = document.querySelector('.grid-cell[data-shot-id="' + CSS.escape(s.id) + '"]');
        if (!cell) return;
        cell.classList.add("selected");
        const cb = cell.querySelector('input[type="checkbox"]');
        if (cb) cb.checked = true;
    });

    if (videoSelection.size) {
        $scriptStatusText.textContent = "Selected " + videoSelection.size + " rendered shot(s) in Video tab";
    } else {
        $scriptStatusText.textContent = "Selected script shots have no rendered images yet; render images before image-to-video.";
    }
    updateScriptFlowState();
    if (missingMedia.length && $sparkStatusText) {
        $sparkStatusText.textContent = "Skipped " + missingMedia.length + " script shot(s) without rendered images: " + missingMedia.slice(0, 4).join(", ");
    }
}

function clearShotList() {
    refreshScriptDomRefs();
    director_shots = {};
    scriptPackage = null;
    storyboardPlan = null;
    $shotList.innerHTML = "";
    $shotList.style.display = "none";
    $shotListPlaceholder.style.display = "block";
    $scriptStatusText.textContent = "Ready";
    $scriptProgress.textContent = "";
    renderScriptPackage(null);
    renderStoryboardPlan(null);
    updateSendToSparkBtn();
    switchScriptFlowStep("idea");
}

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------
let __systemLogSideRight = false;
let __lastLogSpeaker = null;
let __profileLogQueueDelayMs = 0;
let __profileLogQueueTimer = null;
function addLogEntry(type, text) {
    if (!$log) {
        console.log("[" + type + "] " + text);
        return;
    }
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

function setCampaignStatus(role, message, meta, state) {
    if (!$campaignStatusBox) return;
    const roleEl = $campaignStatusBox.querySelector(".status-role");
    const messageEl = $campaignStatusBox.querySelector(".status-message");
    const metaEl = $campaignStatusBox.querySelector(".status-meta");
    if (roleEl) roleEl.textContent = role || "Pipeline";
    if (messageEl) messageEl.textContent = message || "Ready.";
    if (metaEl) metaEl.textContent = meta || "";
    $campaignStatusBox.classList.remove("running", "error", "done");
    if (state) $campaignStatusBox.classList.add(state);
}

function campaignStatusFromEvent(event) {
    const type = event.type || "";
    const text = event.text || "";
    const shotId = event.shot_id || "";
    const elapsed = event.elapsed_ms !== undefined ? String(event.elapsed_ms) + "ms" : "";
    switch (type) {
        case "profile":
            return ["Agent", text || "Profile online", elapsed || "profile", "running"];
        case "pipeline_timing":
            return ["Timing", event.stage || "pipeline", elapsed, "running"];
        case "kimi":
            return ["Kimi", text || "Planning...", shotId || "director", "running"];
        case "kimi_raw":
            return ["Kimi", "Director plan received.", event.campaign_id || "raw", "running"];
        case "kimi_plan":
            return ["Kimi", text || ("Structured plan received (" + (event.count || 0) + " / " + (event.target_shots || event.count || 0) + " shots)"), "plan", "running"];
        case "kimi_review":
            return ["Kimi", "Coverage review score " + (event.score !== undefined ? event.score : "n/a"), event.status || "review", "running"];
        case "hermes":
            return ["Hermes", text || "Working...", shotId || "brain", "running"];
        case "compiler":
            return ["Hermes", text || "Compiling prompt...", shotId || "compiler", "running"];
        case "spark":
            return ["Spark", text || "Rendering...", event.prompt_id || event.status || "render", "running"];
        case "audit":
        case "memory":
            return ["Memory", text || "Writing result...", shotId || "audit", "running"];
        case "remediation":
            return ["Hermes", text || "Remediating...", shotId || "retry", "running"];
        case "warning":
            return ["Warning", text || "Warning", elapsed, "running"];
        case "error":
            return ["Error", text || "Pipeline error", shotId || "failed", "error"];
        case "done":
            return ["Pipeline", text || "Done.", event.shots ? String(event.shots.length) + " shots" : "done", "done"];
        default:
            return ["Pipeline", text || type || "Working...", elapsed, "running"];
    }
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
        addLogEntry("error", "Please enter a prompt");
        return;
    }
    await updatePlatformDetection();

    const length = $lengthSelect ? $lengthSelect.value : "";
    const targetShots = updateTargetCountPill();
    const klein = document.getElementById("model-klein")?.checked;
    const flux2 = document.getElementById("model-flux2")?.checked;
    const turbo = flux2 && !!document.getElementById("model-turbo")?.checked;
    const appendToCampaign = !!document.getElementById("append-campaign")?.checked;
    const selectedCampaignId = (document.getElementById("filter-campaign-id")?.value || "").trim();
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
    if (turbo) addLogEntry("system", "Turbo mode enabled for Flux2.Dev.");
    const platformMode = document.getElementById("platform-mode")?.value || "auto";
    const seriesContinuity = !!document.getElementById("series-continuity")?.checked;
    if (currentPlatformSkill && currentPlatformSkill.active) {
        addLogEntry("system", "Platform skill active: " + (currentPlatformSkill.summary || currentPlatformSkill.label || "TikTok vertical"));
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

    addLogEntry("system", "Campaign started: target " + targetShots + " image" + (targetShots === 1 ? "" : "s") + " / " + brief);
    setCampaignStatus("Pipeline", "Target: " + targetShots + " image" + (targetShots === 1 ? "" : "s"), "opening stream", "running");

    try {
        const resp = await fetch("/api/hermes/run-campaign", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                brief: brief,
                bible_path: "",
                length: length,
                workflow_ids: dedupedWorkflows,
                identity_pack: identity_pack,
                campaign_id: selectedCampaignId,
                append_to_campaign: appendToCampaign,
                platform_mode: platformMode,
                series_continuity: seriesContinuity,
                target_shots: targetShots,
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
            setCampaignStatus("Warning", "Campaign stream disconnected: " + e.message, "recovering", "error");
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
                    setCampaignStatus("Pipeline", "Recovery refresh complete.", "done", "done");
                }
            }, 5000);
        } else {
            setCampaignStatus("Pipeline", "Campaign cancelled.", "cancelled", "done");
        }
    } finally {
        $runBtn.disabled = false;
        $runBtn.textContent = "Generate Images";
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
    const statusParts = campaignStatusFromEvent(event);
    setCampaignStatus(statusParts[0], statusParts[1], statusParts[2], statusParts[3]);
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
            addLogEntry("kimi", text || ("Structured plan received (" + (event.count || 0) + " / " + (event.target_shots || event.count || 0) + " shots)"));
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

        case "platform_skill":
            currentPlatformSkill = event.platform || currentPlatformSkill;
            renderPlatformPill(currentPlatformSkill);
            addLogEntry("system", text || "Platform skill active.");
            break;

        case "spark":
            addLogEntry("spark", text);
            if (event.prompt_id) {
                addLogEntry("memory", "Shot " + shotId + " stored (prompt_id: " + event.prompt_id + ")");
            }
            if (event.status === "rendered" || event.image_url) {
                scheduleCampaignMediaRefresh();
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

        case "pipeline_timing": {
            const stage = event.stage || "stage";
            const elapsed = event.elapsed_ms !== undefined ? String(event.elapsed_ms) + "ms" : "n/a";
            const duration = event.duration_ms !== undefined ? (" · took " + String(event.duration_ms) + "ms") : "";
            addLogEntry("system", "[timing] " + stage + " at " + elapsed + duration);
            break;
        }

        case "done":
            addLogEntry("system", text);
            refreshShotViews();
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

function addScriptChatEntry(agent, text) {
    if (!$scriptChatLog) return null;
    const row = document.createElement("div");
    const kind = agent === "You" ? "user" : (agent === "Error" ? "error" : "hermes");
    row.className = "script-chat-row " + kind;

    const label = document.createElement("div");
    label.className = "script-chat-agent";
    label.textContent = agent;
    row.appendChild(label);

    const bubble = document.createElement("div");
    bubble.className = "script-chat-bubble";
    bubble.textContent = text || "";
    row.appendChild(bubble);

    $scriptChatLog.appendChild(row);
    $scriptChatLog.scrollTop = $scriptChatLog.scrollHeight;
    return bubble;
}

async function sendScriptChat() {
    refreshScriptDomRefs();
    const msg = ($scriptChatInput?.value || "").trim();
    if (!msg) return;

    $scriptChatInput.value = "";
    if ($scriptChatStatus) $scriptChatStatus.textContent = "Hermes is thinking...";
    if ($scriptChatSendBtn) $scriptChatSendBtn.disabled = true;

    addScriptChatEntry("You", msg);
    const hermesBubble = addScriptChatEntry("Hermes", "");

    try {
        const resp = await fetch("/api/hermes/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: msg,
                history: scriptChatHistory,
                session_id: scriptSessionId,
            }),
        });

        if (!resp.ok) {
            const body = await resp.text();
            throw new Error("HTTP " + resp.status + (body ? ": " + body : ""));
        }

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
                    if (data.token) {
                        fullResponse += data.token;
                        if (hermesBubble) hermesBubble.textContent = fullResponse;
                        if ($scriptChatStatus) $scriptChatStatus.textContent = "Hermes streaming...";
                        if ($scriptChatLog) $scriptChatLog.scrollTop = $scriptChatLog.scrollHeight;
                    }
                    if (data.done) {
                        scriptChatHistory.push({ role: "user", content: msg });
                        scriptChatHistory.push({ role: "assistant", content: fullResponse });
                        if (scriptChatHistory.length > 20) scriptChatHistory = scriptChatHistory.slice(-20);
                    }
                    if (data.error) {
                        throw new Error(data.error);
                    }
                } catch (e) {
                    if (e instanceof SyntaxError) continue;
                    throw e;
                }
            }
        }

        if (!fullResponse) {
            throw new Error("empty_chat_response");
        }
        if ($scriptChatStatus) $scriptChatStatus.textContent = "Ready";
    } catch (e) {
        if (hermesBubble && !hermesBubble.textContent) hermesBubble.parentElement?.remove();
        addScriptChatEntry("Error", e.message);
        if ($scriptChatStatus) $scriptChatStatus.textContent = "Error";
    } finally {
        if ($scriptChatSendBtn) $scriptChatSendBtn.disabled = false;
        $scriptChatInput?.focus();
    }
}

// ---------------------------------------------------------------------------
// Characters
// ---------------------------------------------------------------------------
let characterManagerCache = [];
let characterForgeGender = "";
let characterForgeSelectedId = "";
let currentCharacterFlowStep = "design";

function normalizeCharacters(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.characters)) return payload.characters;
    return [];
}

function characterName(char) {
    return String(char?.name || char?.id || "Unnamed").trim();
}

function characterId(char) {
    return String(char?.id || characterName(char)).trim().toLowerCase().replace(/\s+/g, "_");
}

function characterImage(char) {
    return char?.anchor_url || char?.anchor_src || "";
}

function latestCharacterGeneratedImage(char) {
    const approved = Array.isArray(char?.approved_assets) ? char.approved_assets : [];
    const generated = [...approved].reverse().find((asset) => asset?.type === "character" && asset?.url);
    if (generated?.url) return generated.url;
    const history = Array.isArray(char?.render_history) ? char.render_history : [];
    const rendered = [...history].reverse().find((entry) => entry?.type === "character" && Array.isArray(entry.image_urls) && entry.image_urls[0]);
    if (rendered?.image_urls?.[0]) return rendered.image_urls[0];
    return characterImage(char);
}

function characterReferenceImageUrlsForForge(char) {
    const urls = [];
    const addUrl = (url) => {
        const clean = String(url || "").trim();
        if (!clean || urls.includes(clean) || urls.length >= 10) return;
        if (/\.(mp4|mov|webm)(\?|$)/i.test(clean)) return;
        urls.push(clean);
    };
    addUrl(latestCharacterGeneratedImage(char));
    const approved = Array.isArray(char?.approved_assets) ? char.approved_assets : [];
    [...approved].reverse().forEach((asset) => {
        if (asset?.type === "character") addUrl(asset.url);
    });
    ["master_references", "reference_uploads", "sheet_panels"].forEach((key) => {
        const refs = Array.isArray(char?.[key]) ? char[key] : [];
        refs.forEach((ref) => addUrl(ref?.url || ref?.image_url || ref));
    });
    return urls.slice(0, 10);
}

function characterLoraReferenceImageUrls(char) {
    const urls = [];
    const addUrl = (url) => {
        const clean = String(url || "").trim();
        if (!clean || urls.includes(clean)) return;
        if (/\.(mp4|mov|webm)(\?|$)/i.test(clean)) return;
        urls.push(clean);
    };
    addUrl(latestCharacterGeneratedImage(char));
    const approved = Array.isArray(char?.approved_assets) ? char.approved_assets : [];
    [...approved].reverse().forEach((asset) => addUrl(asset?.url || asset?.image_url || asset));
    ["master_references", "reference_uploads", "sheet_panels", "character_sheets"].forEach((key) => {
        const refs = Array.isArray(char?.[key]) ? char[key] : [];
        refs.forEach((ref) => addUrl(ref?.url || ref?.image_url || ref));
    });
    return urls;
}

function selectedCharacterForForge() {
    const selectedId = characterForgeSelectedId || "";
    return characterManagerCache.find((c) => characterId(c) === selectedId)
        || shellState?.characters?.find((c) => characterId(c) === selectedId)
        || null;
}

function setCharacterStepStatus(step, text) {
    const el = document.getElementById("character-step-status-" + step);
    if (el) el.textContent = text;
}

function characterLoraVersions(char) {
    const versions = char?.training?.lora_versions;
    return Array.isArray(versions) ? versions : [];
}

function suggestedCharacterLoraTrigger(char) {
    const base = characterId(char || { id: characterForgeValue("char-forge-name") || "character" }).replace(/_+/g, "_");
    return (base || "character") + "_char";
}

function updateCharacterFlowState() {
    const selected = selectedCharacterForForge();
    const selectedName = selected ? characterName(selected) : "";
    const hasDesign = !!(characterForgeValue("char-forge-name") || characterForgeValue("char-forge-base-prompt"));
    const hasRender = selected ? !!latestCharacterGeneratedImage(selected) : false;
    const refUrls = selected ? characterLoraReferenceImageUrls(selected) : [];
    const loraVersions = selected ? characterLoraVersions(selected) : [];
    const loraReady = refUrls.length >= 10;

    setCharacterStepStatus("design", selected ? "Selected" : hasDesign ? "Draft set" : "Ready");
    setCharacterStepStatus("render", hasRender ? "Rendered" : selected ? "Ready" : "Waiting");
    setCharacterStepStatus("references", refUrls.length ? refUrls.length + " image" + (refUrls.length === 1 ? "" : "s") : "Waiting");
    setCharacterStepStatus("lora", loraVersions.length ? "Pack ready" : loraReady ? "Ready" : selected ? "Need refs" : "Not ready");

    document.querySelectorAll(".script-flow-step[data-character-step]").forEach((el) => {
        const step = el.dataset.characterStep;
        el.classList.toggle("active", step === currentCharacterFlowStep);
        el.classList.toggle("complete",
            (step === "design" && (hasDesign || selected)) ||
            (step === "render" && hasRender) ||
            (step === "references" && refUrls.length > 0) ||
            (step === "lora" && loraVersions.length > 0)
        );
    });

    const selectedEl = document.getElementById("character-lora-selected");
    const refsEl = document.getElementById("character-lora-ref-count");
    const readyEl = document.getElementById("character-lora-readiness");
    const triggerEl = document.getElementById("character-lora-trigger");
    const prepareBtn = document.getElementById("character-lora-prepare-btn");
    const loraStatus = document.getElementById("character-lora-status");
    if (selectedEl) selectedEl.textContent = selectedName || "No character selected";
    if (refsEl) refsEl.textContent = refUrls.length + " usable image" + (refUrls.length === 1 ? "" : "s");
    if (readyEl) {
        readyEl.textContent = !selected
            ? "Needs character"
            : loraReady
                ? "Training-ready pack"
                : "Can generate, add " + Math.max(0, 10 - refUrls.length) + " more for stronger training";
    }
    if (triggerEl && selected && !triggerEl.value.trim()) {
        triggerEl.placeholder = suggestedCharacterLoraTrigger(selected);
    }
    if (prepareBtn) prepareBtn.disabled = !(selected && refUrls.length);
    if (loraStatus) {
        const current = loraStatus.textContent || "";
        const canRefresh = !current || /^(Select a character|Ready to generate|Can generate|No usable|Add at least)/.test(current);
        if (canRefresh) {
            loraStatus.textContent = !selected
                ? "Select a character with approved/reference images before generating a LoRA pack."
                : refUrls.length
                    ? "Ready to generate a LoRA dataset pack for " + selectedName + "."
                    : "No usable image references found for " + selectedName + ".";
        }
    }
}

function switchCharacterFlowStep(step) {
    currentCharacterFlowStep = step || "design";
    document.querySelectorAll("[data-character-step-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.characterStepPanel === currentCharacterFlowStep);
    });
    updateCharacterFlowState();
}

function syncCharacterForgeSelectionUi() {
    const selected = selectedCharacterForForge();
    const selectedId = selected ? characterId(selected) : "";
    const refUrls = selected ? characterReferenceImageUrlsForForge(selected) : [];
    document.querySelectorAll(".character-card-live").forEach((card) => {
        card.classList.toggle("selected", !!selectedId && card.dataset.characterId === selectedId);
    });
    const sheetBtn = document.getElementById("char-forge-sheet-btn");
    const variationBtn = document.getElementById("char-forge-variation-btn");
    const enabled = !!(selectedId && refUrls.length);
    if (sheetBtn) {
        sheetBtn.disabled = !enabled;
        sheetBtn.title = enabled ? "Uses the selected character images as sheet references." : "Select one character with a generated image first.";
    }
    if (variationBtn) {
        variationBtn.disabled = !enabled;
        variationBtn.title = enabled ? "Uses the selected character images as variation references." : "Select one character with a generated image first.";
    }
    updateCharacterFlowState();
}

function characterDnaText(char) {
    const dna = char?.dna && typeof char.dna === "object" ? char.dna : {};
    return JSON.stringify(dna, null, 2);
}

function characterReferences(char) {
    const refs = [];
    if (Array.isArray(char?.master_references)) refs.push(...char.master_references.map((r) => ({ ...r, master: true })));
    if (Array.isArray(char?.reference_uploads)) refs.push(...char.reference_uploads.map((r) => ({ ...r, master: false })));
    return refs.filter((r) => r && r.url);
}

function characterStatus(char) {
    return String(char?.status || "draft").replace(/_/g, " ");
}

function characterUsedInShots(char) {
    return Number(char?.analytics?.used_in_shots || char?.used_in_shots || 0);
}

function characterLastUsed(char) {
    return String(char?.analytics?.last_used_at || char?.last_used_at || "never");
}

function characterRenderHistoryCount(char) {
    return Array.isArray(char?.render_history) ? char.render_history.length : 0;
}

async function loadCharacters() {
    const charList = document.getElementById("char-list");
    if (!charList) return;
    try {
        const resp = await fetch("/api/characters");
        const data = await resp.json();
        const chars = normalizeCharacters(data);

        if (!chars.length) {
            charList.innerHTML = '<div style="color:#666; font-size:12px;">No characters yet</div>';
            return;
        }

        charList.innerHTML = chars.map(c => {
            const img = characterImage(c);
            return (
            '<div class="char-card">' +
            (img ? '<img src="' + escapeHtml(img) + '" alt="' + escapeHtml(characterName(c)) + '">' : '<div class="char-card-fallback"></div>') +
            '<span class="char-name">' + escapeHtml(characterName(c)) + "</span>" +
            "</div>"
            );
        }).join("");
    } catch (e) {
        charList.innerHTML = '<div style="color:#666; font-size:12px;">Failed to load</div>';
    }
}

async function loadCharacterManager() {
    const grid = document.getElementById("character-manager-content");
    const status = document.getElementById("character-manager-status");
    if (!grid) return;
    grid.innerHTML = '<div class="character-manager-status">Loading characters...</div>';
    try {
        const resp = await fetch("/api/characters");
        const payload = await resp.json();
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const chars = normalizeCharacters(payload);
        characterManagerCache = chars;
        if (status) status.textContent = String(chars.length) + " character" + (chars.length === 1 ? "" : "s");
        if (!chars.length) {
            grid.innerHTML = '<div class="character-manager-status">No characters yet.</div>';
            syncCharacterForgeSelectionUi();
            return;
        }
        grid.innerHTML = chars.map((char) => {
            const id = characterId(char);
            const name = characterName(char);
            const img = characterImage(char);
            const dna = char?.dna && typeof char.dna === "object" ? Object.keys(char.dna).length : 0;
            const refs = characterReferences(char).filter((r) => r.master).length;
            const avatar = img
                ? '<img class="character-zoomable" src="' + escapeHtml(img) + '" alt="' + escapeHtml(name) + '" loading="lazy" data-zoom-src="' + escapeHtml(img) + '" data-zoom-title="' + escapeHtml(name) + '" data-zoom-prompt="' + escapeHtml(char?.anchor_prompt || char?.role || "") + '">'
                : '<div class="character-avatar-fallback">' + escapeHtml(name.slice(0, 1).toUpperCase()) + '</div>';
            return (
                '<article class="character-card-live' + (id === characterForgeSelectedId ? " selected" : "") + '" data-character-id="' + escapeHtml(id) + '">' +
                    avatar +
                    '<div>' +
                        '<h3>' + escapeHtml(name) + '</h3>' +
                        '<div class="role">' + escapeHtml(char.role || char.description || "Character") + '</div>' +
                        '<div class="meta"><span>ID ' + escapeHtml(id) + '</span><span>' + escapeHtml(characterStatus(char)) + '</span><span>DNA ' + dna + '</span><span>Master ' + refs + '</span><button class="btn btn-secondary" type="button" onclick="selectCharacterForForge(\'' + escapeHtml(id) + '\')">Use</button><a href="/api/characters/' + encodeURIComponent(id) + '/export-package" target="_blank" rel="noreferrer">Export</a></div>' +
                    '</div>' +
                '</article>'
            );
        }).join("");
        syncCharacterForgeSelectionUi();
    } catch (e) {
        if (status) status.textContent = "Character load failed";
        grid.innerHTML = '<div class="character-manager-status">Character API unavailable: ' + escapeHtml(e?.message || e) + '</div>';
    }
}

function toggleTemplateCharacterRoster() {
    const wrap = document.getElementById("character-roster-wrap");
    const toggle = document.getElementById("character-roster-toggle");
    if (!wrap) return;
    const collapsed = !wrap.classList.contains("roster-collapsed");
    wrap.classList.toggle("roster-collapsed", collapsed);
    if (toggle) {
        toggle.textContent = collapsed ? "Show" : "Hide";
        toggle.setAttribute("aria-expanded", String(!collapsed));
    }
}

async function createCharacterFromManager(event) {
    if (event && event.preventDefault) event.preventDefault();
    const status = document.getElementById("character-manager-status");
    const form = event?.currentTarget?.tagName === "FORM" ? event.currentTarget : null;
    const btn = event?.currentTarget?.tagName === "BUTTON"
        ? event.currentTarget
        : (event?.currentTarget?.querySelector ? event.currentTarget.querySelector('button[type="submit"]') : null);
    const name = (document.getElementById("char-forge-name")?.value || form?.querySelector('[name="name"]')?.value || "").trim();
    const description = (document.getElementById("char-forge-role")?.value || form?.querySelector('[name="description"]')?.value || "").trim();
    const anchorPrompt = (document.getElementById("char-forge-base-prompt")?.value || form?.querySelector('[name="anchor_prompt"]')?.value || "").trim();
    if (!name) {
        if (status) status.textContent = "Name is required.";
        return;
    }
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Saving metadata...";
    try {
        const data = new FormData();
        data.append("name", name);
        data.append("description", description);
        data.append("anchor_prompt", anchorPrompt);
        const resp = await fetch("/api/characters", { method: "POST", body: data });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        if (status) status.textContent = payload.status === "updated" ? "Character metadata updated." : "Character metadata saved.";
        await loadCharacters();
        await loadCharacterManager();
        switchCharacterFlowStep("render");
    } catch (e) {
        if (status) status.textContent = "Save failed: " + (e?.message || e);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function characterForgeValue(id) {
    return (document.getElementById(id)?.value || "").trim();
}

const CHARACTER_NO_TEXT_PROMPT_RULE = "no text, no captions, no labels, no typography, no letters, no numbers, no logos, no watermark";

function withCharacterNoTextRule(prompt) {
    const clean = String(prompt || "").trim().replace(/[,\s]+$/g, "");
    if (!clean) return CHARACTER_NO_TEXT_PROMPT_RULE;
    const lower = clean.toLowerCase();
    const required = ["no text", "no captions", "no labels", "no typography", "no letters", "no numbers", "no logos", "no watermark"];
    if (required.every((term) => lower.includes(term))) return clean;
    return clean + ", " + CHARACTER_NO_TEXT_PROMPT_RULE;
}

function getCharacterForgeSeed() {
    const raw = characterForgeValue("char-forge-seed");
    if (!raw) return null;
    const parsed = parseInt(raw, 10);
    return Number.isFinite(parsed) ? parsed : null;
}

function pickRandom(list) {
    return list[Math.floor(Math.random() * list.length)];
}

function pickRandomSet(list, count) {
    const pool = [...list];
    const picked = [];
    while (pool.length && picked.length < count) {
        const index = Math.floor(Math.random() * pool.length);
        picked.push(pool.splice(index, 1)[0]);
    }
    return picked;
}

function selectedCharacterForgeGender() {
    return characterForgeGender === "male" || characterForgeGender === "female" ? characterForgeGender : "";
}

function characterForgeGenderLabel() {
    const gender = selectedCharacterForgeGender();
    return gender ? gender + " person" : "";
}

function characterForgeNamePool(neutralNames, maleNames, femaleNames) {
    const gender = selectedCharacterForgeGender();
    if (gender === "male") return maleNames;
    if (gender === "female") return femaleNames;
    return neutralNames;
}

function stripCharacterNoTextRule(prompt) {
    let clean = String(prompt || "");
    for (const term of CHARACTER_NO_TEXT_PROMPT_RULE.split(", ")) {
        clean = clean.replace(new RegExp(",?\\s*" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), "");
    }
    return clean.replace(/\s*,\s*,/g, ", ").replace(/^[,\s]+|[,\s]+$/g, "");
}

function applyCharacterForgeGenderToPrompt(prompt, gender) {
    if (!prompt || !gender) return prompt || "";
    const required = CHARACTER_NO_TEXT_PROMPT_RULE.split(", ");
    const hadNoTextRule = required.every((term) => String(prompt).toLowerCase().includes(term));
    let clean = hadNoTextRule ? stripCharacterNoTextRule(prompt) : String(prompt || "").trim();
    clean = clean
        .replace(/\b(male|female)\s+(person|character)\b,?\s*/gi, "")
        .replace(/\s*,\s*,/g, ", ")
        .replace(/^[,\s]+|[,\s]+$/g, "");
    const withGender = [clean, gender + " person"].filter(Boolean).join(", ");
    return hadNoTextRule ? withCharacterNoTextRule(withGender) : withGender;
}

function syncCharacterForgeGenderButtons() {
    const gender = selectedCharacterForgeGender();
    for (const option of ["male", "female"]) {
        const btn = document.getElementById("char-forge-gender-" + option);
        if (!btn) continue;
        const active = gender === option;
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
    }
}

function setCharacterForgeGender(gender) {
    characterForgeGender = gender === "male" || gender === "female" ? gender : "";
    syncCharacterForgeGenderButtons();
    const baseEl = document.getElementById("char-forge-base-prompt");
    if (baseEl?.value) {
        baseEl.value = applyCharacterForgeGenderToPrompt(baseEl.value, selectedCharacterForgeGender());
        composeCharacterPrompts();
    }
    const status = document.getElementById("character-manager-status");
    if (status) {
        const label = selectedCharacterForgeGender() || "no gender";
        status.textContent = "Character gender set to " + label + ". From Role and Regular Person will use it.";
    }
}

function roleHasAny(roleText, terms) {
    return terms.some((term) => roleText.includes(term));
}

function inferCharacterRoleContext(role) {
    const text = String(role || "").toLowerCase();
    const context = {
        ages: ["late 20s", "early 30s", "mid 30s", "early 40s"],
        faces: [
            "attractive real face, balanced features, realistic skin texture, expressive eyes",
            "cinematic casting-quality face, natural facial harmony, believable asymmetry, relaxed confidence",
            "polished but realistic face, clear skin texture, strong screen presence, approachable expression",
        ],
        hair: [
            "healthy well-groomed hair with natural styling",
            "clean contemporary haircut, polished but believable styling",
            "natural hair with subtle professional styling",
        ],
        builds: [
            "fit average build, natural posture",
            "healthy build, relaxed shoulders, believable body proportions",
            "camera-ready but realistic physique, natural stance",
        ],
        wardrobe: [
            "role-appropriate contemporary clothing, flattering fit, no costume exaggeration",
            "polished everyday outfit suited to the role, believable shoes, restrained accessories",
            "modern practical outfit with subtle role-specific details, natural fabrics",
        ],
        locations: [
            "neutral studio background",
            "realistic workplace suited to " + role,
            "sidewalk in natural daylight",
            "simple indoor room with practical lighting",
        ],
        clothes: [
            "main role-appropriate outfit",
            "casual everyday outfit",
            "work outfit variation",
            "simple jacket layer",
        ],
        notes: [
            "attractive but realistic, cinematic casting quality, not plastic, not over-retouched",
        ],
    };

    if (roleHasAny(text, ["instagram", "influencer", "fitness model", "fitness", "model", "athlete", "trainer", "yoga", "pilates", "bodybuilder"])) {
        return {
            ...context,
            ages: ["early 20s", "mid 20s", "late 20s", "early 30s"],
            faces: [
                "highly attractive fitness-model face, strong facial harmony, expressive eyes, realistic skin texture",
                "striking social-media creator face, polished natural beauty, confident relaxed expression",
                "cinematic athletic lead face, defined cheekbones, healthy skin texture, no beauty-filter plastic skin",
            ],
            hair: [
                "healthy camera-ready hair, clean modern styling",
                "sweat-ready styled hair, natural volume, polished but believable",
                "well-groomed contemporary hair, fitness lifestyle styling",
            ],
            builds: [
                "lean athletic build, toned arms and shoulders, realistic fitness proportions",
                "fit model physique, defined core, natural posture, believable anatomy",
                "athletic lifestyle build, strong legs, relaxed confident stance",
            ],
            wardrobe: [
                "premium fitted activewear, clean sneakers, minimal jewelry, modern fitness styling",
                "sleek gym outfit, fitted training top, performance leggings or shorts, realistic fabric texture",
                "athleisure streetwear, cropped jacket or fitted hoodie, clean contemporary styling",
            ],
            locations: [
                "modern gym with soft daylight",
                "minimal fitness studio",
                "urban rooftop at golden hour",
                "bright apartment mirror workout corner without visible text",
            ],
            clothes: [
                "premium gym activewear",
                "athleisure street outfit",
                "minimal studio workout set",
                "casual post-workout jacket layer",
            ],
            notes: [
                "highly attractive fitness creator, modern social media casting, polished realistic skin, confident camera presence",
                "fit adult appearance, no underage styling, no exaggerated body proportions, no plastic beauty filter",
            ],
        };
    }

    if (roleHasAny(text, ["student", "intern", "graduate", "college", "university"])) {
        return {
            ...context,
            ages: ["early 20s", "mid 20s", "late 20s"],
            wardrobe: [
                "campus casual outfit, simple layers, backpack or laptop bag, believable shoes",
                "plain hoodie or overshirt, jeans, clean sneakers, understated accessories",
                "casual contemporary student outfit, practical layers, no school uniform",
            ],
            locations: ["campus walkway", "library study room", "coffee shop table", "small apartment desk"],
            clothes: ["campus casual outfit", "study-day hoodie and jeans", "simple jacket layer", "clean everyday outfit"],
            notes: ["adult college-age appearance, attractive but realistic, natural skin texture"],
        };
    }

    if (roleHasAny(text, ["ceo", "founder", "executive", "lawyer", "attorney", "banker", "consultant", "agent"])) {
        return {
            ...context,
            ages: ["early 30s", "mid 30s", "early 40s", "late 40s"],
            builds: ["fit professional build, upright posture", "healthy executive build, confident stance", "lean professional build, composed posture"],
            wardrobe: [
                "sharp tailored business outfit, premium fabric, understated watch, realistic fit",
                "modern executive suit or blazer, clean shirt, polished shoes",
                "elevated professional wardrobe, restrained colors, quiet luxury details",
            ],
            locations: ["modern office", "conference room", "city sidewalk", "hotel lobby"],
            clothes: ["tailored business outfit", "smart casual blazer look", "formal meeting outfit", "travel-day professional outfit"],
            notes: ["attractive professional presence, composed expression, premium but realistic styling"],
        };
    }

    if (roleHasAny(text, ["nurse", "doctor", "surgeon", "medic", "therapist", "paramedic", "veterinarian"])) {
        return {
            ...context,
            ages: ["mid 20s", "late 20s", "early 30s", "mid 30s", "early 40s"],
            wardrobe: [
                "clean medical scrubs, practical shoes, minimal accessories",
                "white coat over simple clinical outfit, realistic hospital styling",
                "practical healthcare workwear, badge-free, no readable text",
            ],
            locations: ["hospital corridor", "clinic exam room", "medical office", "quiet break room"],
            clothes: ["medical scrubs", "white coat clinical outfit", "simple off-duty outfit", "practical jacket layer"],
            notes: ["competent attractive healthcare worker, natural fatigue detail, realistic skin texture"],
        };
    }

    if (roleHasAny(text, ["retired", "grandparent", "elder", "senior", "old man", "old woman", "grandmother", "grandfather"])) {
        return {
            ...context,
            ages: ["early 60s", "late 60s", "early 70s"],
            faces: [
                "attractive older face, warm expression, realistic wrinkles, dignified screen presence",
                "mature face with strong character, natural skin texture, kind expressive eyes",
                "handsome older features, believable age detail, composed expression",
            ],
            hair: ["well-kept gray hair", "silver hair with natural styling", "neatly groomed mature hairstyle"],
            builds: ["healthy older build, natural posture", "average mature build, relaxed stance", "fit older build, believable proportions"],
            wardrobe: [
                "comfortable polished everyday clothing, well-kept shoes, subtle personal style",
                "simple mature wardrobe, soft layers, realistic fabrics",
                "neat casual outfit, cardigan or jacket layer, understated colors",
            ],
            locations: ["quiet home interior", "neighborhood sidewalk", "small garden", "local cafe"],
            clothes: ["comfortable everyday outfit", "neat casual jacket layer", "simple home outfit", "polished daywear"],
            notes: ["attractive mature person, dignified age detail, not de-aged, not plastic"],
        };
    }

    return context;
}

async function generateCharacterFromRoleWithKimi(role, status) {
    if (status) {
        status.classList.remove("kimi-success", "kimi-fallback");
        status.classList.add("kimi-generating");
        status.textContent = "Asking Kimi to cast and prompt this role...";
    }
    const resp = await fetch("/api/characters/role-prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            role,
            name: characterForgeValue("char-forge-name"),
            gender: selectedCharacterForgeGender(),
        }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.status !== "ok") {
        throw new Error(data.detail || data.error || "Kimi prompt generation failed");
    }

    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
    };
    setValue("char-forge-name", data.name || characterForgeValue("char-forge-name") || "Generated Character");
    setValue("char-forge-role", data.role || role);
    setValue("char-forge-base-prompt", withCharacterNoTextRule(data.base_prompt || ""));
    setValue("char-forge-locations", Array.isArray(data.locations) ? data.locations.join(", ") : String(data.locations || ""));
    setValue("char-forge-clothes", Array.isArray(data.clothes) ? data.clothes.join(", ") : String(data.clothes || ""));
    setValue("char-forge-angles", Array.isArray(data.angles) ? data.angles.join(", ") : String(data.angles || ""));
    setValue("char-forge-seed", String(Math.floor(100000 + Math.random() * 899999)));
    const workflow = document.getElementById("char-forge-workflow");
    if (workflow) workflow.value = "01_flux2_text_to_image";

    const sheetEl = document.getElementById("char-forge-sheet-prompt");
    const variationEl = document.getElementById("char-forge-variation-prompt");
    composeCharacterPrompts();
    if (variationEl && data.variation_prompt) variationEl.value = withCharacterNoTextRule(data.variation_prompt);
    if (status) {
        status.classList.remove("kimi-generating", "kimi-fallback");
        status.classList.add("kimi-success");
        status.textContent = "Kimi generated a role-aware character prompt. Review before sending to Spark.";
    }
    return true;
}

function randomizeCharacterForge() {
    const neutralNames = ["Sable", "Mira", "Cassian", "Nyra", "Orin", "Vale", "Ilya", "Riven", "Mara", "Soren", "Kael", "Vesper"];
    const maleNames = ["Cassian", "Orin", "Soren", "Kael", "Darian", "Lucan", "Ronan", "Malik", "Tomas", "Viktor", "Elias", "Dante"];
    const femaleNames = ["Mira", "Nyra", "Mara", "Vesper", "Selene", "Lyra", "Amara", "Nadia", "Iris", "Elara", "Rhea", "Sabine"];
    const surnames = ["Cross", "Vale", "Nyx", "Ashford", "Kade", "Sol", "Vance", "Morrow", "Reyes", "Ishaan", "Drift", "Noor"];
    const archetypes = [
        "exiled starship pilot",
        "desert relic hunter",
        "underground cybernetic medic",
        "luxury espionage courier",
        "retired arena champion",
        "haunted royal cartographer",
        "orbital salvage engineer",
        "monastic data thief",
        "runaway corporate heir",
        "wilderness signal tracker",
    ];
    const faces = [
        "angular cheekbones, calm severe expression, faint scar through one eyebrow",
        "soft round face, watchful eyes, asymmetrical smile, subtle freckles",
        "long narrow face, tired eyes, broken nose, controlled intensity",
        "heart-shaped face, sharp gaze, small beauty mark below the left eye",
        "square jaw, close-cropped beard shadow, guarded expression",
    ];
    const hair = [
        "silver cropped hair with a shaved left side",
        "black shoulder-length curls tied back with copper thread",
        "auburn bob with blunt bangs and wind-torn ends",
        "white braided topknot with loose temple strands",
        "dark buzz cut with a narrow platinum streak",
    ];
    const wardrobe = [
        "weathered charcoal flight jacket, graphite undersuit, brass hardware",
        "sand-colored expedition coat, wrapped scarf, patched utility trousers",
        "tailored black field suit, matte ceramic buckles, hidden blade holster",
        "deep green medic smock, modular belt, translucent diagnostic gloves",
        "ivory ceremonial coat over armored streetwear, red cord fasteners",
    ];
    const signatures = [
        "glowing amber tattoo on the left forearm",
        "one mechanical hand with exposed silver tendons",
        "small glass data vial worn as a necklace",
        "blue enamel eye patch with engraved constellations",
        "pair of antique pilot goggles hanging at the collar",
        "thin gold facial circuit tracing the right cheekbone",
    ];
    const palettes = [
        "charcoal, oxidized copper, pale amber",
        "bone white, desert red, faded teal",
        "black chrome, electric blue, signal orange",
        "forest green, surgical white, warm brass",
        "midnight violet, silver, muted rose",
    ];
    const cameraStyles = [
        "cinematic production still, 50mm lens, shallow depth of field",
        "premium character concept art, clean silhouette, high material detail",
        "editorial portrait lighting, natural skin texture, grounded realism",
        "high-end game character key art, crisp costume design, strong rim light",
        "film wardrobe test, neutral framing, production-ready anatomy",
    ];
    const locationBanks = [
        ["rain-soaked neon alley", "abandoned orbital dock", "quiet hotel corridor", "underground noodle bar"],
        ["desert highway", "sun-bleached ruins", "wind-carved canyon", "dusty roadside shrine"],
        ["sterile med bay", "crowded night market", "subway platform", "rooftop greenhouse"],
        ["arctic research station", "ice cave", "dim command bunker", "snowfield at blue hour"],
        ["royal archive", "candlelit chapel", "marble train station", "overgrown palace garden"],
    ];
    const clothesBanks = [
        ["hero outfit", "travel coat", "formal dinner variant", "battle-damaged layer"],
        ["field jacket", "rain shell", "sleeveless utility vest", "ceremonial uniform"],
        ["streetwear disguise", "medical workwear", "armored undersuit", "luxury tailored suit"],
        ["cold-weather parka", "desert wrap", "pilot harness", "sleep-deprived off-duty clothes"],
    ];
    const angleBanks = [
        ["front", "3/4 left", "3/4 right", "profile", "rear", "full body", "portrait close-up", "hands detail"],
        ["hero portrait", "waist-up", "walking full body", "over-shoulder", "low angle", "side profile", "back view"],
        ["neutral T-pose", "relaxed stance", "turnaround front", "turnaround side", "turnaround rear", "face close-up", "boots detail"],
    ];

    const genderLabel = characterForgeGenderLabel();
    const name = pickRandom(characterForgeNamePool(neutralNames, maleNames, femaleNames)) + " " + pickRandom(surnames);
    const role = pickRandom(archetypes);
    const face = pickRandom(faces);
    const hairDesc = pickRandom(hair);
    const wardrobeDesc = pickRandom(wardrobe);
    const signature = pickRandom(signatures);
    const palette = pickRandom(palettes);
    const cameraStyle = pickRandom(cameraStyles);
    const locations = pickRandom(locationBanks);
    const clothes = pickRandom(clothesBanks);
    const angles = pickRandom(angleBanks);
    const seed = Math.floor(100000 + Math.random() * 899999);

    const basePrompt = [
        "Portrait of " + name,
        genderLabel,
        role,
        face,
        hairDesc,
        wardrobeDesc,
        signature,
        "fixed color palette: " + palette,
        "consistent face identity, stable anatomy, clear silhouette",
        cameraStyle,
        "no duplicate person",
    ].filter(Boolean).join(", ");

    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
    };
    setValue("char-forge-name", name);
    setValue("char-forge-role", role);
    setValue("char-forge-base-prompt", withCharacterNoTextRule(basePrompt));
    setValue("char-forge-locations", pickRandomSet(locations, Math.min(4, locations.length)).join(", "));
    setValue("char-forge-clothes", pickRandomSet(clothes, Math.min(4, clothes.length)).join(", "));
    setValue("char-forge-angles", pickRandomSet(angles, Math.min(8, angles.length)).join(", "));
    setValue("char-forge-seed", String(seed));

    const workflow = document.getElementById("char-forge-workflow");
    if (workflow) {
        workflow.value = Math.random() > 0.35 ? "01_flux2_text_to_image" : "08_flux2_klein_9b_text_to_image";
    }

    composeCharacterPrompts();
    const status = document.getElementById("character-manager-status");
    if (status) status.textContent = "Random character generated locally. Review the prompts before sending to Spark.";
}

function groundCharacterForge() {
    const neutralNames = ["Alex", "Jordan", "Morgan", "Taylor", "Casey", "Riley", "Jamie", "Avery", "Sam", "Cameron", "Drew", "Robin"];
    const maleNames = ["Michael", "David", "Daniel", "James", "Thomas", "Owen", "Marcus", "Ethan", "Noah", "Caleb", "Andre", "Leo"];
    const femaleNames = ["Sarah", "Maya", "Elena", "Priya", "Nina", "Leah", "Sofia", "Ava", "Clara", "Naomi", "Grace", "Isabel"];
    const surnames = ["Miller", "Parker", "Reed", "Bennett", "Coleman", "Hayes", "Sullivan", "Brooks", "Foster", "Ramirez", "Nguyen", "Patel"];
    const roles = [
        "regular person",
        "office worker",
        "neighbor",
        "teacher",
        "barista",
        "parent",
        "delivery driver",
        "nurse",
        "small business owner",
        "college student",
        "retired accountant",
        "grocery store manager",
    ];
    const ages = ["late 20s", "early 30s", "mid 30s", "early 40s", "late 40s", "early 50s", "mid 60s"];
    const faces = [
        "natural face, mild under-eye texture, ordinary facial proportions, relaxed expression",
        "oval face, subtle smile lines, realistic skin texture, neutral expression",
        "round face, soft jawline, slight forehead lines, calm everyday expression",
        "long face, straight nose, natural asymmetry, unposed expression",
        "square face, faint smile lines, realistic pores, casual expression",
    ];
    const hair = [
        "short brown hair with a practical side part",
        "shoulder-length dark hair worn loose",
        "short graying hair, neatly trimmed",
        "curly black hair pulled back casually",
        "medium blonde hair, simple natural styling",
        "closely cropped hair, natural hairline",
    ];
    const builds = [
        "average build, normal posture",
        "slim average build, casual posture",
        "stocky average build, relaxed shoulders",
        "tall average build, natural stance",
        "short average build, unposed stance",
    ];
    const wardrobe = [
        "plain navy sweater, blue jeans, simple sneakers",
        "gray t-shirt, casual jacket, dark jeans",
        "white button-down shirt, chinos, ordinary leather shoes",
        "black hoodie, straight-leg jeans, worn sneakers",
        "simple cardigan, cotton shirt, casual trousers",
        "work polo shirt, khaki pants, practical shoes",
    ];
    const locations = [
        "apartment kitchen",
        "office hallway",
        "sidewalk in daylight",
        "grocery store aisle",
        "parking lot",
        "living room",
        "coffee shop counter",
        "suburban street",
    ];
    const clothes = [
        "plain t-shirt and jeans",
        "casual jacket and jeans",
        "office shirt and chinos",
        "sweater and casual trousers",
        "hoodie and straight-leg jeans",
        "simple work polo and khaki pants",
    ];
    const genderLabel = characterForgeGenderLabel();
    const name = pickRandom(characterForgeNamePool(neutralNames, maleNames, femaleNames)) + " " + pickRandom(surnames);
    const role = pickRandom(roles);
    const basePrompt = [
        "Photorealistic portrait of " + name,
        pickRandom(ages),
        genderLabel,
        role,
        pickRandom(faces),
        pickRandom(hair),
        pickRandom(builds),
        pickRandom(wardrobe),
        "normal everyday person, documentary realism, realistic skin texture, natural color grading",
        "soft daylight, 50mm lens, casual unposed posture",
        "no fantasy elements, no sci-fi elements, no costume, no armor, no glowing tattoos, no exaggerated features, no glamour retouching",
        "no duplicate person",
    ].filter(Boolean).join(", ");

    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
    };
    setValue("char-forge-name", name);
    setValue("char-forge-role", role);
    setValue("char-forge-base-prompt", withCharacterNoTextRule(basePrompt));
    setValue("char-forge-locations", pickRandomSet(locations, 4).join(", "));
    setValue("char-forge-clothes", pickRandomSet(clothes, 4).join(", "));
    setValue("char-forge-angles", "front, 3/4 left, 3/4 right, side profile, rear, full body, portrait close-up, hands detail");
    setValue("char-forge-seed", String(Math.floor(100000 + Math.random() * 899999)));

    const workflow = document.getElementById("char-forge-workflow");
    if (workflow) workflow.value = "01_flux2_text_to_image";

    composeCharacterPrompts();
    const status = document.getElementById("character-manager-status");
    if (status) status.textContent = "Grounded regular-person character generated locally. Review before sending to Spark.";
}

async function generateCharacterFromRoleForge() {
    const status = document.getElementById("character-manager-status");
    const role = characterForgeValue("char-forge-role");
    if (!role) {
        if (status) status.textContent = "Enter a Role / Archetype first.";
        return;
    }
    let kimiError = "";
    try {
        if (await generateCharacterFromRoleWithKimi(role, status)) return;
    } catch (e) {
        kimiError = e?.message || String(e || "");
        console.warn("Kimi character prompt unavailable; using local role logic.", e);
        if (status) {
            status.classList.remove("kimi-generating", "kimi-success");
            status.classList.add("kimi-fallback");
            status.textContent = "Kimi unavailable; using local role-aware generator...";
        }
    }
    const neutralNames = ["Alex", "Jordan", "Maya", "Noah", "Elena", "Marcus", "Priya", "Owen", "Nina", "Daniel", "Leah", "Victor"];
    const maleNames = ["Michael", "David", "Daniel", "Noah", "Marcus", "Owen", "Victor", "Ethan", "Caleb", "Andre", "Leo", "Thomas"];
    const femaleNames = ["Maya", "Elena", "Priya", "Nina", "Leah", "Sarah", "Sofia", "Ava", "Clara", "Naomi", "Grace", "Isabel"];
    const surnames = ["Reed", "Morgan", "Hayes", "Kline", "Santos", "Bennett", "Patel", "Brooks", "Wright", "Kim", "Foster", "Morales"];
    const context = inferCharacterRoleContext(role);
    const genderLabel = characterForgeGenderLabel();
    const name = characterForgeValue("char-forge-name") || (pickRandom(characterForgeNamePool(neutralNames, maleNames, femaleNames)) + " " + pickRandom(surnames));
    const basePrompt = [
        "Photorealistic character portrait of " + name,
        pickRandom(context.ages),
        genderLabel,
        "role / archetype: " + role,
        pickRandom(context.faces),
        pickRandom(context.hair),
        pickRandom(context.builds),
        pickRandom(context.wardrobe),
        pickRandom(context.notes),
        "believable real person, grounded documentary realism, realistic skin texture, natural color grading",
        "soft daylight, 50mm lens, casual unposed posture, clear face identity, stable anatomy",
        "avoid over-designed costume, avoid fantasy unless the role explicitly requires it, avoid sci-fi unless the role explicitly requires it, no exaggerated features, no glamour retouching",
        "no duplicate person",
    ].filter(Boolean).join(", ");

    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
    };
    setValue("char-forge-name", name);
    setValue("char-forge-base-prompt", withCharacterNoTextRule(basePrompt));
    setValue("char-forge-locations", context.locations.join(", "));
    setValue("char-forge-clothes", context.clothes.join(", "));
    setValue("char-forge-angles", "front, 3/4 left, 3/4 right, side profile, rear, full body, portrait close-up, hands detail");
    setValue("char-forge-seed", String(Math.floor(100000 + Math.random() * 899999)));
    const workflow = document.getElementById("char-forge-workflow");
    if (workflow) workflow.value = "01_flux2_text_to_image";

    composeCharacterPrompts();
    if (status) {
        status.classList.remove("kimi-generating", "kimi-success");
        if (kimiError) status.classList.add("kimi-fallback");
        else status.classList.remove("kimi-fallback");
        status.textContent = kimiError
            ? "Kimi unavailable; generated from role locally. Review before sending to Spark."
            : "Character generated from role locally. Review before sending to Spark.";
    }
}

function composeCharacterPrompts() {
    const name = characterForgeValue("char-forge-name") || "the character";
    const role = characterForgeValue("char-forge-role");
    const base = characterForgeValue("char-forge-base-prompt") || [
        name,
        role,
        "consistent face identity, fixed hair shape, fixed eye color, fixed body proportions, signature wardrobe details, production-ready character design",
    ].filter(Boolean).join(", ");
    const locations = characterForgeValue("char-forge-locations") || "studio gray sweep, exterior daylight, interior practical lighting";
    const clothes = characterForgeValue("char-forge-clothes") || "hero outfit, alternate travel outfit, formal outfit";
    const angles = characterForgeValue("char-forge-angles") || "front, 3/4 left, 3/4 right, profile, rear";

    const sheetPrompt = withCharacterNoTextRule([
        "professional character reference turnaround sheet for " + name,
        role ? "role: " + role : "",
        "core identity: " + base,
        "4K horizontal 16:9 canvas, 3840x2160, pure white or light neutral studio background with very light gray divider lines",
        "wide two-row production layout with six large panels only, clean margins, no square canvas, no overlapping panels, no tilted collage, no giant central portrait, no faded ghost image",
        "consistent soft studio lighting in every panel, gentle key light from upper left, subtle fill light, natural shadows, accurate material detail",
        "Top row contains three large full-body turnaround panels: front view neutral standing pose, left side profile view, back view showing rear hair and outfit construction",
        "Bottom row contains three large detail panels: front face portrait neutral expression with clear eyes and skin texture, warm smile portrait, hands and forearms detail with accurate fingers, accessories, sleeves, and signature details",
        "same person in every panel, same age, same face, same hair color and style, same body proportions, same outfit, same materials, no identity drift, no costume redesign",
        "professional AAA game development and animation pre-production reference sheet, sharp eyelashes and hair strands, crisp facial features, coherent anatomy, clean studio presentation, visible skin texture, fabric weave, no fake writing, no barcode artifacts",
    ].filter(Boolean).join(", "));

    const variationPrompt = withCharacterNoTextRule([
        "controlled character variation grid for " + name,
        role ? "role: " + role : "",
        base,
        "same face, same body proportions, same signature identity markers in every image",
        "locations: " + locations,
        "wardrobe states: " + clothes,
        "camera angles and framings: " + angles,
        "cinematic but consistent lighting, production stills, no identity drift",
    ].filter(Boolean).join(", "));

    const sheetEl = document.getElementById("char-forge-sheet-prompt");
    const variationEl = document.getElementById("char-forge-variation-prompt");
    if (sheetEl) sheetEl.value = sheetPrompt;
    if (variationEl) variationEl.value = variationPrompt;
    const status = document.getElementById("character-manager-status");
    if (status) status.textContent = "Prompts composed locally. Spark not required until generation.";
}

function selectCharacterForForge(charId) {
    const char = characterManagerCache.find((c) => characterId(c) === charId);
    if (!char) return;
    characterForgeSelectedId = characterId(char);
    if (shellState?.characters?.some((c) => characterId(c) === characterForgeSelectedId)) {
        shellState.selectedCharacterId = characterForgeSelectedId;
    }
    const nameEl = document.getElementById("char-forge-name");
    const roleEl = document.getElementById("char-forge-role");
    const baseEl = document.getElementById("char-forge-base-prompt");
    if (nameEl) nameEl.value = characterName(char);
    if (roleEl) roleEl.value = char.role || char.description || "Character";
    if (baseEl) {
        baseEl.value = char.anchor_prompt || [
            characterName(char),
            char.role || "",
            char.dna && Object.keys(char.dna).length ? Object.entries(char.dna).map(([k, v]) => k + ": " + (Array.isArray(v) ? v.join(", ") : String(v))).join(", ") : "",
        ].filter(Boolean).join(", ");
    }
    composeCharacterPrompts();
    syncCharacterForgeSelectionUi();
    const status = document.getElementById("character-manager-status");
    const refUrl = latestCharacterGeneratedImage(char);
    if (status) status.textContent = refUrl
        ? "Selected " + characterName(char) + ". Sheet and variation generation will use this character image."
        : "Selected " + characterName(char) + ". Generate a character image before making sheets or variations.";
    updateCharacterFlowState();
}

function promptForCharacterRender(kind) {
    const raw = kind === "sheet"
        ? characterForgeValue("char-forge-sheet-prompt")
        : kind === "variation"
            ? characterForgeValue("char-forge-variation-prompt")
            : characterForgeValue("char-forge-base-prompt");
    if (!raw) return "";
    return withCharacterNoTextRule(raw);
}

async function renderCharacterOnSpark(kind) {
    const status = document.getElementById("character-manager-status");
    const selected = selectedCharacterForForge();
    const selectedReferenceUrls = selected ? characterReferenceImageUrlsForForge(selected) : [];
    const selectedReferenceUrl = selectedReferenceUrls[0] || "";
    if ((kind === "sheet" || kind === "variation") && !selected) {
        if (status) status.textContent = "Select one character before generating a " + kind + ".";
        syncCharacterForgeSelectionUi();
        return;
    }
    if ((kind === "sheet" || kind === "variation") && !selectedReferenceUrl) {
        if (status) status.textContent = "Selected character needs a generated character image before making a " + kind + ".";
        syncCharacterForgeSelectionUi();
        return;
    }
    const name = (kind === "sheet" || kind === "variation") && selected ? characterName(selected) : characterForgeValue("char-forge-name");
    if (!name) {
        if (status) status.textContent = "Name is required before Spark generation.";
        return;
    }
    if ((kind === "sheet" || kind === "variation") && !promptForCharacterRender(kind)) {
        composeCharacterPrompts();
    }
    switchCharacterFlowStep("render");
    const prompt = promptForCharacterRender(kind);
    if (!prompt) {
        if (status) status.textContent = "Prompt is required before Spark generation.";
        return;
    }
    const workflowId = (kind === "sheet" || kind === "variation")
        ? "02_flux2_multi_reference_character_sheet"
        : (characterForgeValue("char-forge-workflow") || "01_flux2_text_to_image");
    const workflowEl = document.getElementById("char-forge-workflow");
    if (workflowEl && (kind === "sheet" || kind === "variation")) workflowEl.value = workflowId;
    if (status) status.textContent = "Sending " + kind + " prompt to Spark...";
    try {
        const resp = await fetch("/api/characters/spark-render", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                role: selected?.role || characterForgeValue("char-forge-role"),
                prompt,
                render_type: kind,
                workflow_id: workflowId,
                seed: getCharacterForgeSeed(),
                save_character: true,
                character_id: selected ? characterId(selected) : "",
                reference_image_url: selectedReferenceUrl,
                reference_image_urls: selectedReferenceUrls,
            }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        if (status) {
            status.textContent = ((kind === "sheet" || kind === "variation") && payload.reference_image_used === false)
                ? "Spark complete, but the selected workflow has no image-reference input. Use a reference-capable workflow for a true identity lock."
                : "Spark complete: " + (payload.prompt_id || "render saved");
        }
        if (payload?.character?.id) {
            characterForgeSelectedId = characterId(payload.character);
            if (shellState?.characters?.some((c) => characterId(c) === characterForgeSelectedId)) {
                shellState.selectedCharacterId = characterForgeSelectedId;
            }
        }
        renderCharacterResultTiles(payload, kind);
        await loadCharacters();
        await loadCharacterManager();
        syncCharacterForgeSelectionUi();
        updateCharacterFlowState();
    } catch (e) {
        if (status) status.textContent = "Spark generation unavailable: " + (e?.message || e);
    }
}

function renderCharacterResultTiles(payload, kind) {
    const gallery = document.getElementById("character-render-gallery");
    if (!gallery) return;
    const urls = Array.isArray(payload?.image_urls) ? payload.image_urls : [];
    if (!urls.length) {
        gallery.innerHTML = '<div class="character-manager-status">Spark returned no image URLs.</div>';
        return;
    }
    const characterIdValue = characterId(payload?.character || { id: characterForgeValue("char-forge-name") });
    const prompt = payload?.character?.render_prompts?.[kind] || promptForCharacterRender(kind);
    const seed = payload?.seed || getCharacterForgeSeed() || "Random";
    const workflow = characterForgeValue("char-forge-workflow") || "01_flux2_text_to_image";
    const displayKind = kind === "anchor" ? "character" : kind;
    const html = urls.map((url, i) => (
        '<figure class="character-render-tile" title="Double-click to view full size" ' +
            'ondblclick="openCharacterRenderLightboxFromTile(this)" ' +
            'data-image-url="' + escapeHtml(url) + '" ' +
            'data-kind="' + escapeHtml(displayKind) + '" ' +
            'data-index="' + String(i + 1) + '" ' +
            'data-character-name="' + escapeHtml(payload?.character?.name || characterForgeValue("char-forge-name") || "Character") + '" ' +
            'data-prompt="' + escapeHtml(prompt) + '" ' +
            'data-prompt-id="' + escapeHtml(payload?.prompt_id || "") + '" ' +
            'data-seed="' + escapeHtml(String(seed)) + '" ' +
            'data-workflow="' + escapeHtml(workflow) + '">' +
            '<img src="' + escapeHtml(url) + '" alt="' + escapeHtml(displayKind) + ' render">' +
            '<figcaption class="caption">' +
                '<span>' + escapeHtml(displayKind) + ' #' + String(i + 1) + '</span>' +
                (kind === "sheet" ? '<button class="btn btn-secondary character-panel-extract-btn" type="button" ondblclick="event.stopPropagation()" onclick="event.stopPropagation(); extractCharacterSheetPanelsFromRender(\'' + escapeHtml(characterIdValue) + '\', \'' + escapeHtml(url) + '\', \'' + escapeHtml(payload?.prompt_id || "") + '\')">Extract Panels</button>' : '') +
            '</figcaption>' +
        '</figure>'
    )).join("");
    if (gallery.querySelector(".character-manager-status")) gallery.innerHTML = "";
    gallery.insertAdjacentHTML("afterbegin", html);
}

function openCharacterRenderLightboxFromTile(tile) {
    if (!tile?.dataset?.imageUrl) return;
    openLightbox({
        image_url: tile.dataset.imageUrl,
        variant: tile.dataset.index || "-",
        seed: tile.dataset.seed || "Random",
        workflow: tile.dataset.workflow || "-",
        status: "complete",
        prompt: tile.dataset.prompt || "-",
        prompt_id: tile.dataset.promptId || "-",
        workflow_profile: "Character " + (tile.dataset.kind || "render"),
        identity_type: "character",
        identity_name: tile.dataset.characterName || characterForgeValue("char-forge-name") || "",
    });
}

async function extractCharacterSheetPanelsFromRender(charId, imageUrl, promptId) {
    const status = document.getElementById("character-manager-status") || document.getElementById("character-save-status");
    if (!charId || !imageUrl) return;
    if (status) status.textContent = "Extracting sheet panels...";
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(charId) + "/sheet-panels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                image_url: imageUrl,
                rows: 2,
                columns: 4,
                source_prompt_id: promptId || "",
                make_master: false,
                notes: "extracted from generated character sheet",
            }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        if (status) status.textContent = "Extracted " + String((payload.panels || []).length) + " sheet panel reference(s).";
        await loadCharacters();
        await loadCharacterManager();
        switchCharacterFlowStep("references");
        if (shellState?.view === "characters") {
            await fetchCharacters();
            await renderCharactersContent();
        }
    } catch (e) {
        if (status) status.textContent = "Panel extraction failed: " + (e?.message || e);
    }
}

async function prepareCharacterLoraPack() {
    const selected = selectedCharacterForForge();
    const status = document.getElementById("character-lora-status") || document.getElementById("character-manager-status");
    const output = document.getElementById("character-lora-pack-output");
    const btn = document.getElementById("character-lora-prepare-btn");
    if (!selected) {
        if (status) status.textContent = "Select a character before preparing a LoRA pack.";
        updateCharacterFlowState();
        return;
    }
    const trigger = (document.getElementById("character-lora-trigger")?.value || "").trim() || suggestedCharacterLoraTrigger(selected);
    if (btn) btn.disabled = true;
    if (status) status.textContent = "Preparing LoRA dataset pack...";
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(characterId(selected)) + "/lora-pack", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                trigger_token: trigger,
                notes: "Prepared from the Characters workflow LoRA step.",
            }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const pack = payload.lora_version || {};
        if (status) {
            status.textContent = payload.ready_for_training
                ? "LoRA dataset pack ready: " + (pack.id || payload.pack_id || "prepared")
                : "LoRA pack prepared, but add more references before training. Current image count: " + String(payload.image_count || 0) + ".";
        }
        if (output) {
            output.textContent = JSON.stringify({
                character_id: payload.character_id,
                trigger_token: payload.trigger_token,
                image_count: payload.image_count,
                ready_for_training: payload.ready_for_training,
                manifest_path: payload.manifest_path,
                pack_path: payload.pack_path,
                trainer_status: payload.trainer_status,
            }, null, 2);
        }
        if (payload?.character?.id) characterForgeSelectedId = characterId(payload.character);
        await loadCharacterManager();
        switchCharacterFlowStep("lora");
    } catch (e) {
        if (status) status.textContent = "LoRA pack failed: " + (e?.message || e);
    } finally {
        if (btn) btn.disabled = false;
        updateCharacterFlowState();
    }
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
async function loadStats() {
    try {
        const resp = await fetch("/api/stats");
        const data = await resp.json();
        if (document.getElementById("stat-shots")) document.getElementById("stat-shots").textContent = data.shots_in_store || 0;
        if (document.getElementById("stat-sessions")) document.getElementById("stat-sessions").textContent = data.chat_sessions || 0;
        if (data.ram_percent != null) {
            if (document.getElementById("stat-ram")) document.getElementById("stat-ram").textContent = data.ram_percent + "%";
        }
        if (document.getElementById("home-queue")) document.getElementById("home-queue").textContent = data.shots_in_store || 0;
    } catch (e) {
        // silent
    }
    try {
        const resp = await fetch("/api/memory/stats");
        const stats = await resp.json();
        const pct = Number(stats.success_rate || 0);
        const success = pct > 0 && pct <= 1 ? Math.round(pct * 100) + "%" : (pct ? String(pct) + "%" : "0%");
        const set = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        set("home-events", stats.total_events ?? stats.events ?? "0");
        set("home-insights", stats.total_insights ?? stats.insights ?? "0");
        set("home-success", success);
        set("home-sessions", stats.active_sessions ?? stats.sessions ?? "0");
        const timeEl = document.querySelector("#main .hero-card:last-child .hero-val");
        if (timeEl && stats.time_range) timeEl.textContent = stats.time_range;
    } catch (e) {
        // silent
    }
}

// ---------------------------------------------------------------------------
// Shots
// ---------------------------------------------------------------------------
async function loadShots() {
    if (!$filmstrip) return;
    try {
        syncShotFiltersFromControls();
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
                        audit_critical_failures: s.audit_critical_failures || [],
                        audit_noncritical_issues: s.audit_noncritical_issues || [],
                        audit_decision_reasons: s.audit_decision_reasons || [],
                        audit_model_score: s.audit_model_score ?? "",
                        audit_checks_score: s.audit_checks_score ?? "",
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
        syncShotFiltersFromControls();
        const resp = await fetch("/api/shots");
        const data = await resp.json();
        const allShots = Array.isArray(data) ? data : (data.shots || []);
        let shots = _sortShots(allShots.filter(s => !!s.image_url || !!s.video_url).filter(shotMatchesFilters));
        const totalBeforeCap = shots.length;
        if (shots.length > MAX_VIDEO_THUMBS) shots = shots.slice(-MAX_VIDEO_THUMBS);
        videoShotsById = {};
        shots.forEach(s => { videoShotsById[s.id] = s; });
        if (!shots.length) {
            gridEl.innerHTML = '<div class="grid-placeholder"><p>No media available yet.</p></div>';
            if (statusEl) statusEl.textContent = "Ready — no media found in /api/shots";
            return;
        }
        gridEl.innerHTML = "";
        shots.forEach(s => {
            const selected = videoSelection.has(s.id);
            const cell = document.createElement("div");
            const isRetry = !!(s.retry_of || s.parent_shot_id || String(s.id).includes("__retry_"));
            const state = String(s.state || s.status || "").toLowerCase();
            const auditStatus = String(s.audit_status || "").toLowerCase() || (state.includes("fail") ? "fail" : (state.includes("pass") ? "pass" : ""));
            const cls = ["grid-cell", "rendered", "video-library-cell"];
            if (selected) cls.push("selected");
            if (auditStatus === "pass") cls.push("audit-pass");
            if (auditStatus === "fail") cls.push("audit-fail");
            if (isRetry) cls.push("retry-cell");
            cell.className = cls.join(" ");
            cell.dataset.shotId = s.id;

            const mediaEl = s.image_url ? document.createElement("img") : document.createElement("video");
            if (s.image_url) {
                mediaEl.src = s.image_url;
                mediaEl.alt = s.id;
                mediaEl.loading = "lazy";
                mediaEl.decoding = "async";
            } else {
                mediaEl.src = s.video_url;
                mediaEl.muted = true;
                mediaEl.controls = true;
                mediaEl.preload = "metadata";
                mediaEl.playsInline = true;
                mediaEl.title = s.id;
                mediaEl.addEventListener("click", (event) => event.stopPropagation());
            }

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
            if (s.video_url) {
                const vb = document.createElement("span");
                vb.className = "audit-badge pass";
                vb.textContent = "VIDEO";
                label.appendChild(vb);
            } else if (s.video_status) {
                const vs = document.createElement("span");
                const status = String(s.video_status || "").toLowerCase();
                vs.className = "audit-badge " + (status === "error" ? "fail" : "pass");
                vs.textContent = "VIDEO_" + status.toUpperCase();
                label.appendChild(vs);
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
                const preview = document.createElement("div");
                preview.className = "video-prompt-preview";
                const promptText = String(s.video_prompt || "");
                preview.textContent = promptText.substring(0, 140) + (promptText.length > 140 ? "..." : "");
                preview.title = videoPromptBadgeTitle(s);
                label.appendChild(preview);
            }

            if (s.video_prompt) {
                const dot = document.createElement("span");
                dot.className = "video-prompt-dot";
                dot.title = "Video prompt attached";
                cell.appendChild(dot);
            }

            const frame = document.createElement("div");
            frame.className = "video-thumb-frame";
            frame.appendChild(mediaEl);
            cell.appendChild(frame);
            cell.appendChild(label);
            cell.addEventListener("click", () => toggleVideoSelect(s.id));
            cell.addEventListener("dblclick", (event) => {
                event.preventDefault();
                if (!s.image_url && s.video_url) {
                    window.open(s.video_url, "_blank", "noopener");
                    return;
                }
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
                    audit_critical_failures: s.audit_critical_failures || [],
                    audit_noncritical_issues: s.audit_noncritical_issues || [],
                    audit_decision_reasons: s.audit_decision_reasons || [],
                    audit_model_score: s.audit_model_score ?? "",
                    audit_checks_score: s.audit_checks_score ?? "",
                    retry_of: s.retry_of || s.parent_shot_id || "",
                    video_prompt: s.video_prompt || "",
                    video_prompt_source: s.video_prompt_source || "",
                    variant: "-",
                });
            });
            gridEl.appendChild(cell);
        });
        if (statusEl) {
            const withPrompts = shots.filter(s => !!s.video_prompt).length;
            const videos = shots.filter(s => !!s.video_url).length;
            statusEl.textContent = "Ready — loaded " + shots.length + " media item(s)" +
                (videos ? (" · " + videos + " video(s)") : "") +
                (withPrompts ? (" · " + withPrompts + " with video prompts") : " · 0 with video prompts") +
                (totalBeforeCap > MAX_VIDEO_THUMBS ? (" (latest " + MAX_VIDEO_THUMBS + " of " + totalBeforeCap + ")") : "");
        }
        updateVideoSelectionUI();
    } catch (e) {
        if (statusEl) statusEl.textContent = "Failed to load media: " + e.message;
    }
}

async function importRenderedMedia() {
    const input = document.getElementById("video-import-path");
    const status = document.getElementById("video-import-status");
    const path = (input?.value || "").trim();
    if (!path) {
        if (status) status.value = "Enter a folder or report path";
        return;
    }
    if (status) status.value = "Importing...";
    try {
        const resp = await fetch("/api/import/sienna-batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ report_path: path }),
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") {
            if (status) status.value = "Import failed: " + (data.detail || data.error || resp.status);
            return;
        }
        const images = Number(data.images || 0);
        const videos = Number(data.videos || 0);
        const imported = Number(data.imported || 0);
        const updated = Number(data.updated_existing || 0);
        if (status) status.value = images + " image(s), " + videos + " video(s); " + imported + " new, " + updated + " updated";
        await loadShots();
        await loadVideoLibrary();
    } catch (e) {
        if (status) status.value = "Import error: " + e.message;
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

function savePendingVideoJobs() {
    try {
        localStorage.setItem(VIDEO_JOBS_KEY, JSON.stringify(pendingVideoJobs.slice(-80)));
    } catch (_e) {
        // best effort
    }
}

function loadPendingVideoJobs() {
    try {
        const parsed = JSON.parse(localStorage.getItem(VIDEO_JOBS_KEY) || "[]");
        pendingVideoJobs = Array.isArray(parsed) ? parsed.filter(job => job && job.prompt_id && job.shot_id) : [];
    } catch (_e) {
        pendingVideoJobs = [];
    }
}

function addPendingVideoJobs(jobs) {
    const existing = new Map(pendingVideoJobs.map(job => [String(job.prompt_id), job]));
    (jobs || []).forEach((job) => {
        if (!job?.prompt_id || !job?.shot_id) return;
        existing.set(String(job.prompt_id), {
            ...job,
            status: job.status || "queued",
            queued_at: job.queued_at || new Date().toISOString(),
        });
    });
    pendingVideoJobs = Array.from(existing.values());
    savePendingVideoJobs();
}

function scheduleVideoJobPoll(delayMs = 5000) {
    if (videoJobPollTimer) clearTimeout(videoJobPollTimer);
    if (!pendingVideoJobs.length) return;
    videoJobPollTimer = setTimeout(syncPendingVideoJobs, delayMs);
}

function videoJobStatusText(summary) {
    const complete = Number(summary?.complete || 0);
    const running = Number(summary?.running || 0);
    const errors = Number(summary?.errors || 0);
    const total = pendingVideoJobs.length + complete + errors;
    return "Video jobs: " + complete + " complete, " + running + " running/queued, " + errors + " error" + (errors === 1 ? "" : "s") + (total ? " (" + total + " tracked)" : "");
}

async function syncPendingVideoJobs() {
    if (!pendingVideoJobs.length) return;
    const jobs = pendingVideoJobs.slice();
    try {
        const resp = await fetch("/api/video/sync-jobs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jobs }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.status !== "ok") throw new Error(data.detail || data.error || "HTTP " + resp.status);
        const terminal = new Set();
        const failed = [];
        (data.results || []).forEach((result) => {
            if (result.status === "complete" || result.status === "error") terminal.add(String(result.prompt_id));
            if (result.status === "error") failed.push(result);
        });
        pendingVideoJobs = pendingVideoJobs.filter(job => !terminal.has(String(job.prompt_id)));
        savePendingVideoJobs();
        if ($sparkStatusText) $sparkStatusText.textContent = videoJobStatusText(data);
        if ($sparkProgress) {
            const latestComplete = (data.results || []).find(r => r.status === "complete" && r.video_url);
            const latestError = failed[0];
            $sparkProgress.textContent = latestComplete
                ? "Saved " + latestComplete.video_url
                : latestError
                    ? ((latestError.shot_id || "job") + ": " + (latestError.error || "error"))
                    : "Polling ComfyUI for finished MP4s...";
        }
        if (terminal.size) {
            await loadShots();
            await loadVideoLibrary();
        }
        if (pendingVideoJobs.length) scheduleVideoJobPoll(5000);
    } catch (e) {
        if ($sparkStatusText) $sparkStatusText.textContent = "Video status sync failed: " + (e?.message || e);
        scheduleVideoJobPoll(10000);
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

async function processSelectedVideos() {
    if (!videoSelection.size) {
        alert("Select at least one image");
        return;
    }
    const videoOptions = syncVideoQuickOptions();
    const duration = parseInt(String(videoOptions.duration || $videoDuration?.value || 5), 10);
    const fps = parseInt($videoFps?.value || "24", 10);
    const workflowId = videoOptions.workflowId || getSelectedVideoWorkflow();
    const videoPrompt = ($videoPrompt?.value || "").trim();
    const selectedForVideo = Array.from(videoSelection).filter(id => {
        const shot = videoShotsById[id];
        return shot && evaluateShotForVideo(shot).eligible;
    });
    const skipped = videoSelection.size - selectedForVideo.length;
    if (!selectedForVideo.length) {
        $sparkStatusText.textContent = "No rendered images selected for video. Select image cards in the Video tab first.";
        $sparkProgress.textContent = skipped ? (skipped + " selected item(s) had no image") : "";
        return;
    }
    $startBatchBtn.disabled = true;
    $startBatchBtn.textContent = "Processing...";
    $sparkStatusText.textContent = "Processing " + selectedForVideo.length + " image(s) into videos via " + workflowId + (skipped ? " (" + skipped + " skipped)" : "") + "...";
    try {
        const resp = await fetch("/api/video/process", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
                shot_ids: selectedForVideo,
                duration,
                fps,
                workflow_id: workflowId,
                mode: videoOptions.mode,
                resolution: videoOptions.resolution,
                aspect_ratio: videoOptions.aspectRatio,
                prompt: videoPrompt,
                platform_mode: document.getElementById("platform-mode")?.value || "auto",
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
        $sparkStatusText.textContent = "Video jobs queued (" + workflowId + "): " + done + " queued, " + blocked + " blocked, " + errs + " errors";
        const failures = (data.results || []).filter(r => r.status === "blocked" || r.status === "error");
        const failureText = failures.slice(0, 4).map(r =>
            (r.shot_id || "shot") + ": " + (r.error || (r.reasons || []).join(",") || r.status)
        ).join(" | ");
        const jobs = (data.results || [])
            .filter(r => r.status === "ok" && r.prompt_id)
            .map(r => ({
                shot_id: r.shot_id,
                prompt_id: r.prompt_id,
                campaign_id: currentCampaignId || "",
                workflow_id: r.workflow_id || workflowId,
                seed: r.seed,
                duration,
                fps,
                host: r.host || "",
                status: "queued",
            }));
        if (jobs.length) {
            addPendingVideoJobs(jobs);
            $sparkProgress.textContent = "Queued " + jobs.length + " ComfyUI job(s). Polling for completed MP4s...";
            scheduleVideoJobPoll(2000);
        } else {
            $sparkProgress.textContent = failureText || (data.output_dir || "");
        }
        if (failures.length) {
            addLogEntry("error", "Video processing issues: " + failureText);
        }
    } catch (e) {
        $sparkStatusText.textContent = "Error: " + e.message;
    } finally {
        $startBatchBtn.disabled = false;
        $startBatchBtn.textContent = "Process";
    }
}

async function generateVideoPromptsForSelected() {
    if (!videoSelection.size) {
        $sparkStatusText.textContent = "Select at least one rendered image before generating video prompts.";
        return;
    }
    const videoOptions = syncVideoQuickOptions();
    const duration = parseInt(String(videoOptions.duration || $videoDuration?.value || 5), 10);
    const fps = parseInt($videoFps?.value || "24", 10);
    const workflowId = videoOptions.workflowId || getSelectedVideoWorkflow();
    const selectedForPrompt = Array.from(videoSelection).filter(id => {
        const shot = videoShotsById[id];
        return shot && evaluateShotForVideo(shot).eligible;
    });
    const skipped = videoSelection.size - selectedForPrompt.length;
    if (!selectedForPrompt.length) {
        $sparkStatusText.textContent = "No rendered images selected for prompt generation.";
        $sparkProgress.textContent = skipped ? (skipped + " selected item(s) had no image") : "";
        return;
    }

    const btn = document.getElementById("video-generate-primary-btn");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Generating Prompt...";
    }
    $sparkStatusText.textContent = "Generating video prompt(s) from " + selectedForPrompt.length + " selected image(s)...";
    $sparkProgress.textContent = skipped ? (skipped + " skipped because no rendered image was available") : "";

    const prompts = {};
    try {
        const resp = await fetch("/api/video/generate-prompts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                shot_ids: selectedForPrompt,
                duration,
                fps,
                campaign_id: currentCampaignId || "",
                workflow_id: workflowId,
                mode: videoOptions.mode,
                resolution: videoOptions.resolution,
                aspect_ratio: videoOptions.aspectRatio,
                platform_mode: document.getElementById("platform-mode")?.value || "auto",
            }),
        });
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error(text || ("HTTP " + resp.status));
        }
        if (!resp.body) throw new Error("Prompt stream unavailable");

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let saved = 0;
        let analyzed = 0;
        let promptEvents = 0;
        let streamErrors = 0;
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
                if (!line.trim()) continue;
                let event;
                try {
                    event = JSON.parse(line);
                } catch (_e) {
                    continue;
                }
                if (event.error) {
                    streamErrors += 1;
                    $sparkProgress.textContent = String(event.error);
                    continue;
                }
                if (event.agent && event.status === "thinking") {
                    $sparkStatusText.textContent = event.agent + " is generating video prompt(s)... " + analyzed + "/" + selectedForPrompt.length + " analyzed";
                } else if (event.agent && event.result) {
                    const shotLabel = event.shot_id ? (event.shot_id + ": ") : "";
                    if (String(event.agent).includes("Vision Analyst")) analyzed += 1;
                    if (String(event.agent).includes("Prompt Engineer")) promptEvents += 1;
                    $sparkStatusText.textContent = "Prompt generation progress: " + analyzed + "/" + selectedForPrompt.length + " analyzed, " + promptEvents + " prompt update(s)";
                    $sparkProgress.textContent = shotLabel + String(event.result).slice(0, 180);
                }
                if (event.prompts && typeof event.prompts === "object") {
                    Object.assign(prompts, event.prompts);
                    saved = Number(event.saved || Object.keys(prompts).length || saved);
                }
            }
        }

        if (Object.keys(prompts).length) {
            const firstPrompt = prompts[selectedForPrompt[0]] || Object.values(prompts)[0] || "";
            if ($videoPrompt && firstPrompt) $videoPrompt.value = String(firstPrompt);
            selectedForPrompt.forEach((id) => {
                if (videoShotsById[id] && prompts[id]) {
                    videoShotsById[id].video_prompt = prompts[id];
                    videoShotsById[id].video_prompt_source = "vision_prompt_agent";
                }
            });
            $sparkStatusText.textContent = "Generated " + Object.keys(prompts).length + " video prompt(s). Review/edit, then click Process.";
            $sparkProgress.textContent = (saved ? (saved + " prompt(s) saved to selected media") : "Prompt ready") +
                (streamErrors ? (" · " + streamErrors + " warning(s), fallback used where needed") : "");
            await loadVideoLibrary();
            updateVideoSelectionUI();
        } else {
            $sparkStatusText.textContent = "Prompt generation finished, but no prompts were returned.";
            $sparkProgress.textContent = streamErrors ? (streamErrors + " warning(s) reported") : "";
        }
    } catch (e) {
        $sparkStatusText.textContent = "Prompt generation failed: " + (e?.message || e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Generate Prompt From Selected Images";
        }
    }
}

async function exportCarousel() {
    const selected = Array.from(videoSelection);
    if (!selected.length) {
        $sparkStatusText.textContent = "Select at least one image or clip for carousel export.";
        return;
    }
    const btn = document.getElementById("carousel-export-btn");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Exporting...";
    }
    try {
        const resp = await fetch("/api/export/carousel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                shot_ids: selected,
                campaign_id: currentCampaignId || "",
                platform_mode: document.getElementById("platform-mode")?.value || "tiktok",
            }),
        });
        const data = await resp.json();
        if (!resp.ok || data.status !== "ok") throw new Error(data.detail || data.error || "Export failed");
        $sparkStatusText.textContent = "Carousel export ready: " + data.count + " file(s)";
        $sparkProgress.innerHTML = '<a href="' + escapeHtml(data.zip_url || "#") + '" target="_blank" rel="noopener">Open ZIP</a>';
        addLogEntry("system", "Carousel export: " + (data.zip_url || data.zip_path || "ready"));
    } catch (e) {
        $sparkStatusText.textContent = "Carousel export failed: " + (e?.message || e);
        addLogEntry("error", "Carousel export failed: " + (e?.message || e));
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Export Carousel";
        }
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
function formatLightboxList(value) {
    if (Array.isArray(value)) {
        const clean = value.map(v => String(v || "").trim()).filter(Boolean);
        return clean.length ? clean.join("; ") : "-";
    }
    const text = String(value || "").trim();
    return text || "-";
}

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
    const auditParts = [];
    if (result.audit_model_score !== undefined && result.audit_model_score !== "") auditParts.push("model " + result.audit_model_score);
    if (result.audit_checks_score !== undefined && result.audit_checks_score !== "") auditParts.push("checks " + result.audit_checks_score);
    document.getElementById("lightbox-audit").textContent = audit;
    const auditReasonEl = document.getElementById("lightbox-audit-reasons");
    if (auditReasonEl) auditReasonEl.textContent = formatLightboxList(result.audit_decision_reasons);
    const auditCriticalEl = document.getElementById("lightbox-audit-critical");
    if (auditCriticalEl) auditCriticalEl.textContent = formatLightboxList(result.audit_critical_failures);
    const auditIssuesEl = document.getElementById("lightbox-audit-issues");
    if (auditIssuesEl) {
        const issuesText = formatLightboxList(result.audit_issues);
        auditIssuesEl.textContent = auditParts.length && issuesText !== "-"
            ? (issuesText + "; " + auditParts.join("; "))
            : (issuesText !== "-" ? issuesText : (auditParts.length ? auditParts.join("; ") : "-"));
    }
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

function memoryNodeColor(ele) {
  const type = String(ele.data("type") || "").toLowerCase();
  const eventType = String(ele.data("event_type") || "").toLowerCase();
  const retry = eventType === "retry_linked" || String(ele.data("retry_of") || "");
  if (ele.data("success") === false) return "#ff4d6d";
  if (retry) return "#d16cff";
  if (type === "session") return "#ffc857";
  if (type === "insight") return "#b388ff";
  if (type === "concept") return "#ff5ab4";
  if (eventType === "shot_planned") return "#a8b3bd";
  if (eventType.startsWith("render_")) return "#00d7ff";
  if (eventType.startsWith("audit_")) return "#ffb74d";
  if (eventType.startsWith("remediation_")) return "#8a7dff";
  if (eventType === "final_outcome" || ele.data("success") === true) return "#75ff9b";
  if (eventType === "import_completed") return "#7ce7d0";
  return MEM_TYPE_COLOR[type] || "#6ea8fe";
}

function memoryEdgeColor(ele) {
  const type = String(ele.data("type") || "").toLowerCase();
  if (type === "learned_from") return "#b388ff";
  if (type.includes("retry")) return "#d16cff";
  if (type.includes("audit")) return "#ffb74d";
  if (type.includes("outcome")) return "#75ff9b";
  return "#40627f";
}

function memoryNodeLabel(ele) {
  const raw = String(ele.data("label") || ele.data("id") || "");
  if (raw.length <= 30) return raw;
  return raw.slice(0, 27) + "...";
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
          'background-color': memoryNodeColor,
          'background-blacken': -0.08,
          'label': memoryNodeLabel,
          'color': '#dffbff',
          'font-family': 'JetBrains Mono, ui-monospace, monospace',
          'font-size': '9.5px',
          'font-weight': 500,
          'text-wrap': 'wrap',
          'text-max-width': '92px',
          'text-outline-color': '#05090f',
          'text-outline-width': 3,
          'text-background-color': 'rgba(4, 8, 13, 0.72)',
          'text-background-opacity': 0.72,
          'text-background-padding': '3px',
          'text-margin-y': 8,
          'text-valign': 'bottom',
          'text-halign': 'center',
          'width': (n) => {
            const base = Number(n.data('size') || (n.data('type') === 'session' ? 28 : 18));
            const conf = Number(n.data('confidence') || 0.5);
            const imp = Number(n.data('importance') || 1);
            return Math.max(18, Math.min(62, base + 2 + (conf * 9) + (imp * 3)));
          },
          'height': (n) => {
            const base = Number(n.data('size') || (n.data('type') === 'session' ? 28 : 18));
            const conf = Number(n.data('confidence') || 0.5);
            const imp = Number(n.data('importance') || 1);
            return Math.max(18, Math.min(62, base + 2 + (conf * 9) + (imp * 3)));
          },
          'shape': (n) => ({ session: 'diamond', insight: 'star', concept: 'round-rectangle' }[n.data('type')] || 'ellipse'),
          'border-width': (n) => {
            const et = String(n.data('event_type') || "");
            if (et === "retry_linked" || String(n.data('retry_of') || "")) return 4;
            if (n.data('success') === false) return 4;
            if (n.data('success') === true) return 3;
            return 2;
          },
          'border-color': (n) => {
            const et = String(n.data('event_type') || "");
            if (et === "retry_linked" || String(n.data('retry_of') || "")) return '#f0a5ff';
            if (n.data('success') === false) return '#ffd1dc';
            if (n.data('success') === true) return '#ceffd9';
            return memoryNodeColor(n);
          },
          'border-opacity': 0.86,
          'shadow-blur': 22,
          'shadow-color': memoryNodeColor,
          'shadow-opacity': 0.32,
          'shadow-offset-x': 0,
          'shadow-offset-y': 0,
        }
      },
      {
        selector: '.nexus-node',
        style: {
          'background-color': '#00bcd4',
          'border-color': '#80deea',
          'border-width': 3,
          'shape': 'round-rectangle',
          'font-size': '10px',
          'color': '#dffbff',
          'shadow-color': '#00d7ff',
          'shadow-opacity': 0.44,
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
          'line-color': memoryEdgeColor,
          'opacity': 0.58,
          'width': (e) => Math.min(6, 1.15 + (Number(e.data('weight') || 1) * 0.8)),
          'target-arrow-color': memoryEdgeColor,
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.72,
          'curve-style': 'bezier',
          'control-point-step-size': 42,
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
      { selector: ':selected', style: { 'border-width': 5, 'border-color': '#fff', 'shadow-opacity': 0.72 } },
      { selector: '.memory-dim', style: { 'opacity': 0.12 } },
    ],
    layout: {
      name: 'cose',
      padding: 46,
      animate: false,
      nodeRepulsion: 9400,
      idealEdgeLength: 92,
      edgeElasticity: 112,
      nestingFactor: 5,
      gravity: 74,
      numIter: 1200,
      initialTemp: 220,
      coolingFactor: 0.95,
      minTemp: 1.0,
    },
    userPanningEnabled: true,
    userZoomingEnabled: true,
  });
  setMemoryLayoutChrome("force");
  const lanesEnabled = !!document.getElementById("mem-view-lanes")?.checked;
  if (lanesEnabled) applyMemoryLaneLayout();
  attachMemorySelectionHandlers();
  updateMemoryHeatOverlay();
}

function memoryCyLayout(name) {
  if (!window._memoryCy) return;
  const lanes = document.getElementById("mem-view-lanes");
  if (lanes) {
    lanes.checked = false;
    lanes.parentElement?.classList.remove("active");
  }
  const layoutKey = name === "cose" ? "force" : name === "breadthfirst" ? "tree" : name;
  const options = {
    name,
    padding: name === "cose" ? 46 : 28,
    animate: true,
    animationDuration: 480,
  };
  if (name === "cose") {
    Object.assign(options, {
      nodeRepulsion: 9400,
      idealEdgeLength: 92,
      edgeElasticity: 112,
      nestingFactor: 5,
      gravity: 74,
      numIter: 1200,
      initialTemp: 220,
      coolingFactor: 0.95,
      minTemp: 1.0,
    });
  }
  window._memoryCy.layout(options).run();
  setMemoryLayoutChrome(layoutKey);
}

function setMemoryLayoutChrome(layoutKey) {
  document.querySelectorAll(".memory-view .graph-toolbar button[data-layout]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.layout === layoutKey);
  });
  const wrap = document.querySelector(".memory-view .graph-wrap");
  if (wrap) wrap.dataset.layout = layoutKey;
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
  setMemoryLayoutChrome("lanes");
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

// ---------------------------------------------------------------------------
// Static Shell Router
// ---------------------------------------------------------------------------
const SHELL_VIEWS = {
    home: { section: "Images", current: "Generation" },
    characters: { section: "Characters", current: "DNA" },
    script: { section: "Script", current: "Director" },
    products: { section: "Products", current: "Prompt Builder" },
    spark: { section: "Spark", current: "Queue" },
    memory: { section: "Memory", current: "Graph" },
    settings: { section: "Settings", current: "System" },
};

let shellState = {
    view: "home",
    characters: [],
    selectedCharacterId: "",
    charactersRosterCollapsed: false,
    products: [],
    selectedProductId: "",
    productBanks: {},
    productRecipe: null,
    variations: [],
};

function getShellView() {
    return document.getElementById("view");
}

function normalizeProducts(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.products)) return payload.products;
    return [];
}

function productName(product) {
    return String(product?.name || product?.id || "Custom Product").trim();
}

function productId(product) {
    return String(product?.id || productName(product)).trim().toLowerCase().replace(/\s+/g, "_");
}

function productDescription(product) {
    return String(product?.description || product?.descriptor || product?.anchor_prompt || "").trim();
}

function productImage(product) {
    return product?.image_url || product?.anchor_url || product?.anchor_src || "";
}

function renderProductPreview(product) {
    const img = productImage(product);
    if (img) {
        return '<img src="' + escapeHtml(img) + '" alt="' + escapeHtml(productName(product)) + '" loading="lazy">';
    }
    const label = productName(product).slice(0, 2).toUpperCase();
    return '<div class="product-preview-fallback"><span>' + escapeHtml(label) + '</span></div>';
}

function renderPortrait(char, size) {
    const img = characterImage(char);
    if (img) {
        return '<img class="character-zoomable" src="' + escapeHtml(img) + '" alt="' + escapeHtml(characterName(char)) + '" loading="lazy" data-zoom-src="' + escapeHtml(img) + '" data-zoom-title="' + escapeHtml(characterName(char)) + '" data-zoom-prompt="' + escapeHtml(char?.anchor_prompt || "") + '">';
    }
    if (typeof portraitSVG === "function") {
        return portraitSVG({ id: characterId(char), name: characterName(char), accent: char?.accent || "cyan" }, size || 220);
    }
    return '<div class="character-placeholder">' + escapeHtml(characterName(char).slice(0, 1).toUpperCase()) + "</div>";
}

function updateShellChrome(viewId) {
    const meta = SHELL_VIEWS[viewId] || SHELL_VIEWS.home;
    document.querySelectorAll(".rail-item[data-view]").forEach((item) => {
        item.classList.toggle("active", item.dataset.view === viewId);
    });
    const section = document.getElementById("crumbSection");
    const current = document.getElementById("crumbCurrent");
    if (section) section.textContent = meta.section;
    if (current) current.textContent = meta.current;
}

function navigate(viewId) {
    if (!getShellView()) return;
    const target = SHELL_VIEWS[viewId] ? viewId : "home";
    shellState.view = target;
    if (window.location.hash !== "#/" + target) {
        history.pushState(null, "", "#/" + target);
    }
    updateShellChrome(target);
    if (target === "characters") {
        renderCharactersTab();
        return;
    }
    if (target === "script") {
        renderScriptTab();
        return;
    }
    if (target === "products") {
        renderProductsTab();
        return;
    }
    if (target === "settings") {
        renderSettingsTab();
        configDirty = {};
        loadConfig();
        return;
    }
    renderShellPlaceholder(target);
}

window.navigate = navigate;

window.addEventListener("popstate", () => {
    const fromHash = (window.location.hash || "#/home").replace(/^#\/?/, "") || "home";
    shellState.view = SHELL_VIEWS[fromHash] ? fromHash : "home";
    updateShellChrome(shellState.view);
    if (shellState.view === "characters") renderCharactersTab();
    else if (shellState.view === "script") renderScriptTab();
    else if (shellState.view === "products") renderProductsTab();
    else if (shellState.view === "settings") {
        renderSettingsTab();
        configDirty = {};
        loadConfig();
    }
    else renderShellPlaceholder(shellState.view);
});

window.addEventListener("hashchange", () => {
    const fromHash = (window.location.hash || "#/home").replace(/^#\/?/, "") || "home";
    const target = SHELL_VIEWS[fromHash] ? fromHash : "home";
    if (target !== shellState.view) navigate(target);
});

window.addEventListener("DOMContentLoaded", () => {
    const initial = (window.location.hash || "#/home").replace(/^#\/?/, "") || "home";
    navigate(SHELL_VIEWS[initial] ? initial : "home");
});

function renderShellPlaceholder(viewId) {
    const view = getShellView();
    if (!view) return;
    if (viewId === "home") {
        view.innerHTML =
            '<div class="view-inner">' +
                '<div class="view-header">' +
                    '<div><div class="eyebrow">Command Center</div><h1>Forge NPS</h1><p class="sub">Campaign control, character identity, render queue, and memory audit workspace.</p></div>' +
                    '<div class="actions"><button class="btn btn-primary" onclick="navigate(\'characters\')">Characters</button></div>' +
                '</div>' +
                '<div class="hero-grid">' +
                    '<div class="panel stat"><span class="stat-label">Shots</span><span class="stat-value" id="stat-shots">0</span><span class="stat-sub">In store</span></div>' +
                    '<div class="panel stat"><span class="stat-label">Sessions</span><span class="stat-value" id="stat-sessions">0</span><span class="stat-sub">Chat memory</span></div>' +
                    '<div class="panel stat"><span class="stat-label">RAM</span><span class="stat-value" id="stat-ram">0%</span><span class="stat-sub">Host usage</span></div>' +
                    '<div class="panel stat"><span class="stat-label">Queue</span><span class="stat-value" id="home-queue">0</span><span class="stat-sub">Active media</span></div>' +
                '</div>' +
                '<div class="home-body">' +
                    '<section class="panel"><div class="panel-header"><div class="title">Characters</div><div class="meta" id="home-character-count">loading</div></div><div class="panel-body"><div class="char-list-inline" id="char-list"></div></div></section>' +
                    '<section class="panel"><div class="panel-header"><div class="title">Quick Actions</div></div><div class="panel-body quick-actions">' +
                        '<button class="quick-action" onclick="navigate(\'characters\')"><span class="title">Character DNA</span><span class="desc">Manage characters and traits</span></button>' +
                        '<button class="quick-action" onclick="navigate(\'script\')"><span class="title">Script Director</span><span class="desc">Plan, edit, and select shots</span></button>' +
                        '<button class="quick-action" onclick="navigate(\'products\')"><span class="title">Product Builder</span><span class="desc">Compose product prompt recipes</span></button>' +
                        '<button class="quick-action" onclick="navigate(\'spark\')"><span class="title">Spark Queue</span><span class="desc">Review render work</span></button>' +
                    '</div></section>' +
                '</div>' +
            '</div>';
        loadStats();
        refreshCharacterSummary();
        return;
    }
    const meta = SHELL_VIEWS[viewId] || SHELL_VIEWS.home;
    view.innerHTML =
        '<div class="view-inner">' +
            '<div class="view-header"><div><div class="eyebrow">' + escapeHtml(meta.section) + '</div><h1>' + escapeHtml(meta.section) + '</h1><p class="sub">This workspace is wired into the shell; the next production panel can mount here without changing navigation.</p></div></div>' +
            '<section class="panel"><div class="panel-body"><span class="t-meta">No static panel is mounted for this tab yet.</span></div></section>' +
        '</div>';
}

function renderScriptTab() {
    const view = getShellView();
    if (!view) return;
    view.innerHTML = `
        <div class="view-inner script-shell">
            <div class="view-header">
                <div>
                    <div class="eyebrow">Director</div>
                    <h1>Script</h1>
                    <p class="sub">Develop a locked script package, then convert it into scene-aware coverage for Spark.</p>
                </div>
                <div class="actions">
                    <button class="btn" onclick="clearShotList()">Reset</button>
                    <button class="btn btn-primary" id="send-to-spark-btn" onclick="sendToSpark()" disabled>Send Selected to Spark</button>
                </div>
            </div>

            <div class="script-workspace">
                <section class="panel script-brief-panel">
                    <div class="panel-header">
                        <div class="title">01 Brief</div>
                        <div class="meta" id="script-progress"></div>
                    </div>
                    <div class="panel-body script-brief-body">
                        <div class="form-inline">
                            <label class="form-row"><span>Title</span><input class="input" type="text" id="script-title" placeholder="Campaign or film title"></label>
                            <label class="form-row"><span>Tone</span><input class="input" type="text" id="script-tone" placeholder="restrained sci-fi thriller"></label>
                            <label class="form-row small"><span>Runtime</span><input class="input" type="number" id="script-runtime" value="60" min="15" max="720"></label>
                            <label class="form-row small"><span>Scenes</span><input class="input" type="number" id="script-scenes" value="4" min="1" max="12"></label>
                        </div>
                        <textarea id="script-brief" class="textarea script-brief-input" placeholder="Paste the campaign prompt, script, or brand brief..." rows="9"></textarea>
                        <div class="script-controls">
                            <label class="script-file-control">
                                <span class="t-label">Upload</span>
                                <input class="input" type="file" id="brief-file-input" accept=".md,.txt,.pdf" onchange="uploadBrief()">
                            </label>
                            <button class="btn btn-primary" id="develop-script-btn" onclick="developScriptPackage()">Develop Script Package</button>
                        </div>
                        <div id="script-status" class="script-status-line">
                            <span id="script-status-text">Ready</span>
                        </div>
                    </div>
                </section>

                <section class="panel script-package-panel">
                    <div class="panel-header"><div class="title">02 Locked Package</div><div class="meta">Treatment / continuity / edit</div></div>
                    <div class="panel-body script-package-tabs">
                        <div class="script-package-box"><h4>Treatment</h4><div id="script-treatment-output" class="script-output"><div class="script-empty-mini">No treatment yet.</div></div></div>
                        <div class="script-package-box"><h4>Continuity</h4><div id="script-continuity-output" class="script-output"><div class="script-empty-mini">No continuity locks yet.</div></div></div>
                        <div class="script-package-box"><h4>Edit Plan</h4><div id="script-edit-output" class="script-output"><div class="script-empty-mini">No edit plan yet.</div></div></div>
                    </div>
                </section>

                <section class="panel script-scenes-panel">
                    <div class="panel-header"><div class="title">03 Scenes and Beats</div><div class="meta">Structured script</div></div>
                    <div class="panel-body"><div id="script-scenes-output" class="script-scenes-output"><div class="script-empty-mini">Generate the package to see scene structure.</div></div></div>
                </section>

                <section class="panel script-json-panel">
                    <div class="panel-header"><div class="title">04 Package JSON</div><div class="meta">Editable lockfile</div></div>
                    <textarea id="script-package-json" class="textarea" spellcheck="false" placeholder="The locked script package appears here. You can edit it before generating coverage."></textarea>
                </section>

                <section class="panel script-chat-panel">
                    <div class="script-chat-header">
                        <span>Hermes Notes</span>
                        <span id="script-chat-status">Ready</span>
                    </div>
                    <div id="script-chat-log" class="script-chat-log"></div>
                    <div class="script-chat-input-row">
                        <input class="input" type="text" id="script-chat-input" placeholder="Message Hermes..." onkeydown="if(event.key==='Enter')sendScriptChat()">
                        <button class="btn" id="script-chat-send-btn" onclick="sendScriptChat()">Send</button>
                    </div>
                </section>

                <section class="panel script-shot-panel">
                    <div class="panel-header">
                        <div class="title">05 Coverage Shotlist</div>
                        <div class="meta"><input class="input" type="number" id="script-target-shots" min="1" max="120" placeholder="auto" style="width:90px;"><button class="btn btn-primary" id="generate-shots-btn" onclick="generateShotList()">Generate Coverage Shotlist</button></div>
                    </div>
                    <div class="panel-body script-shot-body">
                        <div id="shot-list-placeholder" class="script-empty">
                            <p>Generate a script package, then convert it into coverage.</p>
                        </div>
                        <div id="shot-list" class="shot-list" style="display:none;"></div>
                    </div>
                </section>
            </div>
        </div>`;
    refreshScriptDomRefs();
    updateSendToSparkBtn();
}

async function fetchProducts() {
    const resp = await fetch("/api/products");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const payload = await resp.json();
    shellState.products = normalizeProducts(payload).map((product) => ({ ...product, id: productId(product) }));
    if (!shellState.selectedProductId && shellState.products.length) {
        shellState.selectedProductId = shellState.products[0].id;
    }
    if (shellState.products.length && !shellState.products.some((p) => p.id === shellState.selectedProductId)) {
        shellState.selectedProductId = shellState.products[0].id;
    }
    return shellState.products;
}

async function fetchProductBanks() {
    const resp = await fetch("/api/banks?mode=product");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const payload = await resp.json();
    shellState.productBanks = payload && typeof payload === "object" ? payload : {};
    return shellState.productBanks;
}

async function renderProductsTab() {
    const view = getShellView();
    if (!view) return;
    view.innerHTML =
        '<div class="view-inner">' +
            '<div class="view-header">' +
                '<div><div class="eyebrow">Product System</div><h1>Products</h1><p class="sub">Product roster, bank-driven visual recipes, deterministic seeds, and render-ready prompt output.</p></div>' +
                '<div class="actions"><button class="btn" onclick="renderProductsTab()">Refresh</button><button class="btn btn-primary" onclick="buildProductRecipe()">Build Prompt</button></div>' +
            '</div>' +
            '<div id="product-error" class="character-error hidden"></div>' +
            '<div id="product-content" class="character-loading">Loading products...</div>' +
        '</div>';

    try {
        await Promise.all([fetchProducts(), fetchProductBanks()]);
        renderProductsContent();
    } catch (e) {
        const err = document.getElementById("product-error");
        const content = document.getElementById("product-content");
        if (err) {
            err.classList.remove("hidden");
            err.textContent = "Product data unavailable: " + (e?.message || e);
        }
        if (content) content.innerHTML = "";
    }
}

function renderProductsContent() {
    const content = document.getElementById("product-content");
    if (!content) return;
    const selected = shellState.products.find((p) => p.id === shellState.selectedProductId) || shellState.products[0] || null;
    if (selected) shellState.selectedProductId = selected.id;
    const initialName = selected ? productName(selected) : "";
    const initialDescription = selected ? productDescription(selected) : "";
    content.innerHTML =
        '<div class="product-workspace">' +
            '<aside class="product-sidebar panel">' +
                '<div class="panel-header"><div class="title">Roster</div><div class="meta">' + shellState.products.length + '</div></div>' +
                '<div class="panel-body product-roster">' + renderProductRoster(selected) + '</div>' +
            '</aside>' +
            '<section class="product-main">' +
                '<div class="product-builder-grid">' +
                    '<section class="panel product-identity-card">' +
                        '<div class="panel-header"><div class="title">Product Identity</div><div class="meta">descriptor</div></div>' +
                        '<div class="panel-body product-identity-body">' +
                            '<div class="product-preview">' + renderProductPreview(selected || { name: "Product" }) + '</div>' +
                            '<div class="product-form-stack">' +
                                '<label class="field"><span class="t-label">Product Name</span><input class="input" id="product-name-input" value="' + escapeHtml(initialName) + '" placeholder="Emberdrive Mk-II"></label>' +
                                '<label class="field"><span class="t-label">Description</span><textarea class="textarea" id="product-description-input" rows="6" placeholder="Describe the physical product, signature details, materials, proportions, and brand cues.">' + escapeHtml(initialDescription) + '</textarea></label>' +
                                '<label class="product-check"><input type="checkbox" id="product-seed-lock" checked> Deterministic product seed</label>' +
                            '</div>' +
                        '</div>' +
                    '</section>' +
                    '<section class="panel product-banks-card">' +
                        '<div class="panel-header"><div class="title">Variation Banks</div><div class="meta">' + Object.keys(shellState.productBanks).length + ' banks</div></div>' +
                        '<div class="panel-body product-bank-grid">' + renderProductBankControls() + '</div>' +
                    '</section>' +
                '</div>' +
                '<section class="panel product-recipe-card">' +
                    '<div class="panel-header"><div class="title">Prompt Recipe</div><div class="meta" id="product-recipe-meta">not built</div></div>' +
                    '<div class="panel-body">' +
                        '<textarea class="textarea product-prompt-output" id="product-prompt-output" readonly placeholder="Build a prompt to preview the compiled recipe."></textarea>' +
                        '<div class="product-recipe-actions"><button class="btn" onclick="copyProductPrompt()">Copy Prompt</button><span class="t-meta" id="product-copy-status"></span></div>' +
                    '</div>' +
                '</section>' +
                '<section class="panel product-gallery-card">' +
                    '<div class="panel-header"><div class="title">Product Variation Gallery</div><div class="meta">renders</div></div>' +
                    '<div class="panel-body product-gallery-empty">No product renders loaded.</div>' +
                '</section>' +
            '</section>' +
        '</div>';
}

function renderProductRoster(selected) {
    if (!shellState.products.length) {
        return '<div class="product-empty">No configured products. Use the custom identity editor to compile a product prompt.</div>';
    }
    return shellState.products.map((product) => {
        const active = selected && product.id === selected.id ? " active" : "";
        return (
            '<button class="product-pick card interactive' + active + '" type="button" onclick="selectProduct(\'' + escapeHtml(product.id) + '\')">' +
                '<span class="product-pick-thumb">' + renderProductPreview(product) + '</span>' +
                '<span class="product-pick-copy"><span class="name">' + escapeHtml(productName(product)) + '</span><span class="role">' + escapeHtml(productDescription(product) || "Product") + '</span></span>' +
            '</button>'
        );
    }).join("");
}

function renderProductBankControls() {
    const order = ["angle", "material", "context", "lighting"];
    const keys = order.filter((key) => Array.isArray(shellState.productBanks[key]));
    Object.keys(shellState.productBanks).forEach((key) => {
        if (!keys.includes(key) && Array.isArray(shellState.productBanks[key])) keys.push(key);
    });
    if (!keys.length) return '<div class="product-empty">No product banks found.</div>';
    return keys.map((key) => {
        const options = shellState.productBanks[key] || [];
        return (
            '<label class="field product-bank-field"><span class="t-label">' + escapeHtml(key) + '</span>' +
                '<select class="select" id="product-bank-' + escapeHtml(key) + '">' +
                    options.map((option, index) => '<option value="' + escapeHtml(option) + '"' + (index === 0 ? " selected" : "") + '>' + escapeHtml(option) + '</option>').join("") +
                '</select></label>'
        );
    }).join("");
}

async function selectProduct(productIdValue) {
    shellState.selectedProductId = productIdValue;
    renderProductsContent();
}

function collectProductSelections() {
    const selections = {
        product_description: document.getElementById("product-description-input")?.value.trim() || document.getElementById("product-name-input")?.value.trim() || "high-end professional product",
    };
    Object.keys(shellState.productBanks).forEach((key) => {
        const el = document.getElementById("product-bank-" + key);
        if (el && el.value) selections[key] = el.value;
    });
    return selections;
}

async function buildProductRecipe() {
    const output = document.getElementById("product-prompt-output");
    const meta = document.getElementById("product-recipe-meta");
    try {
        if (meta) meta.textContent = "building";
        const resp = await fetch("/api/build-recipe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: "product", selections: collectProductSelections() }),
        });
        const recipe = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(recipe.detail || recipe.error || "HTTP " + resp.status);
        shellState.productRecipe = recipe;
        if (output) output.value = recipe.prompt || "";
        if (meta) meta.textContent = "seed " + (recipe.seed ?? "n/a");
    } catch (e) {
        if (meta) meta.textContent = "error";
        if (output) output.value = "Build failed: " + (e?.message || e);
    }
}

async function copyProductPrompt() {
    const output = document.getElementById("product-prompt-output");
    const status = document.getElementById("product-copy-status");
    if (!output || !output.value) return;
    try {
        await navigator.clipboard.writeText(output.value);
        if (status) status.textContent = "copied";
    } catch (_e) {
        output.select();
        if (status) status.textContent = "selected";
    }
    setTimeout(() => { if (status) status.textContent = ""; }, 1800);
}

function renderSettingsTab() {
    const view = getShellView();
    if (!view) return;
    view.innerHTML = `
        <div class="view-inner settings-container">
            <div class="view-header">
                <div>
                    <div class="eyebrow">System</div>
                    <h1>Settings</h1>
                    <p class="sub">Configure provider routing, local model hosts, ComfyUI endpoints, and Spark workflow defaults.</p>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" onclick="saveAllSettings()">Save All</button>
                    <div id="settings-toast" class="test-result"></div>
                </div>
            </div>

            <section class="panel settings-panel">
                <div class="panel-header"><div class="title">Backend Mode</div><div class="meta">runtime routing</div></div>
                <div class="panel-body settings-mode-row">
                    <span class="backend-label" id="backend-label-local">Local</span>
                    <label class="settings-switch" title="Toggle backend mode">
                        <input type="checkbox" id="cfg-backend-mode" onchange="onBackendModeToggle()">
                        <span></span>
                    </label>
                    <span class="backend-label" id="backend-label-api">API</span>
                </div>
            </section>

            <div class="settings-grid settings-flow-grid">
                <section class="panel settings-panel settings-card-wide lmstudio-card">
                    <div class="panel-header"><div class="title"><span class="settings-step">1</span> Local Model Server</div><div class="meta">LM Studio</div></div>
                    <div class="panel-body">
                        <p class="card-desc">LM Studio connection used by Hermes chat and Vision audit.</p>
                        <div class="settings-form-grid">
                            <label class="form-row"><span>Host</span><input class="input" type="text" id="cfg-lmstudio-host" placeholder="http://localhost" onchange="markDirty('models.hermes_3.host')"></label>
                            <label class="form-row small"><span>Port</span><input class="input" type="number" id="cfg-lmstudio-port" placeholder="1234" onchange="markDirty('models.hermes_3.port')"></label>
                            <label class="form-row"><span>Chat Model</span><input class="input" type="text" id="cfg-lmstudio-model" placeholder="qwen3.6-35b-a3b" onchange="markDirty('models.hermes_3.model_name')"></label>
                            <label class="form-row"><span>Vision Model</span><input class="input" type="text" id="cfg-visual-model" placeholder="qwen3.6-35b-a3b" onchange="markDirty('models.kimi_vl.model_name')"></label>
                            <label class="form-row settings-span-2"><span>Vision Endpoint</span><input class="input" type="text" id="cfg-vision-endpoint-api1" placeholder="http://localhost:1234/v1" onchange="markDirty('models.kimi_vl.endpoint_api1')"></label>
                        </div>
                        <div class="card-actions">
                            <button class="btn" onclick="testLMStudio()">Test & Detect</button>
                            <button class="btn" onclick="loadLMStudioModel()">Load Model</button>
                            <button class="btn" onclick="testVision()">Test Vision</button>
                            <button class="btn btn-primary" onclick="reloadHermesVision()">Reload Hermes/Vision</button>
                        </div>
                        <div class="settings-result-grid">
                            <div id="lmstudio-test-result" class="test-result"></div>
                            <div id="vision-test-result" class="test-result"></div>
                        </div>
                        <div id="lmstudio-models-list" class="settings-model-select" style="display:none;">
                            <label class="t-label">Available Models</label>
                            <select id="lmstudio-models-select" class="select" onchange="document.getElementById('cfg-lmstudio-model').value=this.value;markDirty('models.hermes_3.model_name');"></select>
                        </div>
                    </div>
                </section>

                <section class="panel settings-panel ai-provider-card">
                    <div class="panel-header"><div class="title"><span class="settings-step">2</span> Cloud Director API</div><div class="meta">optional</div></div>
                    <div class="panel-body">
                        <p class="card-desc">Remote API used for director planning when API mode is active.</p>
                        <div class="settings-form-grid settings-form-grid-single">
                            <label class="form-row"><span>API Key</span><input class="input" type="password" id="cfg-kimi-api-key" placeholder="Bearer token..." onchange="markDirty('kimi.api_key')"></label>
                            <label class="form-row"><span>Provider Endpoint</span><input class="input" type="text" id="cfg-kimi-endpoint" placeholder="https://integrate.api.nvidia.com/v1/chat/completions" onchange="markDirty('kimi.endpoint')"></label>
                            <label class="form-row"><span>Director Model</span><input class="input" type="text" id="cfg-director-model" placeholder="moonshotai/kimi-k2-instruct" onchange="markDirty('models.director_kimi.model_name')"></label>
                            <label class="form-row"><span>Director Endpoint</span><input class="input" type="text" id="cfg-director-endpoint-api1" placeholder="https://integrate.api.nvidia.com/v1/chat/completions" onchange="markDirty('models.director_kimi.endpoint_api1')"></label>
                        </div>
                        <div class="card-actions">
                            <button class="btn" onclick="testProvider()">Test Provider</button>
                            <button class="btn" onclick="testDirector()">Test Director</button>
                        </div>
                        <div class="settings-result-grid">
                            <div id="kimi-test-result" class="test-result"></div>
                            <div id="director-test-result" class="test-result"></div>
                        </div>
                    </div>
                </section>

                <section class="panel settings-panel comfy-card">
                    <div class="panel-header"><div class="title"><span class="settings-step">3</span> Render Workers</div><div class="meta">Spark / ComfyUI</div></div>
                    <div class="panel-body">
                        <p class="card-desc">Spark and ComfyUI endpoints used by image and video generation.</p>
                        <div class="settings-form-grid settings-form-grid-single">
                            <label class="form-row"><span>Spark Primary WebSocket</span><input class="input" type="text" id="cfg-spark-primary" placeholder="ws://localhost:8000" onchange="markDirty('spark.primary')"></label>
                            <label class="form-row"><span>Spark Secondary WebSocket</span><input class="input" type="text" id="cfg-spark-secondary" placeholder="ws://localhost:8001" onchange="markDirty('spark.secondary')"></label>
                            <label class="form-row"><span>Spark Workflow File</span><input class="input" type="text" id="cfg-spark-workflow" placeholder="workflows/01_flux2_text_to_image.json" onchange="markDirty('spark.workflow_file')"></label>
                            <label class="form-row"><span>ComfyUI Primary</span><input class="input" type="text" id="cfg-comfyui-primary" placeholder="http://localhost:8188" onchange="markDirty('comfyui.primary')"></label>
                            <label class="form-row"><span>ComfyUI Secondary</span><input class="input" type="text" id="cfg-comfyui-secondary" placeholder="http://localhost:8189" onchange="markDirty('comfyui.secondary')"></label>
                        </div>
                        <div class="card-actions"><button class="btn" onclick="testComfyUIAll()">Test Render Workers</button></div>
                        <div class="server-status-row" id="comfyui-server-status">
                            <span class="server-status-item"><span class="server-dot" id="server-dot-primary"></span>Primary</span>
                            <span class="server-status-item"><span class="server-dot" id="server-dot-secondary"></span>Secondary</span>
                            <span class="server-status-item"><span class="server-dot" id="server-dot-spark"></span>Spark</span>
                        </div>
                        <div id="comfyui-test-result" class="test-result"></div>
                    </div>
                </section>

                <section class="panel settings-panel settings-card-wide bank-editor-card">
                    <div class="panel-header"><div class="title"><span class="settings-step">4</span> Bank Editor</div><div class="meta">prompt variation banks</div></div>
                    <div class="panel-body">
                        <p class="card-desc">Default prompt bank entries used by character variation templates.</p>
                        <div class="settings-bank-grid">
                            <label class="form-row"><span>Pose Bank</span><textarea class="textarea" id="cfg-bank-pose" rows="7" spellcheck="false">standing neutral
sitting
walking
running
jumping
leaning
lying down
profile view
back view</textarea></label>
                            <label class="form-row"><span>View Bank</span><textarea class="textarea" id="cfg-bank-view" rows="7" spellcheck="false">front view
side view
three-quarter view
bird's eye view
worm's eye view
close up
medium shot
full body</textarea></label>
                            <label class="form-row"><span>Lighting Bank</span><textarea class="textarea" id="cfg-bank-lighting" rows="7" spellcheck="false">golden hour
motivated source-based light
soft studio light
hard shadows
neon glow
moonlight
overcast
high key
low key</textarea></label>
                            <label class="form-row"><span>Background Bank</span><textarea class="textarea" id="cfg-bank-background" rows="7" spellcheck="false">urban street
lush forest
minimalist white studio
cyberpunk cityscape
desert dunes
cozy interior
mountain range
beach</textarea></label>
                        </div>
                        <div class="card-actions"><button class="btn" onclick="savePromptBanks()">Save Banks</button></div>
                        <div id="settings-bank-result" class="test-result"></div>
                    </div>
                </section>
            </div>
        </div>
    `;
}

async function fetchCharacters() {
    const resp = await fetch("/api/characters");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const payload = await resp.json();
    shellState.characters = normalizeCharacters(payload).map((char) => ({ ...char, id: characterId(char) }));
    if (!shellState.selectedCharacterId && shellState.characters.length) {
        shellState.selectedCharacterId = shellState.characters[0].id;
    }
    if (!shellState.characters.some((c) => c.id === shellState.selectedCharacterId)) {
        shellState.selectedCharacterId = shellState.characters[0]?.id || "";
    }
    return shellState.characters;
}

async function refreshCharacterSummary() {
    try {
        const chars = await fetchCharacters();
        const count = document.getElementById("home-character-count");
        if (count) count.textContent = String(chars.length);
        loadCharacters();
    } catch (_e) {
        const count = document.getElementById("home-character-count");
        if (count) count.textContent = "offline";
    }
}

async function renderCharactersTab() {
    const view = getShellView();
    if (!view) return;
    view.innerHTML =
        '<div class="view-inner">' +
            '<div class="view-header">' +
                '<div><div class="eyebrow">Identity System</div><h1>Characters</h1><p class="sub">Character portraits, DNA traits, render prompts, and variation history.</p></div>' +
                '<div class="actions"><button class="btn btn-primary" onclick="openCharacterCreate()">New Character</button><button class="btn" onclick="renderCharactersTab()">Refresh</button></div>' +
            '</div>' +
            '<div id="character-create" class="panel character-create hidden">' + renderCharacterCreateForm() + '</div>' +
            '<div id="character-error" class="character-error hidden"></div>' +
            '<div id="character-content" class="character-loading">Loading characters...</div>' +
        '</div>';

    try {
        await fetchCharacters();
        await renderCharactersContent();
    } catch (e) {
        const err = document.getElementById("character-error");
        const content = document.getElementById("character-content");
        if (err) {
            err.classList.remove("hidden");
            err.textContent = "Character API unavailable: " + (e?.message || e);
        }
        if (content) content.innerHTML = "";
    }
}

function renderCharacterCreateForm() {
    return (
        '<form id="character-create-form" class="character-create-form" onsubmit="createCharacter(event)">' +
            '<div class="field"><label class="t-label" for="new-character-name">Name</label><input class="input" id="new-character-name" name="name" required placeholder="Sienna Vale"></div>' +
            '<div class="field grow"><label class="t-label" for="new-character-description">Description</label><input class="input" id="new-character-description" name="description" placeholder="Role, silhouette, core visual identity"></div>' +
            '<div class="field"><label class="t-label" for="new-character-anchor">Character Image</label><input class="input" id="new-character-anchor" name="anchor_image" type="file" accept="image/png,image/jpeg,image/webp"></div>' +
            '<div class="character-create-actions"><button class="btn btn-primary" type="submit">Create</button><button class="btn btn-ghost" type="button" onclick="openCharacterCreate(false)">Cancel</button></div>' +
        '</form>'
    );
}

function openCharacterCreate(force) {
    const el = document.getElementById("character-create");
    if (!el) return;
    const show = force === undefined ? el.classList.contains("hidden") : !!force;
    el.classList.toggle("hidden", !show);
    if (show) document.getElementById("new-character-name")?.focus();
}

async function createCharacter(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = true;
    try {
        const data = new FormData(form);
        const resp = await fetch("/api/characters", { method: "POST", body: data });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        shellState.selectedCharacterId = characterId({ id: payload.id || data.get("name") });
        openCharacterCreate(false);
        form.reset();
        await renderCharactersTab();
    } catch (e) {
        const err = document.getElementById("character-error");
        if (err) {
            err.classList.remove("hidden");
            err.textContent = "Create failed: " + (e?.message || e);
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function renderCharactersContent() {
    const content = document.getElementById("character-content");
    if (!content) return;
    if (!shellState.characters.length) {
        content.innerHTML =
            '<section class="panel character-empty"><div class="panel-body"><h2 class="t-h2">No characters yet</h2><p class="t-meta">Create the first character and attach a character image.</p><button class="btn btn-primary" onclick="openCharacterCreate(true)">New Character</button></div></section>';
        return;
    }

    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId) || shellState.characters[0];
    shellState.selectedCharacterId = selected.id;
    const collapsed = !!shellState.charactersRosterCollapsed;
    content.innerHTML =
        '<div class="character-tab-grid' + (collapsed ? ' roster-collapsed' : '') + '">' +
            '<aside class="character-sidebar" aria-label="Character roster">' +
                '<div class="section-head character-roster-head"><h2>Roster</h2><div class="bar"></div><span class="meta">' + shellState.characters.length + '</span><button class="btn btn-ghost character-roster-toggle" type="button" aria-expanded="' + String(!collapsed) + '" onclick="toggleCharacterRoster()">' + (collapsed ? "Show" : "Hide") + '</button></div>' +
                '<div class="char-selector">' + shellState.characters.map(renderCharacterPick).join("") + '</div>' +
            '</aside>' +
            '<section class="character-workspace">' + renderCharacterDetail(selected) + '</section>' +
        '</div>';
    await loadCharacterVariations(selected.id);
}

async function toggleCharacterRoster() {
    shellState.charactersRosterCollapsed = !shellState.charactersRosterCollapsed;
    await renderCharactersContent();
}

function renderCharacterPick(char) {
    const active = char.id === shellState.selectedCharacterId ? " active" : "";
    const score = Number(char.score || 0);
    const refs = characterReferences(char).filter((r) => r.master).length;
    return (
        '<button class="char-pick card interactive' + active + '" type="button" onclick="selectCharacter(\'' + escapeHtml(char.id) + '\')">' +
            '<span class="portrait">' + renderPortrait(char, 56) + '</span>' +
            '<span class="char-pick-copy"><span class="name">' + escapeHtml(characterName(char)) + '</span><span class="role">' + escapeHtml(char.role || char.description || "Character") + '</span><span class="role">' + escapeHtml(characterStatus(char)) + ' | ' + refs + ' master ref(s)</span></span>' +
            '<span class="badge b-accent">' + String(score || 0) + '</span>' +
        '</button>'
    );
}

function renderCharacterDetail(char) {
    const score = Number(char.score || 0);
    const prompt = withCharacterNoTextRule(char.anchor_prompt || ("Portrait of " + characterName(char)));
    const refs = characterReferences(char);
    const masterRefs = refs.filter((r) => r.master);
    return (
        '<div class="char-hero">' +
            '<section class="panel anchor-card">' +
                '<div class="anchor-img">' + renderPortrait(char, 420) + '</div>' +
                '<div class="anchor-footer">' +
                    '<div class="consistency"><span class="score">' + String(score || 0) + '% consistency | ' + escapeHtml(characterStatus(char)) + '</span><div class="progress"><div class="fill" style="width:' + Math.max(0, Math.min(100, score)) + '%"></div></div><span class="t-meta">' + masterRefs.length + ' master ref(s) | ' + characterRenderHistoryCount(char) + ' render(s) | used in ' + characterUsedInShots(char) + ' shot(s) | last ' + escapeHtml(characterLastUsed(char)) + '</span></div>' +
                    '<a class="btn" href="/api/characters/' + encodeURIComponent(char.id) + '/export-package" target="_blank" rel="noreferrer">Export Package</a>' +
                '</div>' +
            '</section>' +
            '<section class="panel dna-editor">' +
                '<div class="panel-header"><div class="title">' + escapeHtml(characterName(char)) + '</div><div class="meta">' + escapeHtml(char.role || "Character") + '</div></div>' +
                '<div class="dna-body">' +
                    '<div class="dna-pane">' +
                        '<h3>Profile Kit</h3>' +
                        '<div class="character-profile-fields">' +
                            '<label>Status<select class="input" id="character-status-editor"><option value="draft"' + (char.status === "draft" ? " selected" : "") + '>Draft</option><option value="needs_review"' + (char.status === "needs_review" ? " selected" : "") + '>Needs Review</option><option value="production_approved"' + (char.status === "production_approved" ? " selected" : "") + '>Production Approved</option><option value="deprecated"' + (char.status === "deprecated" ? " selected" : "") + '>Deprecated</option></select></label>' +
                            '<label>Bio<textarea class="textarea character-mini-textarea" id="character-bio-editor">' + escapeHtml(char.bio || char.description || "") + '</textarea></label>' +
                            '<label>Personality Notes<textarea class="textarea character-mini-textarea" id="character-personality-editor">' + escapeHtml(char.personality_notes || "") + '</textarea></label>' +
                            '<label>Voice Profile<input class="input" id="character-voice-editor" value="' + escapeHtml(char.voice_profile || "") + '" placeholder="accent, cadence, vocal age"></label>' +
                            '<label>Gait / Performance<input class="input" id="character-gait-editor" value="' + escapeHtml(char.gait_style || "") + '" placeholder="posture, walk cycle, gesture habits"></label>' +
                        '</div>' +
                        '<h3>DNA JSON</h3>' +
                        '<textarea class="textarea dna-textarea" id="character-dna-editor" spellcheck="false">' + escapeHtml(characterDnaText(char)) + '</textarea>' +
                        '<div class="character-actions"><button class="btn btn-primary" onclick="saveSelectedCharacterProfile()">Save Profile</button><button class="btn" onclick="saveSelectedCharacterDna()">Save DNA Only</button><button class="btn" onclick="renderCharacterPrompt()">Render Character</button><span class="t-meta" id="character-save-status"></span></div>' +
                    '</div>' +
                    '<div class="dna-pane dna-preview">' +
                        '<h4>Character Prompt</h4><p id="character-anchor-prompt">' + escapeHtml(prompt) + '</p>' +
                        '<h4>Master References</h4>' + renderCharacterReferenceStrip(refs) +
                        '<h4>Extracted Sheet Panels</h4>' + renderCharacterSheetPanels(char) +
                        '<form class="character-reference-upload" onsubmit="uploadSelectedCharacterReference(event)">' +
                            '<input class="input" name="reference_image" type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm" required>' +
                            '<select class="input" name="reference_type"><option value="auto">Auto Type</option><option value="face_closeup">Face</option><option value="full_body">Full Body</option><option value="outfit">Outfit</option><option value="expression_sheet">Expression Sheet</option><option value="pose">Pose</option><option value="motion_clip">Motion Clip</option></select>' +
                            '<button class="btn" type="submit">Upload Ref</button>' +
                        '</form>' +
                        '<h4>Fixed Traits</h4>' + renderDnaPreview(char) +
                        '<h4>Production Actions</h4>' + renderCharacterProductionActions(char) +
                        '<div class="character-benchmark-output" id="character-benchmark-output"></div>' +
                    '</div>' +
                '</div>' +
            '</section>' +
        '</div>' +
        '<section class="panel character-variations-panel">' +
            '<div class="panel-header"><div class="title">Variations</div><div class="meta" id="character-variation-count">loading</div></div>' +
            '<div class="panel-body"><div class="filter-chips"><button class="chip active" type="button">All</button><button class="chip" type="button">Pose</button><button class="chip" type="button">Lighting</button><button class="chip" type="button">Wardrobe</button></div><div class="var-gallery" id="character-variation-gallery"></div></div>' +
        '</section>'
    );
}

function renderDnaPreview(char) {
    const dna = char?.dna && typeof char.dna === "object" ? char.dna : {};
    const keys = Object.keys(dna);
    if (!keys.length) return '<p class="t-meta">No fixed DNA traits recorded.</p>';
    return '<div class="character-trait-grid">' + keys.slice(0, 8).map((key) => {
        const value = Array.isArray(dna[key]) ? dna[key].join(", ") : String(dna[key] ?? "");
        return '<div class="character-trait"><span>' + escapeHtml(key) + '</span><strong>' + escapeHtml(value) + '</strong></div>';
    }).join("") + '</div>';
}

function renderCharacterReferenceStrip(refs) {
    if (!refs.length) return '<p class="t-meta">No references yet. Upload or generate a character image, then lock strong outputs as master references.</p>';
    return '<div class="character-reference-strip">' + refs.slice(0, 8).map((ref) => {
        const type = ref.type || "reference";
        const badge = ref.master ? "LOCKED" : "REF";
        const isVideo = /\.(mp4|mov|webm)(\?|$)/i.test(ref.url || "");
        return (
            '<figure class="character-reference-thumb">' +
                (isVideo ? '<div class="character-video-ref">VIDEO</div>' : '<img class="character-zoomable" src="' + escapeHtml(ref.url || "") + '" alt="' + escapeHtml(type) + '" loading="lazy" data-zoom-src="' + escapeHtml(ref.url || "") + '" data-zoom-title="' + escapeHtml(type) + '" data-zoom-prompt="' + escapeHtml(ref.notes || ref.source || "") + '">') +
                '<figcaption><span>' + escapeHtml(badge) + '</span>' + escapeHtml(type) + (!ref.master && !isVideo ? '<button type="button" onclick="lockCharacterReferenceAsMaster(\'' + escapeHtml(ref.url || "") + '\', \'' + escapeHtml(type) + '\')">Lock</button>' : '') + '</figcaption>' +
            '</figure>'
        );
    }).join("") + '</div>';
}

function renderCharacterSheetPanels(char) {
    const panels = Array.isArray(char?.sheet_panels) ? char.sheet_panels : [];
    if (!panels.length) {
        return '<p class="t-meta">No sheet panels extracted yet. Generate a character sheet, then click Extract Panels on the sheet result.</p>';
    }
    return '<div class="character-reference-strip character-panel-strip">' + panels.slice(-16).reverse().map((panel) => {
        const type = panel.type || "sheet_panel";
        return (
            '<figure class="character-reference-thumb character-panel-thumb">' +
                '<img class="character-zoomable" src="' + escapeHtml(panel.url || "") + '" alt="' + escapeHtml(type) + '" loading="lazy" data-zoom-src="' + escapeHtml(panel.url || "") + '" data-zoom-title="' + escapeHtml(type) + '" data-zoom-prompt="' + escapeHtml(panel.notes || "sheet panel") + '">' +
                '<figcaption><span>' + escapeHtml(String((panel.panel_index ?? 0) + 1)) + '</span>' + escapeHtml(type) + '<button type="button" onclick="lockCharacterReferenceAsMaster(\'' + escapeHtml(panel.url || "") + '\', \'' + escapeHtml(type) + '\')">Lock</button></figcaption>' +
            '</figure>'
        );
    }).join("") + '</div>';
}

function renderCharacterProductionActions(char) {
    const anchor = characterImage(char);
    const latestSheet = Array.isArray(char?.candidate_assets)
        ? [...char.candidate_assets].reverse().find((asset) => asset?.type === "sheet" && asset?.url)
        : null;
    return (
        '<div class="character-op-grid">' +
            '<button class="btn" type="button" onclick="loadSelectedCharacterBenchmarks()">Load Benchmarks</button>' +
            '<button class="btn" type="button" onclick="auditSelectedCharacterPrompt()">Audit Current Prompt</button>' +
            '<button class="btn" type="button" onclick="lockSelectedCharacterAnchor()" ' + (anchor ? "" : "disabled") + '>Lock Anchor as Master</button>' +
            '<button class="btn" type="button" onclick="extractLatestCharacterSheetPanels()" ' + (latestSheet ? "" : "disabled") + '>Extract Latest Sheet</button>' +
            '<button class="btn" type="button" onclick="selectCharacterForForge(\'' + escapeHtml(char.id) + '\')">Send to Forge</button>' +
        '</div>' +
        '<p class="t-meta">Character sheets can be split into reusable typed references. Training, video continuity, and collaboration are tracked in the profile schema until backing services exist.</p>'
    );
}

async function selectCharacter(charId) {
    shellState.selectedCharacterId = charId;
    characterForgeSelectedId = charId;
    await renderCharactersContent();
    syncCharacterForgeSelectionUi();
}

async function saveSelectedCharacterDna() {
    const editor = document.getElementById("character-dna-editor");
    const status = document.getElementById("character-save-status");
    if (!editor || !shellState.selectedCharacterId) return;
    try {
        const dna = JSON.parse(editor.value || "{}");
        const resp = await fetch("/api/characters/save-dna", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: shellState.selectedCharacterId, dna }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        if (status) status.textContent = payload.status || "saved";
        const char = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
        if (char) char.dna = dna;
        setTimeout(() => { if (status) status.textContent = ""; }, 2200);
    } catch (e) {
        if (status) status.textContent = "Invalid DNA: " + (e?.message || e);
    }
}

async function saveSelectedCharacterProfile() {
    const editor = document.getElementById("character-dna-editor");
    const status = document.getElementById("character-save-status");
    if (!editor || !shellState.selectedCharacterId) return;
    try {
        const visualDna = JSON.parse(editor.value || "{}");
        const resp = await fetch("/api/characters/" + encodeURIComponent(shellState.selectedCharacterId) + "/profile", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                status: document.getElementById("character-status-editor")?.value || "draft",
                bio: document.getElementById("character-bio-editor")?.value || "",
                personality_notes: document.getElementById("character-personality-editor")?.value || "",
                voice_profile: document.getElementById("character-voice-editor")?.value || "",
                gait_style: document.getElementById("character-gait-editor")?.value || "",
                visual_dna: visualDna,
            }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const idx = shellState.characters.findIndex((c) => c.id === shellState.selectedCharacterId);
        if (idx >= 0) shellState.characters[idx] = { ...payload, id: characterId(payload) };
        if (status) status.textContent = "profile saved";
        setTimeout(() => { if (status) status.textContent = ""; }, 2200);
        await renderCharactersContent();
    } catch (e) {
        if (status) status.textContent = "Save failed: " + (e?.message || e);
    }
}

async function uploadSelectedCharacterReference(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const status = document.getElementById("character-save-status");
    if (!shellState.selectedCharacterId) return;
    const btn = form.querySelector("button");
    if (btn) btn.disabled = true;
    try {
        const data = new FormData(form);
        const resp = await fetch("/api/characters/" + encodeURIComponent(shellState.selectedCharacterId) + "/references", {
            method: "POST",
            body: data,
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const idx = shellState.characters.findIndex((c) => c.id === shellState.selectedCharacterId);
        if (idx >= 0) shellState.characters[idx] = { ...payload, id: characterId(payload) };
        form.reset();
        if (status) status.textContent = "reference uploaded";
        await renderCharactersContent();
    } catch (e) {
        if (status) status.textContent = "Upload failed: " + (e?.message || e);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function lockSelectedCharacterAnchor() {
    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
    const status = document.getElementById("character-save-status");
    const url = characterImage(selected);
    if (!selected || !url) return;
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(selected.id) + "/master-reference", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, type: "face_closeup", source: "anchor_lock", score: selected.score || 0 }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const idx = shellState.characters.findIndex((c) => c.id === selected.id);
        if (idx >= 0) shellState.characters[idx] = { ...payload, id: characterId(payload) };
        if (status) status.textContent = "master reference locked";
        await renderCharactersContent();
    } catch (e) {
        if (status) status.textContent = "Lock failed: " + (e?.message || e);
    }
}

async function lockCharacterReferenceAsMaster(url, type) {
    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
    const status = document.getElementById("character-save-status");
    if (!selected || !url) return;
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(selected.id) + "/master-reference", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, type: type || "reference", source: "manual_reference_lock", score: selected.score || 0 }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const idx = shellState.characters.findIndex((c) => c.id === selected.id);
        if (idx >= 0) shellState.characters[idx] = { ...payload, id: characterId(payload) };
        if (status) status.textContent = "reference locked as master";
        await renderCharactersContent();
    } catch (e) {
        if (status) status.textContent = "Lock failed: " + (e?.message || e);
    }
}

async function extractLatestCharacterSheetPanels() {
    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
    const latestSheet = Array.isArray(selected?.candidate_assets)
        ? [...selected.candidate_assets].reverse().find((asset) => asset?.type === "sheet" && asset?.url)
        : null;
    if (!selected || !latestSheet) return;
    await extractCharacterSheetPanelsFromRender(selected.id, latestSheet.url, latestSheet.prompt_id || "");
}

async function auditSelectedCharacterPrompt() {
    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
    const output = document.getElementById("character-benchmark-output");
    const status = document.getElementById("character-save-status");
    if (!selected) return;
    const prompt = withCharacterNoTextRule(selected.anchor_prompt || document.getElementById("character-anchor-prompt")?.textContent || characterName(selected));
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(selected.id) + "/audit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                image_url: characterImage(selected),
                prompt,
                render_type: "character",
            }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        if (output) {
            output.innerHTML =
                '<div class="character-audit-result">' +
                    '<strong>' + escapeHtml(payload.status || "audit") + ' | ' + String(payload.overall_score || 0) + '</strong>' +
                    '<span>face ' + String(payload.face_score || 0) + ' | body ' + String(payload.body_score || 0) + ' | wardrobe ' + String(payload.wardrobe_score || 0) + '</span>' +
                    '<p>' + escapeHtml((payload.fail_reasons || []).join("; ") || "No blocking issues from heuristic audit.") + '</p>' +
                '</div>';
        }
        if (status) status.textContent = "audit complete";
        await fetchCharacters();
    } catch (e) {
        if (status) status.textContent = "Audit failed: " + (e?.message || e);
    }
}

async function loadSelectedCharacterBenchmarks() {
    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
    const output = document.getElementById("character-benchmark-output");
    if (!selected || !output) return;
    output.textContent = "Loading benchmarks...";
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(selected.id) + "/benchmarks");
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        const benchmarks = Array.isArray(payload.benchmarks) ? payload.benchmarks : [];
        output.innerHTML = '<div class="character-benchmark-list">' + benchmarks.map((bench) => (
            '<details>' +
                '<summary>' + escapeHtml(bench.label || bench.id || "Benchmark") + '</summary>' +
                '<p>' + escapeHtml(bench.goal || "") + '</p>' +
                '<textarea class="textarea character-mini-textarea" readonly>' + escapeHtml(bench.compiled_prompt || "") + '</textarea>' +
            '</details>'
        )).join("") + '</div>';
    } catch (e) {
        output.textContent = "Benchmarks unavailable: " + (e?.message || e);
    }
}

async function renderCharacterPrompt() {
    const selected = shellState.characters.find((c) => c.id === shellState.selectedCharacterId);
    const status = document.getElementById("character-save-status");
    if (!selected) return;
    try {
        if (status) status.textContent = "rendering";
        const resp = await fetch("/api/characters/render", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: characterName(selected),
                prompt: withCharacterNoTextRule(selected.anchor_prompt || document.getElementById("character-anchor-prompt")?.textContent || characterName(selected)),
            }),
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.detail || payload.error || "HTTP " + resp.status);
        if (status) status.textContent = "character rendered";
        await renderCharactersTab();
    } catch (e) {
        if (status) status.textContent = "Render failed: " + (e?.message || e);
    }
}

async function loadCharacterVariations(charId) {
    const gallery = document.getElementById("character-variation-gallery");
    const count = document.getElementById("character-variation-count");
    if (!gallery) return;
    try {
        const resp = await fetch("/api/characters/" + encodeURIComponent(charId) + "/variations");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const variations = await resp.json();
        shellState.variations = Array.isArray(variations) ? variations : [];
        if (count) count.textContent = String(shellState.variations.length);
        if (!shellState.variations.length) {
            gallery.innerHTML = '<div class="character-empty-inline">No variations found for this character.</div>';
            return;
        }
        gallery.innerHTML = shellState.variations.map((item, index) => {
            const score = Number(item.score || 0);
            return (
                '<figure class="thumb character-variation-thumb" title="' + escapeHtml(item.prompt || item.id || "") + '">' +
                    '<img class="character-zoomable" src="' + escapeHtml(item.src || "") + '" alt="' + escapeHtml(item.id || "variation") + '" loading="lazy" data-zoom-src="' + escapeHtml(item.src || "") + '" data-zoom-title="' + escapeHtml(item.type || "variation") + '" data-zoom-prompt="' + escapeHtml(item.prompt || "") + '" data-zoom-seed="' + escapeHtml(item.seed || index) + '">' +
                    '<figcaption class="meta-overlay">' + escapeHtml(item.type || "variation") + ' | ' + String(score || 0) + ' | seed ' + escapeHtml(item.seed || index) + '</figcaption>' +
                '</figure>'
            );
        }).join("");
    } catch (e) {
        if (count) count.textContent = "error";
        gallery.innerHTML = '<div class="character-empty-inline">Variations unavailable: ' + escapeHtml(e?.message || e) + '</div>';
    }
}

// Close lightbox on Escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $lightboxModal && $lightboxModal.classList.contains("active")) {
        closeLightbox();
    }
});

document.addEventListener("dblclick", (event) => {
    const target = event.target?.closest?.(".character-zoomable");
    if (!target) return;
    const src = target.dataset.zoomSrc || target.getAttribute("src") || "";
    if (!src) return;
    event.preventDefault();
    openLightbox({
        image_url: src,
        variant: target.dataset.zoomTitle || target.getAttribute("alt") || "Character",
        seed: target.dataset.zoomSeed || "",
        workflow: "Characters",
        status: "preview",
        prompt: target.dataset.zoomPrompt || target.getAttribute("title") || "",
    });
});
