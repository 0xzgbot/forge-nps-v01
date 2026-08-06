/* Cinesmith Videos — generation mode chips (Start frames | First → Last | Text).
 * Loaded after app.js. Wraps processSelectedVideos without editing its body.
 */
(function (global) {
  "use strict";

  const FIRST_LAST_WORKFLOW_ID = "05_ltx2.3_first_last_frame_to_video";
  const START_FRAME_WORKFLOW_ID = "04_ltx2.3_image_to_video";
  const TEXT_WORKFLOW_ID =
    (typeof global.DEFAULT_TEXT_VIDEO_WORKFLOW_ID === "string" && global.DEFAULT_TEXT_VIDEO_WORKFLOW_ID) ||
    "09_ltx23_text_to_video_draft_clean";

  const MODE = {
    START: "start_frames",
    FIRST_LAST: "first_last",
    TEXT: "text",
  };

  let videoMode = MODE.START;
  let _origProcessSelectedVideos = null;
  let _origUpdateVideoSelectionUI = null;
  let _bound = false;

  function $(id) {
    return document.getElementById(id);
  }

  function getSelectionOrdered() {
    const set = global.videoSelection;
    if (!set || typeof set[Symbol.iterator] !== "function") return [];
    return Array.from(set);
  }

  function getEligibleOrdered() {
    const evaluate =
      typeof global.evaluateShotForVideo === "function"
        ? global.evaluateShotForVideo
        : function () {
            return { eligible: true };
          };
    const byId = global.videoShotsById || {};
    return getSelectionOrdered().filter(function (id) {
      const shot = byId[id];
      return shot && evaluate(shot).eligible;
    });
  }

  function isFirstLastWorkflowId(id) {
    const s = String(id || "").toLowerCase();
    return s.indexOf("first_last") >= 0 || s.indexOf("first-last") >= 0;
  }

  function setStatus(msg, progress) {
    const statusEl = $("spark-status-text");
    const progressEl = $("spark-progress");
    if (statusEl && msg != null) statusEl.textContent = msg;
    if (progressEl && progress != null) progressEl.textContent = progress;
  }

  function setModelSelect(workflowId) {
    const select = $("video-model-select");
    if (!select || !workflowId) return;
    const hasOption = Array.from(select.options || []).some(function (o) {
      return o.value === workflowId;
    });
    if (hasOption) select.value = workflowId;
    if (typeof global.syncVideoQuickOptions === "function") {
      try {
        global.syncVideoQuickOptions();
      } catch (_e) {
        /* ignore */
      }
    }
  }

  function updateEmptyState() {
    const empty = $("video-mode-empty-state");
    const hint = $("video-generate-panel-hint");
    const selected = getEligibleOrdered();
    if (hint) {
      if (videoMode === MODE.FIRST_LAST) {
        if (selected.length >= 2) {
          hint.textContent =
            "start → end pair ready (" + selected.length + " selected; using first & last)";
        } else {
          hint.textContent = "select 2 stills (start, then end)";
        }
      } else if (videoMode === MODE.TEXT) {
        hint.textContent = "text-to-video (no stills required)";
      } else {
        hint.textContent = "selected start frames";
      }
    }
    if (!empty) return;
    const showEmpty = videoMode === MODE.FIRST_LAST && selected.length < 2;
    empty.hidden = !showEmpty;
  }

  function setMode(mode, opts) {
    const options = opts || {};
    const next = [MODE.START, MODE.FIRST_LAST, MODE.TEXT].indexOf(mode) >= 0 ? mode : MODE.START;
    videoMode = next;

    document.querySelectorAll("#video-mode-chips [data-video-mode]").forEach(function (btn) {
      const active = btn.getAttribute("data-video-mode") === videoMode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });

    if (!options.skipModelSync) {
      if (videoMode === MODE.FIRST_LAST) {
        setModelSelect(FIRST_LAST_WORKFLOW_ID);
      } else if (videoMode === MODE.START) {
        const select = $("video-model-select");
        if (select && isFirstLastWorkflowId(select.value)) {
          setModelSelect(START_FRAME_WORKFLOW_ID);
        }
      } else if (videoMode === MODE.TEXT) {
        const select = $("video-model-select");
        if (select && !String(select.value || "").match(/T2V|text_to_video/i)) {
          // Prefer an explicit T2V option if present; otherwise leave model alone.
          const t2v = Array.from(select.options || []).find(function (o) {
            return /T2V|text_to_video/i.test(o.value);
          });
          if (t2v) setModelSelect(t2v.value);
        }
      }
    }

    updateEmptyState();
    return videoMode;
  }

  function onChipClick(ev) {
    const btn = ev.currentTarget;
    const mode = btn && btn.getAttribute("data-video-mode");
    if (!mode) return;
    setMode(mode);
    if (mode === MODE.FIRST_LAST) {
      const n = getEligibleOrdered().length;
      if (n < 2) {
        setStatus(
          "First → Last: select two stills (start frame, then end frame).",
          n ? n + " selected — need 2" : "No frames selected"
        );
      } else {
        setStatus("First → Last mode: will interpolate from first selected still to last.", "");
      }
    } else if (mode === MODE.TEXT) {
      setStatus("Text mode: enter a prompt and produce motion (no stills required).", "");
    } else {
      setStatus("Start frames mode: select stills, then produce motion.", "");
    }
  }

  function onModelChange() {
    const select = $("video-model-select");
    if (!select) return;
    if (isFirstLastWorkflowId(select.value) && videoMode !== MODE.FIRST_LAST) {
      setMode(MODE.FIRST_LAST, { skipModelSync: true });
    } else if (
      videoMode === MODE.FIRST_LAST &&
      !isFirstLastWorkflowId(select.value) &&
      !String(select.value || "").match(/T2V|text_to_video/i)
    ) {
      setMode(MODE.START, { skipModelSync: true });
    } else if (String(select.value || "").match(/T2V|text_to_video/i) && videoMode === MODE.START) {
      // Keep start_frames mode for hybrid T2V/I2V distilled when stills are selected.
    }
  }

  async function processFirstLast() {
    const eligible = getEligibleOrdered();
    if (eligible.length < 2) {
      setStatus(
        "First → Last needs two stills. Select a start frame, then an end frame.",
        eligible.length ? eligible.length + " selected — need 2" : "No frames selected"
      );
      updateEmptyState();
      return;
    }
    const startId = eligible[0];
    const endId = eligible[eligible.length - 1];
    if (startId === endId) {
      setStatus("First → Last needs two different stills.", "");
      return;
    }

    const videoOptions =
      typeof global.syncVideoQuickOptions === "function"
        ? global.syncVideoQuickOptions()
        : typeof global.getVideoGenerationOptions === "function"
          ? global.getVideoGenerationOptions()
          : {};
    const duration = parseInt(
      String(videoOptions.duration || ($("video-duration-select") || {}).value || 5),
      10
    );
    const fps = parseInt(String(($("video-fps") || {}).value || "24"), 10);
    const workflowId = FIRST_LAST_WORKFLOW_ID;
    setModelSelect(workflowId);
    const videoPrompt = String(($("video-prompt") || {}).value || "").trim();
    const effectiveAspectRatio =
      typeof global.effectiveVideoAspectRatioForSelected === "function"
        ? global.effectiveVideoAspectRatioForSelected([startId, endId], videoOptions)
        : videoOptions.aspectRatio || "16:9";
    if (typeof global.applyVideoAspectSummaryOverride === "function") {
      global.applyVideoAspectSummaryOverride(videoOptions, effectiveAspectRatio);
    }

    const btn = $("start-batch-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Processing...";
    }
    setStatus(
      "First → Last: queueing LTX pair via " +
        workflowId +
        " (start → end)…",
      ""
    );

    try {
      const platformMode =
        typeof global.getEffectiveModeState === "function"
          ? (global.getEffectiveModeState().platform || {}).mode || "auto"
          : "auto";
      const resp = await fetch("/api/video/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shot_ids: [startId],
          end_shot_id: endId,
          duration: duration,
          fps: fps,
          workflow_id: workflowId,
          mode: "first_last",
          resolution: videoOptions.resolution || "540p",
          aspect_ratio: effectiveAspectRatio,
          prompt: videoPrompt,
          platform_mode: platformMode,
          min_audit_score: 0,
          min_audit_confidence: 0,
          require_audit_pass: false,
          allow_failed_override: true,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || data.status !== "ok") {
        throw new Error(data.detail || data.error || "First/last video processing failed");
      }
      const done = (data.results || []).filter(function (r) {
        return r.status === "ok";
      }).length;
      const blocked = (data.results || []).filter(function (r) {
        return r.status === "blocked";
      }).length;
      const errs = (data.results || []).filter(function (r) {
        return r.status === "error";
      }).length;
      const effectiveWorkflow = data.workflow_id || workflowId;
      setStatus(
        "First → Last jobs queued (" +
          effectiveWorkflow +
          "): " +
          done +
          " queued, " +
          blocked +
          " blocked, " +
          errs +
          " errors",
        ""
      );
      const jobs = (data.results || [])
        .filter(function (r) {
          return r.status === "ok" && r.prompt_id;
        })
        .map(function (r) {
          return {
            shot_id: r.shot_id,
            prompt_id: r.prompt_id,
            campaign_id: global.currentCampaignId || "",
            workflow_id: r.workflow_id || effectiveWorkflow,
            seed: r.seed,
            duration: duration,
            fps: fps,
            host: r.host || "",
            status: "queued",
            end_shot_id: r.end_shot_id || endId,
          };
        });
      if (jobs.length && typeof global.addPendingVideoJobs === "function") {
        global.addPendingVideoJobs(jobs);
        const progressEl = $("spark-progress");
        if (progressEl) {
          progressEl.textContent =
            "Queued " + jobs.length + " first→last ComfyUI job(s). Polling for completed MP4s...";
        }
        if (typeof global.scheduleVideoJobPoll === "function") {
          global.scheduleVideoJobPoll(2000);
        }
      } else {
        const failures = (data.results || []).filter(function (r) {
          return r.status === "blocked" || r.status === "error";
        });
        const failureText = failures
          .slice(0, 4)
          .map(function (r) {
            return (
              (r.shot_id || "shot") +
              ": " +
              (r.error || (r.reasons || []).join(",") || r.status)
            );
          })
          .join(" | ");
        const progressEl = $("spark-progress");
        if (progressEl) progressEl.textContent = failureText || data.output_dir || "";
      }
    } catch (e) {
      setStatus("Error: " + (e && e.message ? e.message : e), "");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Produce motion";
      }
    }
  }

  async function processSelectedVideosWrapped() {
    if (videoMode === MODE.TEXT) {
      if (typeof global.processTextVideo === "function") {
        return global.processTextVideo();
      }
    }
    if (videoMode === MODE.FIRST_LAST) {
      return processFirstLast();
    }
    // Start frames — preserve original single-frame I2V behavior.
    if (_origProcessSelectedVideos) {
      return _origProcessSelectedVideos.apply(this, arguments);
    }
  }

  function updateVideoSelectionUIWrapped() {
    if (_origUpdateVideoSelectionUI) {
      _origUpdateVideoSelectionUI.apply(this, arguments);
    }
    updateEmptyState();
  }

  function bind() {
    if (_bound) return;
    _bound = true;

    document.querySelectorAll("#video-mode-chips [data-video-mode]").forEach(function (btn) {
      btn.addEventListener("click", onChipClick);
    });

    const modelSelect = $("video-model-select");
    if (modelSelect) {
      modelSelect.addEventListener("change", onModelChange);
    }

    if (typeof global.processSelectedVideos === "function") {
      _origProcessSelectedVideos = global.processSelectedVideos;
      global.processSelectedVideos = processSelectedVideosWrapped;
    }
    if (typeof global.updateVideoSelectionUI === "function") {
      _origUpdateVideoSelectionUI = global.updateVideoSelectionUI;
      global.updateVideoSelectionUI = updateVideoSelectionUIWrapped;
    }

    // Ensure First/Last option exists even if HTML is stale.
    if (modelSelect) {
      const exists = Array.from(modelSelect.options || []).some(function (o) {
        return o.value === FIRST_LAST_WORKFLOW_ID;
      });
      if (!exists) {
        const opt = document.createElement("option");
        opt.value = FIRST_LAST_WORKFLOW_ID;
        opt.textContent = "LTX 2.3 First/Last Frame";
        // Insert after start-frame I2V option when present.
        const i2v = Array.from(modelSelect.options || []).find(function (o) {
          return o.value === START_FRAME_WORKFLOW_ID;
        });
        if (i2v && i2v.nextSibling) {
          modelSelect.insertBefore(opt, i2v.nextSibling);
        } else {
          modelSelect.appendChild(opt);
        }
      }
    }

    setMode(MODE.START, { skipModelSync: true });
    updateEmptyState();
  }

  const api = {
    MODE: MODE,
    FIRST_LAST_WORKFLOW_ID: FIRST_LAST_WORKFLOW_ID,
    getMode: function () {
      return videoMode;
    },
    setMode: setMode,
    updateEmptyState: updateEmptyState,
    processFirstLast: processFirstLast,
    bind: bind,
  };

  global.CinesmithVideoModes = api;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    // app.js is already evaluated (script is after app.js); bind immediately.
    bind();
  }
})(typeof window !== "undefined" ? window : globalThis);
