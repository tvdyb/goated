"""CME ingest error types.

Fail-loud policy: every unexpected condition raises a typed exception.
No silent swallowing, no partial data returns.
"""

from __future__ import annotations


class CMEIngestError(Exception):
    """Base exception for all CME data ingest errors."""

    def __init__(self, message: str, *, source: str | None = None) -> None:
        self.source = source
        super().__init__(message)


class CMEChainError(CMEIngestError):
    """Options chain pull failed (HTTP error, parse failure, missing data)."""


class CMESettleError(CMEIngestError):
    """Settlement price pull failed."""


class CMEParityError(CMEIngestError):
    """Put-call parity violation exceeds tolerance threshold."""
