/* Empty states + H10 Assemble/Export discoverability + Spark recovery + Memory Agency learning.
   Prefer this module over app.js edits. Hermes-first agency language. */
(function (global) {
  "use strict";

  var SPARK_DISMISS_KEY = "cinesmith_spark_recovery_dismissed_until";
  var SPARK_DISMISS_MS = 12 * 60 * 1000;
  var OBSERVE_DEBOUNCE_MS = 80;
  var POLL_MS = 4000;

  var COPY = {
    images: {
      kicker: "Images gallery",
      title: "No stills yet — Hermes is standing by",
      body:
        "Brief Hermes on Agency or Images, then Run with Hermes. Spark will fill this filmstrip.",
      primaryLabel: "Open Images brief",
      primaryAction: "images",
      secondaryLabel: "Agency home",
      secondaryAction: "agency",
    },
    videos: {
      kicker: "Videos",
      title: "No start frames selected",
      body:
        "Select stills from Images (or Stories frames), or write a text prompt for text-to-video.",
      primaryLabel: "Open Images",
      primaryAction: "images",
      secondaryLabel: "Text-to-video prompt",
      secondaryAction: "video-prompt",
    },
    stories: {
      kicker: "Stories",
      title: "Nothing to assemble yet",
      body:
        "Produce with Hermes first — frames and clips land here, then Assemble / Export package becomes available.",
      primaryLabel: "Produce with Hermes",
      primaryAction: "produce-story",
      secondaryLabel: "Story brief",
      secondaryAction: "story-brief",
    },
    characters: {
      kicker: "Characters",
      title: "No characters locked yet",
      body:
        "Sheet from photo locks a face/body as master reference. Multi-panel continuity sheet generates when Spark is online.",
      primaryLabel: "Sheet from photo",
      primaryAction: "char-upload",
      secondaryLabel: "Create character",
      secondaryAction: "char-design",
    },
    videosFirstLast: {
      kicker: "First → Last",
      title: "Pick a start frame, then an end frame",
      body: "Selection order matters. Hermes queues LTX first/last pair motion for the pair.",
      primaryLabel: "Open Images",
      primaryAction: "images",
      secondaryLabel: "Text-to-video",
      secondaryAction: "video-prompt",
    },
  };

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  function toast(msg, type, ms) {
    if (global.CinesmithCore && typeof CinesmithCore.toast === "function") {
      CinesmithCore.toast(msg, type || "info", ms);
      return;
    }
    if (typeof global.globalToast === "function") {
      global.globalToast(msg, type || "info", ms);
    }
  }

  function goPage(page) {
    if (typeof global.switchPage === "function") {
      global.switchPage(page);
    }
  }

  function runAction(action) {
    switch (action) {
      case "agency":
        goPage("create-view");
        break;
      case "images":
        goPage("dashboard-view");
        setTimeout(function () {
          var el = document.getElementById("brief-input");
          if (el) el.focus();
        }, 80);
        break;
      case "video-prompt":
        goPage("spark-view");
        setTimeout(function () {
          var el =
            document.getElementById("video-custom-brief") ||
            document.getElementById("video-prompt");
          if (el) el.focus();
        }, 80);
        break;
      case "produce-story":
        goPage("script-view");
        setTimeout(function () {
          if (typeof global.switchScriptFlowStep === "function") {
            global.switchScriptFlowStep("brief");
          }
          var btn =
            document.querySelector(
              '#script-view button.script-primary-action, #script-view [onclick*="runScriptPipeline"]'
            ) || document.getElementById("run-script-pipeline-btn");
          if (btn && !btn.disabled) {
            /* focus / scroll; do not auto-run */
            try {
              btn.scrollIntoView({ block: "nearest", behavior: "smooth" });
            } catch (_e) {}
            btn.focus();
          }
          var brief = document.getElementById("script-brief");
          if (brief) brief.focus();
        }, 100);
        break;
      case "story-brief":
        goPage("script-view");
        setTimeout(function () {
          if (typeof global.switchScriptFlowStep === "function") {
            global.switchScriptFlowStep("brief");
          }
          var brief = document.getElementById("script-brief");
          if (brief) brief.focus();
        }, 80);
        break;
      case "char-design":
        goPage("identity-view");
        setTimeout(function () {
          if (typeof global.switchCharacterFlowStep === "function") {
            global.switchCharacterFlowStep("design");
          }
          var name = document.getElementById("char-cinesmith-name");
          if (name) name.focus();
        }, 80);
        break;
      case "char-upload":
        goPage("identity-view");
        setTimeout(function () {
          if (typeof global.switchCharacterFlowStep === "function") {
            global.switchCharacterFlowStep("references");
          }
          var input =
            document.getElementById("identity-upload-input") ||
            document.querySelector('#identity-view input[type="file"]');
          if (input) {
            try {
              input.scrollIntoView({ block: "nearest", behavior: "smooth" });
            } catch (_e2) {}
            input.click();
          }
        }, 100);
        break;
      case "settings-spark":
        goPage("settings-view");
        setTimeout(function () {
          var el =
            document.getElementById("cfg-comfyui-primary") ||
            document.querySelector(".comfy-card");
          if (el && el.scrollIntoView) {
            try {
              el.scrollIntoView({ block: "center", behavior: "smooth" });
            } catch (_e3) {}
          }
          if (el && el.focus) el.focus();
        }, 120);
        break;
      default:
        break;
    }
  }

  function buildEmptyCard(key, opts) {
    opts = opts || {};
    var c = COPY[key] || COPY.images;
    var el = document.createElement("div");
    el.className =
      "cinesmith-empty-state" + (opts.inline ? " cinesmith-empty-inline" : "");
    el.setAttribute("data-cinesmith-empty", key);
    el.setAttribute("role", "status");
    el.innerHTML =
      '<div class="fes-kicker">' +
      escapeHtml(c.kicker) +
      "</div>" +
      '<p class="fes-title">' +
      escapeHtml(c.title) +
      "</p>" +
      '<p class="fes-body">' +
      escapeHtml(c.body) +
      "</p>" +
      '<div class="fes-actions">' +
      '<button type="button" class="btn" data-fes-action="' +
      escapeHtml(c.primaryAction) +
      '">' +
      escapeHtml(c.primaryLabel) +
      "</button>" +
      '<button type="button" class="btn btn-secondary" data-fes-action="' +
      escapeHtml(c.secondaryAction) +
      '">' +
      escapeHtml(c.secondaryLabel) +
      "</button>" +
      "</div>";
    el.querySelectorAll("[data-fes-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        runAction(btn.getAttribute("data-fes-action"));
      });
    });
    return el;
  }

  function isVisuallyEmpty(host, itemSelector) {
    if (!host) return true;
    var items = host.querySelectorAll(itemSelector);
    if (items.length) return false;
    /* Ignore our own empty state nodes */
    var meaningful = Array.prototype.slice.call(host.children).filter(function (ch) {
      if (ch.classList && ch.classList.contains("cinesmith-empty-state")) return false;
      if (ch.getAttribute && ch.getAttribute("data-cinesmith-empty")) return false;
      if (ch.classList && ch.classList.contains("grid-placeholder")) return false;
      var t = (ch.textContent || "").trim();
      if (!t) return false;
      /* Loading placeholders still count as non-empty until load finishes */
      if (/^loading/i.test(t)) return false;
      return true;
    });
    return meaningful.length === 0;
  }

  function ensureEmptyInHost(host, key, itemSelector, opts) {
    if (!host) return;
    opts = opts || {};
    var empty = isVisuallyEmpty(host, itemSelector);
    var existing = host.querySelector('[data-cinesmith-empty="' + key + '"]');
    if (!empty) {
      if (existing) existing.remove();
      /* Remove bare placeholders when real content exists */
      host.querySelectorAll(".grid-placeholder").forEach(function (p) {
        if (!p.querySelector("[data-cinesmith-empty]")) p.remove();
      });
      return;
    }
    if (existing) return;
    var card = buildEmptyCard(key, opts);

    if (key === "videos") {
      var ph = host.querySelector(".grid-placeholder");
      if (ph) {
        ph.classList.add("cinesmith-empty-host");
        ph.innerHTML = "";
        ph.appendChild(card);
        return;
      }
    }

    if (key === "stories") {
      host.innerHTML = "";
      host.appendChild(card);
      return;
    }

    if (key === "characters") {
      var loading = host.querySelector(".character-manager-status");
      if (loading && /loading/i.test(loading.textContent || "")) return;
      host.innerHTML = "";
      host.appendChild(card);
      return;
    }

    host.appendChild(card);
  }

  function refreshImagesEmpty() {
    ensureEmptyInHost(
      document.getElementById("filmstrip"),
      "images",
      ".filmstrip-item"
    );
  }

  function refreshVideosEmpty() {
    var grid = document.getElementById("spark-grid");
    if (!grid) return;
    /* Real media cells */
    var hasCells = grid.querySelectorAll(
      ".grid-cell, .video-library-cell, .filmstrip-item"
    ).length;
    var existing = grid.querySelector('[data-cinesmith-empty="videos"]');
    if (hasCells) {
      if (existing) {
        var host = existing.closest(".grid-placeholder") || existing;
        if (host.classList && host.classList.contains("grid-placeholder")) {
          host.remove();
        } else {
          existing.remove();
        }
      }
      return;
    }
    if (existing) return;
    var ph = grid.querySelector(".grid-placeholder");
    if (ph) {
      ph.classList.add("cinesmith-empty-host");
      ph.innerHTML = "";
      ph.appendChild(buildEmptyCard("videos", { inline: true }));
      return;
    }
    var wrap = document.createElement("div");
    wrap.className = "grid-placeholder cinesmith-empty-host";
    wrap.appendChild(buildEmptyCard("videos", { inline: true }));
    grid.appendChild(wrap);
  }

  function refreshCharactersEmpty() {
    var grid = document.getElementById("character-manager-content");
    if (!grid) return;
    if (/loading/i.test((grid.textContent || "").slice(0, 40))) return;
    var hasCards = grid.querySelectorAll(
      ".character-card-live, .char-card, article.character-card-live"
    ).length;
    var existing = grid.querySelector('[data-cinesmith-empty="characters"]');
    if (hasCards) {
      if (existing) existing.remove();
      return;
    }
    /* Treat short "No characters" status as empty */
    if (!existing) {
      grid.innerHTML = "";
      grid.appendChild(buildEmptyCard("characters", { inline: true }));
    }
  }

  function storyDeliverableStats() {
    var shots = Array.isArray(global.scriptVideoShots)
      ? global.scriptVideoShots
      : [];
    var frames = 0;
    var clips = 0;
    shots.forEach(function (s) {
      if (!s) return;
      if (s.image_url) frames += 1;
      if (s.video_url) clips += 1;
    });
    /* Storyboard panel images also count as deliverables */
    var boardImgs = document.querySelectorAll(
      "#storyboard-output img, .storyboard-panel img, .script-storyboard-panel img"
    ).length;
    if (!frames && boardImgs) frames = boardImgs;
    var sid =
      global.currentScriptProjectId ||
      (document.getElementById("script-project-id") || {}).value ||
      "";
    return {
      frames: frames,
      clips: clips,
      total: frames + clips,
      hasProject: !!String(sid || "").trim(),
      ready: frames + clips > 0,
    };
  }

  function setExportDisabled(btn, disabled, reason) {
    if (!btn) return;
    btn.disabled = !!disabled;
    if (disabled) {
      btn.setAttribute("aria-disabled", "true");
      btn.title = reason || "Produce with Hermes first — nothing to package yet.";
      btn.dataset.emptyBlocked = "1";
    } else {
      btn.removeAttribute("aria-disabled");
      if (btn.dataset.emptyBlocked === "1") {
        btn.title =
          btn.getAttribute("data-default-title") ||
          "ZIP: script, frames, clips, captions, audio honesty";
        delete btn.dataset.emptyBlocked;
      }
    }
  }

  function refreshStoriesAssembleExport() {
    /* Ensure product surface strip exists */
    if (
      global.CinesmithProduct &&
      typeof global.CinesmithProduct.ensureStoriesAssembleCta === "function"
    ) {
      try {
        global.CinesmithProduct.ensureStoriesAssembleCta();
      } catch (_e) {}
    }

    var stats = storyDeliverableStats();
    var strip = document.getElementById("cinesmith-stories-export-strip");
    var reasonText = stats.ready
      ? "Ready to package · " +
        stats.frames +
        " frame" +
        (stats.frames === 1 ? "" : "s") +
        (stats.clips
          ? " · " + stats.clips + " clip" + (stats.clips === 1 ? "" : "s")
          : "") +
        "."
      : "Disabled until Hermes produces frames or clips. Brief the story, then Produce with Hermes.";

    if (strip) {
      strip.classList.toggle("fse-ready", !!stats.ready);
      strip.classList.toggle("fse-empty", !stats.ready);

      var copyStrong = strip.querySelector(".fse-copy strong");
      if (copyStrong) {
        copyStrong.textContent = stats.ready
          ? "Assemble / Export package"
          : "Assemble / Export package";
      }
      var copySpan = strip.querySelector(".fse-copy span");
      if (copySpan) {
        copySpan.textContent = stats.ready
          ? "ZIP handoff ready — narrative package, frames, clips, captions, audio honesty."
          : "ZIP handoff waits on frames or clips from Hermes.";
      }

      var reason = strip.querySelector(".fse-reason");
      if (!reason) {
        reason = document.createElement("p");
        reason.className = "fse-reason";
        strip.appendChild(reason);
      }
      reason.textContent = reasonText;

      var hermesCta = strip.querySelector(".fse-cta-hermes");
      if (!stats.ready) {
        if (!hermesCta) {
          hermesCta = document.createElement("button");
          hermesCta.type = "button";
          hermesCta.className = "btn btn-secondary fse-cta-hermes";
          hermesCta.textContent = "Produce with Hermes first";
          hermesCta.addEventListener("click", function () {
            runAction("produce-story");
          });
          strip.appendChild(hermesCta);
        }
        hermesCta.hidden = false;
      } else if (hermesCta) {
        hermesCta.hidden = true;
      }
    }

    var exportBtns = document.querySelectorAll(
      "#export-story-package-btn, #export-story-package-cta, #export-story-package-videos, [data-cinesmith-export-package]"
    );
    exportBtns.forEach(function (btn) {
      if (!btn.dataset.defaultTitle && btn.title) {
        btn.dataset.defaultTitle = btn.title;
      }
      setExportDisabled(btn, !stats.ready, reasonText);
      /* Intercept empty clicks once */
      if (!btn.dataset.emptyGuard) {
        btn.addEventListener(
          "click",
          function (ev) {
            var st = storyDeliverableStats();
            if (!st.ready) {
              ev.preventDefault();
              ev.stopPropagation();
              toast(
                "Nothing to assemble yet — produce with Hermes first.",
                "warn",
                3200
              );
              return false;
            }
          },
          true
        );
        btn.dataset.emptyGuard = "1";
      }
    });

    /* Stories videos step empty list */
    var list = document.getElementById("script-video-output-list");
    if (list) {
      var hasOutputs = list.querySelectorAll(
        "img, video, .script-video-output-card, .script-video-card, [data-video-url]"
      ).length;
      var existing = list.querySelector('[data-cinesmith-empty="stories"]');
      if (hasOutputs) {
        if (existing) existing.remove();
      } else if (!existing) {
        /* Replace bare empty mini text */
        list.innerHTML = "";
        list.appendChild(buildEmptyCard("stories", { inline: true }));
      }
    }

    /* Handoff title/copy when empty */
    var handoffTitle = document.getElementById("script-video-handoff-title");
    var handoffCopy = document.getElementById("script-video-handoff-copy");
    if (handoffTitle && handoffCopy && !stats.ready) {
      if (!handoffTitle.dataset.polishedEmpty) {
        handoffTitle.textContent = "No frames or clips yet";
        handoffCopy.textContent =
          "Produce with Hermes first. Assemble / Export stays disabled until start frames or clips land.";
        handoffTitle.dataset.polishedEmpty = "1";
      }
    } else if (handoffTitle && stats.ready) {
      handoffTitle.textContent =
        stats.frames +
        " frame" +
        (stats.frames === 1 ? "" : "s") +
        (stats.clips
          ? " · " + stats.clips + " clip" + (stats.clips === 1 ? "" : "s")
          : "");
      handoffCopy.textContent =
        "Deliverables ready — Assemble / Export package is available above.";
      delete handoffTitle.dataset.polishedEmpty;
    }
  }

  /* ---- Spark recovery strip ---- */
  function sparkUiUrl(readiness) {
    var checks = (readiness && readiness.checks) || {};
    var cfg = checks.config || {};
    var spark = checks.spark || {};
    var raw =
      spark.url ||
      cfg.comfy_primary ||
      (document.getElementById("cfg-comfyui-primary") || {}).value ||
      "http://127.0.0.1:8188";
    raw = String(raw || "").trim();
    if (!raw) raw = "http://127.0.0.1:8188";
    /* Convert ws://host:port → http for UI open */
    if (/^wss?:\/\//i.test(raw)) {
      raw = raw.replace(/^ws/i, "http").replace(/\/+$/, "");
    }
    if (!/^https?:\/\//i.test(raw)) {
      raw = "http://" + raw.replace(/^\/+/, "");
    }
    /* Drop path like /system_stats if present */
    try {
      var u = new URL(raw);
      return u.origin;
    } catch (_e) {
      return raw.replace(/\/system_stats.*$/i, "").replace(/\/+$/, "");
    }
  }

  function isSparkDown(readiness) {
    if (!readiness || !readiness.checks) return false;
    var spark = readiness.checks.spark;
    if (!spark) return false;
    return !spark.ok;
  }

  function isSparkDismissed() {
    try {
      var until = Number(localStorage.getItem(SPARK_DISMISS_KEY) || 0);
      return until && Date.now() < until;
    } catch (_e) {
      return false;
    }
  }

  function dismissSparkRecovery() {
    try {
      localStorage.setItem(
        SPARK_DISMISS_KEY,
        String(Date.now() + SPARK_DISMISS_MS)
      );
    } catch (_e) {}
    var banner = document.getElementById("cinesmith-spark-recovery");
    if (banner) banner.classList.remove("visible");
  }

  function ensureSparkRecoveryBanner() {
    var banner = document.getElementById("cinesmith-spark-recovery");
    if (banner) return banner;

    banner = document.createElement("div");
    banner.id = "cinesmith-spark-recovery";
    banner.className = "cinesmith-spark-recovery-top";
    banner.setAttribute("role", "status");
    banner.innerHTML =
      '<div class="fsr-icon" aria-hidden="true">⚡</div>' +
      '<div class="fsr-copy">' +
      "<strong>Spark is offline — Hermes can plan, but renders wait</strong>" +
      "<p>Check <code>COMFYUI_PRIMARY</code> in Settings, open the Spark/ComfyUI UI, then re-test connections. Agency work continues; image and video jobs need Spark.</p>" +
      '<div class="fsr-meta" id="cinesmith-spark-recovery-meta"></div>' +
      "</div>" +
      '<div class="fsr-actions">' +
      '<button type="button" data-fsr="settings">Check COMFYUI_PRIMARY</button>' +
      '<button type="button" data-fsr="open-ui">Open Spark UI</button>' +
      '<button type="button" data-fsr="retest">Re-test connections</button>' +
      '<a class="fsr-docs" data-fsr="docs" href="/static/docs/DESKTOP_SPARK_PACKAGE.md#spark-offline-recovery" target="_blank" rel="noopener">Desktop Spark package</a>' +
      '<button type="button" class="fsr-dismiss" data-fsr="dismiss" title="Hide for a while">Dismiss</button>' +
      "</div>";

    banner.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t || !t.getAttribute) return;
      var act = t.getAttribute("data-fsr");
      if (!act && t.closest) {
        var hit = t.closest("[data-fsr]");
        if (hit) act = hit.getAttribute("data-fsr");
      }
      if (!act) return;
      if (act === "settings") {
        runAction("settings-spark");
      } else if (act === "open-ui") {
        var url = sparkUiUrl(global.__cinesmithReadiness);
        window.open(url, "_blank", "noopener");
      } else if (act === "retest") {
        if (typeof global.refreshSystemReadiness === "function") {
          global.refreshSystemReadiness(true);
        }
        if (typeof global.testComfyUIAll === "function") {
          try {
            global.testComfyUIAll();
          } catch (_e) {}
        }
        toast("Re-testing Spark / render workers…", "info", 2200);
      } else if (act === "dismiss") {
        dismissSparkRecovery();
      }
      /* docs: default link navigation */
    });

    /* Prefer top of main content column */
    var mainCol = document.querySelector(
      "body > div[style*='flex:1'], body > div[style*='flex: 1']"
    );
    var createView = document.getElementById("create-view");
    if (mainCol && createView && createView.parentNode === mainCol) {
      mainCol.insertBefore(banner, mainCol.firstChild);
    } else if (createView && createView.parentNode) {
      createView.parentNode.insertBefore(banner, createView);
    } else {
      document.body.insertBefore(banner, document.body.firstChild);
    }
    return banner;
  }

  function updateSparkRecovery(readiness) {
    readiness = readiness || global.__cinesmithReadiness;
    var banner = ensureSparkRecoveryBanner();
    var down = isSparkDown(readiness);
    if (!down) {
      banner.classList.remove("visible");
      try {
        localStorage.removeItem(SPARK_DISMISS_KEY);
      } catch (_e) {}
      return;
    }
    if (isSparkDismissed()) {
      banner.classList.remove("visible");
      return;
    }
    var meta = document.getElementById("cinesmith-spark-recovery-meta");
    if (meta) {
      var url = sparkUiUrl(readiness);
      var err =
        (readiness.checks &&
          readiness.checks.spark &&
          (readiness.checks.spark.error || readiness.checks.spark.status)) ||
        "unreachable";
      meta.textContent = "Endpoint: " + url + " · status: " + err;
    }
    /* Fix docs href if static mount differs — keep relative path under docs */
    var docs = banner.querySelector('a[data-fsr="docs"]');
    if (docs) {
      docs.href = "/static/docs/DESKTOP_SPARK_PACKAGE.md#spark-offline-recovery";
      docs.title =
        "docs/DESKTOP_SPARK_PACKAGE.md — Spark offline recovery (COMFYUI_PRIMARY, UI, re-test)";
    }
    banner.classList.add("visible");
  }

  function hookReadinessPoll() {
    if (typeof global.refreshSystemReadiness === "function" && !global.refreshSystemReadiness._cinesmithEmptyHooked) {
      var orig = global.refreshSystemReadiness;
      var wrapped = function (manual) {
        var ret = orig.apply(this, arguments);
        if (ret && typeof ret.then === "function") {
          return ret.then(function (data) {
            try {
              updateSparkRecovery(data || global.__cinesmithReadiness);
            } catch (_e) {}
            return data;
          });
        }
        try {
          updateSparkRecovery(global.__cinesmithReadiness);
        } catch (_e2) {}
        return ret;
      };
      wrapped._cinesmithEmptyHooked = true;
      global.refreshSystemReadiness = wrapped;
    }

    /* Seed from any cached readiness */
    if (global.__cinesmithReadiness) {
      updateSparkRecovery(global.__cinesmithReadiness);
    } else if (typeof global.refreshSystemReadiness === "function") {
      try {
        global.refreshSystemReadiness(false);
      } catch (_e3) {}
    }

    /* Lightweight secondary poll (does not replace app.js interval) */
    setInterval(function () {
      if (global.__cinesmithReadiness) updateSparkRecovery(global.__cinesmithReadiness);
    }, 15000);
  }

  /* ---- Memory Agency learning (J1) ---- */
  function ensureMemoryAgencyCard() {
    var view = document.getElementById("memory-view");
    if (!view) return null;
    var existing = document.getElementById("cinesmith-memory-agency-card");
    if (existing) return existing;

    var card = document.createElement("div");
    card.id = "cinesmith-memory-agency-card";
    card.innerHTML =
      '<div class="fma-kicker">Agency learning</div>' +
      "<h3>Hermes remembers what worked — and what failed</h3>" +
      "<p>This desk is the agency brain’s long-term memory: campaign attempts, audits, and durable rules Hermes injects on the next brief. " +
      "It is not a chat log — it is production intelligence that compounds across Images, Stories, and Spark jobs.</p>" +
      '<div class="fma-status" id="cinesmith-memory-failure-status">' +
      '<span class="fma-chip" id="cinesmith-memory-fail-chip"><span class="dot"></span>Failure auto-consolidate …</span>' +
      '<span class="fma-hint" id="cinesmith-memory-fail-hint">Status loads from the failure-auto-consolidate endpoint when available.</span>' +
      "</div>";

    var layout = view.querySelector(".memory-layout");
    var pad = view.querySelector('[style*="padding:20px"], [style*="padding: 20px"]');
    if (pad) {
      pad.insertBefore(card, pad.firstChild);
    } else if (layout && layout.parentNode) {
      layout.parentNode.insertBefore(card, layout);
    } else {
      view.insertBefore(card, view.firstChild);
    }
    return card;
  }

  async function refreshMemoryFailureStatus() {
    ensureMemoryAgencyCard();
    var chip = document.getElementById("cinesmith-memory-fail-chip");
    var hint = document.getElementById("cinesmith-memory-fail-hint");
    if (!chip) return;

    /* Prefer cached CinesmithCost data */
    var data = global.__cinesmithFailureAuto;
    if (!data) {
      try {
        if (global.CinesmithCore && typeof CinesmithCore.api === "function") {
          data = await CinesmithCore.api(
            "GET",
            "/api/product/failure-auto-consolidate"
          );
        } else {
          var resp = await fetch("/api/product/failure-auto-consolidate");
          if (resp.ok) data = await resp.json();
        }
        if (data) global.__cinesmithFailureAuto = data;
      } catch (_e) {
        data = null;
      }
    }

    if (!data) {
      chip.className = "fma-chip warn";
      chip.innerHTML =
        '<span class="dot"></span>Failure auto-consolidate unavailable';
      if (hint) {
        hint.textContent =
          "Endpoint offline or advanced mode only — consolidate still runs when Hermes records failures.";
      }
      return;
    }

    var count = Number(data.failure_count_since_consolidate || 0);
    var thr = Number(data.threshold || 3);
    var state = "ok";
    if (count > 0) state = "warn";
    if (count >= thr) state = "bad";
    chip.className = "fma-chip" + (state === "ok" ? "" : " " + state);
    chip.innerHTML =
      '<span class="dot"></span>Auto-consolidate ' +
      count +
      "/" +
      thr +
      " failures";

    var latest = data.latest_summary;
    if (hint) {
      if (latest) {
        hint.textContent =
          "Latest: " +
          String(
            latest.hermes_hint || latest.rule || latest.summary_id || "summary"
          ).slice(0, 160);
      } else {
        hint.textContent =
          "After " +
          thr +
          " pipeline failures, Hermes consolidates a durable memory rule for the next campaign.";
      }
    }
  }

  /* ---- Observers / init ---- */
  var debounceTimer = null;
  function scheduleRefresh() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      refreshAll();
    }, OBSERVE_DEBOUNCE_MS);
  }

  function refreshAll() {
    try {
      refreshImagesEmpty();
    } catch (_e) {}
    try {
      refreshVideosEmpty();
    } catch (_e2) {}
    try {
      refreshCharactersEmpty();
    } catch (_e3) {}
    try {
      refreshStoriesAssembleExport();
    } catch (_e4) {}
  }

  function observeHosts() {
    var ids = [
      "filmstrip",
      "spark-grid",
      "character-manager-content",
      "script-video-output-list",
      "storyboard-output",
      "cinesmith-stories-export-strip",
    ];
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el || el._cinesmithEmptyObserved) return;
      var mo = new MutationObserver(scheduleRefresh);
      mo.observe(el, { childList: true, subtree: true });
      el._cinesmithEmptyObserved = true;
    });
  }

  function hookPageSwitches() {
    document.querySelectorAll(".nav-tab[data-page]").forEach(function (tab) {
      if (tab.dataset.emptyBound) return;
      tab.addEventListener("click", function () {
        setTimeout(function () {
          observeHosts();
          refreshAll();
          var page = tab.getAttribute("data-page");
          if (page === "memory-view") {
            ensureMemoryAgencyCard();
            refreshMemoryFailureStatus();
          }
        }, 60);
      });
      tab.dataset.emptyBound = "1";
    });

    /* switchPage may not always click nav tabs */
    if (typeof global.switchPage === "function" && !global.switchPage._cinesmithEmptyHooked) {
      var orig = global.switchPage;
      var wrapped = function (page) {
        var ret = orig.apply(this, arguments);
        setTimeout(function () {
          observeHosts();
          refreshAll();
          if (page === "memory-view" || page === "memory") {
            ensureMemoryAgencyCard();
            refreshMemoryFailureStatus();
          }
        }, 80);
        return ret;
      };
      wrapped._cinesmithEmptyHooked = true;
      global.switchPage = wrapped;
    }
  }

  function init() {
    ensureSparkRecoveryBanner();
    hookReadinessPoll();
    hookPageSwitches();
    observeHosts();
    refreshAll();
    ensureMemoryAgencyCard();
    refreshMemoryFailureStatus();

    setInterval(function () {
      observeHosts();
      refreshAll();
    }, POLL_MS);

    setInterval(function () {
      if (
        document.getElementById("memory-view") &&
        document.getElementById("memory-view").classList.contains("active")
      ) {
        refreshMemoryFailureStatus();
      }
    }, 20000);
  }

  global.CinesmithEmptyStates = {
    init: init,
    refresh: refreshAll,
    refreshStories: refreshStoriesAssembleExport,
    updateSparkRecovery: updateSparkRecovery,
    refreshMemory: refreshMemoryFailureStatus,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(init, 160);
    });
  } else {
    setTimeout(init, 160);
  }
})(window);
