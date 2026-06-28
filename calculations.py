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

from helius import TransferEvent


@dataclass
class WalletPosition:
    wallet: str
    total_accumulated: float  # sum of all inbound transfers, ever
    current_balance: float
    retention_pct: float  # current_balance / total_accumulated * 100

    @property
    def total_distributed(self) -> float:
        return max(self.total_accumulated - self.current_balance, 0.0)


def total_accumulated(transfers: list[TransferEvent], wallet: str) -> float:
    """Sum of every inbound transfer to `wallet` for this mint, ever.

    This is intentionally the simplest possible accumulation model for
    the MVP: total tokens ever received. It does not net out anything
    or try to detect wash trading / internal transfers between a user's
    own wallets -- that's future work (see scoring.py module docstring).
    """
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

    retention_pct is current_balance / total_accumulated, expressed as a
    percentage and capped at 100 (a wallet that only ever received
    tokens once and still holds all of them is at 100%, not above, even
    if current_balance ends up slightly higher than the summed transfer
    log due to e.g. a missed transfer or rounding).
    """
    accumulated = total_accumulated(transfers, wallet)

    if accumulated <= 0:
        # No inbound transfer history found (e.g. minted directly, or
        # history truncated). Fall back to treating current balance as
        # the full accumulated amount -- i.e. 100% retention -- rather
        # than dividing by zero. This is a conservative assumption that
        # should be revisited once average-up/historical modeling lands.
        accumulated = current_balance
        retention_pct = 100.0 if current_balance > 0 else 0.0
    else:
        retention_pct = (current_balance / accumulated) * 100.0
        retention_pct = min(retention_pct, 100.0)

    return WalletPosition(
        wallet=wallet,
        total_accumulated=accumulated,
        current_balance=current_balance,
        retention_pct=retention_pct,
    )
