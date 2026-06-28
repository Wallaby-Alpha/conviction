"""
scoring.py

The Conviction Score algorithm itself. This is the file you should
expect to rewrite repeatedly as the formula evolves -- it's deliberately
isolated from API access (helius.py), filtering (filters.py), and raw
math (calculations.py) so changing the scoring approach never requires
touching those.

Current MVP approach
---------------------
1. Classify each qualifying wallet into a retention band (Diamond Hands /
   Strong / Medium / Weak / Distributed) using config.RETENTION_BANDS.
2. Compute a weighted average of retention_pct across all wallets, where
   the weight is each wallet's *current balance*, dampened (sqrt by
   default) so a single whale can't dominate the score.
3. Map that weighted average (0-100) directly to the Conviction Score.

This is intentionally simple. Known limitations to revisit:
    - Doesn't account for wallet "quality" (smart money vs. random).
    - Doesn't detect averaging up, dip buying, or time-weighted conviction.
    - Treats every retained token equally regardless of when it was bought.
These are explicitly future work (see project README / future features).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import config
from calculations import WalletPosition


@dataclass
class ClassifiedWallet:
    position: WalletPosition
    band: str


@dataclass
class ConvictionResult:
    score: float  # 0-100
    classified_wallets: list[ClassifiedWallet]
    band_counts: dict[str, int]
    wallets_analyzed: int


def classify_retention(retention_pct: float) -> str:
    """Map a retention percentage to its band label using
    config.RETENTION_BANDS (must be sorted descending by min_pct)."""
    for band in config.RETENTION_BANDS:
        if retention_pct >= band.min_pct:
            return band.label
    # Should be unreachable since the last band's min_pct is 0, but keep
    # a safe fallback.
    return config.RETENTION_BANDS[-1].label


def _size_weight(balance: float) -> float:
    """Dampen raw balance so large holders contribute proportionally
    more than small ones, without one wallet swamping everyone else."""
    mode = config.SCORING.size_weight_dampening
    safe_balance = max(balance, 0.0)

    if mode == "linear":
        return safe_balance
    if mode == "log":
        return math.log1p(safe_balance)
    # default: sqrt
    return math.sqrt(safe_balance)


def compute_conviction_score(
    positions: list[WalletPosition],
) -> ConvictionResult:
    """Compute the overall Conviction Score (0-100) for a token given the
    retention positions of all qualifying, filtered investor wallets.

    Returns a ConvictionResult with the score, per-wallet classification,
    and counts per band -- everything app.py needs to render the report.
    """
    classified: list[ClassifiedWallet] = []
    band_counts: dict[str, int] = {band.label: 0 for band in config.RETENTION_BANDS}

    for position in positions:
        capped_retention = min(position.retention_pct, config.SCORING.cap_retention_at_pct)
        band = classify_retention(capped_retention)
        band_counts[band] += 1
        classified.append(ClassifiedWallet(position=position, band=band))

    if len(positions) < config.SCORING.min_wallets_for_score:
        # Not enough signal for a meaningful score. Returning 0.0 rather
        # than raising, so the CLI can still print a clear "insufficient
        # data" style result alongside the breakdown.
        return ConvictionResult(
            score=0.0,
            classified_wallets=classified,
            band_counts=band_counts,
            wallets_analyzed=len(positions),
        )

    weighted_sum = 0.0
    weight_total = 0.0
    for position in positions:
        capped_retention = min(position.retention_pct, config.SCORING.cap_retention_at_pct)
        weight = _size_weight(position.current_balance)
        weighted_sum += capped_retention * weight
        weight_total += weight

    score = (weighted_sum / weight_total) if weight_total > 0 else 0.0
    score = max(0.0, min(100.0, score))

    return ConvictionResult(
        score=round(score, 1),
        classified_wallets=classified,
        band_counts=band_counts,
        wallets_analyzed=len(positions),
    )
