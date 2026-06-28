"""
Unit tests for scoring.py -- band classification and the weighted
conviction score.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from calculations import WalletPosition
from scoring import classify_retention, compute_conviction_score


def make_position(wallet, balance, retention_pct):
    accumulated = balance / (retention_pct / 100.0) if retention_pct > 0 else balance
    return WalletPosition(
        wallet=wallet,
        total_accumulated=accumulated,
        current_balance=balance,
        retention_pct=retention_pct,
    )


def test_classify_retention_bands():
    assert classify_retention(100) == "Diamond Hands"
    assert classify_retention(95) == "Diamond Hands"
    assert classify_retention(94.9) == "Strong"
    assert classify_retention(80) == "Strong"
    assert classify_retention(79.9) == "Medium"
    assert classify_retention(60) == "Medium"
    assert classify_retention(59.9) == "Weak"
    assert classify_retention(40) == "Weak"
    assert classify_retention(39.9) == "Distributed"
    assert classify_retention(0) == "Distributed"


def test_uniform_retention_gives_that_score_regardless_of_weighting():
    positions = [
        make_position("A", balance=1_000, retention_pct=80),
        make_position("B", balance=50_000, retention_pct=80),
        make_position("C", balance=200, retention_pct=80),
    ]
    result = compute_conviction_score(positions)
    assert result.score == 80.0


def test_larger_holders_weighted_more_heavily():
    positions = [
        make_position("Whale", balance=1_000_000, retention_pct=100),
        make_position("Small1", balance=100, retention_pct=0),
        make_position("Small2", balance=100, retention_pct=0),
        make_position("Small3", balance=100, retention_pct=0),
    ]
    result = compute_conviction_score(positions)
    assert result.score > 50.0


def test_band_counts_sum_to_wallets_analyzed():
    positions = [
        make_position("A", balance=1000, retention_pct=96),  # Diamond
        make_position("B", balance=1000, retention_pct=85),  # Strong
        make_position("C", balance=1000, retention_pct=65),  # Medium
        make_position("D", balance=1000, retention_pct=45),  # Weak
        make_position("E", balance=1000, retention_pct=10),  # Distributed
    ]
    result = compute_conviction_score(positions)
    assert sum(result.band_counts.values()) == 5
    assert result.band_counts["Diamond Hands"] == 1
    assert result.band_counts["Strong"] == 1
    assert result.band_counts["Medium"] == 1
    assert result.band_counts["Weak"] == 1
    assert result.band_counts["Distributed"] == 1


def test_below_minimum_wallets_returns_zero_not_error():
    positions = [make_position("A", balance=1000, retention_pct=90)]
    result = compute_conviction_score(positions)
    assert result.wallets_analyzed == 1
    assert result.score == 0.0  # below config.SCORING.min_wallets_for_score


def test_empty_positions_does_not_crash():
    result = compute_conviction_score([])
    assert result.score == 0.0
    assert result.wallets_analyzed == 0


def test_score_is_bounded_0_to_100():
    positions = [
        make_position("A", balance=999_999_999, retention_pct=100),
        make_position("B", balance=1, retention_pct=100),
        make_position("C", balance=1, retention_pct=100),
    ]
    result = compute_conviction_score(positions)
    assert 0.0 <= result.score <= 100.0
    assert result.score == 100.0


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
