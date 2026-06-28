"""
Unit tests for filters.py -- infrastructure exclusion and the minimum
balance threshold.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from helius import TokenAccountHolder, TokenMetadata
from filters import filter_holders, apply_minimum_balance_threshold


def make_metadata(total_supply=1_000_000, decimals=6):
    return TokenMetadata(
        mint="MintXYZ",
        name="Test Token",
        symbol="TST",
        decimals=decimals,
        total_supply_raw=int(total_supply * (10 ** decimals)),
    )


def make_holder(owner, balance, decimals=6):
    return TokenAccountHolder(
        owner=owner,
        token_account=f"acct-{owner}",
        balance_raw=int(balance * (10 ** decimals)),
        decimals=decimals,
    )


def test_minimum_balance_threshold_excludes_small_wallets():
    metadata = make_metadata(total_supply=1_000_000)
    holders = [
        make_holder("Big", balance=5_000),     # 0.5%
        make_holder("Small", balance=500),     # 0.05% -- below 0.1% default
    ]
    result = apply_minimum_balance_threshold(holders, metadata)
    owners = {h.owner for h in result}
    assert "Big" in owners
    assert "Small" not in owners


def test_known_infrastructure_excluded():
    metadata = make_metadata()
    program_owner = next(iter(config.PROGRAM_ACCOUNT_OWNERS))
    holders = [
        make_holder("RealInvestor", balance=10_000),
        make_holder(program_owner, balance=50_000),
    ]
    result = filter_holders(holders, metadata)
    owners = {h.owner for h in result.investor_holders}
    assert "RealInvestor" in owners
    assert program_owner not in owners
    excluded_owners = {h.owner for h, _ in result.excluded}
    assert program_owner in excluded_owners


def test_burn_address_excluded():
    metadata = make_metadata()
    holders = [
        make_holder("RealInvestor", balance=10_000),
        make_holder("1nc1nerator11111111111111111111111111111111", balance=999_999),
    ]
    result = filter_holders(holders, metadata)
    owners = {h.owner for h in result.investor_holders}
    assert "RealInvestor" in owners
    assert "1nc1nerator11111111111111111111111111111111" not in owners


def test_large_holder_flagged_not_excluded():
    metadata = make_metadata(total_supply=1_000_000)
    holders = [make_holder("Whale", balance=80_000)]  # 8% > 5% threshold
    result = filter_holders(holders, metadata)
    owners = {h.owner for h in result.investor_holders}
    assert "Whale" in owners  # still included
    flagged_owners = {h.owner for h, _ in result.flagged_for_review}
    assert "Whale" in flagged_owners


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
