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

  // Strike expand state is persisted in localStorage so the panel
  // stays open across the strike-grid's frequent OOB re-renders
  // (orderbook_snapshot fires every ~3s).
  const EXPAND_KEY = "lipmm_expanded_strikes";

  function getExpandedSet() {
    try {
      return new Set(JSON.parse(localStorage.getItem(EXPAND_KEY) || "[]"));
    } catch (_) {
      return new Set();
    }
  }
  function saveExpandedSet(set) {
    localStorage.setItem(EXPAND_KEY, JSON.stringify([...set]));
  }

  // Per-strike theo-override form drafts. Every keystroke saves the
  // value in localStorage; every htmx OOB swap of the strike grid
  // (which fires every ~3s on orderbook updates) blows away the input
  // elements, so we restore from drafts after each swap. Cleared on
  // successful submit. Without this, the user can't type a 4-char
  // reason without losing it.
  const THEO_DRAFT_KEY = "lipmm_theo_drafts";

  function getTheoDrafts() {
    try {
      return JSON.parse(localStorage.getItem(THEO_DRAFT_KEY) || "{}");
    } catch (_) {
      return {};
    }
  }
  function saveTheoDrafts(d) {
    localStorage.setItem(THEO_DRAFT_KEY, JSON.stringify(d));
  }
  function setTheoDraft(slug, name, value) {
    const d = getTheoDrafts();
    if (!d[slug]) d[slug] = {};
    d[slug][name] = value;
    saveTheoDrafts(d);
  }
  function clearTheoDraft(slug) {
    const d = getTheoDrafts();
    delete d[slug];
    saveTheoDrafts(d);
  }

  function applyTheoDrafts() {
    const d = getTheoDrafts();
    let changed = false;
    for (const slug of Object.keys(d)) {
      const form = document.querySelector(
        `[data-slug="${slug}"] form[data-form="theo-override-inline"]`
      );
      if (!form) {
        // Strike row not in DOM anymore (collapsed / vanished). Drop
        // the draft so it doesn't survive forever.
        delete d[slug];
        changed = true;
        continue;
      }
      for (const [name, value] of Object.entries(d[slug])) {
        const input = form.querySelector(`[name="${name}"]`);
        if (input && input.value !== value) input.value = value;
      }
    }
    if (changed) saveTheoDrafts(d);
  }

  function bindTheoDraftSave() {
    document.body.addEventListener("input", (e) => {
      const form = e.target.closest('form[data-form="theo-override-inline"]');
      if (!form) return;
      const wrap = form.closest("[data-slug]");
      const slug = wrap ? wrap.dataset.slug : null;
      const name = e.target.name;
      if (!slug || !name) return;
      setTheoDraft(slug, name, e.target.value);
    });
  }

  function applyPersistedExpansions() {
    const open = getExpandedSet();
    let changed = false;
    for (const slug of [...open]) {
      const expand = document.getElementById("expand-" + slug);
      const row = document.querySelector(`.strike-row[data-slug="${slug}"]`);
      if (expand && row) {
        expand.classList.remove("hidden");
        row.classList.add("expanded");
        const caret = row.querySelector(".strike-caret");
        if (caret) caret.style.transform = "rotate(90deg)";
      } else {
        // The strike disappeared from the grid (e.g. event rotated);
        // drop it from the persisted set so it doesn't accumulate.
        open.delete(slug);
        changed = true;
      }
    }
    if (changed) saveExpandedSet(open);
  }

  function bindStrikeExpand() {
    document.body.addEventListener("click", (e) => {
      // Don't expand if the click was on an actionable child (price chip,
      // button, etc.). Those have their own data-action handlers that
      // run via stopPropagation.
      if (e.target.closest("[data-action]")) return;
      if (e.target.closest("button")) return;
      const row = e.target.closest(".strike-row");
      if (!row) return;
      const slug = row.dataset.slug;
      const expand = document.getElementById("expand-" + slug);
      if (!expand) return;
      const opening = expand.classList.contains("hidden");
      expand.classList.toggle("hidden");
      row.classList.toggle("expanded", opening);
      const caret = row.querySelector(".strike-caret");
      if (caret) caret.style.transform = opening ? "rotate(90deg)" : "";
      const set = getExpandedSet();
      if (opening) set.add(slug); else set.delete(slug);
      saveExpandedSet(set);
    });
  }

  function bindFeedToggle() {
    document.body.addEventListener("click", (e) => {
      const btn = e.target.closest('[data-action="toggle-feed"]');
      if (!btn) return;
      e.preventDefault();
      const feed = document.getElementById("decision-feed");
      if (!feed) return;
      const extras = feed.querySelectorAll(".feed-extra");
      const opening = extras.length > 0 && extras[0].classList.contains("hidden");
      extras.forEach((el) => el.classList.toggle("hidden", !opening));
      const caret = btn.querySelector(".feed-caret");
      if (caret) caret.style.transform = opening ? "rotate(90deg)" : "";
      const counter = btn.querySelector("[data-feed-count]");
      if (counter) counter.textContent = String(opening ? extras.length + 3 : 3);
    });
  }

  function bindPriceChipSeed() {
    document.body.addEventListener("click", (e) => {
      const chip = e.target.closest('[data-action="seed-manual"]');
      if (!chip) return;
      e.preventDefault();
      e.stopPropagation();
      const ticker = chip.dataset.ticker;
      // Yes click → bid (buy Yes); No click → ask (sell Yes).
      // Either way, limit_price_cents = the chip's value.
      const side = chip.dataset.side === "yes" ? "bid" : "ask";
      const priceC = chip.dataset.price;
      seedManualOrderForm({ ticker, side, price_cents: priceC });
      openDrawer("manual");
      showToast(`seeded manual order: ${ticker} ${side} ${priceC}¢`);
    });
  }

  function seedManualOrderForm({ ticker, side, price_cents }) {
    const form = document.querySelector('form[data-form="manual-order"]');
    if (!form) return;
    const t = form.querySelector('[name="ticker"]');     if (t) t.value = ticker || "";
    const s = form.querySelector('[name="side"]');       if (s) s.value = side || "bid";
    const p = form.querySelector('[name="limit_price_cents"]');
    if (p) p.value = price_cents || "";
    // Trigger notional preview recalc
    form.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // ── Operator drawer (Phase 10c) ────────────────────────────────
  const DRAWER_KEY = "lipmm_drawer_open";
  const TAB_KEY = "lipmm_drawer_tab";
  const VALID_TABS = new Set(["theos", "pauses", "knobs", "locks", "manual"]);

  function openDrawer(tab) {
    document.body.classList.add("drawer-open");
    localStorage.setItem(DRAWER_KEY, "1");
    if (tab) setActiveTab(tab);
  }
  function closeDrawer() {
    document.body.classList.remove("drawer-open");
    localStorage.setItem(DRAWER_KEY, "0");
  }
  function toggleDrawer() {
    if (document.body.classList.contains("drawer-open")) closeDrawer();
    else openDrawer();
  }
  function setActiveTab(name) {
    if (!VALID_TABS.has(name)) name = "theos";
    localStorage.setItem(TAB_KEY, name);
    document.querySelectorAll(".drawer-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll("[data-tab-panel]").forEach((p) => {
      p.classList.toggle("hidden", p.dataset.tabPanel !== name);
    });
  }
  function applyPersistedDrawerState() {
    if (localStorage.getItem(DRAWER_KEY) === "1") {
      document.body.classList.add("drawer-open");
    }
    setActiveTab(localStorage.getItem(TAB_KEY) || "theos");
  }

  function bindDrawer() {
    // Toggle (FAB or close button)
    document.body.addEventListener("click", (e) => {
      const t = e.target.closest('[data-action="toggle-drawer"]');
      if (!t) return;
      e.preventDefault();
      toggleDrawer();
    });
    // Tab buttons
    document.body.addEventListener("click", (e) => {
      const tab = e.target.closest("[data-tab]");
      if (!tab) return;
      e.preventDefault();
      setActiveTab(tab.dataset.tab);
    });
    // After every htmx OOB swap of the drawer, re-apply the active tab
    // AND re-open any strike rows that were expanded — the swap blew
    // away both pieces of client-side state.
    document.body.addEventListener("htmx:afterSwap", () => {
      applyPersistedDrawerState();
      applyPersistedExpansions();
      applyTheoDrafts();
      tickCountdowns();
    });
    document.body.addEventListener("htmx:wsAfterMessage", () => {
      applyPersistedDrawerState();
      applyPersistedExpansions();
      applyTheoDrafts();
      tickCountdowns();
    });
  }

  function bindKnobInline() {
    // Drawer's Knobs tab uses live sliders. Debounce-submit on change
    // (after the user releases the slider).
    document.body.addEventListener("change", async (e) => {
      const form = e.target.closest('form[data-form="knob-inline"]');
      if (!form) return;
      const fd = new FormData(form);
      const name = fd.get("name");
      const value = parseFloat(fd.get("value"));
      if (!name || Number.isNaN(value)) return;
      // Update the inline value display immediately
      const display = form.querySelector(".knob-value");
      if (display) display.textContent = value.toFixed(2);
      await callJson("/control/set_knob", { name, value });
    });
    // Live-update the inline value on input (no API call yet)
    document.body.addEventListener("input", (e) => {
      const form = e.target.closest('form[data-form="knob-inline"]');
      if (!form) return;
      const value = parseFloat(form.querySelector('[name="value"]').value);
      if (Number.isNaN(value)) return;
      const display = form.querySelector(".knob-value");
      if (display) display.textContent = value.toFixed(2);
    });
  }

  function bindCmdEnterManualOrder() {
    document.body.addEventListener("keydown", (e) => {
      if (!(e.key === "Enter" && (e.metaKey || e.ctrlKey))) return;
      const form = e.target.closest('form[data-form="manual-order"]');
      if (!form) return;
      e.preventDefault();
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
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
      // If the call cleared a theo override, wipe any stale draft for
      // that ticker's slug so a half-typed value doesn't reappear on
      // the next swap.
      if (url === "/control/clear_theo_override") {
        const wrap = btn.closest("[data-slug]");
        if (wrap && wrap.dataset.slug) clearTheoDraft(wrap.dataset.slug);
      }
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
      } else if (kind === "theo-override" || kind === "theo-override-inline") {
        const ticker = (fd.get("ticker") || form.dataset.ticker || "").trim();
        const yes_cents = parseInt(fd.get("yes_cents"), 10);
        const confidence = parseFloat(fd.get("confidence"));
        const reason = (fd.get("reason") || "").trim();
        if (!ticker) return showToast("ticker required");
        if (!Number.isInteger(yes_cents) || yes_cents < 1 || yes_cents > 99) {
          return showToast("yes_cents must be 1..99");
        }
        if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
          return showToast("confidence must be 0..1");
        }
        if (reason.length < 4) return showToast("reason must be ≥4 chars");
        const yes_p = (yes_cents / 100).toFixed(2);
        // Step 1: rich preview confirm()
        const msg = (
          `OVERRIDE THEO for ${ticker}?\n\n` +
          `  Setting fair value = ${yes_cents}c (P(Yes) = ${yes_p})\n` +
          `  confidence = ${confidence}\n` +
          `  reason = ${reason}\n\n` +
          `The bot will quote this strike as if its fair value is ` +
          `${yes_cents} cents until you clear the override or restart ` +
          `the bot.\n\nClick OK to continue to ticker confirmation.`
        );
        if (!confirm(msg)) return;
        // Step 2: type the ticker exactly
        const typed = prompt(`To confirm, type the ticker name "${ticker}" exactly:`);
        if (typed === null) return;  // cancelled
        if (typed.trim() !== ticker) {
          return showToast(`override aborted — typed "${typed}" did not match "${ticker}"`);
        }
        await callJson("/control/set_theo_override", {
          ticker, yes_cents, confidence, reason,
        });
        // Clear the draft for this strike — submission succeeded, the
        // server-side state is now the source of truth and the next
        // render will reflect it.
        const wrap = form.closest("[data-slug]");
        if (wrap && wrap.dataset.slug) clearTheoDraft(wrap.dataset.slug);
        form.reset();
        const conf = form.querySelector("[name=confidence]");
        if (conf) conf.value = "1.0";
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

  function fmtTimeRemaining(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return "expired";
    const s = Math.floor(seconds);
    const days = Math.floor(s / 86400);
    const hours = Math.floor((s % 86400) / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${String(mins).padStart(2, "0")}m`;
    return `${mins}:${String(secs).padStart(2, "0")}`;
  }

  function tickCountdowns() {
    const now = Date.now() / 1000;
    document.querySelectorAll('[data-time-remaining="true"]').forEach((el) => {
      const endTs = parseFloat(el.dataset.endTs);
      if (!Number.isFinite(endTs)) return;
      el.textContent = fmtTimeRemaining(endTs - now);
      if (endTs - now <= 0) {
        el.classList.remove("text-emerald-300");
        el.classList.add("text-rose-300");
      } else if (endTs - now <= 3600) {
        el.classList.remove("text-emerald-300");
        el.classList.add("text-amber-300");
      }
    });
  }

  function startCountdownTicker() {
    // 1Hz cadence is cheap (no network), but the *visible* string only
    // changes once per minute when > 1h remaining and once per hour
    // when > 1d remaining. The flicker the operator was seeing came
    // from htmx OOB swaps replacing the data-time-remaining elements
    // with their server-rendered "—" placeholder; we now call
    // tickCountdowns() right after every swap so the placeholder is
    // overwritten within a frame instead of waiting up to 1s.
    setInterval(tickCountdowns, 1000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupHtmxAuth();
    bindLoginForm();
    bindLogout();
    bindKillPanel();
    bindStrikeExpand();
    bindFeedToggle();
    bindPriceChipSeed();
    bindGenericCalls();
    bindForms();
    bindDrawer();
    bindKnobInline();
    bindCmdEnterManualOrder();
    bindTheoDraftSave();
    bindNotionalPreview();
    if (location.pathname === "/dashboard") {
      if (!getJwt()) { location.href = "/login"; return; }
      openWebSocket();
      startCountdownTicker();
      applyPersistedDrawerState();
      applyPersistedExpansions();
      applyTheoDrafts();
    }
  });
})();
