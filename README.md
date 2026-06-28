# Solana Token Conviction Score

A command-line tool that analyzes a Solana token's large holders and
produces a **Conviction Score (0-100)**: a measure of how strongly
significant holders have retained the tokens they accumulated, versus
distributed them.

The hypothesis: a token whose major holders still hold most of what
they bought shows higher conviction than one where large holders have
sold off most of their position.

This is an MVP focused on a correct, modular data pipeline and scoring
engine — not a polished app. It's designed so a web UI (Streamlit,
FastAPI + React, etc.) can be layered on top later without touching the
core logic.

## Setup

```bash
pip install -r requirements.txt
export HELIUS_API_KEY=your_key_here
```

Get a free Helius API key at https://www.helius.dev.

## Usage

```bash
python app.py <TOKEN_MINT>
```

Example output:

```
Token: Example Token (EXMP)
Mint: Mint1...
Total Supply: 1,000,000
Wallet inclusion threshold: >= 0.100% of supply
Wallets analyzed: 5
--------------------------------------------------
Diamond Hands: 0
Strong: 1
Medium: 1
Weak: 1
Distributed: 2
--------------------------------------------------
Conviction Score: 63.9/100
==================================================
```

### Options

| Flag             | Description                                                  |
|------------------|----------------------------------------------------------------|
| `--no-cache`     | Bypass the local cache and force fresh API calls                |
| `--min-pct`      | Minimum % of supply a wallet must hold to be analyzed (default 0.1%) |
| `--max-wallets`  | Safety cap on wallets analyzed (default 500)                   |
| `--show-excluded`| Print which wallets were filtered out as infrastructure, and why |

## How it works

1. **`helius.py`** — All Helius API calls (token metadata, current
   holders/balances via `getTokenAccounts`, historical transfers via
   the Enhanced Transactions API). Includes local disk caching
   (`cache/`, 1 hour TTL) to limit API usage.
2. **`filters.py`** — Strips out exchanges, liquidity pools, bridges,
   burn addresses, and program-owned accounts. Flags (but doesn't
   exclude) very large holders as possible team/treasury wallets for
   manual review.
3. **`calculations.py`** — Pure math: sums a wallet's total inbound
   transfers ever ("accumulated"), compares to current balance, and
   computes retention % (capped at 100%).
4. **`scoring.py`** — Classifies each wallet into a retention band
   (Diamond Hands / Strong / Medium / Weak / Distributed) and computes
   the overall Conviction Score as a size-weighted average of
   retention, with `sqrt` dampening so one whale can't dominate.
5. **`config.py`** — Every threshold (inclusion %, band cutoffs, size
   weighting, cache TTL, etc.) lives here, not buried in logic code.
6. **`app.py`** — CLI glue. No business logic of its own.

## Known limitations (by design, for the MVP)

- Accumulation is "every token ever received," not "every token ever
  bought" — it doesn't distinguish a purchase from an internal transfer
  between a user's own wallets, and doesn't do average-up/dip-buy
  detection.
- Team/treasury wallets are flagged by size heuristic, not a verified
  label list. Verify manually before treating a token's score as final.
- No price feed — wallet "size" weighting in the score uses token
  amount, not USD value.

## Planned, not yet built

- Wallet quality / smart-money scoring
- Wallet profitability
- Average-up / dip-buying detection
- Historical conviction-over-time charts
- Streamlit or FastAPI + React UI
- Multi-token comparison
- REST API endpoint

## Running tests

```bash
python tests/test_calculations.py
python tests/test_scoring.py
python tests/test_filters.py
```
