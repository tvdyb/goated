"""Dashboard control plane — HTTP/WebSocket surface for runtime bot control.

The bot's `LIPRunner` reads `ControlState` each cycle to honor pause scopes,
the kill switch, and runtime knob overrides. The HTTP server (FastAPI app)
mutates `ControlState` in response to authenticated commands from a web
dashboard. Every command is audited via the existing `DecisionLogger`
with `record_type: "operator_command"`.

v1 scope (this PR — Phase 1):
  - `ControlState` with pause-scope (global / ticker / side), kill-switch,
    knob overrides, and a monotonic version counter for future optimistic
    concurrency.
  - JWT bearer auth keyed off a per-deployment shared secret in
    `LIPMM_CONTROL_SECRET` env var.
  - REST endpoints: pause/resume/kill/arm/set_knob/swap_strategy + state.
  - Audit-record emission for every command.

Out of scope for v1 (planned for later phases):
  - Manual orders + side locks (Phase 2)
  - WebSocket push + multi-tab sync (Phase 3)
  - Frontend dashboard pages (Phase 4)
  - Disk-cap retention manager (Phase 5)
"""

from lipmm.control.broadcaster import Broadcaster
from lipmm.control.manual_orders import (
    ManualOrderOutcome,
    submit_manual_order,
)
from lipmm.control.notebooks import NotebookRegistry, TheoNotebook
from lipmm.control.state import (
    ControlConfig,
    ControlState,
    KillState,
    PauseScope,
    SideLock,
    TheoOverride,
)
from lipmm.control.server import ControlServer, build_app
from lipmm.control.web import mount_dashboard

__all__ = [
    "Broadcaster",
    "ControlConfig",
    "ControlServer",
    "ControlState",
    "KillState",
    "ManualOrderOutcome",
    "NotebookRegistry",
    "PauseScope",
    "SideLock",
    "TheoNotebook",
    "TheoOverride",
    "build_app",
    "mount_dashboard",
    "submit_manual_order",
]
