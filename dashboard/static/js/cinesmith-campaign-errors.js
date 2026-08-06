/* Cinesmith campaign compile errors — toasts + failed-shot list for Images progress UI. */
(function (global) {
  "use strict";

  const state = {
    failures: [], // { shot_id, stage, message, recoverable, hint, workflow_id, t }
  };

  function toast(msg, type, ms) {
    if (global.CinesmithCore && CinesmithCore.toast) CinesmithCore.toast(msg, type, ms);
    else if (typeof global.globalToast === "function") global.globalToast(msg, type, ms);
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  function isStructuredShotError(event) {
    if (!event || event.type !== "error") return false;
    // Structured shape from HermesCampaignService.format_shot_error
    return !!(event.stage || event.message || typeof event.recoverable === "boolean");
  }

  function normalizeFailure(event) {
    const message = String(event.message || event.text || "Shot failed").trim();
    const hint = String(event.hint || "").trim();
    return {
      shot_id: String(event.shot_id || "").trim() || "—",
      stage: String(event.stage || "compile").trim() || "compile",
      message: message,
      recoverable: event.recoverable !== false,
      hint: hint,
      workflow_id: String(event.workflow_id || "").trim(),
      t: Date.now(),
    };
  }

  function failureKey(f) {
    return [f.shot_id, f.stage, f.workflow_id, f.message].join("|");
  }

  function addFailure(event) {
    const f = normalizeFailure(event);
    const key = failureKey(f);
    // Dedupe identical events from double handlers
    if (state.failures.some(function (x) { return failureKey(x) === key; })) {
      return f;
    }
    state.failures.push(f);
    if (state.failures.length > 40) state.failures = state.failures.slice(-40);
    return f;
  }

  function ensurePanel() {
    let panel = document.getElementById("campaign-compile-errors");
    if (panel) return panel;
    const status = document.getElementById("campaign-status-box");
    panel = document.createElement("div");
    panel.id = "campaign-compile-errors";
    panel.className = "campaign-compile-errors";
    panel.setAttribute("aria-live", "polite");
    panel.hidden = true;
    if (status && status.parentNode) {
      status.parentNode.insertBefore(panel, status.nextSibling);
    } else {
      document.body.appendChild(panel);
    }
    return panel;
  }

  function renderPanel() {
    const panel = ensurePanel();
    const items = state.failures.slice().reverse();
    if (!items.length) {
      panel.hidden = true;
      panel.innerHTML = "";
      return;
    }
    panel.hidden = false;
    const rows = items.map(function (f) {
      const stageLabel = f.stage.charAt(0).toUpperCase() + f.stage.slice(1);
      const rec = f.recoverable
        ? '<span class="cce-badge ok">recoverable</span>'
        : '<span class="cce-badge bad">blocking</span>';
      const hint = f.hint
        ? '<div class="cce-hint">Retry: ' + escapeHtml(f.hint) + "</div>"
        : '<div class="cce-hint">Retry: re-run the campaign after fixing Hermes / Spark.</div>';
      const wf = f.workflow_id
        ? '<span class="cce-wf">' + escapeHtml(f.workflow_id) + "</span>"
        : "";
      return (
        '<li class="cce-item" data-shot="' + escapeHtml(f.shot_id) + '">' +
        '<div class="cce-top">' +
        '<strong class="cce-shot">' + escapeHtml(f.shot_id) + "</strong>" +
        '<span class="cce-stage">' + escapeHtml(stageLabel) + "</span>" +
        rec +
        wf +
        "</div>" +
        '<div class="cce-msg">' + escapeHtml(f.message) + "</div>" +
        hint +
        "</li>"
      );
    }).join("");
    panel.innerHTML =
      '<div class="cce-head">' +
      "<strong>Failed shots</strong>" +
      '<span class="cce-count">' + items.length + "</span>" +
      '<button type="button" class="cce-clear" id="cce-clear-btn">Clear</button>' +
      "</div>" +
      '<ul class="cce-list">' + rows + "</ul>";
    const clearBtn = document.getElementById("cce-clear-btn");
    if (clearBtn) {
      clearBtn.onclick = function () {
        state.failures = [];
        renderPanel();
      };
    }
  }

  function ensureStyles() {
    if (document.getElementById("campaign-compile-errors-style")) return;
    const style = document.createElement("style");
    style.id = "campaign-compile-errors-style";
    style.textContent =
      ".campaign-compile-errors{margin:8px 0 10px;padding:10px 12px;border:1px solid #7a2d2d;border-radius:6px;background:#1a0f0f;color:#d7c8c8;font-family:JetBrains Mono,ui-monospace,monospace;font-size:11px;}" +
      ".campaign-compile-errors .cce-head{display:flex;align-items:center;gap:10px;margin-bottom:8px;color:#f0d0d0;}" +
      ".campaign-compile-errors .cce-count{background:#5a2020;color:#ffd0d0;border-radius:999px;padding:1px 8px;font-size:10px;}" +
      ".campaign-compile-errors .cce-clear{margin-left:auto;background:transparent;border:1px solid #664;color:#ccc;border-radius:4px;padding:2px 8px;cursor:pointer;font:inherit;}" +
      ".campaign-compile-errors .cce-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px;max-height:180px;overflow:auto;}" +
      ".campaign-compile-errors .cce-item{padding:8px;border:1px solid #3a2222;border-radius:4px;background:#140c0c;}" +
      ".campaign-compile-errors .cce-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:4px;}" +
      ".campaign-compile-errors .cce-shot{color:#ffb4b4;}" +
      ".campaign-compile-errors .cce-stage{color:#9aa0aa;text-transform:uppercase;letter-spacing:.06em;font-size:10px;}" +
      ".campaign-compile-errors .cce-badge{font-size:9px;padding:1px 6px;border-radius:999px;border:1px solid #444;}" +
      ".campaign-compile-errors .cce-badge.ok{border-color:#3a6a4a;color:#9dceb0;}" +
      ".campaign-compile-errors .cce-badge.bad{border-color:#8a4040;color:#f0a0a0;}" +
      ".campaign-compile-errors .cce-wf{color:#6f7785;font-size:10px;}" +
      ".campaign-compile-errors .cce-msg{color:#e2d4d4;line-height:1.35;}" +
      ".campaign-compile-errors .cce-hint{margin-top:4px;color:#8fa88f;font-size:10px;}";
    document.head.appendChild(style);
  }

  function onCampaignEvent(event) {
    if (!event) return;

    if (event.type === "compile_errors" && Array.isArray(event.errors)) {
      // Failures were usually already streamed as type=error; merge + one summary toast.
      event.errors.forEach(function (err) {
        if (err && typeof err === "object") addFailure(err);
      });
      const n = event.failed_count != null ? event.failed_count : event.errors.length;
      const ok = event.ok_count != null ? event.ok_count : "";
      toast(
        n + " shot compile(s) failed" + (ok !== "" ? " · " + ok + " ready for Spark" : "") + ". See failed shots list for retry hints.",
        "error",
        5600
      );
      renderPanel();
      return;
    }

    if (isStructuredShotError(event) && (event.shot_id || event.stage)) {
      const f = addFailure(event);
      // Per-shot toast only for non-compile stages (render/audit); compile uses summary toast.
      if (f.stage !== "compile" && f.stage !== "refine") {
        const label = f.shot_id !== "—" ? f.shot_id : "Shot";
        toast(label + " · " + f.stage + ": " + f.message.slice(0, 120), "error", 4800);
      }
      renderPanel();
    }
  }

  function reset() {
    state.failures = [];
    renderPanel();
  }

  function patchCampaignHook() {
    if (typeof global.handleCampaignEvent !== "function") return;
    if (global.handleCampaignEvent.__campaignErrorsPatched) return;
    const orig = global.handleCampaignEvent;
    function wrapped(event) {
      try { onCampaignEvent(event); } catch (_e) {}
      return orig(event);
    }
    wrapped.__campaignErrorsPatched = true;
    // Preserve other patches (e.g. agency) if already applied on orig
    if (orig.__agencyPatched) wrapped.__agencyPatched = true;
    global.handleCampaignEvent = wrapped;
  }

  function init() {
    ensureStyles();
    ensurePanel();
    patchCampaignHook();
    setTimeout(patchCampaignHook, 400);
    setTimeout(patchCampaignHook, 1600);
  }

  global.CinesmithCampaignErrors = {
    init: init,
    onCampaignEvent: onCampaignEvent,
    reset: reset,
    getFailures: function () { return state.failures.slice(); },
    isStructuredShotError: isStructuredShotError,
    normalizeFailure: normalizeFailure,
  };

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(init, 90);
  });
})(window);
