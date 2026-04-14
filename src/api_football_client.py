"""
api_football_client.py — API-Football integration for SportSignal.

API: https://v3.football.api-sports.io
Key: b6a69d2b007e40020c7b260c437256ed
Free tier: 100 calls/day

Key data:
- Live fixtures (today's matches)
- Injuries (affects YES/NO odds)
- AI predictions (win probabilities)
- H2H (head-to-head)
"""

import requests
import time
from datetime import datetime, timezone
from typing import Optional

API_KEY = "b6a69d2b007e40020c7b260c437256ed"
BASE_URL = "https://v3.football.api-sports.io"

# Rate limit: 100 calls/day
_calls_today = 0
_last_reset = None


def _rate_limit():
    """Track API calls (simple counter)."""
    global _calls_today, _last_reset
    today = datetime.now(timezone.utc).date()
    
    if _last_reset != today:
        _calls_today = 0
        _last_reset = today
    
    if _calls_today >= 95:  # Keep buffer
        return False
    _calls_today += 1
    return True


def _get(endpoint: str, params: dict = None) -> dict:
    """Make API call with rate limiting."""
    if not _rate_limit():
        return {"error": "Rate limit reached", "results": 0, "response": []}
    
    url = f"{BASE_URL}{endpoint}"
    headers = {"x-apisports-key": API_KEY}
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            return {"error": f"HTTP {r.status_code}", "results": 0, "response": []}
    except Exception as e:
        return {"error": str(e), "results": 0, "response": []}


# ── Live Fixtures ──────────────────────────────────────────────────────────────

def get_todays_fixtures(league_ids: list = None) -> list:
    """
    Get today's football fixtures.
    
    Args:
        league_ids: List of league IDs to filter (optional)
                   Champions League: 2, Premier League: 39, La Liga: 140,
                   Serie A: 135, Bundesliga: 78, Ligue 1: 61
    
    Returns:
        List of fixture dicts
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params = {"date": today}
    
    # Fetch all fixtures for the day (no league filter - it breaks date search)
    all_fixtures = _get("/fixtures", params).get("response", [])
    
    # Filter by league if requested
    if league_ids:
        league_ids_str = [str(l) for l in league_ids]
        all_fixtures = [
            f for f in all_fixtures
            if str(f.get("league", {}).get("id", "")) in league_ids_str
        ]
    
    return all_fixtures


def get_upcoming_fixtures(days: int = 3, league_ids: list = None) -> list:
    """
    Get fixtures for the next N days.
    """
    all_fixtures = []
    for day_offset in range(days):
        from datetime import timedelta
        date = (datetime.now(timezone.utc) + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        data = _get("/fixtures", {"date": date})
        all_fixtures.extend(data.get("response", []))
        time.sleep(0.3)
    
    # Filter by league if requested
    if league_ids:
        league_ids_str = [str(l) for l in league_ids]
        all_fixtures = [
            f for f in all_fixtures
            if str(f.get("league", {}).get("id", "")) in league_ids_str
        ]
    
    return all_fixtures


def get_live_fixture(fixture_id: int) -> dict:
    """Get detailed live fixture data."""
    data = _get(f"/fixtures", {"id": fixture_id})
    fixtures = data.get("response", [])
    return fixtures[0] if fixtures else {}


# ── Injuries ─────────────────────────────────────────────────────────────────

def get_injuries(date_from: str = None, date_to: str = None, league_id: int = None) -> list:
    """
    Get injury data for teams/leagues.
    
    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        league_id: Filter by league
    
    Returns:
        List of injury records
    """
    params = {}
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    if league_id:
        params["league"] = league_id
    
    data = _get("/injuries", params)
    return data.get("response", [])


def get_team_injuries(team_id: int) -> list:
    """Get injuries for a specific team."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    two_weeks = (datetime.now(timezone.utc).replace(day=datetime.now().day + 14) if datetime.now().day + 14 <= 28 else datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    
    data = _get("/injuries", {"team": team_id, "from": today, "to": "2026-05-01"})
    return data.get("response", [])


def get_match_injuries(home_team: str, away_team: str) -> dict:
    """
    Get injuries for a specific match.
    Returns impact assessment for each team.
    """
    injuries = get_injuries()
    
    home_injuries = []
    away_injuries = []
    
    for inj in injuries:
        player = inj.get("player", {})
        team = inj.get("team", {}).get("name", "").lower()
        reason = inj.get("reason", "")
        date = inj.get("date", "")
        
        player_info = {
            "name": player.get("name", "Unknown"),
            "position": player.get("position", "Unknown"),
            "reason": reason,
            "date": date,
        }
        
        # Simple team matching
        home_lower = home_team.lower()
        away_lower = away_team.lower()
        
        if any(t in team for t in home_lower.split()):
            home_injuries.append(player_info)
        if any(t in team for t in away_lower.split()):
            away_injuries.append(player_info)
    
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_injuries": home_injuries,
        "away_injuries": away_injuries,
        "home_count": len(home_injuries),
        "away_count": len(away_injuries),
        "impact": _calc_injury_impact(home_injuries, away_injuries),
    }


