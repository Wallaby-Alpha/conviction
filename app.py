"""
app.py

CLI entry point. Wires together helius.py (data), filters.py (noise
removal), calculations.py (retention math), and scoring.py (the
Conviction Score) into one report.

Usage:
    python app.py <TOKEN_MINT> [--no-cache] [--min-pct 0.001]
"""

from __future__ import annotations

import argparse
import sys

import config
from calculations import compute_retention
from filters import apply_minimum_balance_threshold, filter_holders
from helius import HeliusAPIError, HeliusClient
from scoring import compute_conviction_score


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute a Conviction Score for a Solana token."
    )
    parser.add_argument("mint", help="Token mint address")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the local cache and force fresh API calls",
    )
    parser.add_argument(
        "--min-pct",
        type=float,
        default=config.MIN_HOLDER_PCT_OF_SUPPLY,
        help=(
            "Minimum fraction of total supply a wallet must hold to be "
            "analyzed (e.g. 0.001 = 0.1%%). Default from config.py."
        ),
    )
    parser.add_argument(
        "--max-wallets",
        type=int,
        default=config.MAX_WALLETS_TO_ANALYZE,
        help="Safety cap on number of wallets analyzed.",
    )
    parser.add_argument(
        "--show-excluded",
        action="store_true",
        help="Print wallets that were excluded as infrastructure, and why.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    use_cache = not args.no_cache

    try:
        client = HeliusClient()
    except HeliusAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Fetching token metadata for {args.mint} ...")
    try:
        metadata = client.get_token_metadata(args.mint, use_cache=use_cache)
    except HeliusAPIError as exc:
        print(f"Failed to fetch token metadata: {exc}", file=sys.stderr)
        return 1

    print(f"Fetching holder list ...")
    try:
        raw_holders = client.get_token_holders(args.mint, use_cache=use_cache)
    except HeliusAPIError as exc:
        print(f"Failed to fetch token holders: {exc}", file=sys.stderr)
        return 1

    if not raw_holders:
        print("No holders found for this mint. Is the address correct?")
        return 1

    # Helius's getTokenAccounts doesn't always return decimals per-row;
    # backfill from metadata so balance math is correct everywhere.
    for h in raw_holders:
        if not h.decimals:
            h.decimals = metadata.decimals

    qualifying_holders = apply_minimum_balance_threshold(
        raw_holders, metadata, min_pct_of_supply=args.min_pct
    )

    filter_result = filter_holders(qualifying_holders, metadata)
    investor_holders = filter_result.investor_holders[: args.max_wallets]

    if args.show_excluded and filter_result.excluded:
        print("\nExcluded as non-investor wallets:")
        for holder, reason in filter_result.excluded:
            print(f"  {holder.owner}  ({reason}, balance={holder.balance:,.2f})")

    if filter_result.flagged_for_review:
        print("\nFlagged for review (large holder, possible team/treasury):")
        for holder, reason in filter_result.flagged_for_review:
            print(f"  {holder.owner}  balance={holder.balance:,.2f}")

    if not investor_holders:
        print(
            "\nNo qualifying investor wallets found above the "
            f"{args.min_pct * 100:.3f}% threshold after filtering."
        )
        return 1

    print(f"\nAnalyzing {len(investor_holders)} qualifying wallet(s) ...")

    positions = []
    for i, holder in enumerate(investor_holders, start=1):
        print(f"  [{i}/{len(investor_holders)}] {holder.owner}", end="\r")
        transfers = client.get_wallet_transfers(
            holder.owner, args.mint, use_cache=use_cache
        )
        position = compute_retention(transfers, holder.owner, holder.balance)
        positions.append(position)
    print()  # clear the progress line

    result = compute_conviction_score(positions)

    print_report(metadata, result, args.min_pct)
    return 0


def print_report(metadata, result, min_pct: float) -> None:
    print("\n" + "=" * 50)
    print(f"Token: {metadata.name} ({metadata.symbol})")
    print(f"Mint: {metadata.mint}")
    print(f"Total Supply: {metadata.total_supply:,.0f}")
    print(f"Wallet inclusion threshold: >= {min_pct * 100:.3f}% of supply")
    print(f"Wallets analyzed: {result.wallets_analyzed}")
    print("-" * 50)
    for band in config.RETENTION_BANDS:
        count = result.band_counts.get(band.label, 0)
        print(f"{band.label}: {count}")
    print("-" * 50)
    if result.wallets_analyzed < config.SCORING.min_wallets_for_score:
        print(
            f"Conviction Score: N/A "
            f"(fewer than {config.SCORING.min_wallets_for_score} qualifying wallets)"
        )
    else:
        print(f"Conviction Score: {result.score}/100")
    print("=" * 50)


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
