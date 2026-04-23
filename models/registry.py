"""Commodity → model registry.

Loads `config/commodities.yaml` and instantiates one `Theo` per commodity
that has a fully-specified config. Stub entries (those tagged `stub: true`)
are recorded so `get()` can raise a clear "not yet configured" error
instead of silently falling back.

Deliverable 1 wires only WTI (GBM). Other model families register their
class here as they come online.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from models.base import Theo
from models.gbm import GBMTheo


@dataclass(frozen=True, slots=True)
class CommodityConfig:
    commodity: str
    model_name: str
    raw: dict[str, Any] = field(default_factory=dict)
    is_stub: bool = False


_MODEL_BUILDERS: dict[str, Any] = {
    "gbm": lambda cfg: GBMTheo(params_version=cfg.raw.get("params_version", "v0")),
    # "jump_diffusion": lambda cfg: ...,   # deliverable 4
    # "regime_switch":  lambda cfg: ...,   # deliverable 5
    # "point_mass":     lambda cfg: ...,   # deliverable 5
    # "student_t":      lambda cfg: ...,   # deliverable 4 alternative
}


class Registry:
    def __init__(self, config_path: str | Path) -> None:
        self._configs: dict[str, CommodityConfig] = {}
        self._instances: dict[str, Theo] = {}
        self._load(Path(config_path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"commodities config not found: {path}")
        with path.open() as f:
            doc = yaml.safe_load(f)
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: expected top-level mapping, got {type(doc).__name__}")

        for commodity, raw in doc.items():
            if not isinstance(raw, dict):
                raise ValueError(f"{path}: commodity {commodity!r} must be a mapping")
            model_name = raw.get("model")
            if not model_name:
                raise ValueError(f"{path}: commodity {commodity!r} missing `model` field")
            is_stub = bool(raw.get("stub", False))
            cfg = CommodityConfig(
                commodity=commodity, model_name=model_name, raw=raw, is_stub=is_stub
            )
            self._configs[commodity] = cfg

            if is_stub:
                continue
            builder = _MODEL_BUILDERS.get(model_name)
            if builder is None:
                raise ValueError(
                    f"{commodity}: model {model_name!r} has no builder registered "
                    f"(expected one of {sorted(_MODEL_BUILDERS)})"
                )
            self._instances[commodity] = builder(cfg)

    def get(self, commodity: str) -> Theo:
        if commodity in self._instances:
            return self._instances[commodity]
        if commodity in self._configs and self._configs[commodity].is_stub:
            raise NotImplementedError(
                f"{commodity}: registered as stub, not yet configured for pricing"
            )
        raise KeyError(f"{commodity}: not in registry")

    def config(self, commodity: str) -> CommodityConfig:
        if commodity not in self._configs:
            raise KeyError(f"{commodity}: not in registry")
        return self._configs[commodity]

    def commodities(self, *, configured_only: bool = False) -> list[str]:
        if configured_only:
            return sorted(self._instances)
        return sorted(self._configs)
