"""Risk-neutral density (RND) extraction pipeline.

F4-ACT-03: closes GAP-006, GAP-036, GAP-037, GAP-038, GAP-041,
GAP-042, GAP-043, GAP-044, GAP-045, GAP-049, GAP-101, GAP-003.

Pipeline: CME options chain -> BL density -> SVI smooth -> Figlewski tails
-> bucket integration -> per-bucket Yes-prices for Kalshi half-line strikes.
"""

from engine.rnd.breeden_litzenberger import bl_density
from engine.rnd.bucket_integrator import BucketPrices, integrate_buckets
from engine.rnd.figlewski import extend_tails
from engine.rnd.pipeline import RNDValidationError, compute_rnd
from engine.rnd.svi import SVIParams, svi_calibrate

__all__ = [
    "bl_density",
    "svi_calibrate",
    "SVIParams",
    "extend_tails",
    "integrate_buckets",
    "BucketPrices",
    "compute_rnd",
    "RNDValidationError",
]
