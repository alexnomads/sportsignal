"""
limitless_client.py — Limitless Exchange API client for SportSignal.

Base URL: https://api.limitless.exchange
Auth: HMAC-SHA256 for trading, public for market data.
"""

import os
import hmac
import hashlib
import base64
import time
import requests
from datetime import datetime, timezone
from typing import Optional

BASE_URL = "https://api.limitless.exchange"

# API credentials from environment variables
API_KEY = os.environ.get("LIMITLESS_API_KEY", "")
API_SECRET = os.environ.get("LIMITLESS_API_SECRET", "")


def _sign_request(method: str, path: str, body: str = "") -> dict:
    """Generate HMAC-SHA256 signature headers."""
    timestamp = datetime.now(timezone.utc).isoformat()
    message = f"{timestamp}\n{method}\n{path}\n{body}"
    
    signature = base64.b64encode(
        hmac.new(
            base64.b64decode(API_SECRET),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    
    return {
        "lmts-api-key": API_KEY,
        "lmts-timestamp": timestamp,
        "lmts-signature": signature,
    }


def _get(path: str, params: dict = None, auth: bool = False) -> dict:
    """Make GET request with optional HMAC auth."""
    url = f"{BASE_URL}{path}"
    headers = {}
    
    if auth:
        sig_headers = _sign_request("GET", path)
        headers.update(sig_headers)
    
    r = requests.get(url, params=params, headers=headers, timeout=10)
    
    # Rate limit handling
    if r.status_code == 429:
        time.sleep(0.5)
        return _get(path, params, auth)
    
    if r.status_code != 200:
        raise Exception(f"API error {r.status_code}: {r.text}")
    
    return r.json()


def _post(path: str, body: dict = None, auth: bool = True) -> dict:
    """Make POST request with HMAC auth."""
    url = f"{BASE_URL}{path}"
    json_body = body or {}
    body_str = ""
    
    if json_body:
        import json
        body_str = json.dumps(json_body)
    
    sig_headers = _sign_request("POST", path, body_str)
    headers = {
        "Content-Type": "application/json",
        **sig_headers
    }
    
    r = requests.post(url, data=body_str, headers=headers, timeout=10)
    
    if r.status_code == 429:
        time.sleep(0.5)
        return _post(path, body, auth)
    
    if r.status_code not in (200, 201):
        raise Exception(f"API error {r.status_code}: {r.text}")
    
    return r.json()


# ── Public Market Endpoints ──────────────────────────────────────────────────

def get_active_markets(
    limit: int = 50,
    page: int = 1,
    sort_by: str = "high_value",
    trade_type: str = None,
    automation_type: str = "sports",
    category_id: int = None,
    sport: str = None,  # "Football" or "Basketball"
) -> dict:
    """
    Browse active sports markets from Limitless.
    
    Args:
        limit: Items per page (max 100)
        page: Page number
        sort_by: "ending_soon", "high_value", "lp_rewards", "newest", "trending"
        trade_type: "amm", "clob", or None for all
        automation_type: "sports" for sports markets
        category_id: Filter by category ID
        sport: "Football" or "Basketball" filter via tags
    
    Returns:
        Dict with 'data' (list of markets) and 'totalMarketsCount'
    """
    params = {
        "limit": min(limit, 25),
        "page": page,
        "sortBy": sort_by,
        "automationType": automation_type,
    }
    
    if trade_type:
        params["tradeType"] = trade_type
    if category_id:
        params["categoryId"] = category_id
    
    data = _get("/markets/active", params=params, auth=False)
    
    # Filter by sport if specified
    if sport:
        filtered = [
            m for m in data.get("data", [])
            if sport.lower() in " ".join(m.get("tags", []) + m.get("categories", [])).lower()
        ]
        data["data"] = filtered
    
    return data


def get_market(slug_or_address: str) -> dict:
    """Get detailed info for a specific market."""
    return _get(f"/markets/{slug_or_address}", auth=False)


def search_markets(query: str, limit: int = 20) -> dict:
    """Search markets by keyword."""
    return _get("/markets/search", params={"q": query, "limit": limit}, auth=False)


def get_feed_events(slug: str, limit: int = 20) -> dict:
    """Get recent feed events (trades, activity) for a market."""
    return _get(f"/markets/{slug}/feed-events", params={"limit": limit}, auth=False)


def get_category_counts() -> dict:
    """Get market counts by category."""
    return _get("/markets/category-count", auth=False)


# ── Authenticated Endpoints ───────────────────────────────────────────────────

def get_portfolio_positions(account: str) -> dict:
    """Get public positions for any wallet address."""
    return _get(f"/portfolio/{account}/positions", auth=False)


def get_categories() -> dict:
    """Get navigation categories."""
    return _get("/navigation/categories", auth=False)


# ── Data Helpers ─────────────────────────────────────────────────────────────

def format_volume(volume_str: str) -> str:
    """Format volume from token decimals to human readable."""
    try:
        vol = int(volume_str) / 1e6  # USDC 6 decimals
        if vol >= 1_000_000:
            return f"${vol/1_000_000:.1f}M"
        elif vol >= 1_000:
            return f"${vol/1_000:.1f}K"
        else:
            return f"${vol:.2f}"
    except:
        return "$0"


def parse_price(prices: list) -> dict:
    """Parse prices array [yes%, no%] into dict."""
    try:
        return {
            "yes": round(float(prices[0]) * 100, 1) if len(prices) > 0 else 50,
            "no": round(float(prices[1]) * 100, 1) if len(prices) > 1 else 50,
        }
    except:
        return {"yes": 50, "no": 50}


def get_sport_tag(market: dict) -> str:
    """Extract sport tag from market tags/categories."""
    tags = market.get("tags", []) + market.get("categories", [])
    for tag in tags:
        t = tag.lower()
        if t in ("football", "basketball", "nba", "epl", "premier league", "la liga", "serie a", "bundesliga", "ligue 1"):
            return "Football" if "football" in t or "liga" in t or "serie" in t or "bundes" in t or "ligue" in t or "premier" in t or "epl" in t else "Basketball"
    return "Other"
