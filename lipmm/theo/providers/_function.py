"""`function_provider` — wrap a plain async function into a
Protocol-compliant TheoProvider.

For in-process Python integrations that don't need warmup / shutdown /
cached state, the boilerplate of a class can be skipped. This decorator
generates the wrapper class, sets `series_prefix`, and gives no-op
warmup/shutdown.

Example:

    from lipmm.theo import TheoResult
    from lipmm.theo.providers import function_provider

    @function_provider(series_prefix="KXISMPMI", source="pmi-bayes-v1")
    async def pmi_theo(ticker: str) -> TheoResult:
        prob = await my_model.predict(ticker)
        return TheoResult(
            yes_probability=prob, confidence=0.85,
            computed_at=time.time(), source="pmi-bayes-v1",
        )

    theo_registry.register(pmi_theo)   # decorator returns the instance

If you DO need warmup/shutdown, write a class implementing the protocol
directly — that's still the right path for stateful providers.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from lipmm.theo.base import TheoResult


def function_provider(
    *,
    series_prefix: str,
    source: str = "function-provider",
) -> Callable[[Callable[[str], Awaitable[TheoResult]]], "_FunctionProvider"]:
    """Decorator that turns an async `(ticker) -> TheoResult` function
    into a TheoProvider instance ready to register.

    The decorated callable's `series_prefix` attribute is set to the
    given value; pass `"*"` to match all tickers.

    The function is called once per ticker per cycle; it must be fast
    (no upstream I/O on the hot path — cache instead).
    """
    if not series_prefix:
        raise ValueError("series_prefix required (use '*' for wildcard)")

    def _wrap(
        fn: Callable[[str], Awaitable[TheoResult]],
    ) -> "_FunctionProvider":
        return _FunctionProvider(fn=fn, series_prefix=series_prefix, source=source)

    return _wrap


class _FunctionProvider:
    """Minimal TheoProvider that delegates to a single async function."""

    def __init__(
        self,
        *,
        fn: Callable[[str], Awaitable[TheoResult]],
        series_prefix: str,
        source: str,
    ) -> None:
        self._fn = fn
        self.series_prefix = series_prefix
        self.source = source

    async def warmup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def theo(self, ticker: str) -> TheoResult:
        return await self._fn(ticker)

    def __repr__(self) -> str:
        name = getattr(self._fn, "__qualname__", repr(self._fn))
        return (
            f"_FunctionProvider(fn={name}, "
            f"series_prefix={self.series_prefix!r}, source={self.source!r})"
        )
