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
const MAX_DASHBOARD_THUMBS = 180;
const MAX_VIDEO_THUMBS = 180;
let campaignSort = { key: "name", reverse: false };
let mediaSort = { key: "time", reverse: false };
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
const $sparkGrid = document.getElementById("spark-grid");
const $sparkStatusText = document.getElementById("spark-status-text");
const $sparkProgress = document.getElementById("spark-progress");
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
    const msk = document.getElementById("media-sort-key");
    const msr = document.getElementById("media-sort-reverse");
    if (msk) mediaSort.key = msk.value || "time";
    if (msr) mediaSort.reverse = !!msr.checked;
    syncInlineMediaSortControls();
    initDashboardResizer();
});

function id(s) { return document.getElementById(s); }

function onCampaignSortChange() {
    const key = document.getElementById("campaign-sort-key")?.value || "name";
    const reverse = !!document.getElementById("campaign-sort-reverse")?.checked;
    campaignSort = { key, reverse };
    loadCampaignFolders();
}

function onMediaSortChange() {
    const key = document.getElementById("media-sort-key")?.value || "time";
    const reverse = !!document.getElementById("media-sort-reverse")?.checked;
    mediaSort = { key, reverse };
    syncInlineMediaSortControls();
    loadShots();
    loadVideoLibrary();
}

function syncInlineMediaSortControls() {
    const keyInline = document.getElementById("media-sort-key-inline");
    const revInline = document.getElementById("media-sort-reverse-inline");
    if (keyInline) keyInline.value = mediaSort.key;
    if (revInline) revInline.checked = !!mediaSort.reverse;
}

