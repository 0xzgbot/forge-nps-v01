/* Cinesmith Agency — Adobe-tier EP console, command palette, production timeline */
(function (global) {
  "use strict";

  const STAGES = [
    { id: "brief", label: "Brief" },
    { id: "plan", label: "Plan" },
    { id: "critique", label: "Critique" },
    { id: "compile", label: "Compile" },
    { id: "render", label: "Render" },
    { id: "audit", label: "Audit" },
    { id: "memory", label: "Memory" },
    { id: "done", label: "Done" },
  ];

  let timelineState = {
    active: false,
    mode: "images", // images | story
    stage: "brief",
    message: "Ready for a brief",
    meta: "",
    progress: 0,
    events: [],
  };

  function toast(msg, type, ms) {
    if (global.CinesmithCore && CinesmithCore.toast) CinesmithCore.toast(msg, type, ms);
    else if (typeof globalToast === "function") globalToast(msg, type, ms);
  }

  function setTimeline(partial) {
    timelineState = Object.assign({}, timelineState, partial || {});
    renderTimeline();
    renderEpStatus();
  }

  function stageFromCampaignEvent(event) {
    const type = (event && event.type) || "";
    const map = {
      kimi: "plan",
      kimi_raw: "plan",
      kimi_plan: "plan",
      kimi_review: "critique",
      hermes: "compile",
      compiler: "compile",
      compile_errors: "compile",
      spark: "render",
      audit: "audit",
      memory: "memory",
      remediation: "compile",
      done: "done",
      error: "done",
      warning: "plan",
      profile: "brief",
    };
    return map[type] || timelineState.stage || "brief";
  }

  function progressFromStage(stage) {
    const idx = STAGES.findIndex(function (s) { return s.id === stage; });
    if (idx < 0) return timelineState.progress || 0;
    return Math.round((idx / (STAGES.length - 1)) * 100);
  }

  function onCampaignEvent(event) {
    if (!event) return;
    const stage = stageFromCampaignEvent(event);
    const msg = event.text || event.message || stage;
    const events = (timelineState.events || []).slice(-40);
    events.push({
      t: Date.now(),
      type: event.type || stage,
      text: String(msg).slice(0, 180),
    });
    setTimeline({
      active: event.type !== "done" && event.type !== "error",
      mode: "images",
      stage: stage,
      message: String(msg).slice(0, 160),
      meta: event.shot_id || event.campaign_id || event.status || "",
      progress: event.type === "done" ? 100 : progressFromStage(stage),
      events: events,
    });
    if (event.type === "done") {
      toast("Campaign complete — review the gallery.", "success");
    }
  }

  function renderTimeline() {
    const host = document.getElementById("agency-production-timeline");
    if (!host) return;
    const stage = timelineState.stage || "brief";
    const activeIdx = Math.max(0, STAGES.findIndex(function (s) { return s.id === stage; }));
    const pct = timelineState.progress || 0;

    const steps = STAGES.map(function (s, i) {
      let cls = "pt-step";
      if (i < activeIdx) cls += " done";
      if (i === activeIdx) cls += timelineState.active ? " active" : (stage === "done" ? " done" : " current");
      return (
        '<div class="' + cls + '" data-stage="' + s.id + '">' +
        '<span class="pt-dot"></span><span class="pt-label">' + s.label + "</span></div>"
      );
    }).join("");

    const recent = (timelineState.events || []).slice(-5).reverse().map(function (e) {
      return '<div class="pt-event"><em>' + escapeHtml(e.type) + "</em> " + escapeHtml(e.text) + "</div>";
    }).join("");

    host.innerHTML =
      '<div class="pt-head">' +
      "<div><strong>Production</strong><span>" + escapeHtml(timelineState.message || "Idle") + "</span></div>" +
      '<div class="pt-pct">' + pct + "%</div></div>" +
      '<div class="pt-track"><i style="width:' + pct + '%"></i></div>' +
      '<div class="pt-steps">' + steps + "</div>" +
      (recent ? '<div class="pt-events">' + recent + "</div>" : "");
  }

  function renderEpStatus() {
    const el = document.getElementById("ep-console-status");
    if (!el) return;
    el.textContent = timelineState.active
      ? (timelineState.stage || "running") + " · " + (timelineState.message || "")
      : (timelineState.stage === "done" ? "Last run complete" : "Hermes standing by");
    el.classList.toggle("live", !!timelineState.active);
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  /* ---------- Command palette (Cmd/Ctrl+K) ---------- */
  const COMMANDS = [
    { id: "agency", label: "Agency home", hint: "Brief Hermes", page: "create-view", keys: "1" },
    { id: "images", label: "Images · live campaign", hint: "Run with Hermes", page: "dashboard-view", keys: "2" },
    { id: "videos", label: "Videos · motion", hint: "Stills to motion", page: "spark-view", keys: "3" },
    { id: "characters", label: "Characters", hint: "Identity locks", page: "identity-view", keys: "4" },
    { id: "stories", label: "Stories", hint: "Multi-beat production", page: "script-view", keys: "5" },
    { id: "assets", label: "Assets", hint: "Brand / product packs", page: "products-view", keys: "6" },
    { id: "settings", label: "Settings", hint: "Spark · Director · keys", page: "settings-view", keys: "7" },
    { id: "memory", label: "Memory", hint: "Agency learning", page: "memory-view", keys: "8" },
    { id: "run-images", label: "Run live image campaign", hint: "From agency brief", action: "run-images" },
    { id: "run-story", label: "Produce as story", hint: "From agency brief", action: "run-story" },
    { id: "sample-brief", label: "Load sample EP brief", hint: "Neon courier stills", action: "sample-brief" },
    { id: "sheet-photo", label: "Character · sheet from photo", hint: "One photo → continuity", action: "sheet-photo" },
    { id: "first-last", label: "Videos · First → Last mode", hint: "Select two stills", action: "first-last" },
    { id: "new-episode", label: "Stories · new series episode", hint: "Multi-episode continuity", action: "new-episode" },
    { id: "coach", label: "Show getting-started guide", hint: "What next?", action: "coach" },
    { id: "readiness", label: "Refresh stack readiness", hint: "Hermes · Spark · Director", action: "readiness" },
    { id: "export", label: "Export story package", hint: "ZIP handoff", action: "export" },
    { id: "score", label: "Continuity scorecard", hint: "Story consistency", action: "score" },
    { id: "review", label: "Open review queue", hint: "Approve / reject frames", action: "review" },
  ];

  function ensurePalette() {
    let el = document.getElementById("cinesmith-cmdk");
    if (el) return el;
    el = document.createElement("div");
    el.id = "cinesmith-cmdk";
    el.innerHTML =
      '<div class="cmdk-backdrop" data-cmdk-close="1"></div>' +
      '<div class="cmdk-panel" role="dialog" aria-label="Command palette">' +
      '<div class="cmdk-input-row">' +
      '<span class="cmdk-kicker">Cinesmith</span>' +
      '<input id="cmdk-input" type="search" placeholder="Go anywhere, run Hermes…" autocomplete="off" />' +
      '<kbd>esc</kbd></div>' +
      '<div id="cmdk-results" class="cmdk-results"></div>' +
      '<div class="cmdk-foot">↑↓ navigate · ↵ select · ⌘K toggle</div></div>';
    document.body.appendChild(el);
    el.addEventListener("click", function (e) {
      if (e.target && e.target.getAttribute("data-cmdk-close")) closePalette();
    });
    const input = el.querySelector("#cmdk-input");
    input.addEventListener("input", function () { renderPaletteResults(input.value); });
    input.addEventListener("keydown", onPaletteKeydown);
    return el;
  }

  let paletteIndex = 0;
  let paletteItems = [];

  function openPalette() {
    const el = ensurePalette();
    el.classList.add("open");
    const input = el.querySelector("#cmdk-input");
    input.value = "";
    paletteIndex = 0;
    renderPaletteResults("");
    setTimeout(function () { input.focus(); }, 10);
  }

  function closePalette() {
    const el = document.getElementById("cinesmith-cmdk");
    if (el) el.classList.remove("open");
  }

  function filterCommands(q) {
    const query = (q || "").trim().toLowerCase();
    if (!query) return COMMANDS.slice();
    return COMMANDS.filter(function (c) {
      return (c.label + " " + c.hint + " " + (c.keys || "")).toLowerCase().indexOf(query) >= 0;
    });
  }

  function renderPaletteResults(q) {
    const host = document.getElementById("cmdk-results");
    if (!host) return;
    paletteItems = filterCommands(q);
    if (!paletteItems.length) {
      host.innerHTML = '<div class="cmdk-empty">No matches</div>';
      return;
    }
    if (paletteIndex >= paletteItems.length) paletteIndex = 0;
    host.innerHTML = paletteItems.map(function (c, i) {
      return (
        '<button type="button" class="cmdk-item' + (i === paletteIndex ? " active" : "") + '" data-idx="' + i + '">' +
        "<strong>" + escapeHtml(c.label) + "</strong>" +
        "<span>" + escapeHtml(c.hint || "") + "</span>" +
        (c.keys ? "<kbd>" + escapeHtml(c.keys) + "</kbd>" : "") +
        "</button>"
      );
    }).join("");
    host.querySelectorAll(".cmdk-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        runCommand(paletteItems[Number(btn.getAttribute("data-idx"))]);
      });
    });
  }

  function onPaletteKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      closePalette();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      paletteIndex = Math.min(paletteItems.length - 1, paletteIndex + 1);
      renderPaletteResults(e.target.value);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      paletteIndex = Math.max(0, paletteIndex - 1);
      renderPaletteResults(e.target.value);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (paletteItems[paletteIndex]) runCommand(paletteItems[paletteIndex]);
    }
  }

  function runCommand(cmd) {
    closePalette();
    if (!cmd) return;
    if (cmd.page && typeof switchPage === "function") {
      switchPage(cmd.page);
      if (cmd.page === "memory-view" && typeof loadMemoryTab === "function") loadMemoryTab();
      toast(cmd.label, "info", 1600);
      return;
    }
    if (cmd.action === "run-images") {
      const btn = document.getElementById("agency-run-images-btn");
      if (btn) btn.click();
      else if (typeof switchPage === "function") switchPage("dashboard-view");
      return;
    }
    if (cmd.action === "run-story") {
      const btn = document.getElementById("agency-run-story-btn");
      if (btn) btn.click();
      else if (typeof switchPage === "function") switchPage("script-view");
      return;
    }
    if (cmd.action === "readiness" && typeof refreshSystemReadiness === "function") {
      refreshSystemReadiness(true);
      return;
    }
    if (cmd.action === "export" && global.CinesmithProduct) {
      const sid =
        global.currentScriptProjectId ||
        (document.getElementById("script-project-id") || {}).value ||
        "";
      CinesmithProduct.exportStoryPackage(sid);
      return;
    }
    if (cmd.action === "score") {
      const btn = document.getElementById("story-scorecard-btn");
      if (btn) btn.click();
      else if (typeof switchPage === "function") switchPage("script-view");
      return;
    }
    if (cmd.action === "review") {
      if (typeof switchPage === "function") switchPage("dashboard-view");
      toast("Double-click a frame · A approve · R reject+remediate", "info", 4000);
      return;
    }
    if (cmd.action === "sample-brief") {
      if (typeof switchPage === "function") switchPage("create-view");
      if (global.CinesmithCoach && typeof CinesmithCoach.fillAgencyBrief === "function") {
        var sample =
          (CinesmithCoach.samples && CinesmithCoach.samples[0] && CinesmithCoach.samples[0].text) ||
          "8 cinematic stills of a courier on a rain-soaked rooftop at night, neon cyan and magenta rim light, anamorphic bokeh, no text";
        CinesmithCoach.fillAgencyBrief(sample);
      } else {
        toast("Open Agency and use Sample briefs chips", "info", 2800);
      }
      return;
    }
    if (cmd.action === "sheet-photo") {
      if (typeof switchPage === "function") switchPage("identity-view");
      setTimeout(function () {
        var btn = document.getElementById("char-sheet-from-photo-btn");
        if (btn) {
          btn.classList.add("cinesmith-coach-pulse");
          toast("Pick a face/body photo → Sheet from photo", "info", 3200);
        }
      }, 180);
      return;
    }
    if (cmd.action === "first-last") {
      if (typeof switchPage === "function") switchPage("spark-view");
      setTimeout(function () {
        var chip = document.getElementById("video-mode-first-last");
        if (chip) {
          chip.click();
          chip.classList.add("cinesmith-coach-pulse");
        }
        toast("Select two stills (start, then end), then produce motion", "info", 3600);
      }, 180);
      return;
    }
    if (cmd.action === "new-episode") {
      if (typeof switchPage === "function") switchPage("script-view");
      setTimeout(function () {
        if (typeof global.createNextSeriesEpisode === "function") {
          global.createNextSeriesEpisode();
        } else {
          toast("Set Series name on Brief, then New episode in series", "info", 3200);
        }
      }, 200);
      return;
    }
    if (cmd.action === "coach") {
      if (typeof switchPage === "function") switchPage("create-view");
      try {
        localStorage.removeItem("cinesmith_coach_dismissed");
      } catch (_e) {
        /* ignore */
      }
      if (global.CinesmithCoach && typeof CinesmithCoach.render === "function") CinesmithCoach.render();
      toast("Getting-started guide restored on Agency", "success", 2400);
    }
  }

  function initKeyboard() {
    document.addEventListener("keydown", function (e) {
      const tag = (e.target && e.target.tagName) || "";
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        const el = document.getElementById("cinesmith-cmdk");
        if (el && el.classList.contains("open")) closePalette();
        else openPalette();
        return;
      }
      if (e.key === "Escape") {
        closePalette();
      }
    });
  }

  /* ---------- EP console Hermes ask ---------- */
  async function askHermesEp() {
    const input = document.getElementById("ep-hermes-input");
    const log = document.getElementById("ep-hermes-log");
    if (!input || !log) return;
    const msg = (input.value || "").trim();
    if (!msg) return;
    input.value = "";
    appendEp(log, "you", msg);
    appendEp(log, "hermes", "…");
    const bubble = log.lastElementChild && log.lastElementChild.querySelector(".ep-bubble");
    try {
      const resp = await fetch("/api/hermes/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message:
            "You are the Cinesmith executive-producer assistant. Be concise, production-minded, and actionable.\n\n" +
            "User brief/context:\n" +
            ((document.getElementById("agency-brief-input") || {}).value || "(none)") +
            "\n\nUser message:\n" +
            msg,
          history: [],
          session_id: "ep_" + Date.now(),
        }),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let full = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;
          try {
            const data = JSON.parse(line);
            if (data.token) {
              full += data.token;
              if (bubble) bubble.textContent = full;
            }
            if (data.error) throw new Error(data.error);
          } catch (err) {
            if (err instanceof SyntaxError) continue;
            throw err;
          }
        }
      }
      if (!full && bubble) bubble.textContent = "(no response)";
      log.scrollTop = log.scrollHeight;
    } catch (err) {
      if (bubble) bubble.textContent = "Hermes unavailable: " + (err.message || err);
      toast("Hermes chat failed — check Settings / LM Studio", "error");
    }
  }

  function appendEp(log, who, text) {
    const empty = log.querySelector(".ep-empty");
    if (empty) empty.remove();
    const row = document.createElement("div");
    row.className = "ep-row " + who;
    row.innerHTML =
      '<div class="ep-who">' + (who === "you" ? "You" : "Hermes") + "</div>" +
      '<div class="ep-bubble"></div>';
    row.querySelector(".ep-bubble").textContent = text;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function wireEpConsole() {
    const send = document.getElementById("ep-hermes-send");
    const input = document.getElementById("ep-hermes-input");
    if (send && !send.dataset.bound) {
      send.dataset.bound = "1";
      send.addEventListener("click", askHermesEp);
    }
    if (input && !input.dataset.bound) {
      input.dataset.bound = "1";
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey && !(e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          askHermesEp();
        }
      });
    }

    // Quick EP actions
    document.querySelectorAll("[data-ep-quick]").forEach(function (btn) {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        const kind = btn.getAttribute("data-ep-quick");
        const agency = document.getElementById("agency-brief-input");
        if (kind === "improve" && agency && agency.value.trim()) {
          const input = document.getElementById("ep-hermes-input");
          if (input) {
            input.value = "Improve this production brief for a world-class stills campaign. Keep my intent, add shot count, lensing, lighting, continuity locks, and platform if relevant:\n\n" + agency.value.trim();
            askHermesEp();
          }
        }
        if (kind === "shotlist" && agency && agency.value.trim()) {
          const input = document.getElementById("ep-hermes-input");
          if (input) {
            input.value = "Turn this into a tight shot list (6–12 shots) with purpose, framing, and continuity notes:\n\n" + agency.value.trim();
            askHermesEp();
          }
        }
        if (kind === "story-beats" && agency && agency.value.trim()) {
          const input = document.getElementById("ep-hermes-input");
          if (input) {
            input.value = "Propose 4–6 story beats for multi-beat production (hook, develop, turn, pay off). Keep it cinematic:\n\n" + agency.value.trim();
            askHermesEp();
          }
        }
      });
    });
  }

  /* Hook campaign events if handleCampaignEvent exists */
  function patchCampaignHook() {
    if (typeof global.handleCampaignEvent !== "function") return;
    if (global.handleCampaignEvent.__agencyPatched) return;
    const orig = global.handleCampaignEvent;
    function wrapped(event) {
      try { onCampaignEvent(event); } catch (_e) {}
      return orig(event);
    }
    wrapped.__agencyPatched = true;
    global.handleCampaignEvent = wrapped;
  }

  function enhanceEmptyStates() {
    // Soft-touch empty copy if gallery placeholders exist
    const placeholders = document.querySelectorAll(".script-empty-mini, .creator-hermes-empty");
    // leave alone if already customized
  }

  function init() {
    ensurePalette();
    initKeyboard();
    wireEpConsole();
    renderTimeline();
    patchCampaignHook();
    // re-patch after app.js may redefine
    setTimeout(patchCampaignHook, 400);
    setTimeout(patchCampaignHook, 1500);
    enhanceEmptyStates();

    // Sidebar brand polish
    const brand = document.querySelector("#sidebar h1");
    if (brand && !brand.dataset.pro) {
      brand.dataset.pro = "1";
      brand.innerHTML = 'Cinesmith <span class="brand-sub">Agency</span>';
    }
  }

  global.CinesmithAgency = {
    init: init,
    openPalette: openPalette,
    closePalette: closePalette,
    setTimeline: setTimeline,
    onCampaignEvent: onCampaignEvent,
    timelineState: function () { return timelineState; },
  };

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(init, 80);
  });
})(window);
