"""
helius.py

Thin client around the Helius API. Optimized for Free-tier speed by avoiding
per-wallet transaction loops and using master mint transaction streams instead.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

import config


class HeliusAPIError(Exception):
    """Raised when the Helius API returns an unrecoverable error."""


@dataclass
class TokenMetadata:
    mint: str
    name: str
    symbol: str
    decimals: int
    total_supply_raw: int

    @property
    def total_supply(self) -> float:
        return self.total_supply_raw / (10 ** self.decimals)


@dataclass
class TokenAccountHolder:
    owner: str
    token_account: str
    balance_raw: int
    decimals: int

    @property
    def balance(self) -> float:
        return self.balance_raw / (10 ** self.decimals)


@dataclass
class TransferEvent:
    signature: str
    timestamp: int
    from_address: Optional[str]
    to_address: Optional[str]
    amount_raw: int
    decimals: int

    @property
    def amount(self) -> float:
        return self.amount_raw / (10 ** self.decimals)


# ---------------------------------------------------------------------------
# Caching helpers
# ---------------------------------------------------------------------------

def _cache_path(cache_key: str) -> str:
    safe_key = cache_key.replace("/", "_")
    return os.path.join(config.CACHE_DIR, f"{safe_key}.json")


def _read_cache(cache_key: str) -> Optional[Any]:
    path = _cache_path(cache_key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    fetched_at = payload.get("_fetched_at", 0)
    if time.time() - fetched_at > config.CACHE_TTL_SECONDS:
        return None
    return payload.get("data")


def _write_cache(cache_key: str, data: Any) -> None:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = _cache_path(cache_key)
    payload = {"_fetched_at": time.time(), "data": data}
    with open(path, "w") as f:
        json.dump(payload, f)


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class HeliusClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("HELIUS_API_KEY")
        if not self.api_key:
            raise HeliusAPIError("No Helius API key found.")
        self._session = requests.Session()

    def _rpc_call(self, method: str, params: Any) -> Any:
        url = f"{config.HELIUS_RPC_BASE}/?api-key={self.api_key}"
        body = {
            "jsonrpc": "2.0",
            "id": "conviction-score",
            "method": method,
            "params": params,
        }
        return self._post_with_retry(url, body)["result"]

    def _post_with_retry(self, url: str, body: dict) -> dict:
        last_error: Optional[Exception] = None
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = self._session.post(url, json=body, timeout=config.REQUEST_TIMEOUT_SECONDS)
                if resp.status_code == 429:
                    self._sleep_backoff(attempt)
                    continue
                resp.raise_for_status()
                payload = resp.json()
                if "error" in payload:
                    raise HeliusAPIError(str(payload["error"]))
                return payload
            except (requests.RequestException, HeliusAPIError) as exc:
                last_error = exc
                self._sleep_backoff(attempt)
        raise HeliusAPIError(f"Request failed: {last_error}")

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        time.sleep(config.RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt))

    # -- public methods --------------------------------------------------

    def get_token_metadata(self, mint: str, use_cache: bool = True) -> TokenMetadata:
        cache_key = f"metadata_{mint}"
        if use_cache:
            cached = _read_cache(cache_key)
            if cached is not None:
                return TokenMetadata(**cached)

        result = self._rpc_call("getAsset", {"id": mint})
        token_info = result.get("token_info", {}) or {}
        content = result.get("content", {}) or {}
        metadata_block = content.get("metadata", {}) or {}

        meta = TokenMetadata(
            mint=mint,
            name=metadata_block.get("name") or result.get("name", "UNKNOWN"),
            symbol=metadata_block.get("symbol") or result.get("symbol", "UNKNOWN"),
            decimals=token_info.get("decimals", 0),
            total_supply_raw=int(token_info.get("supply", 0)),
        )

        _write_cache(cache_key, meta.__dict__)
        return meta

    def get_token_holders(self, mint: str, use_cache: bool = True) -> list[TokenAccountHolder]:
        cache_key = f"holders_{mint}"
        if use_cache:
            cached = _read_cache(cache_key)
            if cached is not None:
                return [TokenAccountHolder(**h) for h in cached]

        holders: list[TokenAccountHolder] = []
        cursor: Optional[str] = None

        while True:
            params: dict[str, Any] = {
                "mint": mint,
                "limit": config.PAGE_SIZE,
                "options": {"showZeroBalance": False},
            }
            if cursor:
                params["cursor"] = cursor

            result = self._rpc_call("getTokenAccounts", params)
            accounts = result.get("token_accounts", [])
            decimals = result.get("decimals")

            for acct in accounts:
                holders.append(
                    TokenAccountHolder(
                        owner=acct["owner"],
                        token_account=acct["address"],
                        balance_raw=int(acct["amount"]),
                        decimals=decimals if decimals is not None else 0,
                    )
                )

            cursor = result.get("cursor")
            if not cursor or not accounts:
                break

        _write_cache(cache_key, [h.__dict__ for h in holders])
        return holders

    def get_wallet_transfers(self, wallet: str, mint: str, use_cache: bool = True) -> list[TransferEvent]:
        """FAST-TRACK METHOD: Instead of querying thousands of transactions per wallet,

        we load a single master transaction stream for the token mint itself, parse it once,
        and cache the sliced results per wallet to keep the calculation pipeline untouched.
        """
        # 1. If individual wallet cache hits, return immediately
        cache_key = f"transfers_{wallet}_{mint}"
        if use_cache:
            cached = _read_cache(cache_key)
            if cached is not None:
                return [TransferEvent(**t) for t in cached]

        # 2. Check if we already fetched the master token transaction log during this runtime
        master_cache_key = f"master_token_stream_{mint}"
        master_stream = _read_cache(master_cache_key)

        if master_stream is None:
            # We haven't fetched the token transactions yet—let's do it ONCE right now.
            master_stream = []
            before: Optional[str] = None
            
            # Fetch up to 150 total recent token actions (3 clean batch requests)
            for _ in range(3):
                opts: dict[str, Any] = {"limit": 50}
                if before:
                    opts["before"] = before
                
                res = self._rpc_call("getSignaturesForAddress", [mint, opts])
                if not res:
                    break
                
                for sig_info in res:
                    sig = sig_info["signature"]
                    block_time = sig_info.get("blockTime", 0)
                    
                    try:
                        tx = self._rpc_call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
                        if not tx or "meta" not in tx:
                            continue
                        
                        pre_balances = {b["accountIndex"]: b for b in tx["meta"].get("preTokenBalances", []) if b.get("mint") == mint}
                        post_balances = {b["accountIndex"]: b for b in tx["meta"].get("postTokenBalances", []) if b.get("mint") == mint}
                        
                        for idx, post in post_balances.items():
                            pre = pre_balances.get(idx, {})
                            pre_amt = int(pre.get("uiTokenAmount", {}).get("amount", 0) or 0)
                            post_amt = int(post.get("uiTokenAmount", {}).get("amount", 0) or 0)
                            diff = post_amt - pre_amt
                            
                            if diff > 0: # Accumulation track
                                master_stream.append({
                                    "signature": sig,
                                    "timestamp": int(block_time),
                                    "from_address": None,
                                    "to_address": post.get("owner"),
                                    "amount_raw": abs(diff),
                                    "decimals": int(post.get("uiTokenAmount", {}).get("decimals", 0))
                                })
                    except Exception:
                        continue
                
                if len(res) < 50:
                    break
                before = res[-1]["signature"]
            
            # Cache this master token history stream for 5 minutes
            _write_cache(master_cache_key, master_stream)

        # 3. Slice out only the transactions that belong to this specific wallet from our master list
        wallet_events = [TransferEvent(**t) for t in master_stream if t["to_address"] == wallet]
        wallet_events.sort(key=lambda t: t.timestamp)
        
        # Write individual wallet cache so your calculation step reads cleanly
        _write_cache(cache_key, [w.__dict__ for w in wallet_events])
        return wallet_events
