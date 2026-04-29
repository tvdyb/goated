"""Kill-switch primitives for Kalshi order cancellation.

Provides batch-cancel operations and a composable group-trigger
mechanism. These are the building blocks; the full four-trigger kill
switch (ACT-24, Wave 1) composes on top of this module.

Gaps closed: GAP-171 (wire DELETE batch + group trigger endpoints).

Non-negotiables enforced:
  - Fail-loud: partial cancel raises KillSwitchError, never silently continues
  - No pandas
  - Type hints on all public interfaces
  - asyncio for I/O only; trigger evaluation is synchronous
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from feeds.kalshi.errors import KalshiAPIError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class KillSwitchError(Exception):
    """Raised when a kill-switch batch cancel cannot fully complete.

    Attributes:
        failed_order_ids: Order IDs that could not be cancelled after
            all retry attempts.
        partial_errors: List of (order_id, exception) pairs from the
            last retry round.
    """

    def __init__(
        self,
        message: str,
        *,
        failed_order_ids: list[str],
        partial_errors: list[tuple[str, Exception]] | None = None,
    ) -> None:
        self.failed_order_ids = failed_order_ids
        self.partial_errors = partial_errors or []
        super().__init__(message)


# ---------------------------------------------------------------------------
# Protocol for the Kalshi client (allows easy mocking)
# ---------------------------------------------------------------------------


class CancelClient(Protocol):
    """Minimal protocol for the subset of KalshiClient used by kill primitives."""

    async def cancel_order(self, order_id: str) -> dict[str, Any]: ...

    async def batch_cancel_orders(self, order_ids: list[str]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Batch cancel primitives
# ---------------------------------------------------------------------------

# Maximum IDs per single batch request (Kalshi API limit)
_BATCH_CHUNK_SIZE = 100

# Default retry parameters
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BACKOFF_S = 0.5


async def batch_cancel_all(
    client: CancelClient,
    order_ids: list[str],
    *,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_backoff_s: float = _DEFAULT_RETRY_BACKOFF_S,
) -> list[str]:
    """Cancel all orders in the provided list.

    Args:
        client: Kalshi client with cancel endpoints.
        order_ids: List of order IDs to cancel.
        max_retries: Number of retry rounds for failed IDs.
        retry_backoff_s: Base backoff between retry rounds (doubles each round).

    Returns:
        List of successfully cancelled order IDs.

    Raises:
        KillSwitchError: If any order IDs remain uncancelled after all retries.
    """
    if not order_ids:
        logger.info("batch_cancel_all called with empty order list; nothing to do")
        return []

    logger.warning(
        "KILL: batch_cancel_all invoked for %d order(s)", len(order_ids),
    )

    cancelled: list[str] = []
    remaining = list(order_ids)

    for attempt in range(max_retries + 1):
        if not remaining:
            break

        if attempt > 0:
            wait = retry_backoff_s * (2 ** (attempt - 1))
            logger.warning(
                "KILL: retry %d/%d for %d remaining order(s), backoff %.1fs",
                attempt, max_retries, len(remaining), wait,
            )
            await asyncio.sleep(wait)

        newly_cancelled, newly_failed = await _execute_batch_cancel(
            client, remaining,
        )
        cancelled.extend(newly_cancelled)
        remaining = [oid for oid, _ in newly_failed]

    if remaining:
        msg = (
            f"KILL: {len(remaining)} order(s) remain uncancelled after "
            f"{max_retries + 1} attempt(s): {remaining}"
        )
        logger.error(msg)
        raise KillSwitchError(
            msg,
            failed_order_ids=remaining,
        )

    logger.warning("KILL: batch_cancel_all complete — %d order(s) cancelled", len(cancelled))
    return cancelled


def filter_orders_by_event(
    order_ids_with_tickers: list[tuple[str, str]],
    event_ticker: str,
) -> list[str]:
    """Filter order IDs to those belonging to a given event.

    Args:
        order_ids_with_tickers: List of (order_id, market_ticker) pairs.
        event_ticker: Event ticker prefix (e.g. ``KXSOYBEANW-26APR25``).

    Returns:
        List of order IDs whose market ticker starts with the event prefix.
    """
    return [
        oid for oid, ticker in order_ids_with_tickers
        if ticker.startswith(event_ticker)
    ]


def filter_orders_by_market(
    order_ids_with_tickers: list[tuple[str, str]],
    market_ticker: str,
) -> list[str]:
    """Filter order IDs to those on a specific market.

    Args:
        order_ids_with_tickers: List of (order_id, market_ticker) pairs.
        market_ticker: Exact market ticker (e.g. ``KXSOYBEANW-26APR25-17``).

    Returns:
        List of order IDs whose market ticker matches exactly.
    """
    return [
        oid for oid, ticker in order_ids_with_tickers
        if ticker == market_ticker
    ]


async def batch_cancel_by_event(
    client: CancelClient,
    order_ids_with_tickers: list[tuple[str, str]],
    event_ticker: str,
    *,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_backoff_s: float = _DEFAULT_RETRY_BACKOFF_S,
) -> list[str]:
    """Cancel all orders belonging to a given event.

    Args:
        client: Kalshi client with cancel endpoints.
        order_ids_with_tickers: List of (order_id, market_ticker) pairs.
        event_ticker: Event ticker prefix to match.
        max_retries: Number of retry rounds for failed IDs.
        retry_backoff_s: Base backoff between retry rounds.

    Returns:
        List of successfully cancelled order IDs.

    Raises:
        KillSwitchError: If any matching order IDs remain uncancelled.
    """
    filtered = filter_orders_by_event(order_ids_with_tickers, event_ticker)
    logger.warning(
        "KILL: batch_cancel_by_event(%s) — %d order(s) of %d match",
        event_ticker, len(filtered), len(order_ids_with_tickers),
    )
    return await batch_cancel_all(
        client, filtered, max_retries=max_retries, retry_backoff_s=retry_backoff_s,
    )


async def batch_cancel_by_market(
    client: CancelClient,
    order_ids_with_tickers: list[tuple[str, str]],
    market_ticker: str,
    *,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_backoff_s: float = _DEFAULT_RETRY_BACKOFF_S,
) -> list[str]:
    """Cancel all orders on a specific market.

    Args:
        client: Kalshi client with cancel endpoints.
        order_ids_with_tickers: List of (order_id, market_ticker) pairs.
        market_ticker: Exact market ticker to match.
        max_retries: Number of retry rounds for failed IDs.
        retry_backoff_s: Base backoff between retry rounds.

    Returns:
        List of successfully cancelled order IDs.

    Raises:
        KillSwitchError: If any matching order IDs remain uncancelled.
    """
    filtered = filter_orders_by_market(order_ids_with_tickers, market_ticker)
    logger.warning(
        "KILL: batch_cancel_by_market(%s) — %d order(s) of %d match",
        market_ticker, len(filtered), len(order_ids_with_tickers),
    )
    return await batch_cancel_all(
        client, filtered, max_retries=max_retries, retry_backoff_s=retry_backoff_s,
    )


# ---------------------------------------------------------------------------
# Internal: chunked batch execution
# ---------------------------------------------------------------------------


async def _execute_batch_cancel(
    client: CancelClient,
    order_ids: list[str],
) -> tuple[list[str], list[tuple[str, Exception]]]:
    """Execute batch cancel, chunking if necessary.

    Returns:
        Tuple of (successfully_cancelled_ids, [(failed_id, exception), ...]).
    """
    cancelled: list[str] = []
    failed: list[tuple[str, Exception]] = []

    # Chunk into groups of _BATCH_CHUNK_SIZE
    for i in range(0, len(order_ids), _BATCH_CHUNK_SIZE):
        chunk = order_ids[i : i + _BATCH_CHUNK_SIZE]

        if len(chunk) == 1:
            # Single order: use single-cancel endpoint
            try:
                await client.cancel_order(chunk[0])
                cancelled.append(chunk[0])
                logger.info("KILL: cancelled order %s", chunk[0])
            except Exception as exc:
                logger.warning("KILL: failed to cancel order %s: %s", chunk[0], exc)
                failed.append((chunk[0], exc))
        else:
            # Batch cancel
            try:
                result = await client.batch_cancel_orders(chunk)
                # Kalshi batch cancel returns info about cancelled orders.
                # On success, all orders in the batch are cancelled.
                cancelled.extend(chunk)
                logger.info("KILL: batch cancelled %d order(s)", len(chunk))
            except KalshiAPIError as exc:
                # On batch failure, we fall back to individual cancels
                # to determine which specific orders failed.
                logger.warning(
                    "KILL: batch cancel failed for %d order(s): %s; "
                    "falling back to individual cancels",
                    len(chunk), exc,
                )
                for oid in chunk:
                    try:
                        await client.cancel_order(oid)
                        cancelled.append(oid)
                        logger.info("KILL: individually cancelled order %s", oid)
                    except Exception as individual_exc:
                        logger.warning(
                            "KILL: individual cancel failed for %s: %s",
                            oid, individual_exc,
                        )
                        failed.append((oid, individual_exc))

    return cancelled, failed


# ---------------------------------------------------------------------------
# Trigger condition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriggerResult:
    """Result from evaluating a trigger condition."""

    fired: bool
    name: str
    detail: str = ""


# Type alias for trigger condition callables.
# Each callable takes no arguments and returns a TriggerResult.
TriggerCondition = Callable[[], TriggerResult]


# ---------------------------------------------------------------------------
# KillSwitch: group trigger
# ---------------------------------------------------------------------------


@dataclass
class KillSwitch:
    """Composable kill switch that fires batch cancel when any trigger fires.

    The kill switch holds a reference to a Kalshi client and a list of
    trigger conditions. On each ``check_and_fire()`` call (synchronous
    trigger evaluation, async cancel execution), it evaluates all
    conditions. If ANY condition fires, it executes batch cancel on
    the provided order IDs.

    Usage::

        def delta_breach() -> TriggerResult:
            if abs(current_delta) > max_delta:
                return TriggerResult(fired=True, name="delta_breach",
                                     detail=f"delta={current_delta}")
            return TriggerResult(fired=False, name="delta_breach")

        ks = KillSwitch(client=kalshi_client, triggers=[delta_breach])
        # In the main loop:
        result = await ks.check_and_fire(open_order_ids)
        if result.fired:
            # handle post-kill logic
            ...
    """

    client: CancelClient
    triggers: list[TriggerCondition] = field(default_factory=list)
    max_retries: int = _DEFAULT_MAX_RETRIES
    retry_backoff_s: float = _DEFAULT_RETRY_BACKOFF_S
    _armed: bool = field(default=True, init=False, repr=False)

    def arm(self) -> None:
        """Arm the kill switch (enabled by default)."""
        self._armed = True
        logger.warning("KILL: kill switch ARMED")

    def disarm(self) -> None:
        """Disarm the kill switch (for cold-start / maintenance)."""
        self._armed = False
        logger.warning("KILL: kill switch DISARMED")

    @property
    def is_armed(self) -> bool:
        """Whether the kill switch is armed."""
        return self._armed

    def add_trigger(self, trigger: TriggerCondition) -> None:
        """Register a new trigger condition."""
        self.triggers.append(trigger)

    def check_triggers(self) -> TriggerResult | None:
        """Evaluate all triggers synchronously.

        Returns:
            The first TriggerResult that fired, or None if no trigger fired.
        """
        if not self._armed:
            return None

        for trigger in self.triggers:
            result = trigger()
            if result.fired:
                logger.warning(
                    "KILL: trigger fired — name=%s detail=%s",
                    result.name, result.detail,
                )
                return result

        return None

    async def check_and_fire(
        self,
        order_ids: list[str],
    ) -> KillSwitchFireResult:
        """Check triggers and execute batch cancel if any fires.

        This is the main entry point for the kill switch in the
        synchronous main loop. Trigger evaluation is synchronous;
        the batch cancel (I/O) is async.

        Args:
            order_ids: Current list of open order IDs to cancel if
                a trigger fires.

        Returns:
            KillSwitchFireResult with fired status and details.

        Raises:
            KillSwitchError: If batch cancel partially fails after retries.
        """
        trigger_result = self.check_triggers()

        if trigger_result is None:
            return KillSwitchFireResult(
                fired=False,
                trigger_name="",
                trigger_detail="",
                cancelled_ids=[],
                timestamp=time.time(),
            )

        logger.warning(
            "KILL: executing kill switch — trigger=%s, cancelling %d order(s)",
            trigger_result.name, len(order_ids),
        )

        cancelled = await batch_cancel_all(
            self.client,
            order_ids,
            max_retries=self.max_retries,
            retry_backoff_s=self.retry_backoff_s,
        )

        result = KillSwitchFireResult(
            fired=True,
            trigger_name=trigger_result.name,
            trigger_detail=trigger_result.detail,
            cancelled_ids=cancelled,
            timestamp=time.time(),
        )

        logger.warning(
            "KILL: kill switch complete — trigger=%s, cancelled=%d order(s)",
            trigger_result.name, len(cancelled),
        )

        return result


@dataclass(frozen=True)
class KillSwitchFireResult:
    """Result of a kill switch check-and-fire cycle."""

    fired: bool
    trigger_name: str
    trigger_detail: str
    cancelled_ids: list[str]
    timestamp: float
