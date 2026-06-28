"""
calculations.py

Pure math on transfer history and balances: how much a wallet ever
accumulated, what it holds now, and what fraction of its peak
accumulated position it has retained.

No network calls, no filtering decisions, no scoring weights -- those
live in helius.py, filters.py, and scoring.py respectively. Keeping
this file pure makes it trivial to unit test and to swap in a smarter
accumulation model later (e.g. average-up detection) without touching
anything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helius import TransferEvent


@dataclass
class WalletPosition:
    wallet: str
    total_accumulated: float  # sum of all inbound transfers inside window
    current_balance: float
    retention_pct: float  # current_balance / total_accumulated * 100

    @property
    def total_distributed(self) -> float:
        return max(self.total_accumulated - self.current_balance, 0.0)


def total_accumulated(transfers: list[TransferEvent], wallet: str) -> float:
    """Sum of every inbound transfer to `wallet` for this mint, ever."""
    return sum(t.amount for t in transfers if t.to_address == wallet)


def total_sent(transfers: list[TransferEvent], wallet: str) -> float:
    """Sum of every outbound transfer from `wallet` for this mint, ever."""
    return sum(t.amount for t in transfers if t.from_address == wallet)


def compute_retention(
    transfers: list[TransferEvent],
    wallet: str,
    current_balance: float,
) -> WalletPosition:
    """Compute a wallet's accumulation and retention for one mint.

    If no inbound transfers were detected within the active tracking lookback
    timeframe window, total_accumulated defaults to 0.0 and retention rate 
    is calculated at 0.0% to reflect that no active buying occurred.
    """
    accumulated = total_accumulated(transfers, wallet)

    if accumulated <= 0:
        # FIXED: Stop treating pre-existing holders without recent transfers 
        # as perfect 100% Diamond Hands. Setting to 0.0 flags them cleanly.
        accumulated = 0.0
        retention_pct = 0.0
    else:
        retention_pct = (current_balance / accumulated) * 100.0
        retention_pct = min(retention_pct, 100.0)

    return WalletPosition(
        wallet=wallet,
        total_accumulated=accumulated,
        current_balance=current_balance,
        retention_pct=retention_pct,
    )
