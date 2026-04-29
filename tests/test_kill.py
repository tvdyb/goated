"""Tests for engine.kill — kill-switch primitives.

Covers:
  - Batch cancel all orders
  - Batch cancel per-event, per-market
  - Partial failure + retry
  - Exhausted retries raises KillSwitchError
  - Group trigger fires on condition
  - Group trigger does not fire when all conditions False
  - Logging of kill actions
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.kill import (
    KillSwitch,
    KillSwitchError,
    KillSwitchFireResult,
    TriggerResult,
    batch_cancel_all,
    batch_cancel_by_event,
    batch_cancel_by_market,
    filter_orders_by_event,
    filter_orders_by_market,
)
from feeds.kalshi.errors import KalshiAPIError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockCancelClient:
    """Mock Kalshi client for testing cancel operations."""

    def __init__(
        self,
        *,
        fail_ids: set[str] | None = None,
        fail_batch: bool = False,
        fail_count: int = 1,
    ) -> None:
        self.fail_ids = fail_ids or set()
        self.fail_batch = fail_batch
        self._fail_count = fail_count
        self._attempt_counts: dict[str, int] = {}
        self.cancel_order_calls: list[str] = []
        self.batch_cancel_calls: list[list[str]] = []

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        self.cancel_order_calls.append(order_id)
        self._attempt_counts.setdefault(order_id, 0)
        self._attempt_counts[order_id] += 1

        if order_id in self.fail_ids and self._attempt_counts[order_id] <= self._fail_count:
            raise KalshiAPIError(
                f"cancel failed for {order_id}",
                status_code=500,
                body="server error",
            )
        return {"order": {"order_id": order_id, "status": "cancelled"}}

    async def batch_cancel_orders(self, order_ids: list[str]) -> dict[str, Any]:
        self.batch_cancel_calls.append(list(order_ids))
        if self.fail_batch:
            raise KalshiAPIError(
                "batch cancel failed",
                status_code=500,
                body="server error",
            )
        return {"orders": [{"order_id": oid, "status": "cancelled"} for oid in order_ids]}


@pytest.fixture
def mock_client() -> MockCancelClient:
    return MockCancelClient()


# ---------------------------------------------------------------------------
# batch_cancel_all
# ---------------------------------------------------------------------------


class TestBatchCancelAll:
    @pytest.mark.asyncio
    async def test_cancel_all_empty(self, mock_client: MockCancelClient) -> None:
        result = await batch_cancel_all(mock_client, [])
        assert result == []
        assert mock_client.cancel_order_calls == []
        assert mock_client.batch_cancel_calls == []

    @pytest.mark.asyncio
    async def test_cancel_single_order(self, mock_client: MockCancelClient) -> None:
        result = await batch_cancel_all(mock_client, ["order-1"])
        assert result == ["order-1"]
        assert mock_client.cancel_order_calls == ["order-1"]
        assert mock_client.batch_cancel_calls == []

    @pytest.mark.asyncio
    async def test_cancel_multiple_orders(self, mock_client: MockCancelClient) -> None:
        ids = ["order-1", "order-2", "order-3"]
        result = await batch_cancel_all(mock_client, ids)
        assert set(result) == set(ids)
        # Multiple orders go through batch endpoint
        assert len(mock_client.batch_cancel_calls) == 1
        assert set(mock_client.batch_cancel_calls[0]) == set(ids)

    @pytest.mark.asyncio
    async def test_cancel_respects_chunk_size(self) -> None:
        """Orders exceeding chunk size are split into multiple batches."""
        client = MockCancelClient()
        # 150 orders should be split into 100 + 50
        ids = [f"order-{i}" for i in range(150)]
        result = await batch_cancel_all(client, ids)
        assert len(result) == 150
        assert len(client.batch_cancel_calls) == 2
        assert len(client.batch_cancel_calls[0]) == 100
        assert len(client.batch_cancel_calls[1]) == 50


# ---------------------------------------------------------------------------
# Partial failure + retry
# ---------------------------------------------------------------------------


class TestPartialFailureRetry:
    @pytest.mark.asyncio
    async def test_single_order_retry_succeeds(self) -> None:
        """A single failing order succeeds on retry."""
        client = MockCancelClient(fail_ids={"order-1"}, fail_count=1)
        result = await batch_cancel_all(
            client, ["order-1"], max_retries=3, retry_backoff_s=0.0,
        )
        assert result == ["order-1"]
        # First attempt fails, second succeeds
        assert client._attempt_counts["order-1"] == 2

    @pytest.mark.asyncio
    async def test_batch_fallback_to_individual(self) -> None:
        """When batch cancel fails, falls back to individual cancels."""
        client = MockCancelClient(fail_batch=True)
        ids = ["order-1", "order-2"]
        result = await batch_cancel_all(
            client, ids, retry_backoff_s=0.0,
        )
        assert set(result) == {"order-1", "order-2"}
        # Batch was attempted, then individual cancels
        assert len(client.batch_cancel_calls) == 1
        assert len(client.cancel_order_calls) == 2

    @pytest.mark.asyncio
    async def test_partial_failure_retries_remaining(self) -> None:
        """Only failed IDs are retried on subsequent rounds."""
        client = MockCancelClient(fail_ids={"order-2"}, fail_count=1)
        ids = ["order-1", "order-2", "order-3"]
        # Batch will succeed for all, but let's use individual failure
        # by making batch fail so we go to individual path
        client.fail_batch = True
        result = await batch_cancel_all(
            client, ids, max_retries=2, retry_backoff_s=0.0,
        )
        assert set(result) == {"order-1", "order-2", "order-3"}

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self) -> None:
        """KillSwitchError raised when retries are exhausted."""
        client = MockCancelClient(fail_ids={"order-bad"}, fail_count=999)
        with pytest.raises(KillSwitchError) as exc_info:
            await batch_cancel_all(
                client,
                ["order-bad"],
                max_retries=2,
                retry_backoff_s=0.0,
            )
        assert "order-bad" in exc_info.value.failed_order_ids


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


class TestFilterHelpers:
    def test_filter_by_event(self) -> None:
        orders = [
            ("id-1", "KXSOYBEANW-26APR25-17"),
            ("id-2", "KXSOYBEANW-26APR25-18"),
            ("id-3", "KXTRUFAIDP-26APR27-YES"),
        ]
        result = filter_orders_by_event(orders, "KXSOYBEANW-26APR25")
        assert result == ["id-1", "id-2"]

    def test_filter_by_event_no_match(self) -> None:
        orders = [("id-1", "KXTRUFAIDP-26APR27-YES")]
        result = filter_orders_by_event(orders, "KXSOYBEANW-26APR25")
        assert result == []

    def test_filter_by_market(self) -> None:
        orders = [
            ("id-1", "KXSOYBEANW-26APR25-17"),
            ("id-2", "KXSOYBEANW-26APR25-18"),
        ]
        result = filter_orders_by_market(orders, "KXSOYBEANW-26APR25-17")
        assert result == ["id-1"]

    def test_filter_by_market_no_match(self) -> None:
        orders = [("id-1", "KXSOYBEANW-26APR25-17")]
        result = filter_orders_by_market(orders, "KXSOYBEANW-26APR25-99")
        assert result == []


# ---------------------------------------------------------------------------
# batch_cancel_by_event / batch_cancel_by_market
# ---------------------------------------------------------------------------


class TestBatchCancelByEventMarket:
    @pytest.mark.asyncio
    async def test_cancel_by_event(self, mock_client: MockCancelClient) -> None:
        orders = [
            ("id-1", "KXSOYBEANW-26APR25-17"),
            ("id-2", "KXSOYBEANW-26APR25-18"),
            ("id-3", "KXTRUFAIDP-26APR27-YES"),
        ]
        result = await batch_cancel_by_event(
            mock_client, orders, "KXSOYBEANW-26APR25",
            retry_backoff_s=0.0,
        )
        assert set(result) == {"id-1", "id-2"}

    @pytest.mark.asyncio
    async def test_cancel_by_market(self, mock_client: MockCancelClient) -> None:
        orders = [
            ("id-1", "KXSOYBEANW-26APR25-17"),
            ("id-2", "KXSOYBEANW-26APR25-18"),
        ]
        result = await batch_cancel_by_market(
            mock_client, orders, "KXSOYBEANW-26APR25-17",
            retry_backoff_s=0.0,
        )
        assert result == ["id-1"]


# ---------------------------------------------------------------------------
# TriggerResult + KillSwitch
# ---------------------------------------------------------------------------


class TestKillSwitchTrigger:
    @pytest.mark.asyncio
    async def test_no_trigger_fires(self, mock_client: MockCancelClient) -> None:
        trigger = lambda: TriggerResult(fired=False, name="test_trigger")
        ks = KillSwitch(client=mock_client, triggers=[trigger])
        result = await ks.check_and_fire(["order-1"])
        assert result.fired is False
        assert result.cancelled_ids == []
        assert mock_client.cancel_order_calls == []

    @pytest.mark.asyncio
    async def test_trigger_fires(self, mock_client: MockCancelClient) -> None:
        trigger = lambda: TriggerResult(
            fired=True, name="delta_breach", detail="delta=150",
        )
        ks = KillSwitch(
            client=mock_client,
            triggers=[trigger],
            retry_backoff_s=0.0,
        )
        result = await ks.check_and_fire(["order-1", "order-2"])
        assert result.fired is True
        assert result.trigger_name == "delta_breach"
        assert result.trigger_detail == "delta=150"
        assert set(result.cancelled_ids) == {"order-1", "order-2"}

    @pytest.mark.asyncio
    async def test_first_trigger_wins(self, mock_client: MockCancelClient) -> None:
        t1 = lambda: TriggerResult(fired=True, name="trigger_a", detail="a")
        t2 = lambda: TriggerResult(fired=True, name="trigger_b", detail="b")
        ks = KillSwitch(
            client=mock_client,
            triggers=[t1, t2],
            retry_backoff_s=0.0,
        )
        result = await ks.check_and_fire(["order-1"])
        assert result.trigger_name == "trigger_a"

    @pytest.mark.asyncio
    async def test_multiple_triggers_only_first_fires(
        self, mock_client: MockCancelClient,
    ) -> None:
        t1 = lambda: TriggerResult(fired=False, name="trigger_a")
        t2 = lambda: TriggerResult(fired=True, name="trigger_b", detail="b")
        ks = KillSwitch(
            client=mock_client,
            triggers=[t1, t2],
            retry_backoff_s=0.0,
        )
        result = await ks.check_and_fire(["order-1"])
        assert result.trigger_name == "trigger_b"

    @pytest.mark.asyncio
    async def test_disarmed_does_not_fire(self, mock_client: MockCancelClient) -> None:
        trigger = lambda: TriggerResult(fired=True, name="always_fire")
        ks = KillSwitch(
            client=mock_client,
            triggers=[trigger],
            retry_backoff_s=0.0,
        )
        ks.disarm()
        result = await ks.check_and_fire(["order-1"])
        assert result.fired is False
        assert mock_client.cancel_order_calls == []

    @pytest.mark.asyncio
    async def test_arm_after_disarm(self, mock_client: MockCancelClient) -> None:
        trigger = lambda: TriggerResult(fired=True, name="always_fire")
        ks = KillSwitch(
            client=mock_client,
            triggers=[trigger],
            retry_backoff_s=0.0,
        )
        ks.disarm()
        assert not ks.is_armed
        ks.arm()
        assert ks.is_armed
        result = await ks.check_and_fire(["order-1"])
        assert result.fired is True

    def test_check_triggers_sync(self, mock_client: MockCancelClient) -> None:
        """check_triggers is synchronous (no await needed)."""
        trigger = lambda: TriggerResult(fired=True, name="sync_test")
        ks = KillSwitch(client=mock_client, triggers=[trigger])
        result = ks.check_triggers()
        assert result is not None
        assert result.fired is True
        assert result.name == "sync_test"

    def test_add_trigger(self, mock_client: MockCancelClient) -> None:
        ks = KillSwitch(client=mock_client)
        assert len(ks.triggers) == 0
        trigger = lambda: TriggerResult(fired=False, name="added")
        ks.add_trigger(trigger)
        assert len(ks.triggers) == 1


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestKillLogging:
    @pytest.mark.asyncio
    async def test_batch_cancel_logs_warning(
        self, mock_client: MockCancelClient, caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="engine.kill"):
            await batch_cancel_all(mock_client, ["order-1"])
        assert any("KILL: batch_cancel_all invoked" in r.message for r in caplog.records)
        assert any("KILL: batch_cancel_all complete" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_trigger_fire_logs_warning(
        self, mock_client: MockCancelClient, caplog: pytest.LogCaptureFixture,
    ) -> None:
        trigger = lambda: TriggerResult(
            fired=True, name="test_log_trigger", detail="log_detail",
        )
        ks = KillSwitch(
            client=mock_client,
            triggers=[trigger],
            retry_backoff_s=0.0,
        )
        with caplog.at_level(logging.WARNING, logger="engine.kill"):
            await ks.check_and_fire(["order-1"])
        assert any("trigger fired" in r.message for r in caplog.records)
        assert any("test_log_trigger" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_failed_cancel_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        client = MockCancelClient(fail_ids={"order-bad"}, fail_count=999)
        with caplog.at_level(logging.WARNING, logger="engine.kill"):
            with pytest.raises(KillSwitchError):
                await batch_cancel_all(
                    client, ["order-bad"],
                    max_retries=1,
                    retry_backoff_s=0.0,
                )
        assert any("remain uncancelled" in r.message for r in caplog.records)