def _calc_injury_impact(home: list, away: list) -> str:
    """Calculate injury impact on match."""
    # Count key positions lost
    key_positions = ["Goalkeeper", "Defender", "Midfielder", "Forward"]
    
    home_score = sum(1 for p in home if any(p["position"] in k for k in key_positions))
    away_score = sum(1 for p in away if any(p["position"] in k for k in key_positions))
    
    if home_score > away_score + 1:
        return "AWAY_BIAS"  # More home injuries
    elif away_score > home_score + 1:
        return "HOME_BIAS"   # More away injuries
    elif home_score > 2 or away_score > 2:
        return "HIGH_INJURY"  # High injuries overall
    else:
        return "BALANCED"


# ── Predictions ──────────────────────────────────────────────────────────────

def get_predictions(fixture_id: int) -> dict:
    """
    Get AI predictions for a fixture.
    Includes win/draw/loss probabilities, correct score, goals.
    """
    data = _get("/predictions", {"fixture": fixture_id})
    predictions = data.get("response", [])
    return predictions[0] if predictions else {}


def get_match_prediction(home_team: str, away_team: str) -> dict:
    """
    Get prediction for a match by team names.
    Searches today's fixtures for matching teams.
    """
    fixtures = get_todays_fixtures()
    
    for fix in fixtures:
        teams = fix.get("teams", {})
        home = teams.get("home", {}).get("name", "").lower()
        away = teams.get("away", {}).get("name", "").lower()
        
        if home_team.lower() in home or home in home_team.lower():
            if away_team.lower() in away or away in away_team.lower():
                fid = fix.get("fixture", {}).get("id")
                return {
                    "fixture_id": fid,
                    "home_team": teams.get("home", {}).get("name"),
                    "away_team": teams.get("away", {}).get("name"),
                    "predictions": get_predictions(fid),
                }
    
    return {}


# ── Head to Head ────────────────────────────────────────────────────────────

def get_h2h(home_team: str, away_team: str, limit: int = 10) -> dict:
    """
    Get head-to-head history between two teams.
    """
    data = _get("/fixtures/headtohead", {
        "h2h": f"{home_team}-{away_team}",
        "last": limit,
    })
    return data.get("response", [])


# ── Standings / Form ─────────────────────────────────────────────────────────

def get_league_standings(league_id: int, season: int = 2025) -> list:
    """Get league standings."""
    data = _get("/standings", {"league": league_id, "season": season})
    
    standings = data.get("response", [])
    if standings and len(standings) > 0:
        return standings[0].get("league", {}).get("standings", [])
    return []


def get_team_form(team_name: str, league_id: int = None) -> dict:
    """
    Get recent form for a team.
    Returns W/D/L streak and recent results.
    """
    params = {"team": team_name, "last": 5}
    if league_id:
        params["league"] = league_id
    
    data = _get("/fixtures", params)
    fixtures = data.get("response", [])
    
    results = []
    for fix in fixtures:
        teams = fix.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        goals = fix.get("goals", {})
        
        # Determine if our team won/drew/lost
        is_home = team_name.lower() in home.get("name", "").lower()
        
        team_goals = goals.get("home") if is_home else goals.get("away")
        opp_goals = goals.get("away") if is_home else goals.get("home")
        
        if team_goals is None or opp_goals is None:
            continue
            
        if team_goals > opp_goals:
            result = "W"
        elif team_goals < opp_goals:
            result = "L"
        else:
            result = "D"
        
        opp = away.get("name") if is_home else home.get("name")
        results.append({
            "result": result,
            "score": f"{team_goals}-{opp_goals}",
            "opponent": opp,
            "home": is_home,
        })
    
    # Calculate form
    form_str = "".join([r["result"] for r in results])
    wins = form_str.count("W")
    draws = form_str.count("D")
    losses = form_str.count("L")
    
    return {
        "team": team_name,
        "recent": results,
        "form": form_str,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "form_score": wins * 3 + draws,
    }


# ── Cached Results ────────────────────────────────────────────────────────────

# Simple in-memory cache
_cache = {}
_cache_expiry = {}


def get_cached(key: str, max_age_seconds: int = 3600) -> Optional[dict]:
    """Get cached result if still fresh."""
    if key in _cache:
        if key in _cache_expiry:
            if datetime.now(timezone.utc).timestamp() < _cache_expiry[key]:
                return _cache[key]
    return None


def set_cached(key: str, value: dict, max_age_seconds: int = 3600):
    """Cache a result."""
    _cache[key] = value
    _cache_expiry[key] = datetime.now(timezone.utc).timestamp() + max_age_seconds
