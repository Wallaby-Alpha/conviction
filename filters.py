"""
filters.py

Removes non-investor wallets from a holder list before any scoring
happens: exchanges, liquidity pools, bridges, burn addresses, program
accounts, and (flagged, not excluded) likely team/treasury wallets.

This module never touches the network -- it operates purely on the
TokenAccountHolder / TokenMetadata objects already fetched by helius.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from helius import TokenAccountHolder, TokenMetadata

# Solana burn addresses (tokens sent here are gone forever).
BURN_ADDRESSES: set[str] = {
    "1nc1nerator11111111111111111111111111111111",
    "11111111111111111111111111111111111111111",  # system program / null-ish
}


@dataclass
class FilterResult:
    """Holders split into the investor set we'll actually score, plus
    everything we excluded, with the reason, for transparency/debugging."""

    investor_holders: list[TokenAccountHolder]
    excluded: list[tuple[TokenAccountHolder, str]]  # (holder, reason)
    flagged_for_review: list[tuple[TokenAccountHolder, str]]  # not excluded


def is_known_infrastructure(owner: str) -> bool:
    return (
        owner in config.KNOWN_INFRASTRUCTURE_ADDRESSES
        or owner in config.PROGRAM_ACCOUNT_OWNERS
    )


def is_burn_address(owner: str) -> bool:
    return owner in BURN_ADDRESSES


def filter_holders(
    holders: list[TokenAccountHolder],
    metadata: TokenMetadata,
) -> FilterResult:
    """Apply all exclusion rules and return the cleaned investor set.

    Order of operations:
        1. Drop burn addresses (tokens are permanently gone, not "held").
        2. Drop known infrastructure / program-owned accounts.
        3. Flag (but keep) wallets that look like team/treasury based on
           size alone -- we can't be fully sure without on-chain labels,
           so we surface it rather than silently dropping a legitimate
           large holder.
    """
    investor_holders: list[TokenAccountHolder] = []
    excluded: list[tuple[TokenAccountHolder, str]] = []
    flagged: list[tuple[TokenAccountHolder, str]] = []

    total_supply = metadata.total_supply or 1.0  # guard div-by-zero

    for holder in holders:
        if is_burn_address(holder.owner):
            excluded.append((holder, "burn_address"))
            continue

        if is_known_infrastructure(holder.owner):
            excluded.append((holder, "known_infrastructure"))
            continue

        pct_of_supply = holder.balance / total_supply
        if pct_of_supply >= config.TEAM_TREASURY_REVIEW_THRESHOLD:
            flagged.append((holder, "large_holder_possible_team_treasury"))

        investor_holders.append(holder)

    return FilterResult(
        investor_holders=investor_holders,
        excluded=excluded,
        flagged_for_review=flagged,
    )


def apply_minimum_balance_threshold(
    holders: list[TokenAccountHolder],
    metadata: TokenMetadata,
    min_pct_of_supply: float = config.MIN_HOLDER_PCT_OF_SUPPLY,
) -> list[TokenAccountHolder]:
    """Keep only wallets holding at least `min_pct_of_supply` of total
    circulating supply (e.g. 0.001 == 0.1%)."""
    total_supply = metadata.total_supply or 1.0
    min_balance = total_supply * min_pct_of_supply
    return [h for h in holders if h.balance >= min_balance]
