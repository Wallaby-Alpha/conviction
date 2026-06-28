"""
config.py

Central place for every tunable knob in the system. Nothing in helius.py,
calculations.py, filters.py, or scoring.py should hardcode a threshold --
it should read it from here, so the whole system can be retuned without
touching logic code.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Wallet inclusion
# ---------------------------------------------------------------------------

# Only wallets holding at least this fraction of circulating supply are
# analyzed. 0.001 == 0.1%.
MIN_HOLDER_PCT_OF_SUPPLY = 0.001

# Hard cap on how many qualifying wallets we'll analyze in one run, as a
# safety valve against pathological tokens with thousands of large holders.
MAX_WALLETS_TO_ANALYZE = 500


# ---------------------------------------------------------------------------
# Holder classification bands
# ---------------------------------------------------------------------------
# Defined as (label, minimum retention percentage, inclusive lower bound).
# Must be sorted descending by min_pct. The last entry should have
# min_pct == 0 so every retention value lands in exactly one band.

@dataclass(frozen=True)
class RetentionBand:
    label: str
    min_pct: float  # inclusive lower bound, 0-100 scale


RETENTION_BANDS: list[RetentionBand] = [
    RetentionBand("Diamond Hands", 95.0),
    RetentionBand("Strong", 80.0),
    RetentionBand("Medium", 60.0),
    RetentionBand("Weak", 40.0),
    RetentionBand("Distributed", 0.0),
]


# ---------------------------------------------------------------------------
# Conviction score weighting
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringConfig:
    # Retention is capped at 100% for scoring purposes -- a wallet that
    # accumulated more after its initial buys shouldn't be penalized, but
    # it also shouldn't let retention exceed the natural 0-100 scale.
    cap_retention_at_pct: float = 100.0

    # Wallet "size" weight uses current balance (in token units, or USD if
    # a price feed is wired in later). sqrt-dampening prevents one whale
    # from single-handedly deciding the score.
    size_weight_dampening: str = "sqrt"  # "sqrt" | "log" | "linear"

    # Minimum number of qualifying wallets required to produce a score at
    # all. Below this, the sample is too thin to be meaningful.
    min_wallets_for_score: int = 3


SCORING = ScoringConfig()


# ---------------------------------------------------------------------------
# Non-investor wallet filtering
# ---------------------------------------------------------------------------

# Known infrastructure addresses to always exclude, regardless of balance.
# This is a starting seed list -- expand as you identify more. Keyed by
# mint-agnostic owner address (these are real, well-known Solana program /
# infra addresses, not token-specific).
KNOWN_INFRASTRUCTURE_ADDRESSES: set[str] = {
    # Token / associated-token program owned accounts are filtered
    # structurally (see filters.py), not by address, since every token
    # has its own pool/vault addresses. This set is for cross-token
    # infra that shows up everywhere, e.g. well-known CEX hot wallets.
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium AMM authority
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # Raydium authority v4
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",  # Wrapped SOL related
}

# Owner-program substrings/IDs that indicate an account is a program /
# pool / vault rather than a user wallet. If a holder account's *owner
# program* matches one of these, exclude it.
PROGRAM_ACCOUNT_OWNERS: set[str] = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL Token program (raw, non-ATA edge case)
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",  # Associated Token Account program
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Serum DEX v3
    "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin",  # Serum DEX v2
    "whirLbMiicVdio4qvUfM5KAg6Ce8O9z3SBjbsHkPMzvL",  # Orca Whirlpools
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",  # Raydium CLMM
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Serum
}

# Heuristic: if a single wallet's balance exceeds this fraction of total
# supply, flag it for manual review as a likely treasury/team wallet
# rather than auto-excluding it (since we can't always be sure). The
# pipeline will still include it but mark it for transparency.
TEAM_TREASURY_REVIEW_THRESHOLD = 0.05  # 5% of supply


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

CACHE_DIR = "cache"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour


# ---------------------------------------------------------------------------
# Helius API
# ---------------------------------------------------------------------------

HELIUS_API_BASE = "https://api.helius.xyz"
HELIUS_RPC_BASE = "https://mainnet.helius-rpc.com"

# Pagination page size for getTokenAccounts / transfer history calls.
PAGE_SIZE = 1000

# Basic retry/backoff behavior for HTTP calls.
MAX_RETRIES = 4
RETRY_BACKOFF_BASE_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 30
