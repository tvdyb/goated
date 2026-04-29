"""Tests for Pyth Hermes REST client and forward price provider."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feeds.pyth.client import (
    PythClientError,
    PythHermesClient,
    PythPrice,
    PythStaleError,
    PythUnavailableError,
)
from feeds.pyth.forward import (
    PythForwardConfig,
    PythForwardProvider,
    load_pyth_forward_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FEED_ID = "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"

SOY_FEED_ID = "0x0d03b648a12b297160e2fdce53cd643d993f7ade4549f8e91ec6e593cc085c21"


def _make_hermes_response(
    price: int = 117750000,
    conf: int = 500000,
    expo: int = -5,
    publish_time: int | None = None,
    feed_id: str = FEED_ID,
) -> dict:
    if publish_time is None:
        publish_time = int(time.time())
    return {
        "binary": {"encoding": "hex", "data": []},
        "parsed": [
            {
                "id": feed_id.removeprefix("0x"),
                "price": {
                    "price": str(price),
                    "conf": str(conf),
                    "expo": expo,
                    "publish_time": publish_time,
                },
                "ema_price": {
                    "price": str(price),
                    "conf": str(conf),
                    "expo": expo,
                    "publish_time": publish_time,
                },
            }
        ],
    }


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    resp.text = json.dumps(data)
    return resp


# ---------------------------------------------------------------------------
# PythHermesClient tests
# ---------------------------------------------------------------------------


class TestPythHermesClient:
    """Tests for the low-level Pyth Hermes REST client."""

    @pytest.mark.asyncio
    async def test_parse_price_correctly(self) -> None:
        """Price = raw * 10^expo = 117750000 * 10^-5 = 1177.5."""
        data = _make_hermes_response(price=117750000, expo=-5)
        mock_resp = _mock_response(data)

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_latest_price(FEED_ID, max_staleness_ms=60000)
        assert isinstance(result, PythPrice)
        assert abs(result.price - 1177.5) < 0.01
        assert result.conf > 0

    @pytest.mark.asyncio
    async def test_stale_price_raises(self) -> None:
        """Price older than threshold raises PythStaleError."""
        old_time = int(time.time()) - 120  # 2 minutes old
        data = _make_hermes_response(publish_time=old_time)
        mock_resp = _mock_response(data)

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(PythStaleError):
            await client.get_latest_price(FEED_ID, max_staleness_ms=2000)

    @pytest.mark.asyncio
    async def test_zero_price_raises_unavailable(self) -> None:
        """Feed with price=0 and publish_time=0 raises PythUnavailableError."""
        data = _make_hermes_response(price=0, publish_time=0)
        mock_resp = _mock_response(data)

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(PythUnavailableError):
            await client.get_latest_price(FEED_ID, max_staleness_ms=60000)

    @pytest.mark.asyncio
    async def test_http_error_raises_unavailable(self) -> None:
        """Non-200 response raises PythUnavailableError."""
        mock_resp = _mock_response({}, status=500)
        mock_resp.text = "Internal Server Error"

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(PythUnavailableError):
            await client.get_latest_price(FEED_ID)

    @pytest.mark.asyncio
    async def test_missing_parsed_raises(self) -> None:
        """Response without parsed data raises PythClientError."""
        mock_resp = _mock_response({"binary": {}, "parsed": []})

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(PythClientError):
            await client.get_latest_price(FEED_ID)

    @pytest.mark.asyncio
    async def test_client_not_opened_raises(self) -> None:
        """Calling get_latest_price without open() raises."""
        client = PythHermesClient()
        with pytest.raises(PythClientError, match="not opened"):
            await client.get_latest_price(FEED_ID)

    @pytest.mark.asyncio
    async def test_feed_id_normalization(self) -> None:
        """Feed ID without 0x prefix is normalized."""
        data = _make_hermes_response()
        mock_resp = _mock_response(data)

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        # Pass without 0x prefix
        result = await client.get_latest_price(
            FEED_ID.removeprefix("0x"), max_staleness_ms=60000
        )
        assert isinstance(result, PythPrice)

        # Verify the client was called with 0x prefix
        call_args = client._client.get.call_args
        assert call_args[1]["params"]["ids[]"].startswith("0x")

    @pytest.mark.asyncio
    async def test_negative_expo(self) -> None:
        """Handles various exponent values correctly."""
        # WTI: 7540072809321 * 10^-8 = 75400.72809321
        data = _make_hermes_response(price=7540072809321, expo=-8)
        mock_resp = _mock_response(data)

        client = PythHermesClient()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_resp)

        result = await client.get_latest_price(FEED_ID, max_staleness_ms=60000)
        assert abs(result.price - 75400.728) < 0.01


# ---------------------------------------------------------------------------
# PythForwardProvider tests
# ---------------------------------------------------------------------------


class TestPythForwardProvider:
    """Tests for the forward price provider."""

    @pytest.mark.asyncio
    async def test_poll_once_success(self) -> None:
        """Successful poll returns forward in $/bushel."""
        cfg = PythForwardConfig(
            feed_id=SOY_FEED_ID,
            price_divisor=100.0,
        )
        provider = PythForwardProvider(cfg)

        # Mock the client
        mock_price = PythPrice(
            price=1177.5,  # cents/bushel
            conf=5.0,
            publish_time=int(time.time()),
            feed_id=SOY_FEED_ID,
        )
        provider._client = AsyncMock()
        provider._client.get_latest_price = AsyncMock(return_value=mock_price)

        result = await provider.poll_once()
        assert result is not None
        assert abs(result - 11.775) < 0.001  # 1177.5 / 100
        assert provider.pyth_available is True
        assert provider.forward_price == result

    @pytest.mark.asyncio
    async def test_poll_once_stale_returns_none(self) -> None:
        """Stale price returns None and sets pyth_available=False."""
        cfg = PythForwardConfig(feed_id=SOY_FEED_ID)
        provider = PythForwardProvider(cfg)
        provider._client = AsyncMock()
        provider._client.get_latest_price = AsyncMock(
            side_effect=PythStaleError("too old")
        )

        result = await provider.poll_once()
        assert result is None
        assert provider.pyth_available is False

    @pytest.mark.asyncio
    async def test_poll_once_unavailable_returns_none(self) -> None:
        """Unavailable feed returns None and sets pyth_available=False."""
        cfg = PythForwardConfig(feed_id=SOY_FEED_ID)
        provider = PythForwardProvider(cfg)
        provider._client = AsyncMock()
        provider._client.get_latest_price = AsyncMock(
            side_effect=PythUnavailableError("not publishing")
        )

        result = await provider.poll_once()
        assert result is None
        assert provider.pyth_available is False

    @pytest.mark.asyncio
    async def test_forward_persists_across_failures(self) -> None:
        """After a successful poll, the forward_price persists even if
        next poll fails (but pyth_available flips to False)."""
        cfg = PythForwardConfig(feed_id=SOY_FEED_ID, price_divisor=100.0)
        provider = PythForwardProvider(cfg)

        # First: success
        mock_price = PythPrice(
            price=1177.5, conf=5.0,
            publish_time=int(time.time()), feed_id=SOY_FEED_ID,
        )
        provider._client = AsyncMock()
        provider._client.get_latest_price = AsyncMock(return_value=mock_price)
        await provider.poll_once()
        assert provider.forward_price is not None
        saved_fwd = provider.forward_price

        # Second: failure
        provider._client.get_latest_price = AsyncMock(
            side_effect=PythUnavailableError("down")
        )
        await provider.poll_once()
        # forward_price still holds last good value
        assert provider.forward_price == saved_fwd
        assert provider.pyth_available is False

    @pytest.mark.asyncio
    async def test_price_divisor_applied(self) -> None:
        """price_divisor converts raw Pyth price to $/bushel."""
        cfg = PythForwardConfig(feed_id=SOY_FEED_ID, price_divisor=1.0)
        provider = PythForwardProvider(cfg)

        mock_price = PythPrice(
            price=11.775, conf=0.05,
            publish_time=int(time.time()), feed_id=SOY_FEED_ID,
        )
        provider._client = AsyncMock()
        provider._client.get_latest_price = AsyncMock(return_value=mock_price)

        result = await provider.poll_once()
        assert result is not None
        assert abs(result - 11.775) < 0.001


# ---------------------------------------------------------------------------
# Config loader tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for YAML config loader."""

    def test_load_pyth_forward_config(self) -> None:
        cfg = {
            "hermes_http": "https://hermes.pyth.network",
            "feeds": {
                "soy": {
                    "feed_id": SOY_FEED_ID,
                    "max_staleness_ms": 5000,
                    "price_divisor": 100.0,
                }
            },
        }
        result = load_pyth_forward_config(cfg)
        assert result.feed_id == SOY_FEED_ID
        assert result.max_staleness_ms == 5000
        assert result.price_divisor == 100.0
        assert result.hermes_base_url == "https://hermes.pyth.network"

    def test_missing_feed_id_raises(self) -> None:
        cfg = {"feeds": {"soy": {}}}
        with pytest.raises(ValueError, match="feed_id is required"):
            load_pyth_forward_config(cfg)

    def test_defaults_applied(self) -> None:
        cfg = {
            "feeds": {
                "soy": {
                    "feed_id": SOY_FEED_ID,
                }
            },
        }
        result = load_pyth_forward_config(cfg)
        assert result.max_staleness_ms == 2000
        assert result.price_divisor == 100.0
        assert result.poll_interval_s == 5.0
