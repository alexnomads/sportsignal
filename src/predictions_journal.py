"""
predictions_journal.py — Paper trading log for geopolitical predictions.

Manages a journal of user predictions on Polymarket markets, tracking:
- Manual prediction entries (YES/NO, entry price, notes)
- Live price tracking (winning/losing vs entry)
- Auto-resolution detection (won/lost when market closes)
- Performance statistics

Prediction entry format:
{
  "id": "<market_slug>_<timestamp>",
  "market_question": "Will Russia enter Ternuvate by March 31?",
  "market_url": "https://polymarket.com/market/...",
  "condition_id": "will-russia-enter-ternuvate...",
  "direction": "YES",          # User's prediction
  "entry_price": 0.15,         # Price when prediction was made
  "entry_probability": 15,     # Entry probability % (display value)
  "instruments": ["UNG"],      # Related trading instruments
  "notes": "Putin signaled willingness...",
  "created_at": "2026-04-12T09:50:44",
  "last_updated": "2026-04-12T10:50:44",
  "current_price": null,        # Live Polymarket price
  "price_change_pct": null,     # % move from entry
  "status": "active",           # active | resolved
  "outcome": null,             # won | lost (set when resolved)
  "exit_price": null,          # Final settlement price
  "resolved_at": null           # When market closed
}
"""

import json
import re
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

JOURNAL_FILE = Path(__file__).parent.parent / "data" / "predictions_journal.json"
MAX_ENTRIES = 500


# ── URL Helpers ────────────────────────────────────────────────────────────────

def _slug_from_url(url: str) -> str:
    """Extract market slug from Polymarket URL."""
    if not url:
        return ""
    # Handle: https://polymarket.com/market/will-x-happen
    # Handle: polymarket.com/market/will-x-happen
    match = re.search(r'(?:polymarket\.com/[^/]+/)([^/?]+)', url)
    if match:
        return match.group(1)
    # Fallback: just clean the URL
    return url.strip().replace("https://", "").replace("http://", "").replace("polymarket.com/market/", "").split("?")[0].split("#")[0]


def _make_id(market_url: str, created_at: str) -> str:
    """Create unique ID for a prediction."""
    slug = _slug_from_url(market_url)
    ts = created_at.replace(":", "").replace("-", "").replace(".", "")[:14]
    return f"pred_{hashlib.md5(f'{slug}_{ts}'.encode()).hexdigest()[:16]}"


# ── Polymarket Price Fetcher ──────────────────────────────────────────────────

