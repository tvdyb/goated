"""Tests for the Kalshi REST client foundation (ACT-03).

Covers:
  - RSA-PSS signing correctness (round-trip verification)
  - Auth credential loading (env, constructor, errors)
  - Rate limiter behaviour (burst, throttle, recovery)
  - KalshiClient REST methods: happy path + error path
  - Retry/backoff on 429 and 5xx
  - Fail-loud on unexpected responses
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, utils

from feeds.kalshi.auth import KalshiAuth, generate_test_key_pair
from feeds.kalshi.client import KalshiClient, _API_PREFIX
from feeds.kalshi.errors import (
    KalshiAPIError,
    KalshiAuthError,
    KalshiRateLimitError,
    KalshiResponseError,
)
from feeds.kalshi.rate_limiter import (
    CANCEL_REQUEST_COST,
    DEFAULT_REQUEST_COST,
    KalshiRateLimiter,
    KalshiTier,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture()
def rsa_key_pair():
    """Generate a fresh RSA key pair for testing."""
    private_key, pem_bytes = generate_test_key_pair()
    return private_key, pem_bytes


@pytest.fixture()
def auth(rsa_key_pair):
    """KalshiAuth instance with test key."""
    _, pem_bytes = rsa_key_pair
    return KalshiAuth(api_key="test-api-key-uuid", private_key_pem=pem_bytes)


@pytest.fixture()
def base_url():
    return "https://test-api.kalshi.test"


@pytest.fixture()
async def client(auth, base_url):
    """Fully initialized KalshiClient with test auth."""
    c = KalshiClient(auth=auth, base_url=base_url, max_retries=2)
    await c.open()
    yield c
    await c.close()


# ── Auth / Signing Tests ────────────────────────────────────────────

class TestKalshiAuth:
    def test_sign_round_trip(self, rsa_key_pair):
        """Verify signature can be verified with the corresponding public key."""
        private_key, pem_bytes = rsa_key_pair
        auth = KalshiAuth(api_key="key-123", private_key_pem=pem_bytes)

        ts = 1714000000000
        method = "POST"
        path = "/trade-api/v2/portfolio/orders"

        sig_b64 = auth.sign(ts, method, path)
        assert isinstance(sig_b64, str)
        assert len(sig_b64) > 0

        # Verify with public key
        import base64
        sig_bytes = base64.b64decode(sig_b64)
        message = f"{ts}{method}{path}".encode("ascii")
        public_key = private_key.public_key()
        # Should not raise
        public_key.verify(
            sig_bytes,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32,
            ),
            hashes.SHA256(),
        )

    def test_sign_different_messages_produce_different_signatures(self, auth):
        sig1 = auth.sign(1000, "GET", "/a")
        sig2 = auth.sign(1000, "GET", "/b")
        assert sig1 != sig2

    def test_build_headers(self, auth):
        headers = auth.build_headers("GET", "/trade-api/v2/events", timestamp_ms=1714000000000)
        assert headers["KALSHI-ACCESS-KEY"] == "test-api-key-uuid"
        assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1714000000000"
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert len(headers["KALSHI-ACCESS-SIGNATURE"]) > 0

    def test_build_headers_auto_timestamp(self, auth):
        before_ms = int(time.time() * 1000)
        headers = auth.build_headers("GET", "/trade-api/v2/events")
        after_ms = int(time.time() * 1000)
        ts = int(headers["KALSHI-ACCESS-TIMESTAMP"])
        assert before_ms <= ts <= after_ms

    def test_load_key_from_file(self, rsa_key_pair):
        _, pem_bytes = rsa_key_pair
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            path = f.name
        try:
            auth = KalshiAuth(api_key="key-file", private_key_path=path)
            sig = auth.sign(1000, "GET", "/test")
            assert len(sig) > 0
        finally:
            os.unlink(path)

    def test_load_key_from_env(self, rsa_key_pair):
        _, pem_bytes = rsa_key_pair
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(pem_bytes)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {
                "KALSHI_API_KEY": "env-key",
                "KALSHI_PRIVATE_KEY_PATH": path,
            }):
                auth = KalshiAuth()
                assert auth.api_key == "env-key"
                sig = auth.sign(1000, "GET", "/test")
                assert len(sig) > 0
        finally:
            os.unlink(path)

    def test_missing_api_key_raises(self, rsa_key_pair):
        _, pem_bytes = rsa_key_pair
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KALSHI_API_KEY", None)
            with pytest.raises(KalshiAuthError, match="API key"):
                KalshiAuth(private_key_pem=pem_bytes)

    def test_missing_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KALSHI_PRIVATE_KEY_PATH", None)
            with pytest.raises(KalshiAuthError, match="private key"):
                KalshiAuth(api_key="key-123")

    def test_nonexistent_key_file_raises(self):
        with pytest.raises(KalshiAuthError, match="not found"):
            KalshiAuth(api_key="key-123", private_key_path="/nonexistent/key.pem")

    def test_invalid_pem_raises(self):
        with pytest.raises(KalshiAuthError, match="Failed to load"):
            KalshiAuth(api_key="key-123", private_key_pem=b"not-a-valid-pem")


# ── Rate Limiter Tests ──────────────────────────────────────────────

class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_burst_within_capacity(self):
        """Immediate burst should succeed without delay when under capacity."""
        limiter = KalshiRateLimiter(tier=KalshiTier.BASIC)
        # Basic = 200 read tokens. 10 reads = 100 tokens. Should be instant.
        start = time.monotonic()
        for _ in range(10):
            await limiter.acquire_read()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # should be nearly instant

    @pytest.mark.asyncio
    async def test_write_bucket_separate_from_read(self):
        """Read and write are independent buckets."""
        limiter = KalshiRateLimiter(tier=KalshiTier.BASIC)
        # Consume all write tokens
        for _ in range(10):  # 10 * 10 = 100 = full write capacity
            await limiter.acquire_write()
        # Reads should still be available
        await limiter.acquire_read()  # should not block significantly

    @pytest.mark.asyncio
    async def test_throttle_when_exhausted(self):
        """Should wait when tokens are exhausted."""
        limiter = KalshiRateLimiter(tier=KalshiTier.BASIC)
        # Exhaust write bucket (100 tokens)
        for _ in range(10):  # 10 * 10 = 100
            await limiter.acquire_write()

        # Next acquire should take time
        start = time.monotonic()
        await limiter.acquire_write(cost=10)
        elapsed = time.monotonic() - start
        # With 100 tokens/sec refill, 10 tokens needs ~0.1s
        assert elapsed >= 0.05  # some delay expected

    @pytest.mark.asyncio
    async def test_cancel_cost(self):
        """Cancel requests cost 2 tokens, not 10."""
        limiter = KalshiRateLimiter(tier=KalshiTier.BASIC)
        initial = limiter.write_tokens_available
        await limiter.acquire_write(cost=CANCEL_REQUEST_COST)
        # Should have consumed 2 tokens
        remaining = limiter.write_tokens_available
        assert initial - remaining == pytest.approx(CANCEL_REQUEST_COST, abs=1.0)

    @pytest.mark.asyncio
    async def test_recovery_after_drain(self):
        """Tokens refill over time."""
        limiter = KalshiRateLimiter(tier=KalshiTier.BASIC)
        # Drain
        for _ in range(10):
            await limiter.acquire_write()

        assert limiter.write_tokens_available < 5
        await asyncio.sleep(0.15)  # 100 tok/s * 0.15 = 15 tokens refilled
        assert limiter.write_tokens_available >= 10

    @pytest.mark.asyncio
    async def test_tier_config(self):
        """Different tiers have different capacities."""
        basic = KalshiRateLimiter(tier=KalshiTier.BASIC)
        premier = KalshiRateLimiter(tier=KalshiTier.PREMIER)
        assert basic.read_tokens_available == pytest.approx(200.0, abs=1)
        assert premier.read_tokens_available == pytest.approx(1000.0, abs=1)


# ── Client Tests (mocked HTTP) ─────────────────────────────────────

class TestKalshiClient:
    """Tests for KalshiClient REST methods using respx mocking."""

    # -- Happy paths --

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_events(self, client, base_url):
        route = respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(200, json={"events": [{"event_ticker": "EV-1"}], "cursor": "c1"})
        )
        result = await client.get_events(series_ticker="KXSOYBEANW")
        assert result["events"][0]["event_ticker"] == "EV-1"
        assert route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_event(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events/KXSOYBEANW-26APR24").mock(
            return_value=httpx.Response(200, json={"event": {"event_ticker": "KXSOYBEANW-26APR24"}})
        )
        result = await client.get_event("KXSOYBEANW-26APR24")
        assert "event" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_market(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/markets/KXSOYBEANW-26APR24-17").mock(
            return_value=httpx.Response(200, json={"market": {"ticker": "KXSOYBEANW-26APR24-17"}})
        )
        result = await client.get_market("KXSOYBEANW-26APR24-17")
        assert result["market"]["ticker"] == "KXSOYBEANW-26APR24-17"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_orderbook(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/markets/KXSOYBEANW-26APR24-17/orderbook").mock(
            return_value=httpx.Response(200, json={"orderbook": {"yes": [[50, 10]], "no": [[50, 5]]}})
        )
        result = await client.get_orderbook("KXSOYBEANW-26APR24-17")
        assert "orderbook" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_trades(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/markets/trades").mock(
            return_value=httpx.Response(200, json={"trades": [], "cursor": None})
        )
        result = await client.get_trades(ticker="KXSOYBEANW-26APR24-17")
        assert "trades" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_order(self, client, base_url):
        respx.post(f"{base_url}{_API_PREFIX}/portfolio/orders").mock(
            return_value=httpx.Response(200, json={"order": {"order_id": "ord-1", "status": "resting"}})
        )
        result = await client.create_order(
            ticker="KXSOYBEANW-26APR24-17",
            action="buy",
            side="yes",
            order_type="limit",
            count=10,
            yes_price=30,
        )
        assert result["order"]["order_id"] == "ord-1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_cancel_order(self, client, base_url):
        respx.delete(f"{base_url}{_API_PREFIX}/portfolio/orders/ord-1").mock(
            return_value=httpx.Response(200, json={"order": {"order_id": "ord-1", "status": "canceled"}})
        )
        result = await client.cancel_order("ord-1")
        assert result["order"]["status"] == "canceled"

    @pytest.mark.asyncio
    @respx.mock
    async def test_batch_cancel_orders(self, client, base_url):
        respx.delete(f"{base_url}{_API_PREFIX}/portfolio/orders/batch").mock(
            return_value=httpx.Response(200, json={"canceled": ["ord-1", "ord-2"]})
        )
        result = await client.batch_cancel_orders(["ord-1", "ord-2"])
        assert "canceled" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_trigger_order_group(self, client, base_url):
        respx.post(f"{base_url}{_API_PREFIX}/order-groups/grp-1/trigger").mock(
            return_value=httpx.Response(200, json={"status": "triggered"})
        )
        result = await client.trigger_order_group("grp-1")
        assert result["status"] == "triggered"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_positions(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/portfolio/positions").mock(
            return_value=httpx.Response(200, json={"market_positions": []})
        )
        result = await client.get_positions()
        assert "market_positions" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_fills(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/portfolio/fills").mock(
            return_value=httpx.Response(200, json={"fills": []})
        )
        result = await client.get_fills()
        assert "fills" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_balance(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/portfolio/balance").mock(
            return_value=httpx.Response(200, json={"balance": 10000})
        )
        result = await client.get_balance()
        assert result["balance"] == 10000

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_settlements(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/portfolio/settlements").mock(
            return_value=httpx.Response(200, json={"settlements": []})
        )
        result = await client.get_settlements()
        assert "settlements" in result

    # -- Error paths --

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_raises_auth_error(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(KalshiAuthError, match="401"):
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_raises_auth_error(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )
        with pytest.raises(KalshiAuthError, match="403"):
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_retries_then_raises(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(429, json={"error": "too many requests"})
        )
        with pytest.raises(KalshiRateLimitError):
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_500_retries_then_raises(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(KalshiResponseError, match="500"):
            # max_retries=2 in fixture, so 2 attempts then raise
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_unexpected_status_raises_immediately(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(418, text="I'm a teapot")
        )
        with pytest.raises(KalshiResponseError, match="418"):
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_json_raises(self, client, base_url):
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(200, text="not json at all")
        )
        with pytest.raises(KalshiResponseError, match="Malformed JSON"):
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_json_array_raises(self, client, base_url):
        """Non-dict JSON body should raise."""
        respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(200, json=[1, 2, 3])
        )
        with pytest.raises(KalshiResponseError, match="Expected JSON object"):
            await client.get_events()

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_then_success(self, client, base_url):
        """First attempt 500, second attempt 200: should succeed."""
        route = respx.get(f"{base_url}{_API_PREFIX}/events")
        route.side_effect = [
            httpx.Response(500, text="error"),
            httpx.Response(200, json={"events": []}),
        ]
        result = await client.get_events()
        assert result == {"events": []}
        assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_client_not_open_raises(self, auth, base_url):
        """Calling methods without open() should raise."""
        c = KalshiClient(auth=auth, base_url=base_url)
        with pytest.raises(KalshiAPIError, match="not open"):
            await c.get_events()

    @pytest.mark.asyncio
    async def test_context_manager(self, auth, base_url):
        """Async context manager should open and close cleanly."""
        async with KalshiClient(auth=auth, base_url=base_url) as c:
            assert c._client is not None
        assert c._client is None

    # -- Signing integration in client requests --

    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_headers_present(self, client, base_url):
        """All three auth headers should be present in requests."""
        route = respx.get(f"{base_url}{_API_PREFIX}/events").mock(
            return_value=httpx.Response(200, json={"events": []})
        )
        await client.get_events()
        request = route.calls[0].request
        assert "kalshi-access-key" in request.headers or "KALSHI-ACCESS-KEY" in request.headers
        # httpx lowercases headers
        assert "kalshi-access-timestamp" in request.headers
        assert "kalshi-access-signature" in request.headers
