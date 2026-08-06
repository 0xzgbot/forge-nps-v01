/* Side-by-side A/B frame compare — pick two shots, choose a winner */
(function (global) {
  "use strict";

  const state = {
    slotA: null,
    slotB: null,
    busy: false,
  };

  function toast(msg, type, ms) {
    if (global.CinesmithCore && CinesmithCore.toast) return CinesmithCore.toast(msg, type, ms);
    if (typeof globalToast === "function") return globalToast(msg, type, ms);
  }

  function api(method, path, body) {
    if (global.CinesmithCore && CinesmithCore.api) return CinesmithCore.api(method, path, body);
    const opts = { method: method || "GET", headers: {} };
    if (body !== undefined && body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) {
          const err = new Error((data.error && data.error.message) || data.detail || "request failed");
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  function shotFromFilmstripEl(item) {
    if (!item) return null;
    const img = item.querySelector("img");
    const id = item.getAttribute("data-shot-id") || item.dataset.shotId || "";
    if (!id && !img) return null;
    return {
      id: id,
      shot_id: id,
      image_url: img ? img.getAttribute("src") || "" : "",
      prompt: (item.querySelector(".shot-label") && item.querySelector(".shot-label").textContent) || "",
    };
  }

  function collectSelectedShots() {
    const out = [];
    const seen = new Set();

    // Prefer global dashboardSelection when available
    if (global.dashboardSelection && typeof global.dashboardSelection.forEach === "function") {
      global.dashboardSelection.forEach(function (id) {
        if (!id || seen.has(id)) return;
        seen.add(id);
        const safe = (typeof CSS !== "undefined" && CSS.escape)
          ? CSS.escape(String(id))
          : String(id).replace(/"/g, '\\"');
        const el = document.querySelector(
          '.filmstrip-item[data-shot-id="' + safe + '"]'
        );
        const shot = el
          ? shotFromFilmstripEl(el)
          : { id: id, shot_id: id, image_url: "", prompt: "" };
        out.push(shot);
      });
    }

    if (out.length < 2) {
      document.querySelectorAll(".filmstrip-item.selected, .grid-cell.selected").forEach(function (el) {
        const shot = shotFromFilmstripEl(el);
        if (!shot || !shot.id || seen.has(shot.id)) return;
        seen.add(shot.id);
        out.push(shot);
      });
    }
    return out;
  }

  function ensureModal() {
    let modal = document.getElementById("cinesmith-ab-modal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "cinesmith-ab-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-label", "A/B frame compare");
    modal.innerHTML =
      '<div class="fab-backdrop" data-ab-close="1"></div>' +
      '<div class="fab-panel">' +
      '  <div class="fab-head">' +
      "    <div><strong>A/B compare</strong><span class=\"fab-sub\">Pick the stronger frame</span></div>" +
      '    <button type="button" class="fab-x" data-ab-close="1" title="Close">×</button>' +
      "  </div>" +
      '  <div class="fab-grid">' +
      '    <div class="fab-col" data-side="a">' +
      '      <div class="fab-label">A</div>' +
      '      <div class="fab-frame" id="fab-frame-a"><span class="fab-empty">Select frame A</span></div>' +
      '      <div class="fab-meta" id="fab-meta-a"></div>' +
      '      <button type="button" class="fab-pick" data-pick="a" title="1">Winner A</button>' +
      "    </div>" +
      '    <div class="fab-vs">VS</div>' +
      '    <div class="fab-col" data-side="b">' +
      '      <div class="fab-label">B</div>' +
      '      <div class="fab-frame" id="fab-frame-b"><span class="fab-empty">Select frame B</span></div>' +
      '      <div class="fab-meta" id="fab-meta-b"></div>' +
      '      <button type="button" class="fab-pick" data-pick="b" title="2">Winner B</button>' +
      "    </div>" +
      "  </div>" +
      '  <div class="fab-foot">' +
      '    <input id="fab-note" type="text" placeholder="Optional note (why this won)…" />' +
      '    <div class="fab-actions">' +
      '      <button type="button" class="fab-tie" data-pick="tie">Tie</button>' +
      '      <button type="button" class="fab-swap" id="fab-swap" title="Swap A ↔ B">Swap</button>' +
      "    </div>" +
      '    <div class="fab-hint"><kbd>1</kbd> A · <kbd>2</kbd> B · <kbd>T</kbd> tie · <kbd>Esc</kbd> close</div>' +
      "  </div>" +
      "</div>";
    document.body.appendChild(modal);

    modal.addEventListener("click", function (e) {
      const t = e.target;
      if (t && t.getAttribute && t.getAttribute("data-ab-close")) {
        close();
        return;
      }
      const pick = t && t.closest ? t.closest("[data-pick]") : null;
      if (pick) {
        const which = pick.getAttribute("data-pick");
        if (which === "a" || which === "b" || which === "tie") submitWinner(which);
      }
    });
    const swap = modal.querySelector("#fab-swap");
    if (swap) {
      swap.addEventListener("click", function () {
        const tmp = state.slotA;
        state.slotA = state.slotB;
        state.slotB = tmp;
        renderSlots();
      });
    }
    return modal;
  }

  function renderSlots() {
    function paint(side, shot) {
      const frame = document.getElementById("fab-frame-" + side);
      const meta = document.getElementById("fab-meta-" + side);
      if (!frame || !meta) return;
      if (!shot || !shot.image_url) {
        frame.innerHTML = '<span class="fab-empty">Select frame ' + side.toUpperCase() + "</span>";
        meta.textContent = shot && shot.id ? shot.id : "—";
        return;
      }
      frame.innerHTML = '<img src="' + escapeAttr(shot.image_url) + '" alt="' + escapeAttr(shot.id || side) + '" />';
      meta.textContent = (shot.id || shot.shot_id || "shot") + (shot.prompt ? " · " + String(shot.prompt).slice(0, 80) : "");
    }
    paint("a", state.slotA);
    paint("b", state.slotB);
  }

  function escapeAttr(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function openWith(shotA, shotB) {
    ensureModal();
    state.slotA = shotA || null;
    state.slotB = shotB || null;
    renderSlots();
    const note = document.getElementById("fab-note");
    if (note) note.value = "";
    const modal = document.getElementById("cinesmith-ab-modal");
    if (modal) modal.classList.add("active");
  }

  function close() {
    const modal = document.getElementById("cinesmith-ab-modal");
    if (modal) modal.classList.remove("active");
  }

  function openFromSelection() {
    const selected = collectSelectedShots();
    if (selected.length >= 2) {
      openWith(selected[0], selected[1]);
      return;
    }
    if (selected.length === 1 && state.slotA && state.slotA.id !== selected[0].id) {
      openWith(state.slotA, selected[0]);
      return;
    }
    if (selected.length === 1) {
      state.slotA = selected[0];
      toast("Frame A set — select another frame and open A/B again.", "info");
      openWith(state.slotA, state.slotB);
      return;
    }
    // fallback: try current lightbox shot as A
    if (global.CinesmithReview && typeof CinesmithReview.getCurrentShot === "function") {
      const cur = CinesmithReview.getCurrentShot();
      if (cur && cur.image_url) {
        state.slotA = {
          id: cur.id || cur.shot_id,
          shot_id: cur.shot_id || cur.id,
          image_url: cur.image_url,
          prompt: cur.prompt || "",
        };
      }
    }
    openWith(state.slotA, state.slotB);
    if (!state.slotA || !state.slotB) {
      toast("Select two frames in the filmstrip, then Compare A/B.", "warn");
    }
  }

  function setSlotFromShot(shot, side) {
    if (!shot) return;
    const payload = {
      id: shot.id || shot.shot_id || "",
      shot_id: shot.shot_id || shot.id || "",
      image_url: shot.image_url || "",
      prompt: shot.prompt || "",
      campaign_id: shot.campaign_id || "",
    };
    if (side === "b") state.slotB = payload;
    else state.slotA = payload;
  }

  async function submitWinner(which) {
    if (state.busy) return;
    if (!state.slotA || !state.slotB || !state.slotA.id || !state.slotB.id) {
      toast("Need two frames loaded to record a winner.", "warn");
      return;
    }
    if (state.slotA.id === state.slotB.id) {
      toast("A and B are the same shot.", "warn");
      return;
    }
    let winnerId = "";
    if (which === "a") winnerId = state.slotA.id;
    else if (which === "b") winnerId = state.slotB.id;
    else winnerId = "";

    const note = ((document.getElementById("fab-note") || {}).value || "").trim();
    state.busy = true;
    try {
      const data = await api("POST", "/api/product/ab-compare", {
        shot_a_id: state.slotA.id,
        shot_b_id: state.slotB.id,
        winner_id: winnerId,
        note: note,
        campaign_id: state.slotA.campaign_id || state.slotB.campaign_id || "",
      });
      if (data.status !== "ok") {
        throw new Error((data.error && data.error.message) || "A/B save failed");
      }
      const result = data.result || "tie";
      if (result === "tie") toast("Recorded as tie", "info");
      else toast("Winner: " + (data.winner_id || which.toUpperCase()), "success");

      markFilmstripWinner(data.winner_id, data.loser_id);
      if (typeof loadShots === "function") {
        try { loadShots(); } catch (_e) {}
      }
      if (window.CinesmithAgency && CinesmithAgency.setTimeline) {
        CinesmithAgency.setTimeline({
          active: false,
          stage: "audit",
          message: result === "tie" ? "A/B compare: tie" : "A/B winner locked",
          progress: 85,
        });
      }
      close();
    } catch (err) {
      toast((err && err.message) || "A/B compare failed", "error");
    } finally {
      state.busy = false;
    }
  }

  function markFilmstripWinner(winnerId, loserId) {
    document.querySelectorAll(".filmstrip-item, .grid-cell").forEach(function (el) {
      const id = el.getAttribute("data-shot-id") || "";
      if (!id) return;
      el.classList.remove("ab-winner", "ab-loser");
      if (winnerId && id === winnerId) el.classList.add("ab-winner");
      if (loserId && id === loserId) el.classList.add("ab-loser");
    });
  }

  function ensureToolbarButton() {
    if (document.getElementById("cinesmith-ab-compare-btn")) return;
    const host =
      document.getElementById("dashboard-selected-count") ||
      document.querySelector("#dashboard-view .prompt-toolbar") ||
      document.querySelector("#dashboard-view .action-row");
    if (!host || !host.parentNode) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "cinesmith-ab-compare-btn";
    btn.className = "btn btn-secondary";
    btn.title = "Compare two selected frames side-by-side";
    btn.textContent = "Compare A/B";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      openFromSelection();
    });
    if (host.id === "dashboard-selected-count") {
      host.parentNode.insertBefore(btn, host.nextSibling);
    } else {
      host.appendChild(btn);
    }
  }

  function injectCss() {
    if (document.getElementById("cinesmith-ab-css")) return;
    const style = document.createElement("style");
    style.id = "cinesmith-ab-css";
    style.textContent = `
      #cinesmith-ab-modal {
        display: none; position: fixed; inset: 0; z-index: 12000;
        align-items: center; justify-content: center;
      }
      #cinesmith-ab-modal.active { display: flex; }
      #cinesmith-ab-modal .fab-backdrop {
        position: absolute; inset: 0; background: rgba(4, 8, 16, 0.82);
        backdrop-filter: blur(4px);
      }
      #cinesmith-ab-modal .fab-panel {
        position: relative; z-index: 1; width: min(960px, 96vw);
        max-height: 92vh; overflow: auto;
        background: linear-gradient(180deg, #151c2c 0%, #0e141e 100%);
        border: 1px solid #2a3548; border-radius: 14px;
        box-shadow: 0 24px 64px rgba(0,0,0,.55);
        padding: 14px 16px 12px;
      }
      #cinesmith-ab-modal .fab-head {
        display: flex; justify-content: space-between; align-items: flex-start;
        margin-bottom: 12px;
      }
      #cinesmith-ab-modal .fab-head strong {
        color: #fff; font-size: 14px; letter-spacing: .02em; display: block;
      }
      #cinesmith-ab-modal .fab-sub { color: #8f98aa; font-size: 11px; }
      #cinesmith-ab-modal .fab-x {
        border: 0; background: transparent; color: #8f98aa;
        font-size: 22px; line-height: 1; cursor: pointer; padding: 0 4px;
      }
      #cinesmith-ab-modal .fab-grid {
        display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: stretch;
      }
      #cinesmith-ab-modal .fab-col {
        background: #0a0e16; border: 1px solid #243044; border-radius: 12px;
        padding: 10px; display: flex; flex-direction: column; gap: 8px; min-width: 0;
      }
      #cinesmith-ab-modal .fab-label {
        font-size: 11px; font-weight: 800; color: #8eb0ff; letter-spacing: .08em;
      }
      #cinesmith-ab-modal .fab-frame {
        aspect-ratio: 16/10; background: #06090f; border-radius: 8px;
        display: flex; align-items: center; justify-content: center; overflow: hidden;
      }
      #cinesmith-ab-modal .fab-frame img {
        width: 100%; height: 100%; object-fit: contain;
      }
      #cinesmith-ab-modal .fab-empty { color: #5a6478; font-size: 12px; }
      #cinesmith-ab-modal .fab-meta {
        font-size: 11px; color: #8f98aa; min-height: 2.4em;
        overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
      }
      #cinesmith-ab-modal .fab-pick {
        border-radius: 8px; border: 1px solid #1d6b5a; background: #0d2a24;
        color: #35f0d0; font-size: 12px; font-weight: 700; padding: 8px 10px; cursor: pointer;
      }
      #cinesmith-ab-modal .fab-pick:hover { filter: brightness(1.08); }
      #cinesmith-ab-modal .fab-vs {
        align-self: center; font-size: 12px; font-weight: 800; color: #667086;
        letter-spacing: .1em;
      }
      #cinesmith-ab-modal .fab-foot { margin-top: 12px; }
      #cinesmith-ab-modal #fab-note {
        width: 100%; box-sizing: border-box; margin-bottom: 8px;
        background: #0a0e16; border: 1px solid #2f3a4d; border-radius: 8px;
        color: #e8eefc; padding: 8px 10px; font: inherit; font-size: 12px;
      }
      #cinesmith-ab-modal .fab-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
      #cinesmith-ab-modal .fab-tie, #cinesmith-ab-modal .fab-swap {
        border-radius: 8px; border: 1px solid #2f3a4d; background: #121820;
        color: #dce6ff; font-size: 12px; font-weight: 600; padding: 7px 12px; cursor: pointer;
      }
      #cinesmith-ab-modal .fab-hint { font-size: 10px; color: #667086; }
      #cinesmith-ab-modal .fab-hint kbd {
        font-family: 'JetBrains Mono', monospace; border: 1px solid #3d4a63;
        border-radius: 3px; padding: 0 4px; margin: 0 2px; color: #8eb0ff;
      }
      #cinesmith-ab-compare-btn { white-space: nowrap; }
      .filmstrip-item.ab-winner, .grid-cell.ab-winner {
        box-shadow: 0 0 0 2px rgba(53, 240, 208, 0.75);
      }
      .filmstrip-item.ab-loser, .grid-cell.ab-loser {
        opacity: 0.72; box-shadow: 0 0 0 1px rgba(102, 112, 134, 0.5);
      }
      @media (max-width: 720px) {
        #cinesmith-ab-modal .fab-grid { grid-template-columns: 1fr; }
        #cinesmith-ab-modal .fab-vs { text-align: center; padding: 4px 0; }
      }
    `;
    document.head.appendChild(style);
  }

  function initKeys() {
    document.addEventListener("keydown", function (e) {
      const modal = document.getElementById("cinesmith-ab-modal");
      if (!modal || !modal.classList.contains("active")) return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "1") {
        e.preventDefault();
        submitWinner("a");
      } else if (e.key === "2") {
        e.preventDefault();
        submitWinner("b");
      } else if (e.key === "t" || e.key === "T") {
        e.preventDefault();
        submitWinner("tie");
      }
    });
  }

  function init() {
    injectCss();
    ensureToolbarButton();
    ensureModal();
    initKeys();
    // re-attach toolbar if dashboard re-renders chrome
    setTimeout(ensureToolbarButton, 800);
    setTimeout(ensureToolbarButton, 2500);
  }

  global.CinesmithAB = {
    init: init,
    open: openFromSelection,
    openWith: openWith,
    setSlot: setSlotFromShot,
    close: close,
    submitWinner: submitWinner,
  };

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(init, 140);
  });
})(window);
