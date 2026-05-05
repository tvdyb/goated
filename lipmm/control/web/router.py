"""FastAPI mount for the htmx + Jinja dashboard.

Routes:
  GET  /                       → 302 to /dashboard
  GET  /login                  → secret-entry page (unauth'd)
  GET  /dashboard              → main UI shell (unauth'd; JS gates auth)
  GET  /static/{path}          → bundled JS/CSS
  WS   /control/stream/html    → htmx-ws OOB-swap event stream

The dashboard pages don't require auth themselves — they're chrome that
JS hydrates with a JWT from localStorage. Mutations and the HTML WS
both validate the JWT, so an unauthenticated browser sees the shell
but can't change anything or open the live stream.

The HTML WS endpoint reuses the existing `Broadcaster` so a single state
change fans out to BOTH the JSON-speaking `/control/stream` and every
HTML-speaking dashboard tab.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lipmm.control.auth import get_secret
from lipmm.control.web import _paths
from lipmm.control.web.renderer import HtmlWebSocketAdapter, render_initial

if TYPE_CHECKING:
    from lipmm.control.broadcaster import Broadcaster
    from lipmm.control.state import ControlState

logger = logging.getLogger(__name__)

_templates = Jinja2Templates(directory=str(_paths.TEMPLATES_DIR))
# Cache-bust static asset URLs (esp. dashboard.js). Restart of the bot
# bumps this, so every browser pulls fresh JS on the next page load.
import time as _time
_BOOT_TS = int(_time.time())
_templates.env.globals["boot_ts"] = _BOOT_TS


def mount_dashboard(
    app: FastAPI,
    *,
    broadcaster: "Broadcaster",
    state: "ControlState",
    secret: str | None = None,
) -> None:
    """Attach the dashboard surface to `app`. Idempotent at the route
    level (Starlette will raise if you mount twice — caller's job to
    only invoke once per app)."""
    app.mount(
        "/static",
        StaticFiles(directory=str(_paths.STATIC_DIR)),
        name="lipmm-control-static",
    )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request) -> HTMLResponse:
        return _templates.TemplateResponse(request, "login.html")

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page(request: Request) -> HTMLResponse:
        snap = state.snapshot()
        # First-paint includes empty panels — JS opens the WS which then
        # sends the `initial` event with full data (and the up-to-date
        # presence). Server-rendering the snapshot avoids a flash of
        # empty panels for the initial 100ms before the WS opens.
        runtime = None
        collect = getattr(app.state, "collect_runtime", None)
        if collect is not None:
            try:
                runtime = await collect()
            except Exception as exc:
                logger.info("first-paint runtime collect failed: %s", exc)
        incentives = None
        collect_inc = getattr(app.state, "collect_incentives", None)
        if collect_inc is not None and app.state.incentive_cache is not None:
            try:
                incentives = collect_inc()
            except Exception as exc:
                logger.info("first-paint incentives collect failed: %s", exc)
        orderbooks = broadcaster.last_orderbook
        # Phase 10b: build joined strike views + event meta server-side
        # so the very first HTML the browser sees is fully populated
        # (no flash of empty grid before WS opens).
        from lipmm.control.web.renderer import (
            event_meta_from_strikes,
            group_strikes_by_event,
            join_strike_data,
            multi_event_summary,
        )
        strikes = join_strike_data(snap, runtime, incentives, orderbooks)
        active_events = (snap or {}).get("active_events") or []
        groups = group_strikes_by_event(strikes, active_events=active_events)
        summary = multi_event_summary(groups)
        event = event_meta_from_strikes(strikes)
        pnl_total = (runtime or {}).get("total_realized_pnl_dollars", 0.0)
        balance = (runtime or {}).get("balance") or {}
        ctx = {
            "snapshot": snap,
            "presence": broadcaster.presence(),
            "total_tabs": broadcaster.tab_count or 1,
            "records": [],
            "runtime": runtime,
            "incentives": incentives,
            "orderbooks": orderbooks,
            "strikes": strikes,
            "groups": groups,
            "summary": summary,
            "event": event,
            "pnl_total": pnl_total,
            "balance": balance,
        }
        return _templates.TemplateResponse(request, "dashboard.html", ctx)

    @app.websocket("/control/stream/html")
    async def html_stream(websocket: WebSocket) -> None:
        token = websocket.query_params.get("token", "")
        if not token:
            await websocket.close(code=1008, reason="missing token")
            return
        secret_to_use = (
            secret if secret is not None
            else websocket.app.state.control_secret or get_secret()
        )
        try:
            from jose import jwt as _jwt
            claims = _jwt.decode(token, secret_to_use, algorithms=["HS256"])
            actor = claims.get("sub", "operator")
        except Exception as exc:
            await websocket.close(code=1008, reason=f"invalid token: {exc}")
            return

        await websocket.accept()
        adapter = HtmlWebSocketAdapter(websocket)
        tab_id = await broadcaster.register(adapter)
        try:
            collect = getattr(websocket.app.state, "collect_runtime", None)
            runtime = None
            if collect is not None:
                try:
                    runtime = await collect()
                except Exception as exc:
                    logger.info("ws initial runtime collect failed: %s", exc)
            collect_inc = getattr(websocket.app.state, "collect_incentives", None)
            incentives = None
            if collect_inc is not None and websocket.app.state.incentive_cache is not None:
                try:
                    incentives = collect_inc()
                except Exception as exc:
                    logger.info("ws initial incentives collect failed: %s", exc)
            orderbooks = broadcaster.last_orderbook
            # Seed the adapter's "last seen" snapshots so subsequent
            # events (state_change, runtime, incentives, orderbook)
            # render with full context.
            adapter._last_runtime = runtime  # noqa: SLF001
            adapter._last_incentives = incentives  # noqa: SLF001
            adapter._last_orderbooks = orderbooks  # noqa: SLF001
            initial_html = render_initial(
                state.snapshot(),
                presence=broadcaster.presence(),
                total_tabs=broadcaster.tab_count,
                records=[],
                runtime=runtime,
                incentives=incentives,
                orderbooks=orderbooks,
            )
            await websocket.send_text(initial_html)
            await broadcaster.notify_join(tab_id)
            # Read loop just keeps the connection alive; client doesn't
            # send anything actionable in v1.
            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    break
        except Exception as exc:
            logger.info("html WS tab_id=%s closed: %s", tab_id, exc)
        finally:
            await broadcaster.unregister(tab_id)
            # Stash actor for later access if needed
            _ = actor

    logger.info("dashboard mounted: /, /login, /dashboard, /static, WS /control/stream/html")
