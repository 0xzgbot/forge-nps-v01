/* Cinesmith Coach — adaptive “what next?” guide for world-class first-run UX.
   Reads readiness + local milestones; never blocks production. */
(function (global) {
  "use strict";

  var STORAGE_KEY = "cinesmith_coach_v1";
  var DISMISS_KEY = "cinesmith_coach_dismissed";
  var SAMPLE_BRIEFS = [
    {
      id: "neon-courier",
      label: "Neon courier",
      text:
        "8 cinematic stills of a courier on a rain-soaked rooftop at night, neon cyan and magenta rim light, anamorphic bokeh, grounded wardrobe, no text no logos",
    },
    {
      id: "travel-hook",
      label: "Travel series",
      text:
        "TikTok vertical 9:16 series — girl-next-door traveler finds a hidden coastal village at golden hour, hook-first framing, caption-safe bottom third, soft pastel light, 3 beats",
    },
    {
      id: "product-hero",
      label: "Product hero",
      text:
        "6 premium product stills of a matte black wireless earbud case on wet black stone, soft studio key, specular highlights, luxury catalog lighting, no text",
    },
    {
      id: "story-short",
      label: "Short film",
      text:
        "60-second restrained sci-fi short: lone radio operator on a foggy pier receives a signal from the sea. 4 scenes, emotional close-ups, cool teal grade, no dialogue captions in frame",
    },
  ];

  function toast(msg, type, ms) {
    if (global.CinesmithCore && typeof CinesmithCore.toast === "function") {
      CinesmithCore.toast(msg, type || "info", ms);
      return;
    }
    if (typeof global.globalToast === "function") global.globalToast(msg, type || "info", ms);
  }

  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch (_e) {
      return {};
    }
  }

  function saveState(partial) {
    var next = Object.assign(loadState(), partial || {}, { updated_at: Date.now() });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch (_e) {
      /* ignore */
    }
    return next;
  }

  function isDismissed() {
    try {
      return localStorage.getItem(DISMISS_KEY) === "1";
    } catch (_e) {
      return false;
    }
  }

  function setDismissed(v) {
    try {
      if (v) localStorage.setItem(DISMISS_KEY, "1");
      else localStorage.removeItem(DISMISS_KEY);
    } catch (_e) {
      /* ignore */
    }
  }

  function readinessSnapshot() {
    var chips = {
      isolation: document.getElementById("ready-isolation"),
      spark: document.getElementById("ready-spark"),
      lm: document.getElementById("ready-lm"),
      media: document.getElementById("ready-media"),
    };
    function ok(el) {
      return !!(el && el.classList.contains("ok"));
    }
    function bad(el) {
      return !!(el && el.classList.contains("bad"));
    }
    return {
      hermes: ok(chips.isolation),
      spark: ok(chips.spark),
      sparkBad: bad(chips.spark),
      director: ok(chips.lm),
      media: ok(chips.media),
    };
  }

  function go(page) {
    if (typeof global.switchPage === "function") global.switchPage(page);
  }

  function fillAgencyBrief(text) {
    var el =
      document.getElementById("agency-brief-input") ||
      document.getElementById("brief-input");
    if (el) {
      el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      try {
        el.focus();
      } catch (_e) {
        /* ignore */
      }
    }
    saveState({ used_sample_brief: true });
    toast("Sample brief loaded — edit, then Run live image campaign", "success", 3200);
  }

  function fillImagesBrief(text) {
    go("dashboard-view");
    setTimeout(function () {
      var el = document.getElementById("brief-input");
      if (el) {
        el.value = text;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.focus();
      }
    }, 60);
    saveState({ used_sample_brief: true });
  }

  function computeSteps(ready, state) {
    var steps = [];
    if (!ready.hermes) {
      steps.push({
        id: "hermes",
        title: "Confirm Hermes isolation",
        body: "Relaunch with scripts/launch_cinesmith.sh so Hermes stays in repo hermes_home/.",
        cta: "Refresh stack",
        action: "readiness",
        priority: 10,
      });
    }
    if (ready.sparkBad || !ready.spark) {
      steps.push({
        id: "spark",
        title: ready.sparkBad ? "Spark is offline" : "Connect Spark (ComfyUI)",
        body: "Open Settings → set COMFYUI_PRIMARY to your Spark host, then Test. You can still draft briefs offline.",
        cta: "Open Settings",
        action: "settings",
        priority: 20,
      });
    }
    if (!state.used_sample_brief) {
      steps.push({
        id: "brief",
        title: "Load a sample brief",
        body: "Try a production-ready EP brief, tweak it, then run Hermes.",
        cta: "Use neon courier",
        action: "sample-neon",
        priority: 30,
      });
    }
    if (!state.ran_images) {
      steps.push({
        id: "images",
        title: "Run your first live campaign",
        body: "Images desk: Hermes plans → compiles → Spark renders → audits stills.",
        cta: "Go to Images",
        action: "images",
        priority: 40,
      });
    }
    if (!state.locked_character) {
      steps.push({
        id: "character",
        title: "Lock a character from one photo",
        body: "Characters → Sheet from photo. Identity sticks even if Spark is down; multi-panel sheet when online.",
        cta: "Open Characters",
        action: "characters",
        priority: 50,
      });
    }
    if (!state.ran_story) {
      steps.push({
        id: "story",
        title: "Produce a multi-beat story",
        body: "Stories desk or Agency → Produce multi-beat story. Add Series name for episode continuity.",
        cta: "Open Stories",
        action: "stories",
        priority: 60,
      });
    }
    if (!state.tried_first_last) {
      steps.push({
        id: "first_last",
        title: "Try First → Last motion",
        body: "Videos: select two stills (start, then end), First → Last chip, produce LTX pair.",
        cta: "Open Videos",
        action: "videos",
        priority: 70,
      });
    }
    if (!state.exported) {
      steps.push({
        id: "export",
        title: "Export a client package",
        body: "When clips exist: Assemble / Export package for frames, clips, captions, audio honesty.",
        cta: "Stories export",
        action: "export",
        priority: 80,
      });
    }
    steps.sort(function (a, b) {
      return a.priority - b.priority;
    });
    return steps;
  }

  function runAction(action) {
    switch (action) {
      case "readiness":
        if (typeof global.refreshSystemReadiness === "function") {
          global.refreshSystemReadiness(true);
        }
        break;
      case "settings":
        go("settings-view");
        break;
      case "sample-neon":
        go("create-view");
        fillAgencyBrief(SAMPLE_BRIEFS[0].text);
        break;
      case "images":
        go("dashboard-view");
        break;
      case "characters":
        go("identity-view");
        setTimeout(function () {
          var btn = document.getElementById("char-sheet-from-photo-btn");
          if (btn) btn.classList.add("cinesmith-coach-pulse");
          setTimeout(function () {
            if (btn) btn.classList.remove("cinesmith-coach-pulse");
          }, 2400);
        }, 200);
        break;
      case "stories":
        go("script-view");
        break;
      case "videos":
        go("spark-view");
        setTimeout(function () {
          var chip = document.getElementById("video-mode-first-last");
          if (chip) chip.classList.add("cinesmith-coach-pulse");
          setTimeout(function () {
            if (chip) chip.classList.remove("cinesmith-coach-pulse");
          }, 2400);
        }, 200);
        break;
      case "export":
        go("script-view");
        setTimeout(function () {
          var b = document.getElementById("export-story-package-btn");
          if (b) b.classList.add("cinesmith-coach-pulse");
        }, 200);
        break;
      case "dismiss":
        setDismissed(true);
        render();
        toast("Guide hidden. Press ? then reopen coach anytime from Agency.", "info", 2800);
        break;
      case "restore":
        setDismissed(false);
        render();
        break;
      default:
        break;
    }
  }

  function ensureHost() {
    var host = document.getElementById("cinesmith-coach");
    if (host) return host;
    var anchor =
      document.getElementById("agency-live-brief") ||
      document.getElementById("create-view");
    if (!anchor) return null;
    host = document.createElement("section");
    host.id = "cinesmith-coach";
    host.className = "cinesmith-coach";
    host.setAttribute("aria-label", "Getting started guide");
    if (anchor.id === "agency-live-brief") {
      anchor.parentNode.insertBefore(host, anchor);
    } else {
      anchor.insertBefore(host, anchor.firstChild);
    }
    return host;
  }

  function ensureSampleRow() {
    var brief = document.getElementById("agency-live-brief");
    if (!brief || brief.querySelector(".cinesmith-sample-briefs")) return;
    var row = document.createElement("div");
    row.className = "cinesmith-sample-briefs";
    row.innerHTML =
      '<span class="cinesmith-sample-label">Sample briefs</span>' +
      SAMPLE_BRIEFS.map(function (s) {
        return (
          '<button type="button" class="chip cinesmith-sample-chip" data-sample="' +
          s.id +
          '">' +
          escapeHtml(s.label) +
          "</button>"
        );
      }).join("");
    var label = brief.querySelector(".preset-label");
    if (label && label.nextSibling) {
      brief.insertBefore(row, label.nextSibling);
    } else {
      brief.insertBefore(row, brief.firstChild);
    }
    row.querySelectorAll("[data-sample]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-sample");
        var sample = SAMPLE_BRIEFS.find(function (s) {
          return s.id === id;
        });
        if (sample) fillAgencyBrief(sample.text);
      });
    });
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  function render() {
    ensureSampleRow();
    var host = ensureHost();
    if (!host) return;
    if (isDismissed()) {
      host.innerHTML =
        '<button type="button" class="cinesmith-coach-restore" data-coach-action="restore">Show getting-started guide</button>';
      host.querySelector("[data-coach-action]").addEventListener("click", function () {
        runAction("restore");
      });
      return;
    }
    var ready = readinessSnapshot();
    var state = loadState();
    var steps = computeSteps(ready, state);
    var primary = steps[0];
    var doneCount = 0;
    var totalMilestones = 6;
    if (state.used_sample_brief) doneCount++;
    if (state.ran_images) doneCount++;
    if (state.locked_character) doneCount++;
    if (state.ran_story) doneCount++;
    if (state.tried_first_last) doneCount++;
    if (state.exported) doneCount++;
    if (ready.spark) doneCount = Math.min(totalMilestones, doneCount + 0); // spark is gate not milestone count
    var pct = Math.round((doneCount / totalMilestones) * 100);

    var list = steps
      .slice(0, 4)
      .map(function (s, i) {
        return (
          '<li class="cinesmith-coach-step' +
          (i === 0 ? " primary" : "") +
          '">' +
          "<div><strong>" +
          escapeHtml(s.title) +
          "</strong><p>" +
          escapeHtml(s.body) +
          "</p></div>" +
          '<button type="button" class="btn' +
          (i === 0 ? "" : " btn-secondary") +
          '" data-coach-action="' +
          escapeHtml(s.action) +
          '">' +
          escapeHtml(s.cta) +
          "</button></li>"
        );
      })
      .join("");

    host.innerHTML =
      '<div class="cinesmith-coach-head">' +
      "<div><span class=\"cinesmith-coach-kicker\">Getting started</span>" +
      "<h3>Ship your first production in minutes</h3>" +
      "<p class=\"cinesmith-coach-sub\">Hermes plans and renders; you brief like an EP. Spark offline still lets you draft and lock characters.</p></div>" +
      '<div class="cinesmith-coach-meter" title="Setup milestones">' +
      '<span class="cinesmith-coach-pct">' +
      pct +
      "%</span>" +
      '<div class="cinesmith-coach-bar"><i style="width:' +
      pct +
      '%"></i></div>' +
      '<button type="button" class="ghost-btn cinesmith-coach-hide" data-coach-action="dismiss">Hide</button>' +
      "</div></div>" +
      (primary
        ? '<div class="cinesmith-coach-next"><em>Next</em> ' + escapeHtml(primary.title) + "</div>"
        : '<div class="cinesmith-coach-next done">You’re production-ready — ⌘K for command palette.</div>') +
      "<ol class=\"cinesmith-coach-list\">" +
      list +
      "</ol>";

    host.querySelectorAll("[data-coach-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        runAction(btn.getAttribute("data-coach-action"));
      });
    });
  }

  function mark(key) {
    var o = {};
    o[key] = true;
    saveState(o);
    render();
  }

  function hookProductionSignals() {
    // Images campaign
    var runBtn = document.getElementById("run-campaign-btn");
    if (runBtn && !runBtn.dataset.coachHook) {
      runBtn.dataset.coachHook = "1";
      runBtn.addEventListener("click", function () {
        mark("ran_images");
      });
    }
    var agencyImg = document.getElementById("agency-run-images-btn");
    if (agencyImg && !agencyImg.dataset.coachHook) {
      agencyImg.dataset.coachHook = "1";
      agencyImg.addEventListener("click", function () {
        mark("ran_images");
      });
    }
    var agencyStory = document.getElementById("agency-run-story-btn");
    if (agencyStory && !agencyStory.dataset.coachHook) {
      agencyStory.dataset.coachHook = "1";
      agencyStory.addEventListener("click", function () {
        mark("ran_story");
      });
    }
    var pipeBtn = document.getElementById("run-script-pipeline-btn");
    if (pipeBtn && !pipeBtn.dataset.coachHook) {
      pipeBtn.dataset.coachHook = "1";
      pipeBtn.addEventListener("click", function () {
        mark("ran_story");
      });
    }
    var sheetBtn = document.getElementById("char-sheet-from-photo-btn");
    if (sheetBtn && !sheetBtn.dataset.coachHook) {
      sheetBtn.dataset.coachHook = "1";
      sheetBtn.addEventListener("click", function () {
        mark("locked_character");
      });
    }
    var fl = document.getElementById("video-mode-first-last");
    if (fl && !fl.dataset.coachHook) {
      fl.dataset.coachHook = "1";
      fl.addEventListener("click", function () {
        mark("tried_first_last");
      });
    }
    var exp = document.getElementById("export-story-package-btn");
    if (exp && !exp.dataset.coachHook) {
      exp.dataset.coachHook = "1";
      exp.addEventListener("click", function () {
        mark("exported");
      });
    }
  }

  function init() {
    hookProductionSignals();
    render();
    // Re-render when readiness chips update
    var strip = document.getElementById("system-readiness");
    if (strip && typeof MutationObserver !== "undefined") {
      var obs = new MutationObserver(function () {
        render();
      });
      obs.observe(strip, { attributes: true, subtree: true, attributeFilter: ["class"] });
    }
    setInterval(function () {
      hookProductionSignals();
    }, 4000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    setTimeout(init, 0);
  }

  global.CinesmithCoach = {
    render: render,
    mark: mark,
    fillAgencyBrief: fillAgencyBrief,
    fillImagesBrief: fillImagesBrief,
    samples: SAMPLE_BRIEFS,
    runAction: runAction,
  };
})(typeof window !== "undefined" ? window : globalThis);