function syncMediaSortFromInline() {
    const key = document.getElementById("media-sort-key-inline")?.value || "time";
    const reverse = !!document.getElementById("media-sort-reverse-inline")?.checked;
    mediaSort = { key, reverse };
    const keyMain = document.getElementById("media-sort-key");
    const revMain = document.getElementById("media-sort-reverse");
    if (keyMain) keyMain.value = key;
    if (revMain) revMain.checked = reverse;
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
                if ($briefInput && c.brief) {
                    $briefInput.value = c.brief;
                }
                loadShots();
                loadVideoLibrary();
                loadCampaignFolders();
            });
            row.appendChild(campaignBtn);

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

        // Kimi / NIM
        const kimi = currentConfig.kimi || {};
        const keyField = document.getElementById("cfg-kimi-api-key");
        keyField.value = "";
        keyField.placeholder = kimi.api_key_set ? "••••••••  (key saved — paste to replace)" : "nvapi-...";
        document.getElementById("cfg-kimi-endpoint").value = kimi.endpoint || "";

        // Models
        const models = currentConfig.models || {};

        // Director
        const director = models.director_kimi || {};
        document.getElementById("cfg-director-model").value = director.model_name || "";
        document.getElementById("cfg-director-endpoint").value = director.endpoint || "";

        // Thinking (Kimi VL)
        const kimiVl = models.kimi_vl || {};
        document.getElementById("cfg-thinking-model").value = kimiVl.model_name || "";
        document.getElementById("cfg-thinking-endpoint").value = kimiVl.endpoint || "";

        // Visual (same as kimi_vl for now, can be separate)
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
        'models.director_kimi.endpoint': () => document.getElementById("cfg-director-endpoint").value,
        'models.kimi_vl.model_name': () => document.getElementById("cfg-thinking-model").value,
        'models.kimi_vl.endpoint': () => document.getElementById("cfg-thinking-endpoint").value,
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
async function testKimi() {
    const $result = document.getElementById("kimi-test-result");
    const apiKey = document.getElementById("cfg-kimi-api-key").value;
    const endpoint = document.getElementById("cfg-kimi-endpoint").value;

    if (!apiKey || !endpoint) {
        $result.textContent = "Please fill in API key and endpoint";
        $result.className = "test-result err";
        return;
    }

    $result.textContent = "Testing connection...";
    $result.className = "test-result loading";

    try {
        const resp = await fetch("/api/test/kimi", {
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

    if (!primary && !secondary) {
        $result.textContent = "Please fill in at least one ComfyUI host URL";
        $result.className = "test-result err";
        return;
    }

    $result.textContent = "Testing ComfyUI hosts...";
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
    const parts = [p, s].filter(x => x.status !== "skipped").map(x => `${x.label}: ${x.status === "ok" ? "ok" : "fail"} (${x.msg})`);
    const anyFail = [p, s].some(x => x.status === "err");
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
    const zImage = document.getElementById("model-zimage")?.checked;
    const flux2 = document.getElementById("model-flux2")?.checked;
    const turbo = document.getElementById("model-turbo")?.checked;
    const workflow_ids = [];
    if (zImage) workflow_ids.push(turbo ? "spark_image_z_image_turbo" : "spark_image_z_image");
    if (flux2) workflow_ids.push(turbo ? "spark_image_flux2_text_to_image_turbo" : "spark_image_flux2_text_to_image");
    if (!workflow_ids.length) {
        addLogEntry("error", "Select at least one base model: Z-Image and/or Flux2.Dev");
        return;
    }

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
            body: JSON.stringify({ brief: brief, bible_path: biblePath, length: length, workflow_ids: workflow_ids }),
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
            addLogEntry("kimi", "Raw: " + text);
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
                        seed: s.seed || "Random",
                        kimi_plan: s.kimi_plan || null,
                        kimi_rationale: s.kimi_rationale || "",
                        skills_used: s.skills_used || [],
                        prompt_id: s.prompt_id || "",
                        audit_status: s.audit_status || "",
                        audit_score: s.audit_score ?? "",
                        audit_issues: s.audit_issues || [],
                        retry_of: s.retry_of || s.parent_shot_id || "",
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
            if (isRetry) {
                const b2 = document.createElement("span");
                b2.className = "audit-badge retry";
                b2.textContent = "RETRY";
                label.appendChild(b2);
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
                    seed: s.seed || "Random",
                    kimi_plan: s.kimi_plan || null,
                    kimi_rationale: s.kimi_rationale || "",
                    skills_used: s.skills_used || [],
                    prompt_id: s.prompt_id || "",
                    audit_status: s.audit_status || "",
                    audit_score: s.audit_score ?? "",
                    audit_issues: s.audit_issues || [],
                    retry_of: s.retry_of || s.parent_shot_id || "",
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

function updateVideoSelectionUI() {
    if ($videoSelectedCount) {
        let failedCount = 0;
        videoSelection.forEach(id => {
            const s = videoShotsById[id];
            if (s && s.audit_status === "fail") failedCount += 1;
        });
        $videoSelectedCount.value = videoSelection.size + " selected" + (failedCount ? (" (" + failedCount + " failed)") : "");
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
    const duration = parseInt($videoDuration?.value || "4", 10);
    const fps = parseInt($videoFps?.value || "24", 10);
    $startBatchBtn.disabled = true;
    $startBatchBtn.textContent = "Processing...";
    $sparkStatusText.textContent = "Processing " + videoSelection.size + " image(s) into videos...";
    try {
        const resp = await fetch("/api/video/process", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
                shot_ids: Array.from(videoSelection),
                duration,
                fps,
            }),
        });
        const data = await resp.json();
        if (data.status !== "ok") throw new Error(data.error || "Video processing failed");
        const done = (data.results || []).filter(r => r.status === "ok").length;
        $sparkStatusText.textContent = "Video processing complete: " + done + "/" + (data.results || []).length + " ok";
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

// Lightbox
function openLightbox(result) {
    if (!result) return;

    document.getElementById("lightbox-image").src = result.image_url || "";
    document.getElementById("lightbox-variant").textContent = "v" + (result.variant || "-");
    document.getElementById("lightbox-seed").textContent = result.seed || "Random";
    document.getElementById("lightbox-workflow").textContent = result.workflow || "-";
    document.getElementById("lightbox-status").textContent = result.status || "-";
    document.getElementById("lightbox-prompt").textContent = result.prompt || "-";
    document.getElementById("lightbox-negative-prompt").textContent = result.negative_prompt || "-";
    document.getElementById("lightbox-kimi-plan").textContent = result.kimi_plan ? JSON.stringify(result.kimi_plan) : "-";
    document.getElementById("lightbox-kimi-rationale").textContent = result.kimi_rationale || "-";
    document.getElementById("lightbox-skills-used").textContent = Array.isArray(result.skills_used) ? result.skills_used.join(", ") : "-";
    document.getElementById("lightbox-workflow-profile").textContent = result.workflow_profile || "-";
    const standardLabel = result.model_standard_name
        ? (result.model_standard_name + (result.model_standard_version ? " @" + result.model_standard_version : ""))
        : "-";
    document.getElementById("lightbox-model-standard").textContent = standardLabel;
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
    const nodes = Array.isArray(g.nodes) ? g.nodes : [];
    const edges = Array.isArray(g.edges) ? g.edges : [];
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

function initMemoryGraph(nodes, edges) {
  const el = document.getElementById('cy-canvas');
  if (!el || !window.cytoscape) return;
  if (window._memoryCy) { window._memoryCy.destroy(); }
  const MAX_NODES = 220;
  const useNodes = nodes.slice(-MAX_NODES);
  const allowedNodeIds = new Set(useNodes.map((n) => n.id));
  const useEdges = edges.filter((e) => allowedNodeIds.has(e.source) && allowedNodeIds.has(e.target));
  const cyNodes = (useNodes || []).map((n) => ({
    data: {
      id: n.id,
      label: n.label || n.id,
      type: n.type || "event",
      size: n.size || 20,
      ...(n.data || {}),
    },
  }));
  const cyEdges = (useEdges || []).map((e) => ({
    data: {
      id: e.id || (e.source + "->" + e.target),
      source: e.source,
      target: e.target,
      type: e.type || "link",
      label: e.label || "",
    },
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
          'width': (n) => n.data('size') || (n.data('type') === 'session' ? 28 : 18),
          'height': (n) => n.data('size') || (n.data('type') === 'session' ? 28 : 18),
          'shape': (n) => ({ session: 'diamond', insight: 'star', concept: 'rectangle' }[n.data('type')] || 'ellipse'),
        }
      },
      {
        selector: 'edge',
        style: {
          'line-color': '#2a2a2a', 'width': 1.5,
          'target-arrow-color': '#333', 'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
        }
      },
      { selector: ':selected', style: { 'border-width': 2, 'border-color': '#fff' } },
    ],
    layout: { name: 'cose', padding: 20, animate: false },
    userPanningEnabled: true,
    userZoomingEnabled: true,
  });
}

function memoryCyLayout(name) {
  if (!window._memoryCy) return;
  window._memoryCy.layout({ name, padding: 20, animate: true, animationDuration: 400 }).run();
}

async function triggerConsolidate() {
  const btn = event.currentTarget;
  btn.textContent = '⏳ Consolidating…';
  btn.disabled = true;
  try { await fetch('/api/memory/consolidate', { method: 'POST' }); } catch(e) {}
  btn.textContent = '✓ Done';
  setTimeout(() => { btn.textContent = '⚡ Consolidate Memory'; btn.disabled = false; }, 2000);
  loadMemoryTab();
}

// Close lightbox on Escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $lightboxModal.classList.contains("active")) {
        closeLightbox();
    }
});
