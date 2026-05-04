// dashboard.js — JWT auth, htmx wiring, htmx-ws bootstrap.
//
// Pages render without auth; this script reads the JWT from localStorage
// and uses it for every htmx mutation and for the WS handshake. If the
// JWT is absent on /dashboard we redirect to /login.

(function () {
  "use strict";

  const JWT_KEY = "lipmm_jwt";
  const ACTOR_KEY = "lipmm_actor";

  function getJwt() { return localStorage.getItem(JWT_KEY); }
  function getActor() { return localStorage.getItem(ACTOR_KEY) || "operator"; }
  function setSession(jwt, actor) {
    localStorage.setItem(JWT_KEY, jwt);
    localStorage.setItem(ACTOR_KEY, actor || "operator");
  }
  function clearSession() {
    localStorage.removeItem(JWT_KEY);
    localStorage.removeItem(ACTOR_KEY);
  }

  function newRequestId() {
    // 16-char hex — well above the 8-char min_length on the server.
    const a = new Uint8Array(8);
    crypto.getRandomValues(a);
    return "ui-" + Array.from(a).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function setupHtmxAuth() {
    document.body.addEventListener("htmx:configRequest", (evt) => {
      const jwt = getJwt();
      if (jwt) evt.detail.headers["Authorization"] = "Bearer " + jwt;
      // POST endpoints expect JSON; let htmx send JSON if the form is JSON.
      // For hx-vals JSON, htmx-json-enc handles encoding; we still need
      // to attach a request_id to every mutating request.
      const method = (evt.detail.verb || "GET").toUpperCase();
      if (method !== "GET" && evt.detail.parameters) {
        if (!evt.detail.parameters.request_id) {
          evt.detail.parameters.request_id = newRequestId();
        }
      }
    });
    document.body.addEventListener("htmx:responseError", (evt) => {
      const xhr = evt.detail.xhr;
      if (xhr.status === 401) {
        clearSession();
        location.href = "/login";
      } else {
        showToast("error " + xhr.status + ": " + (xhr.responseText || "").slice(0, 200));
      }
    });
  }

  function showToast(msg) {
    // Minimal toast. Replace with something nicer later if it stings.
    const el = document.createElement("div");
    el.textContent = msg;
    el.className = "fixed bottom-4 right-4 max-w-md rounded bg-rose-700 px-3 py-2 text-sm text-white shadow-lg";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function bindLoginForm() {
    const form = document.getElementById("login-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("login-error");
      errEl.classList.add("hidden");
      const fd = new FormData(form);
      const body = JSON.stringify({
        secret: fd.get("secret"),
        actor: fd.get("actor") || "operator",
      });
      try {
        const r = await fetch("/control/auth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        });
        if (!r.ok) {
          const detail = await r.text();
          errEl.textContent = "auth failed: " + detail.slice(0, 200);
          errEl.classList.remove("hidden");
          return;
        }
        const data = await r.json();
        setSession(data.token, data.actor);
        location.href = "/dashboard";
      } catch (err) {
        errEl.textContent = "network error: " + err.message;
        errEl.classList.remove("hidden");
      }
    });
  }

  function bindLogout() {
    const btn = document.getElementById("logout-btn");
    if (!btn) return;
    btn.addEventListener("click", () => {
      clearSession();
      location.href = "/login";
    });
  }

  function bindKillPanel() {
    document.body.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      if (action === "kill") {
        if (!confirm("Trip the kill switch?\n\nThis cancels all resting orders and halts the strategy.")) return;
        await callJson("/control/kill", { reason: "dashboard kill button" });
      } else if (action === "arm") {
        await callJson("/control/arm", {});
      } else if (action === "resume-after-kill") {
        if (!confirm("Resume normal trading?")) return;
        await callJson("/control/resume", { scope: "global" });
      }
    });
  }

  function bindGenericCalls() {
    document.body.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-call]");
      if (!btn) return;
      e.preventDefault();
      const url = btn.dataset.call;
      let payload = {};
      if (btn.dataset.payload) {
        try { payload = JSON.parse(btn.dataset.payload); }
        catch (err) { return showToast("bad payload: " + err.message); }
      }
      if (btn.dataset.confirm && !confirm(btn.dataset.confirm)) return;
      await callJson(url, payload);
    });
  }

  function bindForms() {
    document.body.addEventListener("submit", async (e) => {
      const form = e.target.closest("form[data-form]");
      if (!form) return;
      e.preventDefault();
      const kind = form.dataset.form;
      const fd = new FormData(form);
      if (kind === "pause") {
        const ticker = fd.get("ticker");
        const side = fd.get("side");
        if (!ticker) return showToast("ticker required");
        const body = side
          ? { scope: "side", ticker, side }
          : { scope: "ticker", ticker };
        await callJson("/control/pause", body);
        form.reset();
      } else if (kind === "knob") {
        const name = fd.get("name");
        const value = parseFloat(fd.get("value"));
        if (!name || Number.isNaN(value)) return showToast("name + numeric value required");
        await callJson("/control/set_knob", { name, value });
        form.reset();
      } else if (kind === "lock") {
        const ttl = fd.get("auto_unlock_seconds");
        const body = {
          ticker: fd.get("ticker"),
          side: fd.get("side"),
          reason: fd.get("reason") || "",
        };
        if (ttl) body.auto_unlock_seconds = parseFloat(ttl);
        await callJson("/control/lock_side", body);
        form.reset();
      } else if (kind === "manual-order") {
        const body = {
          ticker: fd.get("ticker"),
          side: fd.get("side"),
          count: parseInt(fd.get("count"), 10),
          limit_price_cents: parseInt(fd.get("limit_price_cents"), 10),
          lock_after: fd.get("lock_after") === "true",
          reason: fd.get("reason") || "",
        };
        const notional = (body.count * body.limit_price_cents) / 100;
        const msg = `Submit MANUAL ORDER?\n\n  ticker: ${body.ticker}\n  side: ${body.side}\n  count: ${body.count}\n  limit: ${body.limit_price_cents}c\n  notional: $${notional.toFixed(2)}\n  lock_after: ${body.lock_after}`;
        if (!confirm(msg)) return;
        await callJson("/control/manual_order", body);
      }
    });
  }

  function bindNotionalPreview() {
    document.body.addEventListener("input", (e) => {
      const form = e.target.closest('form[data-form="manual-order"]');
      if (!form) return;
      const fd = new FormData(form);
      const count = parseInt(fd.get("count"), 10);
      const cents = parseInt(fd.get("limit_price_cents"), 10);
      const el = form.querySelector("[data-notional]");
      if (!el) return;
      if (Number.isFinite(count) && Number.isFinite(cents) && count > 0 && cents > 0) {
        el.textContent = `notional: $${((count * cents) / 100).toFixed(2)} (max payout ${count}.00)`;
      } else {
        el.textContent = "notional: —";
      }
    });
  }

  async function callJson(url, body) {
    const jwt = getJwt();
    if (!jwt) { location.href = "/login"; return; }
    body = Object.assign({ request_id: newRequestId() }, body);
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + jwt,
      },
      body: JSON.stringify(body),
    });
    if (r.status === 401) {
      clearSession();
      location.href = "/login";
      return;
    }
    if (!r.ok) {
      const text = await r.text();
      showToast(`${url} → ${r.status}: ${text.slice(0, 200)}`);
    }
  }

  function setConnectionPill(text, cls) {
    const pill = document.getElementById("connection-pill");
    if (!pill) return;
    pill.textContent = text;
    pill.className = "pill " + cls;
  }

  function openWebSocket() {
    const mount = document.getElementById("ws-mount");
    if (!mount) return;
    const jwt = getJwt();
    if (!jwt) { location.href = "/login"; return; }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/control/stream/html?token=${encodeURIComponent(jwt)}`;
    // htmx-ws reads `ws-connect` from the element; we set it after JWT is
    // ready, then re-process so htmx wires it up.
    mount.setAttribute("ws-connect", url);
    htmx.process(mount);
    setConnectionPill("connecting…", "bg-slate-700 text-slate-300");
    document.body.addEventListener("htmx:wsOpen", () => {
      setConnectionPill("live", "bg-emerald-700/40 text-emerald-200");
    });
    document.body.addEventListener("htmx:wsClose", () => {
      setConnectionPill("disconnected", "bg-rose-700/40 text-rose-200");
    });
    document.body.addEventListener("htmx:wsError", () => {
      setConnectionPill("error", "bg-rose-700/40 text-rose-200");
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupHtmxAuth();
    bindLoginForm();
    bindLogout();
    bindKillPanel();
    bindGenericCalls();
    bindForms();
    bindNotionalPreview();
    if (location.pathname === "/dashboard") {
      if (!getJwt()) { location.href = "/login"; return; }
      openWebSocket();
    }
  });
})();
