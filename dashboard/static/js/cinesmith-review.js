/* Frame review — approve / reject / remediate (Frame.io energy) */
(function (global) {
  "use strict";

  let currentShot = null;
  let reviewBusy = false;

  function toast(msg, type, ms) {
    if (global.CinesmithCore && CinesmithCore.toast) return CinesmithCore.toast(msg, type, ms);
    if (typeof globalToast === "function") return globalToast(msg, type, ms);
  }

  function ensureReviewBar() {
    let bar = document.getElementById("lightbox-review-bar");
    if (bar) return bar;
    const details = document.querySelector("#lightbox-modal .lightbox-details");
    const content = document.querySelector("#lightbox-modal .lightbox-content");
    if (!content) return null;
    bar = document.createElement("div");
    bar.id = "lightbox-review-bar";
    bar.innerHTML =
      '<div class="lrb-head"><strong>Client review</strong><span id="lrb-status">Pending</span></div>' +
      '<div class="lrb-actions">' +
      '<button type="button" class="lrb-btn approve" data-review="approved" title="A">Approve</button>' +
      '<button type="button" class="lrb-btn changes" data-review="needs_changes" title="C">Needs changes</button>' +
      '<button type="button" class="lrb-btn reject" data-review="rejected" title="R">Reject + remediate</button>' +
      '<button type="button" class="lrb-btn ab" id="lrb-ab-btn" title="Compare with another frame">A/B compare</button>' +
      "</div>" +
      '<input id="lrb-note" type="text" placeholder="Optional note for Hermes remediation…" />' +
      '<div class="lrb-hint"><kbd>A</kbd> approve · <kbd>R</kbd> reject+fix · <kbd>B</kbd> A/B slot · <kbd>←</kbd><kbd>→</kbd> frames · <kbd>Esc</kbd> close</div>';
    if (details) content.insertBefore(bar, details);
    else content.appendChild(bar);

    bar.querySelectorAll("[data-review]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        submitReview(btn.getAttribute("data-review"));
      });
    });
    const abBtn = bar.querySelector("#lrb-ab-btn");
    if (abBtn) {
      abBtn.addEventListener("click", function () {
        queueForAbCompare();
      });
    }
    return bar;
  }

  function queueForAbCompare() {
    if (!currentShot || !(currentShot.id || currentShot.shot_id)) {
      toast("Open a frame first.", "warn");
      return;
    }
    const payload = {
      id: currentShot.id || currentShot.shot_id,
      shot_id: currentShot.shot_id || currentShot.id,
      image_url: currentShot.image_url || "",
      prompt: currentShot.prompt || "",
      campaign_id: (currentShot.raw && currentShot.raw.campaign_id) || "",
    };
    if (!global.CinesmithAB) {
      toast("A/B compare module not loaded.", "error");
      return;
    }
    // First press sets A; second (different) shot opens compare as B
    if (!queueForAbCompare._slotA || queueForAbCompare._slotA.id === payload.id) {
      queueForAbCompare._slotA = payload;
      CinesmithAB.setSlot(payload, "a");
      toast("A/B slot A set — open another frame and press A/B again.", "info");
      return;
    }
    CinesmithAB.setSlot(queueForAbCompare._slotA, "a");
    CinesmithAB.setSlot(payload, "b");
    CinesmithAB.openWith(queueForAbCompare._slotA, payload);
    queueForAbCompare._slotA = null;
  }

  function setBarStatus(text, cls) {
    const el = document.getElementById("lrb-status");
    if (!el) return;
    el.textContent = text || "Pending";
    el.className = cls || "";
  }

  function bindShot(result) {
    ensureReviewBar();
    if (!result) {
      currentShot = null;
      return;
    }
    currentShot = {
      id: result.id || result.shot_id || "",
      shot_id: result.shot_id || result.id || "",
      image_url: result.image_url || "",
      review_status: result.review_status || result.client_status || "",
      prompt: result.prompt || "",
      raw: result,
    };
    const rev = String(currentShot.review_status || "").toLowerCase();
    if (rev === "approved") setBarStatus("Approved", "ok");
    else if (rev === "rejected") setBarStatus("Rejected", "bad");
    else if (rev === "needs_changes") setBarStatus("Needs changes", "warn");
    else setBarStatus("Pending review", "");
  }

  async function submitReview(decision) {
    if (reviewBusy) return;
    if (!currentShot || !(currentShot.id || currentShot.shot_id)) {
      toast("No shot selected — open a frame from the gallery.", "warn");
      return;
    }
    const shotId = currentShot.id || currentShot.shot_id;
    const note = ((document.getElementById("lrb-note") || {}).value || "").trim();
    const remediate = decision === "rejected" || decision === "needs_changes";
    reviewBusy = true;
    setBarStatus("Saving…", "");
    try {
      const data = await (global.CinesmithCore
        ? CinesmithCore.api("POST", "/api/product/review", {
            shot_id: shotId,
            decision: decision,
            note: note,
            remediate: remediate,
            max_retries: 1,
          })
        : fetch("/api/product/review", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              shot_id: shotId,
              decision: decision,
              note: note,
              remediate: remediate,
              max_retries: 1,
            }),
          }).then(function (r) { return r.json(); }));

      if (data.status !== "ok") throw new Error((data.error && data.error.message) || data.detail || "review failed");

      currentShot.review_status = decision;
      if (decision === "approved") {
        setBarStatus("Approved", "ok");
        toast("Approved — locked for handoff", "success");
      } else if (decision === "rejected") {
        setBarStatus("Rejected · remediating", "bad");
        const rem = data.remediation;
        const ok = rem && (rem.status === "ok" || (rem.results && rem.results.length));
        toast(ok ? "Rejected — Hermes remediation started" : "Rejected — remediation may need Settings/Spark", ok ? "warn" : "error", 4500);
      } else {
        setBarStatus("Needs changes", "warn");
        toast("Marked needs changes", "warn");
      }

      // mark filmstrip badge
      markFilmstrip(shotId, decision);
      if (typeof loadShots === "function") {
        try { loadShots(); } catch (_e) {}
      }
      if (window.CinesmithAgency && CinesmithAgency.setTimeline) {
        CinesmithAgency.setTimeline({
          active: remediate,
          stage: remediate ? "compile" : "audit",
          message: decision === "approved" ? "Client approved frame" : "Client review: " + decision,
          progress: decision === "approved" ? 100 : 70,
        });
      }
    } catch (err) {
      setBarStatus("Error", "bad");
      toast((err && err.message) || "Review failed", "error");
    } finally {
      reviewBusy = false;
    }
  }

  function markFilmstrip(shotId, decision) {
    const items = document.querySelectorAll(".filmstrip-item, .grid-cell");
    items.forEach(function (el) {
      const id = el.getAttribute("data-shot-id") || "";
      if (id && id !== shotId) return;
      // also match by image src loosely
      el.classList.remove("review-approved", "review-rejected", "review-changes");
      if (decision === "approved") el.classList.add("review-approved");
      if (decision === "rejected") el.classList.add("review-rejected");
      if (decision === "needs_changes") el.classList.add("review-changes");
    });
  }

  function collectFilmstripShots() {
    const out = [];
    document.querySelectorAll(".filmstrip-item img").forEach(function (img) {
      const item = img.closest(".filmstrip-item");
      if (!item) return;
      out.push({
        el: item,
        image_url: img.getAttribute("src") || "",
        id: item.getAttribute("data-shot-id") || img.getAttribute("alt") || "",
      });
    });
    return out;
  }

  function navigateFilmstrip(delta) {
    const shots = collectFilmstripShots();
    if (!shots.length) return;
    let idx = 0;
    if (currentShot && currentShot.image_url) {
      const found = shots.findIndex(function (s) { return s.image_url === currentShot.image_url || s.id === currentShot.id; });
      if (found >= 0) idx = found;
    }
    idx = (idx + delta + shots.length) % shots.length;
    const next = shots[idx];
    // trigger dblclick path via synthetic open if possible
    if (next.el) next.el.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
  }

  function patchOpenLightbox() {
    if (typeof global.openLightbox !== "function") return;
    if (global.openLightbox.__reviewPatched) return;
    const orig = global.openLightbox;
    function wrapped(result) {
      const ret = orig(result);
      try {
        bindShot(result);
      } catch (_e) {}
      return ret;
    }
    wrapped.__reviewPatched = true;
    global.openLightbox = wrapped;
  }

  function patchFilmstripIds() {
    // ensure data-shot-id on filmstrip items when loadShots runs — observe mutations
    const strip = document.getElementById("filmstrip") || document.querySelector(".filmstrip");
    if (!strip || strip.dataset.reviewObs) return;
    strip.dataset.reviewObs = "1";
    const mo = new MutationObserver(function () {
      strip.querySelectorAll(".filmstrip-item").forEach(function (item) {
        if (item.dataset.shotBound) return;
        item.dataset.shotBound = "1";
        const label = item.querySelector(".shot-label");
        const text = (label && label.textContent) || "";
        const m = text.match(/^(SHOT_[^\s—-]+|[a-zA-Z0-9_.:-]+)/);
        if (m) item.setAttribute("data-shot-id", m[1].trim());
      });
    });
    mo.observe(strip, { childList: true, subtree: true });
  }

  function initKeys() {
    document.addEventListener("keydown", function (e) {
      const modal = document.getElementById("lightbox-modal");
      if (!modal || !modal.classList.contains("active")) return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        submitReview("approved");
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        submitReview("rejected");
      } else if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        submitReview("needs_changes");
      } else if (e.key === "b" || e.key === "B") {
        // don't steal B when A/B modal is open
        const abModal = document.getElementById("cinesmith-ab-modal");
        if (abModal && abModal.classList.contains("active")) return;
        e.preventDefault();
        queueForAbCompare();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        navigateFilmstrip(1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        navigateFilmstrip(-1);
      }
    });
  }

  function injectCss() {
    if (document.getElementById("cinesmith-review-css")) return;
    const style = document.createElement("style");
    style.id = "cinesmith-review-css";
    style.textContent = `
      #lightbox-review-bar {
        border-bottom: 1px solid #243044;
        padding: 12px 14px 10px;
        background: linear-gradient(180deg, #151c2c 0%, #10161f 100%);
      }
      #lightbox-review-bar .lrb-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 8px;
      }
      #lightbox-review-bar .lrb-head strong { color: #fff; font-size: 12px; letter-spacing: .02em; }
      #lrb-status { font-size: 11px; color: #8f98aa; font-weight: 600; }
      #lrb-status.ok { color: #35f0d0; }
      #lrb-status.bad { color: #ff6b6b; }
      #lrb-status.warn { color: #ffb45f; }
      .lrb-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
      .lrb-btn {
        border-radius: 8px; border: 1px solid #2f3a4d; background: #121820;
        color: #dce6ff; font-size: 12px; font-weight: 700; padding: 7px 10px; cursor: pointer;
      }
      .lrb-btn.approve { border-color: #1d6b5a; background: #0d2a24; color: #35f0d0; }
      .lrb-btn.reject { border-color: #6b2a2a; background: #2a1212; color: #ff8f8f; }
      .lrb-btn.changes { border-color: #6b4a1d; background: #2a1a10; color: #ffb45f; }
      .lrb-btn.ab { border-color: #3d4a8a; background: #141a32; color: #9eb6ff; }
      .lrb-btn:hover { filter: brightness(1.08); }
      #lrb-note {
        width: 100%; box-sizing: border-box; margin-bottom: 6px;
        background: #0a0e16; border: 1px solid #2f3a4d; border-radius: 8px;
        color: #e8eefc; padding: 8px 10px; font: inherit; font-size: 12px;
      }
      .lrb-hint { font-size: 10px; color: #667086; }
      .lrb-hint kbd {
        font-family: 'JetBrains Mono', monospace; border: 1px solid #3d4a63;
        border-radius: 3px; padding: 0 4px; margin: 0 2px; color: #8eb0ff;
      }
      .filmstrip-item.review-approved, .grid-cell.review-approved {
        box-shadow: 0 0 0 2px rgba(53,240,208,.55);
      }
      .filmstrip-item.review-rejected, .grid-cell.review-rejected {
        box-shadow: 0 0 0 2px rgba(255,107,107,.55);
      }
      .filmstrip-item.review-changes, .grid-cell.review-changes {
        box-shadow: 0 0 0 2px rgba(255,180,95,.55);
      }
    `;
    document.head.appendChild(style);
  }

  function init() {
    injectCss();
    ensureReviewBar();
    patchOpenLightbox();
    patchFilmstripIds();
    initKeys();
    setTimeout(patchOpenLightbox, 500);
    setTimeout(patchOpenLightbox, 2000);
  }

  global.CinesmithReview = {
    init: init,
    submitReview: submitReview,
    bindShot: bindShot,
    getCurrentShot: function () { return currentShot; },
    queueForAbCompare: queueForAbCompare,
  };

  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(init, 100);
  });
})(window);
