"""Threshold-triggered hedge execution with cooldown.

HedgeTrigger checks whether the portfolio delta exceeds a configurable
threshold and, if so, signals that a hedge order should be placed.
Integrates with the kill switch: if IB is disconnected and delta exceeds
threshold, produces a TriggerResult that fires the Kalshi kill switch.

Non-negotiables: no pandas, fail-loud, type hints.
"""

from __future__ import annotations

import logging
import time

from engine.kill import TriggerResult

logger = logging.getLogger(__name__)

# Default: 3 ZS contracts worth of delta
_DEFAULT_THRESHOLD_CONTRACTS: float = 3.0
_DEFAULT_COOLDOWN_S: float = 60.0


class HedgeTrigger:
    """Threshold-triggered hedge with cooldown and kill-switch integration.

    Usage::

        trigger = HedgeTrigger(threshold=3.0, cooldown_s=60.0)

        if trigger.should_hedge(delta_port=5.2):
            # Place hedge order
            trigger.record_hedge()

        # As kill-switch trigger:
        kill_switch.add_trigger(
            trigger.make_kill_trigger(ib_client, delta_port_fn)
        )
    """

    def __init__(
        self,
        threshold: float = _DEFAULT_THRESHOLD_CONTRACTS,
        cooldown_s: float = _DEFAULT_COOLDOWN_S,
    ) -> None:
        """Initialize hedge trigger.

        Args:
            threshold: Delta threshold in contract-equivalents.
                Hedge fires when |delta_port| >= threshold.
            cooldown_s: Minimum seconds between consecutive hedges.
        """
        if threshold <= 0:
            raise ValueError(f"threshold must be positive, got {threshold}")
        if cooldown_s < 0:
            raise ValueError(f"cooldown_s must be non-negative, got {cooldown_s}")

        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._last_hedge_time: float = 0.0

    @property
    def threshold(self) -> float:
        """Delta threshold in contract-equivalents."""
        return self._threshold

    @property
    def cooldown_s(self) -> float:
        """Minimum seconds between hedges."""
        return self._cooldown_s

    @property
    def last_hedge_time(self) -> float:
        """Monotonic timestamp of the last hedge execution."""
        return self._last_hedge_time

    def should_hedge(
        self,
        delta_port: float,
        *,
        now: float | None = None,
    ) -> bool:
        """Check whether a hedge should be executed.

        Args:
            delta_port: Current portfolio delta in contract-equivalents.
            now: Current monotonic time (for testing). Defaults to
                time.monotonic().

        Returns:
            True if |delta_port| >= threshold AND cooldown has elapsed.
        """
        if abs(delta_port) < self._threshold:
            return False

        now = now if now is not None else time.monotonic()
        elapsed = now - self._last_hedge_time

        if elapsed < self._cooldown_s:
            logger.debug(
                "Hedge trigger: delta=%.2f exceeds threshold=%.2f but "
                "cooldown has %.1fs remaining",
                delta_port, self._threshold,
                self._cooldown_s - elapsed,
            )
            return False

        return True

    def record_hedge(self, *, now: float | None = None) -> None:
        """Record that a hedge was just executed (resets cooldown).

        Args:
            now: Current monotonic time (for testing).
        """
        self._last_hedge_time = now if now is not None else time.monotonic()

    def make_kill_trigger(
        self,
        ib_connected_fn: callable,
        delta_port_fn: callable,
    ) -> callable:
        """Create a kill-switch trigger for IB disconnection + delta breach.

        The trigger fires when:
        1. IB is disconnected (ib_connected_fn() returns False), AND
        2. |delta_port| exceeds the threshold.

        This causes the Kalshi kill switch to cancel all resting orders,
        preventing unhedged exposure from growing.

        Args:
            ib_connected_fn: Zero-arg callable returning bool (True if connected).
            delta_port_fn: Zero-arg callable returning float (current delta).

        Returns:
            A zero-arg callable returning TriggerResult.
        """

        def _check() -> TriggerResult:
            ib_ok = ib_connected_fn()
            if ib_ok:
                return TriggerResult(
                    fired=False,
                    name="hedge_ib_disconnect",
                )

            delta = delta_port_fn()
            if abs(delta) >= self._threshold:
                detail = (
                    f"IB disconnected and |delta|={abs(delta):.2f} >= "
                    f"threshold={self._threshold:.2f}"
                )
                logger.warning("HEDGE KILL TRIGGER: %s", detail)
                return TriggerResult(
                    fired=True,
                    name="hedge_ib_disconnect",
                    detail=detail,
                )

            return TriggerResult(
                fired=False,
                name="hedge_ib_disconnect",
                detail=f"IB disconnected but |delta|={abs(delta):.2f} < threshold",
            )

        return _check
