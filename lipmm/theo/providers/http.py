"""`HttpPollTheoProvider` — load theos from a JSON HTTP endpoint
polled on a schedule.

For when the model lives behind a service rather than a file. Same
JSON payload shapes as `FilePollTheoProvider`:

    {"KX-T1": {"yes_cents": 82, "confidence": 0.85, "reason": "..."}}

or:

    [{"ticker": "KX-T1", "yes_cents": 82, "confidence": 0.85}, ...]

Args:
  url: GET endpoint that returns the JSON theos payload.
  series_prefix: registry routing key. '*' = wildcard.
  refresh_s: poll interval. Default 5s.
  staleness_threshold_s: above this (last successful refresh age),
    confidence drops to 0. Default 3× refresh_s. None to disable.
  bearer: optional bearer token; sent as `Authorization: Bearer <token>`.
  headers: optional extra request headers.
  timeout_s: per-request timeout (default 5s).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from lipmm.theo.base import TheoResult
from lipmm.theo.providers.file import _Entry, _parse_json

logger = logging.getLogger(__name__)


_DEFAULT_REFRESH_S = 5.0
_DEFAULT_STALENESS_MULT = 3.0


class HttpPollTheoProvider:
    """TheoProvider that polls a JSON HTTP endpoint."""

    def __init__(
        self,
        url: str,
        *,
        series_prefix: str,
        refresh_s: float = _DEFAULT_REFRESH_S,
        staleness_threshold_s: float | None = -1.0,
        bearer: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_s: float = 5.0,
        source: str = "http-poll",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not url:
            raise ValueError("url required")
        if not series_prefix:
            raise ValueError("series_prefix required (use '*' for wildcard)")
        if refresh_s <= 0:
            raise ValueError(f"refresh_s must be > 0, got {refresh_s}")
        self.series_prefix = series_prefix
        self._url = url
        self._refresh_s = float(refresh_s)
        if staleness_threshold_s == -1.0:
            self._staleness_threshold_s: float | None = (
                _DEFAULT_STALENESS_MULT * self._refresh_s
            )
        else:
            self._staleness_threshold_s = staleness_threshold_s
        self._headers = dict(headers or {})
        if bearer:
            self._headers["Authorization"] = f"Bearer {bearer}"
        self._timeout_s = timeout_s
        self._source = source
        self._owns_client = client is None
        self._client: httpx.AsyncClient | None = client

        self._snapshot: dict[str, _Entry] = {}
        self._snapshot_loaded_at: float = 0.0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ── TheoProvider protocol ──────────────────────────────────────

    async def warmup(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        await self._reload()
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._poll_loop())

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def theo(self, ticker: str) -> TheoResult:
        now = time.time()
        entry = self._snapshot.get(ticker)
        if entry is None:
            return TheoResult(
                yes_probability=0.5, confidence=0.0,
                computed_at=now, source=f"{self._source}:no-row",
                extras={"url": self._url, "ticker": ticker},
            )
        if self._is_stale(now):
            return TheoResult(
                yes_probability=entry.yes_probability,
                confidence=0.0,
                computed_at=now, source=f"{self._source}:stale",
                extras={
                    "url": self._url,
                    "snapshot_age_s": now - self._snapshot_loaded_at,
                    "stored_confidence": entry.confidence,
                },
            )
        return TheoResult(
            yes_probability=entry.yes_probability,
            confidence=entry.confidence,
            computed_at=self._snapshot_loaded_at,
            source=self._source,
            extras={"url": self._url, "reason": entry.reason},
        )

    # ── internals ──────────────────────────────────────────────────

    def _is_stale(self, now: float) -> bool:
        if self._staleness_threshold_s is None:
            return False
        if self._snapshot_loaded_at == 0.0:
            return True
        return (now - self._snapshot_loaded_at) > self._staleness_threshold_s

    async def _poll_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self._refresh_s,
                    )
                    return
                except asyncio.TimeoutError:
                    pass
                await self._reload()
        except asyncio.CancelledError:
            return

    async def _reload(self) -> None:
        if self._client is None:
            return
        try:
            r = await self._client.get(self._url, headers=self._headers)
            r.raise_for_status()
            text = r.text
        except Exception as exc:
            logger.warning(
                "HttpPollTheoProvider: GET %s failed: %s — keeping last snapshot",
                self._url, exc,
            )
            return
        try:
            snapshot = _parse_json(text)
        except Exception as exc:
            logger.warning(
                "HttpPollTheoProvider: parse %s failed: %s — keeping last snapshot",
                self._url, exc,
            )
            return
        self._snapshot = snapshot
        self._snapshot_loaded_at = time.time()
        logger.info(
            "HttpPollTheoProvider: loaded %d entries from %s",
            len(snapshot), self._url,
        )