def _fetch_polymarket_price(condition_id: str = None, market_url: str = None) -> Optional[float]:
    """
    Fetch current YES price from Polymarket.
    Tries condition_id first, then parses from market URL.
    Returns price as float (0.0-1.0) or None if fails.
    """
    url = None
    if condition_id and not condition_id.startswith("will-"):
        # Try gamma API with condition_id
        try:
            api_url = f"https://gamma-api.polymarket.com/markets"
            params = {"conditionId": condition_id}
            r = requests.get(api_url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    market = data[0]
                    prices = market.get("outcomePrices", [])
                    if prices:
                        return float(prices[0])
        except:
            pass
    
    # Build URL from condition_id or use provided URL
    if condition_id and condition_id.startswith("will-"):
        url = f"https://polymarket.com/market/{condition_id}"
    elif market_url:
        url = market_url
    else:
        return None
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        
        html = r.text
        
        # Extract from __NEXT_DATA__
        match = re.search(r'"outcomePrices":\s*\["([^"]+)","([^"]+)"', html)
        if match:
            return float(match.group(1))
        
        # Fallback: try embedded JSON
        match2 = re.search(r'"yesPrice"\s*:\s*"([^"]+)"', html)
        if match2:
            return float(match2.group(1))
        
        return None
    except:
        return None


def _check_market_resolution(condition_id: str = None, market_url: str = None) -> dict:
    """
    Check if a Polymarket market is resolved.
    Returns dict with:
    - is_closed: bool
    - final_price: float or None
    - winner: "YES" | "NO" | None
    - resolved_url: str
    """
    result = {
        "is_closed": False,
        "final_price": None,
        "winner": None,
        "resolved_url": "",
    }
    
    url = None
    if condition_id and condition_id.startswith("will-"):
        url = f"https://polymarket.com/market/{condition_id}"
    elif market_url:
        url = market_url
    
    if not url:
        return result
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return result
        
        html = r.text
        
        # Check for closed/resolved indicators
        is_closed = False
        if '"closed":true' in html or '"active":false' in html:
            is_closed = True
        if 'resolution' in html.lower() and 'resolved' in html.lower():
            is_closed = True
        
        # Check end date
        end_match = re.search(r'"endDate"\s*:\s*"([^"]+)"', html)
        if end_match:
            try:
                end_date = datetime.fromisoformat(end_match.group(1).replace("Z", "+00:00"))
                if end_date.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    is_closed = True
            except:
                pass
        
        result["is_closed"] = is_closed
        result["resolved_url"] = url
        
        # Get final price
        match = re.search(r'"outcomePrices"\s*:\s*\["([^"]+)","([^"]+)"', html)
        if match:
            yes_price = float(match.group(1))
            result["final_price"] = yes_price
            result["winner"] = "YES" if yes_price >= 0.5 else "NO"
        
        return result
        
    except Exception as e:
        return result


# ── Core Journal Functions ────────────────────────────────────────────────────

def load_journal() -> list[dict]:
    """Load all predictions from disk."""
    if not JOURNAL_FILE.exists():
        return []
    try:
        with open(JOURNAL_FILE) as f:
            data = json.load(f)
        return data.get("predictions", [])
    except Exception:
        return []


def _save_journal(predictions: list[dict]) -> None:
    """Save predictions to disk."""
    JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL_FILE, "w") as f:
        json.dump({
            "predictions": predictions,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)


def add_prediction(
    market_question: str,
    market_url: str,
    direction: str,
    entry_price: float,
    notes: str = "",
    instruments: list = None,
    condition_id: str = None,
    bet_amount: float = None,
) -> dict:
    """
    Add a new prediction to the journal.
    
    Args:
        market_question: The market question text
        market_url: Full Polymarket URL
        direction: "YES" or "NO"
        entry_price: Probability when prediction was made (0.0-1.0)
        notes: Optional notes
        instruments: Optional list of related trading instruments
        condition_id: Optional condition ID from Polymarket
        bet_amount: Optional USD amount bet on this prediction
    
    Returns:
        The created prediction dict
    """
    predictions = load_journal()
    now = datetime.now(timezone.utc).isoformat()
    
    pred = {
        "id": _make_id(market_url, now),
        "market_question": market_question,
        "market_url": market_url,
        "condition_id": condition_id or _slug_from_url(market_url),
        "direction": direction.upper(),
        "entry_price": float(entry_price),
        "entry_probability": round(float(entry_price) * 100, 1),
        "instruments": instruments or [],
        "notes": notes,
        "bet_amount": bet_amount,
        "created_at": now,
        "last_updated": now,
        "current_price": None,
        "price_change_pct": None,
        "status": "active",
        "outcome": None,
        "exit_price": None,
        "resolved_at": None,
    }
    
    predictions.append(pred)
    predictions = predictions[-MAX_ENTRIES:]
    _save_journal(predictions)
    
    return pred


def get_prediction_status(pred: dict) -> dict:
    """
    Get current status of a prediction.
    Fetches live price, checks resolution, evaluates outcome.
    
    Returns:
        Updated prediction dict
    """
    now = datetime.now(timezone.utc).isoformat()
    updated = pred.copy()
    
    # Skip if already resolved
    if pred.get("status") == "resolved":
        return updated
    
    # Check market resolution first
    resolution = _check_market_resolution(
        pred.get("condition_id"),
        pred.get("market_url")
    )
    
    if resolution["is_closed"] and resolution["final_price"] is not None:
        # Market closed - determine outcome
        final_price = resolution["final_price"]
        direction = pred.get("direction", "YES")
        
        # For YES: win if final >= 0.5, lose if final < 0.5
        # For NO: win if final < 0.5, lose if final >= 0.5
        if direction == "YES":
            outcome = "won" if final_price >= 0.5 else "lost"
        else:
            outcome = "won" if final_price < 0.5 else "lost"
        
        updated["status"] = "resolved"
        updated["outcome"] = outcome
        updated["exit_price"] = final_price
        updated["resolved_at"] = now
        updated["current_price"] = final_price
        updated["last_updated"] = now
        
        return updated
    
    # Market still open - fetch live price
    current_price = _fetch_polymarket_price(
        pred.get("condition_id"),
        pred.get("market_url")
    )
    
    if current_price is not None:
        updated["current_price"] = current_price
        
        # Calculate % change
        entry = pred.get("entry_price", 0)
        if entry > 0:
            change_pct = ((current_price - entry) / entry) * 100
            updated["price_change_pct"] = round(change_pct, 2)
    
    updated["last_updated"] = now
    return updated


def refresh_all_predictions() -> dict:
    """
    Refresh all active predictions: fetch prices and check resolutions.
    Returns summary of changes.
    """
    predictions = load_journal()
    stats = {
        "total": len(predictions),
        "active": 0,
        "resolved": 0,
        "won": 0,
        "lost": 0,
        "winning": 0,   # Currently winning (active)
        "losing": 0,    # Currently losing (active)
        "pending": 0,   # No price data yet (active)
    }
    
    for i, pred in enumerate(predictions):
        updated = get_prediction_status(pred)
        predictions[i] = updated
        
        if updated["status"] == "resolved":
            stats["resolved"] += 1
            if updated["outcome"] == "won":
                stats["won"] += 1
            else:
                stats["lost"] += 1
        else:
            stats["active"] += 1
            # Determine current standing
            entry = updated.get("entry_price", 0)
            current = updated.get("current_price")
            
            if current is None:
                stats["pending"] += 1
            elif updated["direction"] == "YES":
                if current > entry:
                    stats["winning"] += 1
                else:
                    stats["losing"] += 1
            else:  # NO
                if current < entry:
                    stats["winning"] += 1
                else:
                    stats["losing"] += 1
    
    _save_journal(predictions)
    return stats


def get_active_predictions() -> list[dict]:
    """Get all active (non-resolved) predictions."""
    predictions = load_journal()
    return [p for p in predictions if p.get("status") != "resolved"]


def get_resolved_predictions() -> list[dict]:
    """Get all resolved predictions."""
    predictions = load_journal()
    return [p for p in predictions if p.get("status") == "resolved"]


def delete_prediction(pred_id: str) -> bool:
    """Delete a prediction by ID."""
    predictions = load_journal()
    original_len = len(predictions)
    predictions = [p for p in predictions if p.get("id") != pred_id]
    if len(predictions) < original_len:
        _save_journal(predictions)
        return True
    return False


def get_journal_stats() -> dict:
    """Get summary statistics for the journal."""
    predictions = load_journal()
    
    total = len(predictions)
    active = [p for p in predictions if p.get("status") != "resolved"]
    resolved = [p for p in predictions if p.get("status") == "resolved"]
    
    won = sum(1 for p in resolved if p.get("outcome") == "won")
    lost = sum(1 for p in resolved if p.get("outcome") == "lost")
    
    # Win rate
    win_rate = (won / len(resolved) * 100) if resolved else 0
    
    # Avg edge (entry vs resolution)
    edges = []
    for p in resolved:
        if p.get("entry_price") and p.get("exit_price") is not None:
            # Did it move in our favor?
            moved_favorably = (
                (p["direction"] == "YES" and p["exit_price"] >= p["entry_price"]) or
                (p["direction"] == "NO" and p["exit_price"] <= p["entry_price"])
            )
            if moved_favorably:
                edge = abs(p["exit_price"] - p["entry_price"]) / p["entry_price"] * 100
            else:
                edge = -abs(p["exit_price"] - p["entry_price"]) / p["entry_price"] * 100
            edges.append(edge)
    
    avg_edge = (sum(edges) / len(edges)) if edges else 0
    
    return {
        "total": total,
        "active": len(active),
        "resolved": len(resolved),
        "won": won,
        "lost": lost,
        "win_rate": round(win_rate, 1),
        "avg_edge": round(avg_edge, 1),
        "winning": sum(1 for p in active if p.get("current_price") and 
                      ((p["direction"] == "YES" and p["current_price"] > p["entry_price"]) or
                       (p["direction"] == "NO" and p["current_price"] < p["entry_price"]))),
        "losing": sum(1 for p in active if p.get("current_price") and
                     ((p["direction"] == "YES" and p["current_price"] < p["entry_price"]) or
                      (p["direction"] == "NO" and p["current_price"] > p["entry_price"]))),
    }


def export_journal_csv() -> str:
    """Export journal to CSV format."""
    predictions = load_journal()
    if not predictions:
        return ""
    
    headers = ["Question", "URL", "Direction", "Entry %", "Exit %", "Outcome", "Created", "Resolved"]
    rows = []
    
    for p in predictions:
        rows.append([
            p.get("market_question", ""),
            p.get("market_url", ""),
            p.get("direction", ""),
            f"{p.get('entry_probability', 0):.1f}",
            f"{p.get('exit_price', '') or ''}",
            p.get("outcome", p.get("status", "")),
            p.get("created_at", "")[:10],
            (p.get("resolved_at", "")[:10] if p.get("resolved_at") else ""),
        ])
    
    csv_lines = [",".join(f'"{h}"' for h in headers)]
    for row in rows:
        csv_lines.append(",".join(f'"{v}"' for v in row))
    
    return "\n".join(csv_lines)
