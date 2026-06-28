"""
Unit tests for calculations.py -- the retention math is the foundation
everything else builds on, so it gets the most thorough coverage.

Run with: python -m pytest tests/ -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helius import TransferEvent
from calculations import total_accumulated, total_sent, compute_retention


def make_transfer(to=None, frm=None, amount=0.0, decimals=6, ts=0):
    return TransferEvent(
        signature=f"sig-{ts}-{amount}",
        timestamp=ts,
        from_address=frm,
        to_address=to,
        amount_raw=int(amount * (10 ** decimals)),
        decimals=decimals,
    )


def test_total_accumulated_sums_only_inbound():
    wallet = "WalletA"
    transfers = [
        make_transfer(to=wallet, amount=100, ts=1),
        make_transfer(frm=wallet, to="WalletB", amount=10, ts=2),
        make_transfer(to=wallet, amount=50, ts=3),
    ]
    assert total_accumulated(transfers, wallet) == 150


def test_total_sent_sums_only_outbound():
    wallet = "WalletA"
    transfers = [
        make_transfer(to=wallet, amount=100, ts=1),
        make_transfer(frm=wallet, to="WalletB", amount=10, ts=2),
        make_transfer(frm=wallet, to="WalletC", amount=20, ts=3),
    ]
    assert total_sent(transfers, wallet) == 30


def test_retention_example_from_spec():
    # Matches the exact example in the project brief:
    # bought 100,000, current balance 92,000 -> 92% retention
    wallet = "WalletA"
    transfers = [make_transfer(to=wallet, amount=100_000, ts=1)]
    position = compute_retention(transfers, wallet, current_balance=92_000)
    assert position.total_accumulated == 100_000
    assert position.current_balance == 92_000
    assert position.retention_pct == 92.0
    assert position.total_distributed == 8_000


def test_retention_full_diamond_hands():
    wallet = "WalletA"
    transfers = [make_transfer(to=wallet, amount=50_000, ts=1)]
    position = compute_retention(transfers, wallet, current_balance=50_000)
    assert position.retention_pct == 100.0


def test_retention_fully_distributed():
    wallet = "WalletA"
    transfers = [make_transfer(to=wallet, amount=50_000, ts=1)]
    position = compute_retention(transfers, wallet, current_balance=0)
    assert position.retention_pct == 0.0


def test_retention_capped_at_100_even_if_balance_exceeds_accumulated():
    # Can happen due to e.g. a missed/unindexed inbound transfer.
    wallet = "WalletA"
    transfers = [make_transfer(to=wallet, amount=10_000, ts=1)]
    position = compute_retention(transfers, wallet, current_balance=15_000)
    assert position.retention_pct == 100.0


def test_retention_no_transfer_history_falls_back_to_full_retention():
    wallet = "WalletA"
    position = compute_retention([], wallet, current_balance=1_000)
    assert position.total_accumulated == 1_000
    assert position.retention_pct == 100.0


def test_retention_no_history_and_zero_balance():
    wallet = "WalletA"
    position = compute_retention([], wallet, current_balance=0)
    assert position.retention_pct == 0.0


def test_retention_multiple_buys_then_partial_sell():
    wallet = "WalletA"
    transfers = [
        make_transfer(to=wallet, amount=1_000, ts=1),
        make_transfer(to=wallet, amount=2_000, ts=2),
        make_transfer(frm=wallet, to="exchange", amount=1_500, ts=3),
    ]
    # accumulated = 3000, current balance assumed = 1500
    position = compute_retention(transfers, wallet, current_balance=1_500)
    assert position.total_accumulated == 3_000
    assert position.retention_pct == 50.0


if __name__ == "__main__":
    test_fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed, failed = 0, 0
    for fn in test_fns:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {fn.__name__} -- {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
