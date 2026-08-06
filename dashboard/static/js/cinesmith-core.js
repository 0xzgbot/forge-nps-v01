/* Cinesmith core client — API helpers, structured errors, toasts (shared modules). */
(function (global) {
  "use strict";

  function ensureToastHost() {
    let host = document.getElementById("global-toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "global-toast-host";
      host.setAttribute("aria-live", "polite");
      document.body.appendChild(host);
    }
    return host;
  }

  function toast(msg, type, ms) {
    type = type || "info";
    ms = ms == null ? 3400 : ms;
    if (typeof global.globalToast === "function") {
      global.globalToast(msg, type, ms);
      return;
    }
    const host = ensureToastHost();
    const el = document.createElement("div");
    el.className = "g-toast " + type;
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(function () {
      el.style.opacity = "0";
      el.style.transition = "opacity .2s";
      setTimeout(function () { el.remove(); }, 220);
    }, ms);
  }

  function parseError(data, status) {
    if (data && data.error && typeof data.error === "object") {
      return {
        code: data.error.code || "error",
        message: data.error.message || "Request failed",
        hint: data.error.hint || "",
        recovery: data.error.recovery || "",
        status: status || 0,
      };
    }
    if (data && data.detail) {
      const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      return { code: "http_error", message: detail, hint: "", recovery: "", status: status || 0 };
    }
    return {
      code: "http_error",
      message: "Request failed" + (status ? " (" + status + ")" : ""),
      hint: "",
      recovery: "",
      status: status || 0,
    };
  }

  async function api(method, path, body) {
    const opts = {
      method: method || "GET",
      headers: {},
    };
    if (body !== undefined && body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(path, opts);
    let data = null;
    const text = await resp.text();
    try { data = text ? JSON.parse(text) : {}; } catch (_e) { data = { raw: text }; }
    if (!resp.ok) {
      const err = parseError(data, resp.status);
      const e = new Error(err.message);
      e.cinesmith = err;
      e.status = resp.status;
      e.data = data;
      throw e;
    }
    return data;
  }

  function reportError(err, fallback) {
    const cinesmith = err && err.cinesmith;
    const msg = (cinesmith && cinesmith.message) || (err && err.message) || fallback || "Something went wrong";
    const recovery = cinesmith && cinesmith.recovery;
    toast(recovery ? msg + " — " + recovery : msg, "error", 5200);
    return cinesmith || { message: msg };
  }

  global.CinesmithCore = {
    toast: toast,
    api: api,
    parseError: parseError,
    reportError: reportError,
  };
})(window);
