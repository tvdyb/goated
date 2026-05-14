"""Concrete TheoProvider implementations.

Three accessible paths for plugging in your own theos:

  - `function_provider` — decorator that wraps a single async function
    into a Protocol-compliant provider. Smallest in-process Python
    integration.

  - `FilePollTheoProvider` — polls a CSV/JSON file every N seconds.
    Most accessible: any external tool (Python, R, shell, jq) that can
    write a file works.

  - `HttpPollTheoProvider` — polls a JSON HTTP endpoint every N
    seconds. For when the model lives behind a service.

For stateful providers with non-trivial warmup / shutdown, write a
class implementing the TheoProvider protocol directly. See
`gbm_commodity.py` for the soy reference implementation.
"""

from lipmm.theo.providers._function import function_provider
from lipmm.theo.providers._truev_index import (
    DEFAULT_ANCHOR_PLACEHOLDER,
    DEFAULT_WEIGHTS_BACKTEST,
    DEFAULT_WEIGHTS_LIVE,
    DEFAULT_WEIGHTS_Q1_2026,
    DEFAULT_WEIGHTS_Q4_2025,
    TruEvAnchor,
    TruEvWeights,
    reconstruct_index,
)
from lipmm.theo.providers.file import FilePollTheoProvider
from lipmm.theo.providers.http import HttpPollTheoProvider
from lipmm.theo.providers.truev import TruEVConfig, TruEVTheoProvider
from lipmm.theo.providers.truev_notebook import TruEVNotebook

__all__ = [
    "DEFAULT_ANCHOR_PLACEHOLDER",
    "DEFAULT_WEIGHTS_BACKTEST",
    "DEFAULT_WEIGHTS_LIVE",
    "DEFAULT_WEIGHTS_Q1_2026",
    "DEFAULT_WEIGHTS_Q4_2025",
    "FilePollTheoProvider",
    "HttpPollTheoProvider",
    "TruEVConfig",
    "TruEVNotebook",
    "TruEVTheoProvider",
    "TruEvAnchor",
    "TruEvWeights",
    "function_provider",
    "reconstruct_index",
]
