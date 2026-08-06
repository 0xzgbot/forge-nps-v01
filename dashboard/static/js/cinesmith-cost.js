/* G5 cost meter + J4 failure-auto chip — readiness strip + Settings snapshot */
(function (global) {
  "use strict";

  const POLL_MS = 20000;

  function ensureCostChip() {
    const strip = document.getElementById("system-readiness");
    if (!strip) return null;
    let chip = document.getElementById("ready-cost");
    if (chip) return chip;
    chip = document.createElement("span");
    chip.className = "ready-chip";
    chip.id = "ready-cost";
    chip.setAttribute("data-key", "cost");
    chip.title = "Estimated cloud image API spend (OpenAI / Gemini)";
    chip.innerHTML = '<span class="dot"></span>Cost $0.00';
    const actions = strip.querySelector(".ready-actions");
    if (actions) {
      strip.insertBefore(chip, actions);
    } else {
      strip.appendChild(chip);
    }
    chip.addEventListener("click", function () {
      refreshCostMeter(true);
    });
    return chip;
  }

  function ensureFailureChip() {
    const strip = document.getElementById("system-readiness");
    if (!strip) return null;
    let chip = document.getElementById("ready-fail-mem");
    if (chip) return chip;
    chip = document.createElement("span");
    chip.className = "ready-chip";
    chip.id = "ready-fail-mem";
    chip.setAttribute("data-key", "failure_memory");
    chip.title = "Failure memory auto-consolidate (J4)";
    chip.innerHTML = '<span class="dot"></span>Mem 0/3';
    const actions = strip.querySelector(".ready-actions");
    if (actions) {
      strip.insertBefore(chip, actions);
    } else {
      strip.appendChild(chip);
    }
    return chip;
  }

  function setChip(el, state, label) {
    if (!el) return;
    el.classList.remove("ok", "warn", "bad");
    if (state) el.classList.add(state);
    const text = document.createTextNode(label);
    el.innerHTML = "";
    const d = document.createElement("span");
    d.className = "dot";
    el.appendChild(d);
    el.appendChild(text);
  }

  async function fetchJson(path) {
    if (global.CinesmithCore && typeof CinesmithCore.api === "function") {
      return CinesmithCore.api("GET", path);
    }
    const resp = await fetch(path);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  }

  async function refreshCostMeter(manual) {
    const chip = ensureCostChip();
    try {
      const data = await fetchJson("/api/product/cost-meter");
      const spend = Number(data.estimated_spend_usd || 0);
      const calls = Number(data.total_success || data.total_calls || 0);
      const label =
        "Cost " +
        (data.estimated_spend_display || ("$" + spend.toFixed(2))) +
        (calls ? " · " + calls : "");
      let state = "ok";
      if (spend >= 5) state = "warn";
      if (spend >= 25) state = "bad";
      setChip(chip, state, label);
      chip.title =
        "Cloud image estimate: " +
        (data.estimated_spend_display || ("$" + spend.toFixed(2))) +
        " · " +
        (data.total_calls || 0) +
        " calls (OpenAI/Gemini). Click to refresh.";
      window.__cinesmithCostMeter = data;
      renderSettingsCostPanel(data);
      if (manual && global.CinesmithCore) {
        CinesmithCore.toast(
          "Cloud image spend ~" + (data.estimated_spend_display || ("$" + spend.toFixed(2))),
          spend >= 5 ? "warn" : "info",
          2800
        );
      }
      return data;
    } catch (err) {
      setChip(chip, "warn", "Cost ?");
      if (manual && global.CinesmithCore) {
        CinesmithCore.toast("Cost meter unavailable", "warn");
      }
      return null;
    }
  }

  async function refreshFailureAuto(manual) {
    const chip = ensureFailureChip();
    try {
      const data = await fetchJson("/api/product/failure-auto-consolidate");
      const count = Number(data.failure_count_since_consolidate || 0);
      const thr = Number(data.threshold || 3);
      const consolidated = !!data.last_summary_id;
      let state = "ok";
      if (count > 0) state = "warn";
      if (count >= thr) state = "bad";
      setChip(chip, state, "Mem " + count + "/" + thr);
      const latest = data.latest_summary;
      chip.title = latest
        ? "Last failure memory: " + (latest.hermes_hint || latest.rule || latest.summary_id)
        : "Failures toward auto-memory: " + count + " / " + thr + " (default 3)";
      window.__cinesmithFailureAuto = data;
      renderSettingsFailurePanel(data);
      if (manual && latest && global.CinesmithCore) {
        CinesmithCore.toast(latest.hermes_hint || "Failure memory ready", "info", 3200);
      }
      return data;
    } catch (_e) {
      setChip(chip, "warn", "Mem ?");
      return null;
    }
  }

  function findSettingsHost() {
    return (
      document.getElementById("cost-meter-panel") ||
      document.getElementById("settings-cost-meter") ||
      document.querySelector("#settings-view .settings-extra") ||
      document.getElementById("settings-view")
    );
  }

  function ensureSettingsPanel() {
    let panel = document.getElementById("cost-meter-panel");
    if (panel) return panel;
    const host = findSettingsHost();
    if (!host) return null;
    panel = document.createElement("div");
    panel.id = "cost-meter-panel";
    panel.className = "cost-meter-panel";
    panel.innerHTML =
      '<h3 style="margin:12px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#8f98aa;">Cloud spend &amp; failure memory</h3>' +
      '<div id="cost-meter-body" style="font-size:12px;line-height:1.45;color:#c8cdd8;padding:10px;border:1px solid #2f3a4d;border-radius:8px;background:#111827;"></div>';
    if (host.id === "settings-view") {
      host.appendChild(panel);
    } else {
      host.appendChild(panel);
    }
    return panel;
  }

  function renderSettingsCostPanel(data) {
    ensureSettingsPanel();
    const body = document.getElementById("cost-meter-body");
    if (!body || !data) return;
    const by = data.by_provider || {};
    const parts = Object.keys(by).map(function (p) {
      const b = by[p] || {};
      return (
        p +
        ": $" +
        Number(b.estimated_spend_usd || 0).toFixed(2) +
        " (" +
        (b.success || 0) +
        " ok)"
      );
    });
    const fail = window.__cinesmithFailureAuto;
    let failLine = "";
    if (fail) {
      failLine =
        "<div style=\"margin-top:8px;padding-top:8px;border-top:1px solid #2f3a4d;\">" +
        "Failure auto-memory: <strong>" +
        (fail.failure_count_since_consolidate || 0) +
        "</strong> / " +
        (fail.threshold || 3) +
        " toward consolidate" +
        (fail.latest_summary
          ? "<br/><span style=\"color:#9aa3b5\">" +
            escapeHtml(String(fail.latest_summary.hermes_hint || fail.latest_summary.rule || "").slice(0, 180)) +
            "</span>"
          : "") +
        "</div>";
    }
    body.innerHTML =
      "<div><strong>" +
      escapeHtml(data.estimated_spend_display || ("$" + Number(data.estimated_spend_usd || 0).toFixed(2))) +
      "</strong> estimated · " +
      (data.total_calls || 0) +
      " API calls</div>" +
      (parts.length ? "<div style=\"margin-top:4px;color:#9aa3b5\">" + escapeHtml(parts.join(" · ")) + "</div>" : "") +
      "<div style=\"margin-top:6px;color:#6b7280;font-size:11px\">" +
      escapeHtml(data.note || "Estimates only.") +
      "</div>" +
      failLine;
  }

  function renderSettingsFailurePanel(data) {
    window.__cinesmithFailureAuto = data;
    if (window.__cinesmithCostMeter) {
      renderSettingsCostPanel(window.__cinesmithCostMeter);
    } else {
      ensureSettingsPanel();
      const body = document.getElementById("cost-meter-body");
      if (!body) return;
      body.innerHTML =
        "<div>Failure auto-memory: <strong>" +
        (data.failure_count_since_consolidate || 0) +
        "</strong> / " +
        (data.threshold || 3) +
        "</div>";
    }
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function initCostMeter() {
    ensureCostChip();
    ensureFailureChip();
    refreshCostMeter(false);
    refreshFailureAuto(false);
    setInterval(function () {
      refreshCostMeter(false);
      refreshFailureAuto(false);
    }, POLL_MS);

    // Refresh when Settings tab is opened
    document.querySelectorAll('[data-page="settings-view"]').forEach(function (tab) {
      tab.addEventListener("click", function () {
        setTimeout(function () {
          refreshCostMeter(false);
          refreshFailureAuto(false);
        }, 120);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCostMeter);
  } else {
    initCostMeter();
  }

  global.CinesmithCost = {
    refresh: refreshCostMeter,
    refreshFailureAuto: refreshFailureAuto,
    init: initCostMeter,
  };
})(window);
