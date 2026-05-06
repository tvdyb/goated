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

  // Per-strike knob-form drafts. Same pattern as theo drafts: every
  // OOB swap of the strike grid (~3s) destroys the form inputs, so we
  // mirror them in localStorage and reapply post-swap.
  const KNOB_DRAFT_KEY = "lipmm_knob_drafts";

  function getKnobDrafts() {
    try {
      return JSON.parse(localStorage.getItem(KNOB_DRAFT_KEY) || "{}");
    } catch (_) {
      return {};
    }
  }
  function saveKnobDrafts(d) {
    localStorage.setItem(KNOB_DRAFT_KEY, JSON.stringify(d));
  }
  function setKnobDraft(slug, name, value) {
    const d = getKnobDrafts();
    if (!d[slug]) d[slug] = {};
    d[slug][name] = value;
    saveKnobDrafts(d);
  }
  function clearKnobDraft(slug) {
    const d = getKnobDrafts();
    delete d[slug];
    saveKnobDrafts(d);
  }
  function applyKnobDrafts() {
    const d = getKnobDrafts();
    let changed = false;
    for (const slug of Object.keys(d)) {
      const form = document.querySelector(
        `[data-slug="${slug}"] form[data-form="strike-knob-set"]`
      );
      if (!form) {
        delete d[slug];
        changed = true;
        continue;
      }
      for (const [name, value] of Object.entries(d[slug])) {
        const input = form.querySelector(`[name="${name}"]`);
        if (input && input.value !== value) input.value = value;
      }
    }
    if (changed) saveKnobDrafts(d);
  }
  function bindKnobDraftSave() {
    const handler = (e) => {
      const form = e.target.closest('form[data-form="strike-knob-set"]');
      if (!form) return;
      const wrap = form.closest("[data-slug]");
      const slug = wrap ? wrap.dataset.slug : null;
      const name = e.target.name;
      if (!slug || !name) return;
      setKnobDraft(slug, name, e.target.value);
    };
    document.body.addEventListener("input", handler);
    document.body.addEventListener("change", handler);
  }

  // Preserve scroll position across OOB swaps. The strike grid swaps
  // every ~3s and a few sections grow/shrink, which makes the browser
  // jump (sometimes to the bottom) — losing the operator's place.
  // Capture window.scrollY before the swap, restore after.
  let _scrollY = null;
  function captureScroll() {
    _scrollY = window.scrollY;
  }
  function restoreScroll() {
    if (_scrollY !== null) {
      // requestAnimationFrame so the swap's layout has settled before
      // we scroll — otherwise the restore can read a transient height.
      const y = _scrollY;
      requestAnimationFrame(() => window.scrollTo(0, y));
      _scrollY = null;
    }
  }

  // Mode select toggles yes_cents visual state. In track_mid mode the
  // cents input is just a placeholder (server ignores it), so we make
  // it OBVIOUSLY non-functional: dim the whole cell, strike-through
  // the value, retitle the label, and surface a yellow note row.
  //
  // NOTE: We use `readOnly` (not `disabled`) so the input still submits
  // as part of FormData. A disabled input is omitted from the form
  // submission entirely, which would break the server's required-field
  // validation on yes_cents in track_mid mode.
  function applyModeToggle(form) {
    const sel = form.querySelector("[data-mode-select]");
    const cents = form.querySelector("[data-yes-cents]");
    const cell = form.querySelector("[data-yes-cents-cell]");
    const lbl = form.querySelector("[data-yes-cents-label]");
    const note = form.parentElement
      && form.parentElement.querySelector("[data-track-mid-note]");
    if (!sel || !cents || !cell || !lbl) return;
    const isMid = sel.value === "track_mid";
    cents.readOnly = isMid;
    cents.disabled = false;  // never disable — that strips it from FormData
    if (isMid) {
      cell.style.opacity = "0.35";
      cell.style.background = "#1a1a1a";
      cell.style.borderStyle = "dashed";
      cents.style.textDecoration = "line-through";
      cents.style.cursor = "not-allowed";
      cents.title = "ignored — theo follows orderbook mid each cycle";
      lbl.textContent = "Yes (cents) — IGNORED";
      lbl.style.color = "var(--no)";
      if (note) note.classList.remove("hidden");
    } else {
      cell.style.opacity = "";
      cell.style.background = "var(--surface)";
      cell.style.borderStyle = "";
      cents.style.textDecoration = "";
      cents.style.cursor = "";
      cents.title = "";
      lbl.textContent = "Yes (cents)";
      lbl.style.color = "var(--ink-lo)";
      if (note) note.classList.add("hidden");
    }
  }

  function applyAllModeToggles() {
    document.querySelectorAll('form[data-form="theo-override-inline"]')
      .forEach(applyModeToggle);
  }

  function bindModeToggle() {
    document.body.addEventListener("change", (e) => {
      if (!e.target.matches("[data-mode-select]")) return;
      const form = e.target.closest('form[data-form="theo-override-inline"]');
      if (form) applyModeToggle(form);
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
      // The chip displays cents in ITS OWN side's terms. Yes chip
      // shows yesC (= best_ask_yes), No chip shows noC (= 100 - best_bid_yes).
      // Both seed "Buy {Side} @ chip-price" — the form does the
      // semantic-to-wire translation on submit.
      const semanticSide = chip.dataset.side === "yes" ? "buy_yes" : "buy_no";
      const priceC = chip.dataset.price;
      seedManualOrderForm({ ticker, semantic_side: semanticSide, price_cents: priceC });
      openDrawer("manual");
      const label = semanticSide === "buy_yes" ? "Buy Yes" : "Buy No";
      showToast(`seeded: ${label} @ ${priceC}¢ on ${ticker}`);
    });
  }

  function seedManualOrderForm({ ticker, semantic_side, price_cents }) {
    const form = document.querySelector('form[data-form="manual-order"]');
    if (!form) return;
    const t = form.querySelector('[name="ticker"]');  if (t) t.value = ticker || "";
    const s = form.querySelector('[name="side"]');    if (s) s.value = semantic_side || "buy_yes";
    const p = form.querySelector('[name="limit_price_cents"]');
    if (p) p.value = price_cents || "";
    // Trigger live preview recalc.
    form.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Translate a semantic side ({buy_yes, sell_yes, buy_no, sell_no})
  // and a price in THAT side's cents → the wire-format Yes-cents
  // {bid, ask} that the backend expects. The framework's
  // OrderManager / ExchangeClient only handle Yes-side orders, so
  // every operator intent collapses into Yes-bid or Yes-ask.
  //   buy_yes  @ X  →  bid Yes @ X   (pay X to enter long Yes)
  //   sell_yes @ X  →  ask Yes @ X   (collect X to exit Yes)
  //   buy_no   @ X  →  ask Yes @ 100-X  (sell Yes at 100-X = buy No at X)
  //   sell_no  @ X  →  bid Yes @ 100-X  (buy Yes at 100-X = sell No at X)
  function semanticToWire(semanticSide, priceCents) {
    const p = parseInt(priceCents, 10);
    if (!Number.isFinite(p) || p < 1 || p > 99) return null;
    switch (semanticSide) {
      case "buy_yes":  return { side: "bid", priceYes: p,
                                yesCents: p, noCents: 100 - p,
                                label: `Buy Yes @ ${p}¢`,
                                equiv: `Bid Yes ${p}¢` };
      case "sell_yes": return { side: "ask", priceYes: p,
                                yesCents: p, noCents: 100 - p,
                                label: `Sell Yes @ ${p}¢`,
                                equiv: `Ask Yes ${p}¢` };
      case "buy_no":   return { side: "ask", priceYes: 100 - p,
                                yesCents: 100 - p, noCents: p,
                                label: `Buy No @ ${p}¢`,
                                equiv: `Ask Yes ${100 - p}¢` };
      case "sell_no":  return { side: "bid", priceYes: 100 - p,
                                yesCents: 100 - p, noCents: p,
                                label: `Sell No @ ${p}¢`,
                                equiv: `Bid Yes ${100 - p}¢` };
      default: return null;
    }
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
    // Defer OOB swaps that would destroy a form the user is actively
    // typing in or has a dropdown open inside. hx-preserve keeps the
    // form's value across swaps, but browsers close any open <select>
    // when its element is detached/reattached — so even with values
    // preserved, the dropdown UX is unusable while the bot is pushing
    // 3s OOB updates. We cancel the per-element swap (not the whole
    // WS message), so other parts of the dashboard still update.
    function focusedFormAncestor() {
      const a = document.activeElement;
      if (!a || a === document.body) return null;
      if (!["SELECT", "INPUT", "TEXTAREA"].includes(a.tagName)) return null;
      return a.closest(
        'form[data-form="strike-knob-set"], ' +
        'form[data-form="theo-override-inline"], ' +
        'form[data-form="manual-order"]'
      );
    }
    document.body.addEventListener("htmx:beforeSwap", (e) => {
      const focusedForm = focusedFormAncestor();
      if (focusedForm) {
        const target = e.detail && e.detail.target;
        // Cancel this swap only if its target contains the focused
        // form (i.e., the swap would destroy/move the form). Other
        // swaps (status bar, decision feed, etc.) proceed normally.
        if (target && (target === focusedForm || target.contains(focusedForm))) {
          e.preventDefault();
          return;
        }
      }
      captureScroll();
    });
    const reapplyAll = () => {
      applyPersistedDrawerState();
      applyPersistedExpansions();
      applyTheoDrafts();
      applyKnobDrafts();
      applyAllModeToggles();
      tickCountdowns();
      restoreScroll();
    };
    // Hook every htmx swap-completion path. Different swap mechanisms
    // (regular AJAX response vs WebSocket OOB vs hx-load) fire
    // different events; covering all of them ensures form drafts get
    // restored regardless of how the strike grid was updated.
    document.body.addEventListener("htmx:afterSwap", reapplyAll);
    document.body.addEventListener("htmx:wsAfterMessage", reapplyAll);
    document.body.addEventListener("htmx:oobAfterSwap", reapplyAll);
    document.body.addEventListener("htmx:load", reapplyAll);
    // Belt-and-suspenders: a MutationObserver on the strike grid
    // catches any DOM replacement we missed via the htmx events. Fires
    // synchronously on subtree mutations and re-applies drafts. Cheap
    // — applyKnobDrafts is idempotent and short-circuits when values
    // already match.
    const grid = document.getElementById("strike-grid");
    if (grid) {
      const obs = new MutationObserver(() => {
        applyTheoDrafts();
        applyKnobDrafts();
      });
      obs.observe(grid, { childList: true, subtree: true });
    }
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

  // Find all strike tickers in the DOM whose ticker starts with
  // `<event>-`. Used by the quick-quote flows to bulk-apply theo
  // overrides across an event.
  function strikesForEvent(eventTicker) {
    const prefix = eventTicker + "-";
    const out = [];
    document.querySelectorAll(".strike-row[data-ticker]").forEach((row) => {
      const t = row.dataset.ticker;
      if (t && t.startsWith(prefix)) out.push(t);
    });
    return out;
  }

  // Sequentially POST /control/set_theo_override for each ticker. Toast
  // a running progress count + a final summary. Per-strike failures
  // are logged to the console so the operator can F12-inspect when the
  // bulk apply doesn't fully succeed.
  async function bulkApplyTheoToStrikes(strikes, params) {
    showToast(`Applying ${params.mode} to ${strikes.length} strikes…`);
    let ok = 0;
    const failures = [];
    for (const t of strikes) {
      try {
        await callJson("/control/set_theo_override", {
          ticker: t,
          yes_cents: params.yes_cents,
          confidence: params.confidence,
          reason: params.reason,
          mode: params.mode,
        });
        ok += 1;
      } catch (err) {
        failures.push({ ticker: t, error: String(err && err.message || err) });
      }
    }
    if (failures.length > 0) {
      // Loud + non-self-clearing summary so the operator knows.
      console.error(
        `bulkApplyTheoToStrikes: ${failures.length}/${strikes.length} FAILED:`,
        failures,
      );
      showToast(
        `Quote-all: ${ok}/${strikes.length} applied, ${failures.length} FAILED. ` +
        `Open browser console (F12) for per-strike error.`,
      );
    } else {
      showToast(`Quote-all done: ${ok}/${strikes.length} applied`);
    }
  }

  // Wait up to ~6s for at least one strike row matching the prefix to
  // appear in the DOM. Returns the discovered strike list (possibly
  // empty if timeout). Used by both ⚡ and "add & quote" flows so a
  // freshly-added event auto-waits for its orderbook to broadcast
  // before bulk-applying.
  async function waitForStrikes(eventTicker, maxWaitMs = 6000) {
    const stepMs = 300;
    const steps = Math.ceil(maxWaitMs / stepMs);
    for (let i = 0; i < steps; i += 1) {
      const found = strikesForEvent(eventTicker);
      if (found.length > 0) return found;
      await new Promise((r) => setTimeout(r, stepMs));
    }
    return strikesForEvent(eventTicker);  // final attempt
  }

  function bindEventStrip() {
    document.body.addEventListener("click", async (e) => {
      const addBtn = e.target.closest('[data-action="add-event"]');
      if (addBtn) {
        e.preventDefault();
        e.stopPropagation();
        const ticker = prompt(
          "Add event ticker (e.g. KXISMPMI-26MAY):", "",
        );
        if (!ticker || !ticker.trim()) return;
        const normalized = ticker.trim().toUpperCase();
        if (!/^[A-Z0-9-]+$/.test(normalized)) {
          return showToast("ticker must contain only A-Z, 0-9, and -");
        }
        // Single confirm — server validates against Kalshi and rejects
        // bogus tickers with a 400. No need for an extra ticker-typing
        // step since the operator literally just typed it.
        if (!confirm(
          `Add event "${normalized}"?\n\n` +
          `The server will validate against Kalshi and reject if the ` +
          `event doesn't exist or has 0 tradable markets.`
        )) return;
        try {
          const resp = await callJson("/control/add_event", {
            event_ticker: normalized,
          });
          if (resp && typeof resp.market_count === "number") {
            showToast(
              `Added ${normalized} (${resp.market_count} markets)`,
            );
          }
        } catch (err) {
          // callJson already toasts the server error
        }
        return;
      }
      const rmBtn = e.target.closest('[data-action="remove-event"]');
      if (rmBtn) {
        e.preventDefault();
        e.stopPropagation();
        const ticker = rmBtn.dataset.eventTicker;
        const restingHint = rmBtn.dataset.restingCount || "0";
        if (!ticker) return;
        if (!confirm(
          `Remove event "${ticker}" from active set?\n\n` +
          `The runner will stop tracking its strikes next cycle. Existing ` +
          `resting orders will not be touched (next prompt asks if you want ` +
          `to cancel them too).`
        )) return;
        // Second prompt: cancel resting? Only meaningful if there's
        // any chance of resting orders. We don't know the precise count
        // here without a runtime fetch, so we always ask.
        const cancelResting = confirm(
          `Also cancel any resting orders on ${ticker}'s strikes?\n\n` +
          `OK = cancel them now (atomic with removal).\n` +
          `Cancel = leave them resting; you can cancel manually later.`
        );
        try {
          const resp = await callJson("/control/remove_event", {
            event_ticker: ticker, cancel_resting: cancelResting,
          });
          if (resp && typeof resp.cancelled_orders === "number") {
            showToast(
              `Removed ${ticker}` +
              (resp.cancelled_orders > 0
                ? ` (cancelled ${resp.cancelled_orders} orders)`
                : ""),
            );
          }
        } catch (err) {
          // callJson already toasts
        }
        return;
      }
      const setEventKnobBtn = e.target.closest('[data-action="set-event-knob"]');
      if (setEventKnobBtn) {
        e.preventDefault();
        e.stopPropagation();
        const ticker = setEventKnobBtn.dataset.ticker;
        if (!ticker) return;
        const eventTicker = ticker.lastIndexOf("-") > 0
          ? ticker.substring(0, ticker.lastIndexOf("-")) : ticker;
        // Read sibling form's name + value inputs.
        const form = setEventKnobBtn.closest('form[data-form="strike-knob-set"]');
        if (!form) return showToast("form not found");
        const fd = new FormData(form);
        const name = (fd.get("name") || "").trim();
        const value = parseFloat(fd.get("value"));
        if (!name) return showToast("knob name required");
        if (!Number.isFinite(value)) return showToast("value must be a number");
        if (!confirm(
          `Apply ${name}=${value} to ALL strikes in event ${eventTicker}?\n\n` +
          `(Per-strike overrides on the same knob still win for those strikes.)`,
        )) return;
        await callJson("/control/set_event_knob", {
          event_ticker: eventTicker, name, value,
        });
        return;
      }
      const unlockAllBtn = e.target.closest('[data-action="unlock-all-event"]');
      if (unlockAllBtn) {
        e.preventDefault();
        e.stopPropagation();
        const ev = unlockAllBtn.dataset.eventTicker;
        if (!ev) return;
        // Find every (ticker, side) lock whose ticker starts with the
        // event prefix. Read from the rendered DOM — the events strip
        // and strike rows surface lock state. Easiest: walk strike-row
        // expanded panels for "lift lock" buttons inside this event.
        const prefix = ev + "-";
        const lockBtns = [];
        document.querySelectorAll(
          '[data-call="/control/unlock_side"]'
        ).forEach((btn) => {
          let payload = {};
          try { payload = JSON.parse(btn.dataset.payload || "{}"); }
          catch { return; }
          if (payload.ticker && payload.ticker.startsWith(prefix)) {
            lockBtns.push({ ticker: payload.ticker, side: payload.side });
          }
        });
        if (lockBtns.length === 0) {
          return showToast(`No side-locks found in ${ev}.`);
        }
        if (!confirm(
          `Lift ${lockBtns.length} side-lock(s) in ${ev}?\n\n` +
          `Bot will resume quoting all unlocked sides next cycle.`,
        )) return;
        let ok = 0, fail = 0;
        for (const { ticker, side } of lockBtns) {
          try {
            await callJson("/control/unlock_side", { ticker, side });
            ok += 1;
          } catch {
            fail += 1;
          }
        }
        showToast(
          `Unlock-all: ${ok} unlocked` +
          (fail > 0 ? `, ${fail} failed` : ""),
        );
        return;
      }
      const quoteAllBtn = e.target.closest('[data-action="quote-all-event"]');
      if (quoteAllBtn) {
        e.preventDefault();
        e.stopPropagation();
        const ev = quoteAllBtn.dataset.eventTicker;
        if (!ev) return;
        // Try immediately first; if no strikes in DOM yet (fresh event,
        // runner hasn't pushed an orderbook snapshot), wait up to 6s.
        let strikes = strikesForEvent(ev);
        if (strikes.length === 0) {
          showToast(`Waiting for ${ev} strikes to load…`);
          strikes = await waitForStrikes(ev);
        }
        if (strikes.length === 0) {
          return showToast(
            `No strikes loaded for ${ev} after 6s — runner may be stuck. ` +
            `Check server logs.`,
          );
        }
        // ONE-CLICK panic flow: single confirm, sensible defaults
        // (track_mid + conf 0.95). For custom values, use the per-strike
        // override form.
        if (!confirm(
          `Quick-quote ALL ${strikes.length} strikes in ${ev}?\n\n` +
          `Mode: market mid (theo = (best_bid + best_ask) / 2 each cycle)\n` +
          `Confidence: 0.95 (active-penny mode → quotes INSIDE best)\n` +
          `Reason: "auto-quote-all"\n\n` +
          `Click OK to apply. For custom values, cancel and use the ` +
          `per-strike override form on each strike.`,
        )) return;
        await bulkApplyTheoToStrikes(strikes, {
          mode: "track_mid", confidence: 0.95,
          yes_cents: 50, reason: "auto-quote-all",
        });
        return;
      }
      const addAndQuoteBtn = e.target.closest('[data-action="add-and-quote-event"]');
      if (addAndQuoteBtn) {
        e.preventDefault();
        e.stopPropagation();
        const tickerRaw = prompt(
          "Add event ticker AND immediately quote all its strikes\n\n" +
          "Ticker (e.g. KXISMPMI-26MAY):", "",
        );
        if (!tickerRaw || !tickerRaw.trim()) return;
        const ev = tickerRaw.trim().toUpperCase();
        if (!/^[A-Z0-9-]+$/.test(ev)) {
          return showToast("ticker must contain only A-Z, 0-9, and -");
        }
        if (!confirm(
          `Add event "${ev}" AND apply track_mid + conf 0.95 to ALL strikes?\n\n` +
          `Server validates the ticker against Kalshi first; if it doesn't ` +
          `exist or has 0 markets the whole operation aborts.`,
        )) return;
        try {
          const resp = await callJson("/control/add_event", {
            event_ticker: ev,
          });
          showToast(`Added ${ev} (${resp.market_count} markets) — waiting for strikes to load…`);
        } catch {
          return;  // callJson already toasted
        }
        // Wait up to ~6s for the runner cycle to push strikes into the
        // DOM. The orderbook_snapshot WS message refreshes the grid
        // each cycle.
        const strikes = await waitForStrikes(ev);
        if (strikes.length === 0) {
          return showToast(
            `Added ${ev} but no strikes appeared after 6s — runner may be slow. ` +
            `Click ⚡ on the chip in a few seconds.`,
          );
        }
        await bulkApplyTheoToStrikes(strikes, {
          mode: "track_mid", confidence: 0.95,
          yes_cents: 50, reason: "auto-quote-all-on-add",
        });
        return;
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
      } else if (kind === "strike-knob-set") {
        const ticker = (fd.get("ticker") || form.dataset.ticker || "").trim();
        const name = (fd.get("name") || "").trim();
        const value = parseFloat(fd.get("value"));
        if (!ticker) return showToast("ticker required");
        if (!name) return showToast("knob name required");
        if (!Number.isFinite(value)) return showToast("value must be a number");
        await callJson("/control/set_strike_knob", {
          ticker, name, value,
        });
        // Clear the draft so the next OOB swap doesn't re-fill the form
        // with the value we just submitted.
        const wrap = form.closest("[data-slug]");
        if (wrap && wrap.dataset.slug) clearKnobDraft(wrap.dataset.slug);
        return;
      } else if (kind === "theo-override" || kind === "theo-override-inline") {
        const ticker = (fd.get("ticker") || form.dataset.ticker || "").trim();
        const mode = (fd.get("mode") || "fixed").trim();
        const confidence = parseFloat(fd.get("confidence"));
        const reason = (fd.get("reason") || "").trim();
        // Optional auto-clear: minutes input → seconds for the API
        const acRaw = fd.get("auto_clear_minutes");
        let auto_clear_seconds = null;
        if (acRaw && String(acRaw).trim() !== "") {
          const acMin = parseFloat(acRaw);
          if (!Number.isFinite(acMin) || acMin <= 0 || acMin > 10080) {
            return showToast("auto-clear must be 1..10080 minutes (= 1 week)");
          }
          auto_clear_seconds = acMin * 60;
        }
        // yes_cents handling: in track_mid mode it's a server-side
        // placeholder (the runner ignores it). Don't gate the submit on
        // it being readable from the form — readonly/disabled state
        // history has burned this path before. If the form has no
        // usable value, default to 50 in track_mid; require valid in
        // fixed mode.
        const rawCents = fd.get("yes_cents");
        let yes_cents = parseInt(rawCents, 10);
        if (!Number.isInteger(yes_cents) || yes_cents < 1 || yes_cents > 99) {
          if (mode === "track_mid") {
            yes_cents = 50;  // unused at quote time; just keep Pydantic happy
          } else {
            return showToast("yes_cents must be 1..99");
          }
        }
        if (!ticker) return showToast("ticker required");
        if (mode !== "fixed" && mode !== "track_mid") {
          return showToast(`unknown mode "${mode}"`);
        }
        if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
          return showToast("confidence must be 0..1");
        }
        if (reason.length < 4) return showToast("reason must be ≥4 chars");
        // Step 1: rich preview confirm() — different message per mode
        let msg;
        if (mode === "track_mid") {
          msg = (
            `MARKET-FOLLOWING MODE for ${ticker}?\n\n` +
            `  Theo will track the orderbook MID each cycle\n` +
            `  (yes_cents=${yes_cents} is just a placeholder; ignored)\n` +
            `  confidence = ${confidence}\n` +
            `  reason = ${reason}\n\n` +
            `The bot will quote this strike at best±N each cycle ` +
            `(N depends on confidence) using live mid as theo. If the ` +
            `book becomes one-sided or crossed, both sides skip until ` +
            `the book recovers.\n\n` +
            `This is RISKIER than a fixed override because the bot ` +
            `follows whatever the market does — including bad ticks.\n\n` +
            `Click OK to continue to ticker confirmation.`
          );
        } else {
          const yes_p = (yes_cents / 100).toFixed(2);
          msg = (
            `OVERRIDE THEO for ${ticker}?\n\n` +
            `  Setting fair value = ${yes_cents}c (P(Yes) = ${yes_p})\n` +
            `  confidence = ${confidence}\n` +
            `  reason = ${reason}\n\n` +
            `The bot will quote this strike as if its fair value is ` +
            `${yes_cents} cents until you clear the override or restart ` +
            `the bot.\n\nClick OK to continue to ticker confirmation.`
          );
        }
        if (!confirm(msg)) return;
        // Step 2: type the ticker exactly
        const typed = prompt(`To confirm, type the ticker name "${ticker}" exactly:`);
        if (typed === null) return;  // cancelled
        if (typed.trim() !== ticker) {
          return showToast(`override aborted — typed "${typed}" did not match "${ticker}"`);
        }
        const body = { ticker, yes_cents, confidence, reason, mode };
        if (auto_clear_seconds !== null) body.auto_clear_seconds = auto_clear_seconds;
        await callJson("/control/set_theo_override", body);
        // Clear the draft for this strike — submission succeeded, the
        // server-side state is now the source of truth and the next
        // render will reflect it.
        const wrap = form.closest("[data-slug]");
        if (wrap && wrap.dataset.slug) clearTheoDraft(wrap.dataset.slug);
        form.reset();
        const conf = form.querySelector("[name=confidence]");
        if (conf) conf.value = "1.0";
      } else if (kind === "manual-order") {
        const semanticSide = fd.get("side") || "buy_yes";
        const ticker = fd.get("ticker");
        const count = parseInt(fd.get("count"), 10);
        const cents = parseInt(fd.get("limit_price_cents"), 10);
        const lockAfter = fd.get("lock_after") === "true";
        const reason = fd.get("reason") || "";
        const wire = semanticToWire(semanticSide, cents);
        if (!ticker) return showToast("ticker required");
        if (!Number.isInteger(count) || count <= 0) return showToast("count must be positive integer");
        if (!wire) return showToast("limit price must be 1..99 cents");
        const isBuy = semanticSide.startsWith("buy_");
        const cost = (cents * count) / 100;
        const maxLoss = isBuy ? cost : ((100 - cents) * count) / 100;
        const maxProfit = isBuy ? ((100 - cents) * count) / 100 : cost;
        const msg = (
          `Submit MANUAL ORDER?\n\n` +
          `  ticker: ${ticker}\n` +
          `  ${wire.label}\n` +
          `  ≡ ${wire.equiv} (wire-level)\n` +
          `  count: ${count}\n` +
          `  ${isBuy ? 'cost' : 'proceeds'}: $${cost.toFixed(2)}\n` +
          `  max loss: $${maxLoss.toFixed(2)}\n` +
          `  max profit: $${maxProfit.toFixed(2)}\n` +
          `  lock_after: ${lockAfter}`
        );
        if (!confirm(msg)) return;
        // Backend wire format: side ∈ {bid, ask}, limit_price_cents in
        // Yes-cents. Translation of semantic No-side intents happens
        // here via semanticToWire — backend stays Yes-only.
        await callJson("/control/manual_order", {
          ticker,
          side: wire.side,
          count,
          limit_price_cents: wire.priceYes,
          lock_after: lockAfter,
          reason,
        });
      }
    });
  }

  function recalcManualPreview(form) {
    const fd = new FormData(form);
    const semanticSide = fd.get("side") || "buy_yes";
    const count = parseInt(fd.get("count"), 10);
    const cents = parseInt(fd.get("limit_price_cents"), 10);
    const wire = semanticToWire(semanticSide, cents);

    const equivEl = form.querySelector("[data-equiv]");
    const notionalEl = form.querySelector("[data-notional]");
    const currencyEl = form.querySelector("[data-side-currency]");

    if (currencyEl) {
      currencyEl.textContent =
        semanticSide.endsWith("_yes") ? "Yes" : "No";
    }

    if (!wire || !Number.isInteger(count) || count <= 0) {
      if (equivEl) equivEl.textContent = "≡ enter price + count";
      if (notionalEl) notionalEl.textContent = "cost: —";
      return;
    }

    if (equivEl) equivEl.textContent = `≡ ${wire.equiv}   (${cents}¢ on chosen side / ${100 - cents}¢ on other)`;

    // Cost / max-loss / max-profit framing in the operator's chosen
    // semantic side (consistent: a "buy" pays its limit price upfront,
    // max loss = limit × count; a "sell" collects upfront, max loss =
    // (100 - limit) × count if held to settlement).
    const isBuy = semanticSide.startsWith("buy_");
    const cost = (cents * count) / 100;
    const maxLoss = isBuy
      ? cost
      : ((100 - cents) * count) / 100;
    const maxProfit = isBuy
      ? ((100 - cents) * count) / 100
      : cost;

    if (notionalEl) {
      const verb = isBuy ? "cost" : "proceeds";
      notionalEl.textContent =
        `${verb}: $${cost.toFixed(2)}   ·   max loss: $${maxLoss.toFixed(2)}   ·   max profit: $${maxProfit.toFixed(2)}`;
    }
  }

  function bindNotionalPreview() {
    document.body.addEventListener("input", (e) => {
      const form = e.target.closest('form[data-form="manual-order"]');
      if (!form) return;
      recalcManualPreview(form);
    });
    // <select> change events don't fire `input` consistently across
    // browsers — listen explicitly so flipping the side dropdown
    // recalculates the preview.
    document.body.addEventListener("change", (e) => {
      const form = e.target.closest('form[data-form="manual-order"]');
      if (!form) return;
      recalcManualPreview(form);
    });
  }

  async function callJson(url, body) {
    const jwt = getJwt();
    if (!jwt) { location.href = "/login"; return null; }
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
      return null;
    }
    if (!r.ok) {
      const text = await r.text();
      showToast(`${url} → ${r.status}: ${text.slice(0, 200)}`);
      return null;
    }
    let data = null;
    try { data = await r.json(); } catch (_) { /* not JSON */ }
    // Manual orders return 200 even when the bot couldn't place the
    // order (risk vetoed / exchange rejected / post-only cross). Surface
    // those outcomes so the operator gets feedback instead of silence.
    if (url === "/control/manual_order" && data) {
      if (data.succeeded) {
        const oid = (data.order_id || "").slice(0, 8);
        showToast(`✓ order placed: ${data.action} ${data.size}@${data.price_cents}c (${oid}…)`);
      } else if (data.risk_vetoed) {
        showToast(`✗ risk-vetoed: ${data.reason || "no reason"}`);
      } else {
        const why = data.reason || data.action || "unknown";
        showToast(`✗ exchange rejected: ${why.slice(0, 200)}`);
      }
    }
    return data;
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
    console.log("[lipmm] dashboard.js loaded — knob-drafts+scroll-preserve build");
    setupHtmxAuth();
    bindLoginForm();
    bindLogout();
    bindKillPanel();
    bindStrikeExpand();
    bindFeedToggle();
    bindPriceChipSeed();
    bindGenericCalls();
    bindEventStrip();
    bindForms();
    bindDrawer();
    bindKnobInline();
    bindCmdEnterManualOrder();
    bindTheoDraftSave();
    bindKnobDraftSave();
    bindModeToggle();
    bindNotionalPreview();
    if (location.pathname === "/dashboard") {
      if (!getJwt()) { location.href = "/login"; return; }
      openWebSocket();
      startCountdownTicker();
      applyPersistedDrawerState();
      applyPersistedExpansions();
      applyTheoDrafts();
      applyKnobDrafts();
      applyAllModeToggles();
    }
  });
})();
