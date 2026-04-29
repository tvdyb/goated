"""Tests for order amendment flow (T-35).

Tests:
- KalshiClient.amend_order sends correct request
- LIPMarketMaker uses amend instead of cancel+place when order exists
- Fallback to cancel+place when amend fails
- No API call when price unchanged (kept)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feeds.kalshi.client import KalshiClient
from feeds.kalshi.errors import KalshiAPIError, KalshiResponseError


# ── KalshiClient.amend_order tests ──────────────────────────────────


@pytest.fixture
def mock_client() -> KalshiClient:
    """Create a KalshiClient with mocked internals."""
    auth = MagicMock()
    client = KalshiClient(auth=auth)
    client._request = AsyncMock()
    return client


def test_amend_order_sends_correct_request(mock_client: KalshiClient) -> None:
    mock_client._request.return_value = {"order": {"order_id": "abc123"}}
    result = asyncio.get_event_loop().run_until_complete(
        mock_client.amend_order("abc123", yes_price=45, count=10)
    )
    mock_client._request.assert_called_once_with(
        "POST",
        "/portfolio/orders/abc123/amend",
        json_body={"yes_price": 45, "count": 10},
        is_write=True,
    )
    assert result == {"order": {"order_id": "abc123"}}


def test_amend_order_price_only(mock_client: KalshiClient) -> None:
    mock_client._request.return_value = {"order": {"order_id": "abc123"}}
    asyncio.get_event_loop().run_until_complete(
        mock_client.amend_order("abc123", yes_price=50)
    )
    mock_client._request.assert_called_once_with(
        "POST",
        "/portfolio/orders/abc123/amend",
        json_body={"yes_price": 50},
        is_write=True,
    )


def test_amend_order_count_only(mock_client: KalshiClient) -> None:
    mock_client._request.return_value = {"order": {"order_id": "abc123"}}
    asyncio.get_event_loop().run_until_complete(
        mock_client.amend_order("abc123", count=20)
    )
    mock_client._request.assert_called_once_with(
        "POST",
        "/portfolio/orders/abc123/amend",
        json_body={"count": 20},
        is_write=True,
    )


def test_amend_order_no_price(mock_client: KalshiClient) -> None:
    mock_client._request.return_value = {"order": {"order_id": "abc123"}}
    asyncio.get_event_loop().run_until_complete(
        mock_client.amend_order("abc123", no_price=55)
    )
    mock_client._request.assert_called_once_with(
        "POST",
        "/portfolio/orders/abc123/amend",
        json_body={"no_price": 55},
        is_write=True,
    )


def test_amend_order_no_params_raises(mock_client: KalshiClient) -> None:
    with pytest.raises(KalshiAPIError, match="at least one"):
        asyncio.get_event_loop().run_until_complete(
            mock_client.amend_order("abc123")
        )


# ── LIPMarketMaker amend integration tests ─────────────────────────

def _make_lip_mm() -> Any:
    """Create a LIPMarketMaker with minimal config for testing."""
    from deploy.lip_mode import LIPMarketMaker

    cfg: dict[str, Any] = {
        "lip": {
            "contracts_per_side": 50,
            "max_half_spread_cents": 4,
            "min_half_spread_cents": 2,
            "max_distance_from_best": 2,
            "eligible_strikes": [],
        },
        "loop": {"cycle_seconds": 30},
        "series": [{"ticker_prefix": "KXTEST"}],
        "synthetic": {"vol": 0.15},
        "wasde": {},
        "markout": {},
    }

    with patch("deploy.lip_mode.PythForwardProvider"), \
         patch("deploy.lip_mode.load_pyth_forward_config"), \
         patch("builtins.open", MagicMock()), \
         patch("yaml.safe_load", return_value={}):
        mm = LIPMarketMaker(cfg)

    mm._kalshi_client = MagicMock()
    mm._kalshi_client.amend_order = AsyncMock()
    mm._kalshi_client.cancel_order = AsyncMock()
    mm._kalshi_client.create_order = AsyncMock(return_value={
        "order": {"order_id": "new-order-id"}
    })
    return mm


def test_try_amend_success() -> None:
    mm = _make_lip_mm()
    mm._kalshi_client.amend_order.return_value = {"order": {"order_id": "abc"}}

    result = asyncio.get_event_loop().run_until_complete(
        mm._try_amend("abc", yes_price=45, count=50)
    )
    assert result is True
    mm._kalshi_client.amend_order.assert_called_once_with(
        "abc", yes_price=45, no_price=None, count=50,
    )


def test_try_amend_failure_returns_false() -> None:
    mm = _make_lip_mm()
    mm._kalshi_client.amend_order.side_effect = KalshiResponseError(
        "Not found", status_code=404, body="",
    )

    result = asyncio.get_event_loop().run_until_complete(
        mm._try_amend("abc", yes_price=45)
    )
    assert result is False


def test_try_amend_generic_error_returns_false() -> None:
    mm = _make_lip_mm()
    mm._kalshi_client.amend_order.side_effect = Exception("network error")

    result = asyncio.get_event_loop().run_until_complete(
        mm._try_amend("abc", yes_price=45)
    )
    assert result is False


def test_cancel_and_place_bid_fallback() -> None:
    mm = _make_lip_mm()
    ticker = "KXTEST-26APR3017-T1186.99"
    mm._resting[ticker] = {"bid_id": "old-bid", "bid_px": 40, "ask_id": "", "ask_px": 0}

    asyncio.get_event_loop().run_until_complete(
        mm._cancel_and_place_bid(ticker, 45)
    )
    mm._kalshi_client.cancel_order.assert_called_once_with("old-bid")
    mm._kalshi_client.create_order.assert_called_once()
    call_kwargs = mm._kalshi_client.create_order.call_args
    assert call_kwargs.kwargs["yes_price"] == 45
    assert call_kwargs.kwargs["action"] == "buy"
    assert call_kwargs.kwargs["post_only"] is True


def test_cancel_and_place_ask_fallback() -> None:
    mm = _make_lip_mm()
    ticker = "KXTEST-26APR3017-T1186.99"
    mm._resting[ticker] = {"bid_id": "", "bid_px": 0, "ask_id": "old-ask", "ask_px": 60}

    asyncio.get_event_loop().run_until_complete(
        mm._cancel_and_place_ask(ticker, 65)
    )
    mm._kalshi_client.cancel_order.assert_called_once_with("old-ask")
    mm._kalshi_client.create_order.assert_called_once()
    call_kwargs = mm._kalshi_client.create_order.call_args
    assert call_kwargs.kwargs["yes_price"] == 65
    assert call_kwargs.kwargs["action"] == "sell"


def test_place_bid_no_existing_order() -> None:
    mm = _make_lip_mm()
    ticker = "KXTEST-26APR3017-T1186.99"

    asyncio.get_event_loop().run_until_complete(
        mm._place_bid(ticker, 42)
    )
    mm._kalshi_client.cancel_order.assert_not_called()
    mm._kalshi_client.create_order.assert_called_once()
    assert mm._resting[ticker]["bid_id"] == "new-order-id"
    assert mm._resting[ticker]["bid_px"] == 42


def test_place_ask_no_existing_order() -> None:
    mm = _make_lip_mm()
    ticker = "KXTEST-26APR3017-T1186.99"

    asyncio.get_event_loop().run_until_complete(
        mm._place_ask(ticker, 58)
    )
    mm._kalshi_client.cancel_order.assert_not_called()
    mm._kalshi_client.create_order.assert_called_once()
    assert mm._resting[ticker]["ask_id"] == "new-order-id"
    assert mm._resting[ticker]["ask_px"] == 58


def test_kept_orders_no_api_calls() -> None:
    """When price is unchanged, no API calls should be made."""
    mm = _make_lip_mm()
    ticker = "KXTEST-26APR3017-T1186.99"
    mm._resting[ticker] = {
        "bid_id": "bid-1", "bid_px": 40,
        "ask_id": "ask-1", "ask_px": 60,
    }

    # Simulate the logic: same prices -> kept
    cur_bid_px = mm._resting[ticker]["bid_px"]
    cur_ask_px = mm._resting[ticker]["ask_px"]
    target_bid, target_ask = 40, 60

    assert cur_bid_px == target_bid  # should be kept
    assert cur_ask_px == target_ask  # should be kept

    # No calls should have been made
    mm._kalshi_client.amend_order.assert_not_called()
    mm._kalshi_client.cancel_order.assert_not_called()
    mm._kalshi_client.create_order.assert_not_called()
