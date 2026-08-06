/* Product surface: Hermes-first Agency hub, wizard, export, scorecard, suggestions, audio honesty */
(function (global) {
  "use strict";

  const WIZARD_LOCAL = "cinesmith_setup_wizard_v2_done";

  async function loadCreateHub() {
    if (!global.CinesmithCore) return null;
    try {
      return await CinesmithCore.api("GET", "/api/product/create-hub");
    } catch (err) {
      CinesmithCore.reportError(err, "Agency hub unavailable");
      return null;
    }
  }

  async function loadSuggestions(brief, mode) {
    if (!global.CinesmithCore) return [];
    try {
      const q = new URLSearchParams({
        brief: brief || "",
        mode: mode || "auto",
        limit: "6",
      });
      const data = await CinesmithCore.api("GET", "/api/product/suggestions?" + q.toString());
      return data.suggestions || [];
    } catch (_e) {
      return [];
    }
  }

  async function exportStoryPackage(scriptId) {
    if (!scriptId) {
      CinesmithCore.toast("Select or run a story project first.", "warn");
      return null;
    }
    CinesmithCore.toast("Packaging story deliverables…", "info", 2200);
    try {
      const data = await CinesmithCore.api("POST", "/api/script/export-package?script_id=" + encodeURIComponent(scriptId));
      const silent = data.has_silent_clips ? " (some clips have no audio)" : "";
      CinesmithCore.toast(
        "Exported " + (data.video_count || 0) + " clips + " + (data.frame_count || 0) + " frames" + silent,
        data.has_silent_clips ? "warn" : "success",
        5000
      );
      if (data.download_url) {
        const a = document.createElement("a");
        a.href = data.download_url;
        a.download = "";
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      return data;
    } catch (err) {
      CinesmithCore.reportError(err, "Export failed");
      return null;
    }
  }

  async function loadScorecard(scriptId) {
    if (!scriptId || !global.CinesmithCore) return null;
    try {
      const data = await CinesmithCore.api("GET", "/api/product/scorecard/" + encodeURIComponent(scriptId));
      return data.scorecard || null;
    } catch (err) {
      CinesmithCore.reportError(err, "Scorecard failed");
      return null;
    }
  }

  async function probeMedia(url) {
    if (!url || !global.CinesmithCore) return null;
    try {
      const data = await CinesmithCore.api("POST", "/api/media/probe", { url: url });
      return data.probe || null;
    } catch (_e) {
      return null;
    }
  }

  async function annotateVideoCells() {
    const cells = document.querySelectorAll("#spark-grid .video-library-cell, .script-video-card, [data-video-url]");
    for (const cell of cells) {
      if (cell.dataset.audioProbed === "1") continue;
      const url =
        cell.getAttribute("data-video-url") ||
        cell.dataset.videoUrl ||
        (cell.querySelector("video") && cell.querySelector("video").getAttribute("src")) ||
        "";
      if (!url || (!/\.(mp4|webm|mov|m4v)(\?|$)/i.test(url) && url.indexOf("/videos/") < 0)) continue;
      cell.dataset.audioProbed = "1";
      const probe = await probeMedia(url);
      if (!probe) continue;
      let badge = cell.querySelector(".audio-honesty-badge");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "audio-honesty-badge";
        cell.appendChild(badge);
      }
      if (probe.has_audio) {
        badge.textContent = "Audio";
        badge.classList.add("ok");
        badge.classList.remove("silent");
      } else if (probe.has_video) {
        badge.textContent = "Silent";
        badge.classList.add("silent");
        badge.classList.remove("ok");
      } else {
        badge.textContent = "Media?";
      }
      badge.title = probe.honest_summary || "";
    }
  }

  function renderSuggestions(host, suggestions) {
    if (!host) return;
    host.innerHTML = "";
    if (!suggestions || !suggestions.length) {
      host.innerHTML = '<div class="suggest-empty">Brief Hermes above — intelligence appears as you work.</div>';
      return;
    }
    suggestions.forEach(function (s) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "suggest-card";
      card.innerHTML =
        "<strong>" + escapeHtml(s.title || "Tip") + "</strong>" +
        "<span>" + escapeHtml(s.body || "") + "</span>";
      card.addEventListener("click", function () {
        applySuggestion(s);
      });
      host.appendChild(card);
    });
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str || "";
    return d.innerHTML;
  }

  function applySuggestion(s) {
    const action = s.action || "";
    if (action === "images" || action === "create") {
      if (typeof switchPage === "function") switchPage("dashboard-view");
    } else if (action === "script") {
      if (typeof switchPage === "function") switchPage("script-view");
    } else if (action === "video") {
      if (typeof switchPage === "function") switchPage("spark-view");
    } else if (action === "characters") {
      if (typeof switchPage === "function") switchPage("identity-view");
    } else if (action === "assets") {
      if (typeof switchPage === "function") switchPage("products-view");
    } else if (action === "settings") {
      if (typeof switchPage === "function") switchPage("settings-view");
    }
    CinesmithCore.toast(s.title || "Ready", "info");
  }

  function renderCreateHub(host, data) {
    if (!host || !data) return;
    const modes = data.modes || [];
    host.innerHTML = "";

    if (data.quick_path && data.quick_path.length) {
      const path = document.createElement("div");
      path.className = "create-hub-quick-path";
      path.innerHTML =
        "<div class='preset-label'>15-minute path</div>" +
        '<div class="create-hub-path-row">' +
        data.quick_path
          .map(function (step) {
            return (
              '<div class="create-hub-path-step">' +
              "<span>" +
              escapeHtml(String(step.step || "")) +
              "</span><strong>" +
              escapeHtml(step.title || "") +
              "</strong><em>" +
              escapeHtml(step.hint || "") +
              "</em></div>"
            );
          })
          .join("") +
        "</div>";
      host.appendChild(path);
    }

    const grid = document.createElement("div");
    grid.className = "create-hub-grid";
    modes.forEach(function (m) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "create-hub-card";
      btn.innerHTML =
        "<strong>" + escapeHtml(m.title) + "</strong>" +
        "<span>" + escapeHtml(m.subtitle || "") + "</span>" +
        "<em>" + escapeHtml(m.cta || "Open") + "</em>";
      btn.addEventListener("click", function () {
        if (typeof switchPage === "function" && m.page) switchPage(m.page);
      });
      grid.appendChild(btn);
    });
    host.appendChild(grid);

    if (data.recent_stories && data.recent_stories.length) {
      const rec = document.createElement("div");
      rec.className = "create-hub-recent";
      rec.innerHTML = "<div class='preset-label'>Recent story projects</div>";
      const row = document.createElement("div");
      row.className = "preset-row";
      data.recent_stories.forEach(function (p) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "preset-chip";
        const done = (p.video_complete_count || 0) + "/" + (p.video_shot_count || 0);
        b.textContent = (p.title || p.script_id) + " · " + done;
        b.title = "Open Stories";
        b.addEventListener("click", function () {
          if (typeof switchPage === "function") switchPage("script-view");
          if (p.script_id && typeof loadScriptProjectById === "function") {
            loadScriptProjectById(p.script_id);
          } else {
            CinesmithCore.toast("Open project: " + (p.script_id || ""), "info");
          }
        });
        row.appendChild(b);
      });
      rec.appendChild(row);
      host.appendChild(rec);
    }
  }

  async function refreshQueueStrip(host) {
    if (!host || !global.CinesmithCore) return;
    try {
      const data = await CinesmithCore.api("GET", "/api/product/queue-summary");
      const items = data.items || [];
      if (!items.length) {
        host.innerHTML = '<span class="queue-idle">No active Hermes story jobs</span>';
        return;
      }
      host.innerHTML = items
        .map(function (it) {
          return (
            '<div class="queue-item">' +
            "<strong>" + escapeHtml(it.title || it.script_id || "Story") + "</strong>" +
            '<span class="queue-bar"><i style="width:' + (it.progress_pct || 0) + '%"></i></span>' +
            "<em>" + (it.progress_pct || 0) + "%</em></div>"
          );
        })
        .join("");
    } catch (_e) {
      host.innerHTML = "";
    }
  }

  function wireAgencyLiveBrief() {
    const input = document.getElementById("agency-brief-input");
    const imgBtn = document.getElementById("agency-run-images-btn");
    const storyBtn = document.getElementById("agency-run-story-btn");
    if (!input || input.dataset.bound === "1") return;
    input.dataset.bound = "1";

    function takeBrief() {
      return (input.value || "").trim();
    }

    if (imgBtn) {
      imgBtn.addEventListener("click", function () {
        const brief = takeBrief();
        if (typeof switchPage === "function") switchPage("dashboard-view");
        const target = document.getElementById("brief-input");
        if (target) {
          if (brief) {
            target.value = brief;
            target.dispatchEvent(new Event("input", { bubbles: true }));
          }
          target.focus();
        }
        CinesmithCore.toast(brief ? "Brief loaded — Hermes is ready to run the campaign." : "Open Images and brief Hermes.", "success");
        if (brief && typeof runCampaign === "function" && !global.campaignActive) {
          // Give UI a tick to bind state
          setTimeout(function () {
            try { runCampaign(); } catch (_e) {}
          }, 80);
        }
      });
    }

    if (storyBtn) {
      storyBtn.addEventListener("click", function () {
        const brief = takeBrief();
        if (typeof switchPage === "function") switchPage("script-view");
        const target = document.getElementById("script-brief");
        if (target) {
          if (brief) {
            target.value = brief;
            target.dispatchEvent(new Event("input", { bubbles: true }));
          }
          target.focus();
        }
        if (typeof switchScriptFlowStep === "function") switchScriptFlowStep("brief");
        CinesmithCore.toast(brief ? "Story brief loaded — produce with Hermes when ready." : "Open Stories and brief Hermes.", "success");
      });
    }

    // Ctrl/Cmd+Enter on agency brief
    input.addEventListener("keydown", function (event) {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        if (imgBtn) imgBtn.click();
      }
    });
  }

  /* ---- Setup wizard (multi-step, server + local) ---- */
  let wizardSteps = [];
  let wizardIndex = 0;

  async function maybeStartSetupWizard() {
    try {
      if (localStorage.getItem(WIZARD_LOCAL) === "1") return;
    } catch (_e) {}
    if (!global.CinesmithCore) return;
    try {
      const state = await CinesmithCore.api("GET", "/api/product/wizard-state");
      if (state.completed) {
        try { localStorage.setItem(WIZARD_LOCAL, "1"); } catch (_e) {}
        return;
      }
      wizardSteps = state.steps || [];
      const idx = Math.max(0, wizardSteps.findIndex(function (s) { return s.id === state.step; }));
      wizardIndex = idx >= 0 ? idx : 0;
      showWizardStep();
    } catch (_e) {}
  }

  function showWizardStep() {
    let overlay = document.getElementById("cinesmith-setup-wizard");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "cinesmith-setup-wizard";
      overlay.innerHTML =
        '<div class="onboard-card wizard-card">' +
        '<div class="wizard-progress" id="wizard-progress"></div>' +
        '<h2 id="wizard-title"></h2>' +
        '<p id="wizard-body"></p>' +
        '<div class="onboard-actions">' +
        '<button type="button" id="wizard-skip">Skip setup</button>' +
        '<button type="button" id="wizard-back">Back</button>' +
        '<button type="button" class="primary" id="wizard-next">Continue</button>' +
        "</div></div>";
      document.body.appendChild(overlay);
      overlay.querySelector("#wizard-skip").addEventListener("click", function () { finishWizard(true); });
      overlay.querySelector("#wizard-back").addEventListener("click", function () {
        wizardIndex = Math.max(0, wizardIndex - 1);
        showWizardStep();
      });
      overlay.querySelector("#wizard-next").addEventListener("click", onWizardNext);
    }
    overlay.classList.add("active");
    const step = wizardSteps[wizardIndex] || { title: "Welcome", body: "", id: "welcome" };
    overlay.querySelector("#wizard-title").textContent = step.title || "Setup";
    overlay.querySelector("#wizard-body").textContent = step.body || "";
    overlay.querySelector("#wizard-progress").textContent =
      "Step " + (wizardIndex + 1) + " of " + Math.max(wizardSteps.length, 1);
    overlay.querySelector("#wizard-back").style.visibility = wizardIndex === 0 ? "hidden" : "visible";
    overlay.querySelector("#wizard-next").textContent =
      wizardIndex >= wizardSteps.length - 1 ? "Finish" : "Continue";
  }

  async function onWizardNext() {
    const step = wizardSteps[wizardIndex] || {};
    if (step.id === "spark" || step.id === "director") {
      if (typeof switchPage === "function") switchPage("settings-view");
    }
    if (step.id === "try") {
      if (typeof switchPage === "function") switchPage("create-view");
    }
    if (wizardIndex >= wizardSteps.length - 1) {
      await finishWizard(true);
      return;
    }
    wizardIndex += 1;
    const next = wizardSteps[wizardIndex] || {};
    try {
      await CinesmithCore.api("POST", "/api/product/wizard-state", {
        completed: false,
        step: next.id || "welcome",
      });
    } catch (_e) {}
    showWizardStep();
  }

  async function finishWizard(persist) {
    const overlay = document.getElementById("cinesmith-setup-wizard");
    if (overlay) overlay.classList.remove("active");
    if (persist && global.CinesmithCore) {
      try {
        await CinesmithCore.api("POST", "/api/product/wizard-state", { completed: true, step: "done" });
      } catch (_e) {}
      try { localStorage.setItem(WIZARD_LOCAL, "1"); } catch (_e) {}
      try { localStorage.setItem("cinesmith_onboarding_v1_done", "1"); } catch (_e) {}
      const legacy = document.getElementById("cinesmith-onboarding");
      if (legacy) legacy.classList.remove("active");
      CinesmithCore.toast("Agency online — brief Hermes and run.", "success");
      if (typeof switchPage === "function") switchPage("create-view");
    }
  }

  async function initProductSurface() {
    wireAgencyLiveBrief();

    const hub = document.getElementById("create-hub-panel");
    const suggestHost = document.getElementById("memory-suggestions");
    const queueHost = document.getElementById("queue-progress-strip");

    if (hub) {
      const data = await loadCreateHub();
      renderCreateHub(hub, data);
    }
    if (suggestHost) {
      const brief =
        (document.getElementById("agency-brief-input") || {}).value ||
        (document.getElementById("brief-input") || {}).value ||
        "";
      const suggestions = await loadSuggestions(brief, "auto");
      renderSuggestions(suggestHost, suggestions);
      ["agency-brief-input", "brief-input"].forEach(function (id) {
        const el = document.getElementById(id);
        if (!el || el.dataset.suggestBound === "1") return;
        let t = null;
        el.addEventListener("input", function () {
          clearTimeout(t);
          t = setTimeout(async function () {
            const list = await loadSuggestions(el.value || "", id === "brief-input" ? "images" : "auto");
            renderSuggestions(suggestHost, list);
          }, 500);
        });
        el.dataset.suggestBound = "1";
      });
    }
    if (queueHost) {
      await refreshQueueStrip(queueHost);
      setInterval(function () { refreshQueueStrip(queueHost); }, 15000);
    }

    bindExportButtons();
    ensureStoriesAssembleCta();
    const scoreBtn = document.getElementById("story-scorecard-btn");
    if (scoreBtn && !scoreBtn.dataset.bound) {
      scoreBtn.addEventListener("click", async function () {
        const sid =
          (global.currentScriptProjectId) ||
          (document.getElementById("script-project-id") || {}).value ||
          "";
        const card = await loadScorecard(sid);
        const panel = document.getElementById("story-scorecard-panel");
        if (card && panel) {
          panel.innerHTML =
            "<strong>Continuity " + card.grade + " · " + card.score + "/100</strong>" +
            "<p>" + escapeHtml(card.summary || "") + "</p>" +
            (card.issues && card.issues.length
              ? "<ul>" + card.issues.map(function (i) { return "<li>" + escapeHtml(i) + "</li>"; }).join("") + "</ul>"
              : "") +
            (card.recommendations && card.recommendations.length
              ? "<p>" + escapeHtml(card.recommendations[0]) + "</p>"
              : "");
          panel.hidden = false;
          CinesmithCore.toast("Continuity: " + card.grade + " (" + card.score + ")", card.score >= 70 ? "success" : "warn");
        }
      });
      scoreBtn.dataset.bound = "1";
    }

    await maybeStartSetupWizard();
    setTimeout(annotateVideoCells, 2500);
    setInterval(annotateVideoCells, 20000);
  }

  function currentStoryId() {
    return (
      (global.currentScriptProjectId) ||
      (document.getElementById("script-project-id") || {}).value ||
      ""
    );
  }

  function bindExportButtons() {
    document.querySelectorAll("#export-story-package-btn, [data-cinesmith-export-package]").forEach(function (exportBtn) {
      if (!exportBtn || exportBtn.dataset.bound) return;
      exportBtn.addEventListener("click", function () {
        exportStoryPackage(currentStoryId());
      });
      exportBtn.dataset.bound = "1";
    });
  }

  /** Clear Assemble / Export package CTAs on Stories (Brief header + Videos handoff). */
  function ensureStoriesAssembleCta() {
    if (document.getElementById("cinesmith-stories-export-strip")) {
      bindExportButtons();
      return;
    }
    const styleId = "cinesmith-stories-export-css";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent =
        "#cinesmith-stories-export-strip{" +
        "display:flex;flex-wrap:wrap;align-items:center;gap:10px;" +
        "margin:10px 0 14px;padding:12px 14px;border-radius:12px;" +
        "border:1px solid #2a3a55;background:linear-gradient(135deg,#121a2a 0%,#0e1624 100%);" +
        "}" +
        "#cinesmith-stories-export-strip .fse-copy{flex:1;min-width:180px;}" +
        "#cinesmith-stories-export-strip .fse-copy strong{display:block;color:#fff;font-size:13px;}" +
        "#cinesmith-stories-export-strip .fse-copy span{color:#8f98aa;font-size:11px;}" +
        "#cinesmith-stories-export-strip .btn-primary-export{" +
        "border-color:#1d6b5a;background:#0d2a24;color:#35f0d0;font-weight:700;" +
        "}" +
        "#script-video-export-row{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 4px;}";
      document.head.appendChild(style);
    }

    const scriptView = document.getElementById("script-view");
    if (!scriptView) return;

    // Header-level strip under the flow guide
    const guide = scriptView.querySelector(".script-flow-guide");
    const strip = document.createElement("div");
    strip.id = "cinesmith-stories-export-strip";
    strip.innerHTML =
      '<div class="fse-copy">' +
      "<strong>Assemble / Export package</strong>" +
      "<span>ZIP handoff: narrative package, frames, clips, captions, audio honesty.</span>" +
      "</div>" +
      '<button type="button" class="btn btn-secondary btn-primary-export" data-cinesmith-export-package="1" id="export-story-package-cta">' +
      "Assemble / Export package</button>" +
      '<button type="button" class="btn btn-secondary" id="story-scorecard-btn-cta" title="Continuity score across shots">Continuity score</button>';

    if (guide && guide.parentNode) {
      guide.parentNode.insertBefore(strip, guide.nextSibling);
    } else {
      const header = scriptView.querySelector(".script-director-header");
      if (header && header.parentNode) header.parentNode.insertBefore(strip, header.nextSibling);
      else scriptView.insertBefore(strip, scriptView.firstChild);
    }

    // Videos step secondary CTA
    const videoActions = scriptView.querySelector(".script-video-actions");
    if (videoActions && !document.getElementById("export-story-package-videos")) {
      const vbtn = document.createElement("button");
      vbtn.type = "button";
      vbtn.className = "btn btn-secondary";
      vbtn.id = "export-story-package-videos";
      vbtn.setAttribute("data-cinesmith-export-package", "1");
      vbtn.title = "ZIP: script, frames, clips, captions, audio honesty";
      vbtn.textContent = "Assemble / Export package";
      videoActions.appendChild(vbtn);
    }

    // Wire scorecard twin
    const scoreCta = document.getElementById("story-scorecard-btn-cta");
    const scorePrimary = document.getElementById("story-scorecard-btn");
    if (scoreCta && !scoreCta.dataset.bound) {
      scoreCta.addEventListener("click", function () {
        if (scorePrimary) scorePrimary.click();
        else {
          const sid = currentStoryId();
          loadScorecard(sid).then(function (card) {
            if (!card) return;
            CinesmithCore.toast(
              "Continuity: " + card.grade + " (" + card.score + ")",
              card.score >= 70 ? "success" : "warn"
            );
          });
        }
      });
      scoreCta.dataset.bound = "1";
    }

    // Clarify existing brief-panel button label if still generic
    const briefExport = document.getElementById("export-story-package-btn");
    if (briefExport && !briefExport.dataset.labelPolished) {
      briefExport.textContent = "Assemble / Export package";
      briefExport.dataset.labelPolished = "1";
    }

    bindExportButtons();
  }

  global.CinesmithProduct = {
    init: initProductSurface,
    exportStoryPackage: exportStoryPackage,
    loadScorecard: loadScorecard,
    probeMedia: probeMedia,
    annotateVideoCells: annotateVideoCells,
    loadSuggestions: loadSuggestions,
    ensureStoriesAssembleCta: ensureStoriesAssembleCta,
  };

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(function () {
      if (global.CinesmithProduct) global.CinesmithProduct.init();
    }, 120);
  });
})(window);
