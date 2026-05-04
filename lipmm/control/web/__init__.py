"""Server-rendered htmx + Jinja dashboard for the control plane.

`mount_dashboard(app, broadcaster, state, secret=...)` attaches the
dashboard surface to an existing FastAPI app:

  GET  /                       → redirect to /dashboard
  GET  /login                  → secret-entry page
  GET  /dashboard              → main UI shell
  GET  /static/{path}          → dashboard.js and other assets
  WS   /control/stream/html    → htmx-ws OOB-swap stream

Mounting is opt-in (off by default) so non-dashboard deployments stay
slim and the existing test suite keeps the same surface.
"""

from lipmm.control.web.router import mount_dashboard

__all__ = ["mount_dashboard"]
