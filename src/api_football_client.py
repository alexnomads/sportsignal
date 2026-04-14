"""
api_football_client.py — Enhanced API-Football integration for SportSignal.

API: https://v3.football.api-sports.io
Key: b6a69d2b007e40020c7b260c437256ed
Free tier: 100 calls/day

Data points:
- Fixtures (live + upcoming)
- Injuries (team-level impact)
- AI Predictions (win probability, correct score, advice)
- Head-to-head (H2H history, avg goals, BTTS rate)
- Team form (WDL streak, points, home/away split)
- Match statistics (xG, shots, corners, cards)
- Player goals/assists (for player-specific markets)
- League standings (form table)
"""

import requests
import time
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("API_FOOTBALL_KEY", "b6a69d2b007e40020c7b260c437256ed")
BASE_URL = "https://v3.football.api-sports.io"

# Rate limit: 100 calls/day
_calls_today = 0
_last_reset = None

# Key league IDs
LEAGUE_IDS = {
    "ucl": 2,          # UEFA Champions League
    "epl": 39,         # Premier League
    "laliga": 140,     # La Liga
    "seriea": 135,     # Serie A
    "bundesliga": 78,  # Bundesliga
    "ligue1": 61,      # Ligue 1
}

# Team name aliases (common variations)
TEAM_ALIASES = {
    "manchester city": ["man city", "mancity", "manchester city fc", "manchestercity"],
    "manchester united": ["man utd", "manchester utd", "mu", "manchesterunited"],
    "liverpool": ["liverpool fc", "lfc", "liverpoolfootballclub"],
    "arsenal": ["arsenal fc", "afc", "arsenalfc"],
    "chelsea": ["chelsea fc", "cfc", "chelseafc"],
    "tottenham": ["tottenham hotspur", "spurs", "tottenhamhotspur", "thfc"],
    "real madrid": ["realmadrid", "real", "real madrid cf", "realmadridcf"],
    "barcelona": ["fc barcelona", "barca", "fcbarcelona", "barcelonafc"],
    "bayern": ["bayern munchen", "bayern munich", "fc bayern", "bayern munchen", "bayernmunchen"],
    "psg": ["paris saint germain", "parissaintgermain", "paris sg", "psgparissg"],
    "inter": ["inter milan", "fc inter", "intermilano"],
    "milan": ["ac milan", "acmilan", "milan fc"],
    "juventus": ["juve", "juventusfc"],
    "atletico": ["atletico madrid", "atletico madrid", "atleticomadrid"],
    "dortmund": ["borussia dortmund", "bvb", "borussiadortmund"],
    "sevilla": ["sevilla fc", "sevillafc"],
    "benfica": ["sl benfica", "s.l. benfica", "benfica lisbon"],
    "porto": ["fc porto", "fcp", "fcpinto"],
}

# Team name normalizer
def normalize_team_name(name: str) -> str:
    """Normalize team name to canonical form."""
    name_lower = name.lower().strip()
    
    # Check aliases
    for canonical, aliases in TEAM_ALIASES.items():
        if name_lower == canonical or name_lower in aliases:
            return canonical
    
    # Remove common suffixes
    name_lower = re.sub(r'\s*(fc|sc|f.c.|s.c.|ac|afc|lfc|cfc|thfc|cfc|afc|mcfc|efc)\s*$', '', name_lower, flags=re.IGNORECASE)
    return name_lower.strip()


def _rate_limit():
    """Track API calls (simple counter)."""
    global _calls_today, _last_reset
    today = datetime.now(timezone.utc).date()
    
    if _last_reset != today:
        _calls_today = 0
        _last_reset = today
    
    if _calls_today >= 90:
        logger.warning(f"API-Football rate limit near: {_calls_today}/100 calls used")
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
            logger.warning(f"API-FB HTTP {r.status_code}: {endpoint}")
            return {"error": f"HTTP {r.status_code}", "results": 0, "response": []}
    except Exception as e:
        logger.warning(f"API-FB error: {e}")
        return {"error": str(e), "results": 0, "response": []}


# ── Caching ───────────────────────────────────────────────────────────────────

_cache = {}
_cache_expiry = {}


def get_cached(key: str, max_age_seconds: int = 3600) -> Optional[dict]:
    if key in _cache and key in _cache_expiry:
        if datetime.now(timezone.utc).timestamp() < _cache_expiry[key]:
            return _cache[key]
    return None


def set_cached(key: str, value: dict, max_age_seconds: int = 3600):
    _cache[key] = value
    _cache_expiry[key] = datetime.now(timezone.utc).timestamp() + max_age_seconds


def with_cache(fn):
    """Decorator to cache API results."""
    def wrapper(*args, **kwargs):
        cache_key = f"{fn.__name__}:{':'.join(str(a) for a in args)}:{':'.join(f'{k}={v}' for k,v in sorted(kwargs.items()))}"
        cached = get_cached(cache_key)
        if cached is not None:
            return cached
        result = fn(*args, **kwargs)
        if result:
            set_cached(cache_key, result)
        return result
    return wrapper


# ── Fixtures ─────────────────────────────────────────────────────────────────

def get_todays_fixtures(league_ids: list = None) -> list:
    """Get today's football fixtures across key leagues."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params = {"date": today}
    all_fixtures = _get("/fixtures", params).get("response", [])
    
    if league_ids:
        all_fixtures = [f for f in all_fixtures
                        if str(f.get("league", {}).get("id", "")) in [str(l) for l in league_ids]]
    return all_fixtures


def get_fixtures_for_date_range(days: int = 3) -> list:
    """Get fixtures for next N days."""
    all_fixtures = []
    for day_offset in range(days):
        date = (datetime.now(timezone.utc) + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        data = _get("/fixtures", {"date": date})
        all_fixtures.extend(data.get("response", []))
        time.sleep(0.3)
    return all_fixtures


def find_fixture(home_team: str, away_team: str, fixtures: list = None) -> Optional[dict]:
    """
    Smart fixture matching by team names.
    Handles partial names, aliases, and variations.
    Returns the best matching fixture.
    """
    if fixtures is None:
        fixtures = get_todays_fixtures()
    
    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)
    
    best_match = None
    best_score = 0
    
    for fix in fixtures:
        teams = fix.get("teams", {})
        fix_home = teams.get("home", {}).get("name", "")
        fix_away = teams.get("away", {}).get("name", "")
        
        fix_home_norm = normalize_team_name(fix_home)
        fix_away_norm = normalize_team_name(fix_away)
        
        home_score = _team_match_score(home_norm, fix_home_norm) + _team_match_score(away_norm, fix_away_norm)
        away_score = _team_match_score(home_norm, fix_away_norm) + _team_match_score(away_norm, fix_home_norm)
        
        # Prefer home-away order match
        if home_score >= best_score:
            best_score = home_score
            best_match = fix
        
        # Also check reversed
        if away_score > best_score:
            best_score = away_score
            best_match = fix
    
    # Only return if match is good enough
    if best_score >= 1.5:  # At least one team matches well
        return best_match
    return None


def _team_match_score(name1: str, name2: str) -> float:
    """Score how well two team names match (0-2)."""
    if not name1 or not name2:
        return 0.0
    
    n1, n2 = name1.lower().strip(), name2.lower().strip()
    
    # Exact match
    if n1 == n2:
        return 2.0
    
    # One contains the other (with len threshold)
    if len(n1) >= 4 and n1 in n2:
        return 1.8
    if len(n2) >= 4 and n2 in n1:
        return 1.8
    
    # Check via aliases
    for canonical, aliases in TEAM_ALIASES.items():
        in_aliases1 = n1 in aliases
        in_aliases2 = n2 in aliases
        if (n1 == canonical or in_aliases1) and (n2 == canonical or in_aliases2):
            return 2.0
        if in_aliases1 and (n2 == canonical or in_aliases2):
            return 1.8
        if in_aliases2 and (n1 == canonical or in_aliases1):
            return 1.8
    
    # Word overlap
    words1 = set(n1.split())
    words2 = set(n2.split())
    common = words1 & words2
    if common and len(common) >= 1:
        # Bonus for city/club name matches
        if len(common) >= 2:
            return 1.5
        return 0.8
    
    return 0.0


def extract_teams_from_market_title(title: str) -> tuple:
    """
    Extract team names from a market title.
    Handles formats like:
    - "Bayern München vs Real Madrid"
    - "Liverpool vs PSG — Over 2.5 goals"
    - "Barcelona vs Atletico Madrid: Both teams to score?"
    Returns (home, away) or (None, None)
    """
    # Normalize
    title = title.replace("–", "-").replace("—", "-").replace(":", "-")
    
    # Try " vs " pattern
    if " vs " in title:
        parts = title.split(" vs ")
        home = parts[0].strip()
        away = parts[1].split("-")[0].split("?")[0].split(",")[0].strip()
        return home, away
    
    # Try " - " pattern
    if " - " in title:
        parts = title.split(" - ")
        home = parts[0].strip()
        away = parts[1].split("-")[0].split("?")[0].split(",")[0].strip()
        return home, away
    
    return None, None


def extract_player_from_title(title: str) -> Optional[str]:
    """Extract player name from a market title (for scorer/assist markets)."""
    title_lower = title.lower()
    
    # Patterns for player markets
    patterns = [
        r"(?:to\s+score|sets?\s+the\s+first|sets?\s+a\s+brace|first\s+goalscorer|anytime\s+goalscorer)\s+(?:by\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:to\s+score|scores?|gets?\s+a\s+goal)",
        r"hat-trick\s+(?:by\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"most\s+assists?\s+(?:by\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


# ── Head to Head ──────────────────────────────────────────────────────────────

def get_h2h_enhanced(home_team: str, away_team: str, limit: int = 10) -> dict:
    """
    Get enhanced H2H data between two teams.
    Returns: avg goals, btts rate, home/away win rate, recent results.
    """
    # First try to find fixture for proper H2H
    fixture = find_fixture(home_team, away_team)
    
    results = []
    if fixture:
        fix_id = fixture.get("fixture", {}).get("id")
        # Get H2H for this fixture
        data = _get("/fixtures/headtohead", {
            "h2h": f"{fixture.get('teams',{}).get('home',{}).get('id','')}-{fixture.get('teams',{}).get('away',{}).get('id','')}",
            "last": limit,
        })
        results = data.get("response", [])
    else:
        # Fallback: search by team names
        data = _get("/fixtures/headtohead", {
            "h2h": f"{home_team}-{away_team}",
            "last": limit,
        })
        results = data.get("response", [])
        time.sleep(0.3)
    
    if not results:
        return {}
    
    # Analyze H2H
    total_goals = 0
    btts_count = 0
    home_wins, away_wins, draws = 0, 0, 0
    recent = []
    
    for fix in results[:10]:
        goals = fix.get("goals", {})
        teams = fix.get("teams", {})
        
        home_goals = goals.get("home") or 0
        away_goals = goals.get("away") or 0
        total_goals += home_goals + away_goals
        
        if home_goals > 0 and away_goals > 0:
            btts_count += 1
        
        if home_goals > away_goals:
            home_wins += 1
        elif away_goals > home_goals:
            away_wins += 1
        else:
            draws += 1
        
        recent.append({
            "home": teams.get("home", {}).get("name"),
            "away": teams.get("away", {}).get("name"),
            "score": f"{home_goals}-{away_goals}",
            "home_win": home_goals > away_goals,
        })
    
    n = len(results) or 1
    
    return {
        "matches": n,
        "avg_goals": round(total_goals / n, 2),
        "btts_rate": round(btts_count / n * 100, 1),
        "home_win_rate": round(home_wins / n * 100, 1),
        "away_win_rate": round(away_wins / n * 100, 1),
        "draw_rate": round(draws / n * 100, 1),
        "home_team": home_team,
        "away_team": away_team,
        "recent": recent,
    }


# ── AI Predictions ─────────────────────────────────────────────────────────────

def get_predictions_enhanced(fixture_id: int) -> dict:
    """
    Get enhanced predictions for a fixture.
    Win probabilities, correct score, total goals, advice.
    """
    data = _get("/predictions", {"fixture": fixture_id})
    preds = data.get("response", [])
    
    if not preds:
        return {}
    
    p = preds[0]
    league = p.get("league", {})
    teams = p.get("teams", {})
    comparison = p.get("comparison", {})
    predictions = p.get("predictions", {})
    advice = predictions.get("advice", "")
    winning_percent = predictions.get("winning_percent", {})
    
    # Win probabilities
    home_win_pct = 0.0
    draw_pct = 0.0
    away_win_pct = 0.0
    
    if winning_percent:
        home_data = winning_percent.get("home", {})
        draw_data = winning_percent.get("draws", {})
        away_data = winning_percent.get("away", {})
        
        def parse_pct(d):
            if isinstance(d, dict):
                v = d.get("percent", "0")
                if isinstance(v, str):
                    v = v.replace("%", "").strip()
                try:
                    return float(v)
                except:
                    return 0.0
            return 0.0
        
        home_win_pct = parse_pct(home_data)
        draw_pct = parse_pct(draw_data)
        away_win_pct = parse_pct(away_data)
    
    # Total goals prediction
    total_goals_pred = predictions.get("total", {})
    if isinstance(total_goals_pred, dict):
        goals_advice = total_goals_pred.get("advice", "")
        over_pct = total_goals_pred.get("over", {}).get("value", "")
        under_pct = total_goals_pred.get("under", {}).get("value", "")
    else:
        goals_advice = ""
        over_pct = ""
        under_pct = ""
    
    # Correct score
    correct_score = predictions.get("correct_score", "")
    winning_team = predictions.get("winner", {})
    if isinstance(winning_team, dict):
        winner_name = winning_team.get("name", "")
        winner_comment = winning_team.get("comment", "")
    else:
        winner_name = ""
        winner_comment = ""
    
    return {
        "fixture_id": fixture_id,
        "league": league.get("name", ""),
        "home_team": teams.get("home", {}).get("name", ""),
        "away_team": teams.get("away", {}).get("name", ""),
        "win_probs": {
            "home_win": home_win_pct,
            "draw": draw_pct,
            "away_win": away_win_pct,
        },
        "total_goals": {
            "advice": goals_advice,
            "over_pct": over_pct,
            "under_pct": under_pct,
        },
        "correct_score": correct_score,
        "winner": winner_name,
        "winner_comment": winner_comment,
        "advice": advice,
        "form": comparison,
    }


# ── Match Statistics ───────────────────────────────────────────────────────────

def get_match_stats(fixture_id: int) -> dict:
    """
    Get detailed match statistics (xG, shots, possession, corners, cards, etc.)
    For past fixtures or live matches.
    """
    data = _get("/fixtures", {"id": fixture_id})
    fixtures = data.get("response", [])
    
    if not fixtures:
        return {}
    
    fix = fixtures[0]
    stats_data = fix.get("statistics", [])
    
    if not stats_data:
        return {}
    
    # stats_data is a list with one item per team
    team_stats = {}
    for stat_set in stats_data:
        team_name = stat_set.get("team", {}).get("name", "")
        stats = {}
        for item in stat_set.get("statistics", []):
            stat_name = item.get("type", "").lower().replace(" ", "_")
            # Try to parse value
            val = item.get("value", "")
            if isinstance(val, str):
                if val in ["True", "False", None]:
                    val = 1 if val == "True" else 0
                else:
                    # Extract numbers
                    nums = re.findall(r"[\d.]+", str(val))
                    val = float(nums[0]) if nums else 0.0
            stats[stat_name] = val
        team_stats[team_name] = stats
    
    return team_stats


def get_recent_stats(team_name: str, last_n: int = 5) -> dict:
    """
    Get aggregated stats over last N matches for a team.
    Returns avg goals scored/conceded, avg shots, avg corners.
    """
    params = {"team": team_name, "last": last_n}
    data = _get("/fixtures", params)
    fixtures = data.get("response", [])
    
    if not fixtures:
        return {}
    
    total_goals_scored = 0
    total_goals_conceded = 0
    total_shots = 0
    total_shots_on_target = 0
    total_corners = 0
    total_yellows = 0
    total_reds = 0
    matches = 0
    
    for fix in fixtures:
        goals = fix.get("goals", {})
        is_home = team_name.lower() in fix.get("teams", {}).get("home", {}).get("name", "").lower()
        
        scored = goals.get("home") if is_home else goals.get("away")
        conceded = goals.get("away") if is_home else goals.get("home")
        
        if scored is not None:
            total_goals_scored += scored
            matches += 1
        if conceded is not None:
            total_goals_conceded += conceded
        
        # Try to get stats
        stats_list = fix.get("statistics", [])
        for stat_set in stats_list:
            stat_name = stat_set.get("team", {}).get("name", "").lower()
            if team_name.lower() in stat_name:
                for item in stat_set.get("statistics", []):
                    t = item.get("type", "").lower()
                    val = item.get("value", "")
                    if isinstance(val, str) and val not in ["True", "False", None, ""]:
                        nums = re.findall(r"[\d.]+", str(val))
                        v = float(nums[0]) if nums else 0.0
                    elif val == "True":
                        v = 1.0
                    else:
                        v = 0.0
                    
                    if "shot" in t and "on target" not in t:
                        total_shots += v
                    elif "shot" in t and "target" in t:
                        total_shots_on_target += v
                    elif "corner" in t:
                        total_corners += v
                    elif "yellow" in t:
                        total_yellows += v
                    elif "red" in t:
                        total_reds += v
    
    n = matches or 1
    return {
        "team": team_name,
        "matches": matches,
        "avg_goals_scored": round(total_goals_scored / n, 2),
        "avg_goals_conceded": round(total_goals_conceded / n, 2),
        "avg_shots": round(total_shots / n, 1),
        "avg_shots_on_target": round(total_shots_on_target / n, 1),
        "avg_corners": round(total_corners / n, 1),
        "avg_yellows": round(total_yellows / n, 1),
        "avg_reds": round(total_reds / n, 1),
    }


# ── Injuries ─────────────────────────────────────────────────────────────────

def get_match_injuries(home_team: str, away_team: str) -> dict:
    """
    Get injuries for both teams in a match.
    Returns impact score for each team.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    two_weeks = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")
    
    data = _get("/injuries", {"from": today, "to": two_weeks})
    injuries = data.get("response", [])
    
    home_injuries = []
    away_injuries = []
    
    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)
    
    for inj in injuries:
        team_name = inj.get("team", {}).get("name", "")
        team_norm = normalize_team_name(team_name)
        player = inj.get("player", {})
        
        if team_norm == home_norm or team_norm == away_norm:
            info = {
                "name": player.get("name", ""),
                "position": player.get("position", "Unknown"),
                "reason": inj.get("reason", ""),
                "date": inj.get("date", ""),
            }
            
            if team_norm == home_norm:
                home_injuries.append(info)
            else:
                away_injuries.append(info)
    
    # Calculate impact
    def calc_impact(injuries_list):
        """Score injury impact: 0 = none, 1 = minor, 2 = moderate, 3 = high"""
        if not injuries_list:
            return 0, "none", injuries_list
        
        key_count = sum(1 for i in injuries_list 
                       if i["position"] in ["Goalkeeper", "Defender", "Midfielder", "Forward"])
        if key_count >= 4:
            return 3, "high", injuries_list
        elif key_count >= 2:
            return 2, "moderate", injuries_list
        elif key_count >= 1:
            return 1, "minor", injuries_list
        return 0, "none", injuries_list
    
    home_impact, home_level, _ = calc_impact(home_injuries)
    away_impact, away_level, _ = calc_impact(away_injuries)
    
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_count": len(home_injuries),
        "away_count": len(away_injuries),
        "home_key_injuries": home_impact,
        "away_key_injuries": away_impact,
        "home_level": home_level,
        "away_level": away_level,
        "home_injuries": home_injuries[:5],
        "away_injuries": away_injuries[:5],
    }


# ── Team Form ─────────────────────────────────────────────────────────────────

def get_team_form_enhanced(team_name: str, league_id: int = None) -> dict:
    """
    Enhanced team form with home/away splits and form score.
    """
    params = {"team": team_name, "last": 10}
    if league_id:
        params["league"] = league_id
    
    data = _get("/fixtures", params)
    fixtures = data.get("response", [])
    
    home_results = []
    away_results = []
    
    for fix in fixtures:
        teams = fix.get("teams", {})
        goals = fix.get("goals", {})
        
        fix_home = teams.get("home", {}).get("name", "")
        is_home = normalize_team_name(team_name) == normalize_team_name(fix_home)
        
        home_goals = goals.get("home") or 0
        away_goals = goals.get("away") or 0
        
        if home_goals is None or away_goals is None:
            continue
        
        if home_goals > away_goals:
            result = "W"
        elif home_goals < away_goals:
            result = "L"
        else:
            result = "D"
        
        results_list = home_results if is_home else away_results
        results_list.append({
            "result": result,
            "score": f"{home_goals}-{away_goals}",
            "opponent": teams.get("away", {}).get("name") if is_home else teams.get("home", {}).get("name"),
            "home": is_home,
        })
    
    def calc_form(r_list):
        if not r_list:
            return {"form": "", "wins": 0, "draws": 0, "losses": 0, "form_score": 0, "points": 0}
        form_str = "".join(r["result"] for r in r_list)
        wins = form_str.count("W")
        draws = form_str.count("D")
        losses = form_str.count("L")
        return {
            "form": form_str,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "form_score": wins * 3 + draws,
            "points": wins * 3 + draws,
            "recent": r_list[:5],
        }
    
    home_form = calc_form(home_results)
    away_form = calc_form(away_results)
    all_form = calc_form(home_results + away_results)
    
    return {
        "team": team_name,
        "overall": all_form,
        "home": home_form,
        "away": away_form,
        "home_win_pct": round(home_form["wins"] / max(len(home_results), 1) * 100, 1),
        "away_win_pct": round(away_form["wins"] / max(len(away_results), 1) * 100, 1),
        "total_matches": len(home_results) + len(away_results),
    }


# ── Market Type Detection ─────────────────────────────────────────────────────

def detect_market_type(title: str) -> str:
    """Detect what type of market this is from the title."""
    title_lower = title.lower()
    
    if any(k in title_lower for k in ["over 2.5", "under 2.5", "total goals", "total score", "goals"]):
        return "total_goals"
    if any(k in title_lower for k in ["both teams", "btts", "each team", "to score"]):
        return "btts"
    if any(k in title_lower for k in ["clean sheet", "both teams to score", "shutout"]):
        return "clean_sheet"
    if any(k in title_lower for k in ["corner", "corners"]):
        return "corners"
    if any(k in title_lower for k in ["yellow", "red card", "cards", "booking"]):
        return "cards"
    if any(k in title_lower for k in ["score", "win", "winner", "qualify", "advance"]):
        return "match_result"
    if any(k in title_lower for k in ["first", "last", "scorer", "goalscorer", "brace", "hat-trick", "trick"]):
        return "scorer"
    if any(k in title_lower for k in ["assist", "most assist"]):
        return "assists"
    if any(k in title_lower for k in ["half", "1st half", "2nd half", "1h", "2h"]):
        return "half_result"
    
    return "general"


def get_market_relevant_data(home_team: str, away_team: str, market_type: str) -> dict:
    """
    Fetch all API-Football data relevant to a specific market type.
    Returns a consolidated dict optimized for the signal calculation.
    """
    result = {
        "home_team": home_team,
        "away_team": away_team,
        "market_type": market_type,
    }
    
    # H2H data (always useful)
    h2h = get_h2h_enhanced(home_team, away_team)
    if h2h:
        result["h2h"] = h2h
    
    # Team forms
    home_form = get_team_form_enhanced(home_team)
    away_form = get_team_form_enhanced(away_team)
    result["home_form"] = home_form
    result["away_form"] = away_form
    
    # Form comparison
    home_pts = home_form.get("overall", {}).get("points", 0)
    away_pts = away_form.get("overall", {}).get("points", 0)
    home_matches = home_form.get("overall", {}).get("wins", 0) + home_form.get("overall", {}).get("draws", 0) + home_form.get("overall", {}).get("losses", 0)
    away_matches = away_form.get("overall", {}).get("wins", 0) + away_form.get("overall", {}).get("draws", 0) + away_form.get("overall", {}).get("losses", 0)
    
    home_ppg = home_pts / max(home_matches, 1)
    away_ppg = away_pts / max(away_matches, 1)
    
    result["form_comparison"] = {
        "home_ppg": round(home_ppg, 2),
        "away_ppg": round(away_ppg, 2),
        "home_form_score": home_form.get("overall", {}).get("form_score", 0),
        "away_form_score": away_form.get("overall", {}).get("form_score", 0),
        "form_diff": round(home_ppg - away_ppg, 2),
    }
    
    # Recent stats
    home_stats = get_recent_stats(home_team)
    away_stats = get_recent_stats(away_team)
    result["home_stats"] = home_stats
    result["away_stats"] = away_stats
    
    # Injury impact
    injuries = get_match_injuries(home_team, away_team)
    result["injuries"] = injuries
    
    # Try to get predictions if fixture is found
    fixtures = get_todays_fixtures()
    fixture = find_fixture(home_team, away_team, fixtures)
    if fixture:
        fix_id = fixture.get("fixture", {}).get("id")
        result["fixture_id"] = fix_id
        result["predictions"] = get_predictions_enhanced(fix_id)
    
    return result


# ── Signal Scoring Helper ──────────────────────────────────────────────────────

def calculate_implied_probability(data: dict, market_type: str) -> tuple:
    """
    Calculate implied probability from API-Football data for a given market type.
    Returns (implied_pct, confidence, breakdown)
    
    For match_result: uses H2H win rates + form + predictions
    For total_goals: uses H2H avg goals + recent stats
    For btts: uses H2H BTTS rate + team scoring stats
    For corners: uses recent corner averages
    For cards: uses recent card averages
    """
    implied = 50.0
    confidence = "LOW"
    breakdown = []
    
    h2h = data.get("h2h", {})
    form = data.get("form_comparison", {})
    home_stats = data.get("home_stats", {})
    away_stats = data.get("away_stats", {})
    injuries = data.get("injuries", {})
    preds = data.get("predictions", {})
    
    if market_type == "match_result":
        # Use H2H + form + predictions
        components = []
        
        # H2H home win rate
        if h2h:
            h2h_home = h2h.get("home_win_rate", 50)
            components.append(("H2H home win%", h2h_home))
        
        # Form points per game
        home_ppg = form.get("home_ppg", 1.5)
        away_ppg = form.get("away_ppg", 1.5)
        # Convert PPG to win probability (roughly)
        form_home_win_pct = 33 + (home_ppg - away_ppg) * 20  # Rough mapping
        form_home_win_pct = max(20, min(80, form_home_win_pct))
        components.append(("Form PPG diff", form_home_win_pct))
        
        # API-Football predictions
        if preds and preds.get("win_probs"):
            win_probs = preds["win_probs"]
            api_home = win_probs.get("home_win", 0)
            api_draw = win_probs.get("draw", 0)
            api_away = win_probs.get("away_win", 0)
            components.append(("API-FB prediction", api_home if api_home > 0 else 50))
        
        # Average components
        if components:
            implied = sum(v for _, v in components) / len(components)
            breakdown = [f"{k}: {v:.1f}%" for k, v in components]
            
            if preds.get("advice"):
                breakdown.append(f"Advice: {preds['advice']}")
        
        confidence = "HIGH" if preds and preds.get("advice") else "MEDIUM"
        
        # Injury adjustment
        home_impact = injuries.get("home_key_injuries", 0)
        away_impact = injuries.get("away_key_injuries", 0)
        if home_impact > away_impact:
            implied -= home_impact * 2
        elif away_impact > home_impact:
            implied += away_impact * 2
    
    elif market_type == "total_goals":
        # Use H2H avg goals + recent xG data
        components = []
        
        if h2h:
            avg_g = h2h.get("avg_goals", 2.5)
            components.append(("H2H avg goals", avg_g))
        
        home_scored = home_stats.get("avg_goals_scored", 0)
        home_conceded = home_stats.get("avg_goals_conceded", 0)
        away_scored = away_stats.get("avg_goals_scored", 0)
        away_conceded = away_stats.get("avg_goals_conceded", 0)
        
        # Expected total
        exp_total = (home_scored + away_scored + home_conceded + away_conceded) / 4
        if exp_total > 0:
            components.append(("Recent avg goals", exp_total * 2))  # Total = 2 teams
        
        if components:
            implied = sum(v for _, v in components) / len(components) * 100 / 2.5  # Normalize to 2.5 line
            implied = min(max(implied, 0), 100)
            breakdown = [f"{k}: {v:.2f}" for k, v in components]
        
        confidence = "MEDIUM" if components else "LOW"
    
    elif market_type == "btts":
        # Both teams to score
        components = []
        
        if h2h:
            btts_rate = h2h.get("btts_rate", 50)
            components.append(("H2H BTTS%", btts_rate))
        
        # Check if both teams score frequently
        if home_stats.get("avg_goals_scored", 0) > 0.8:
            components.append(("Home scoring rate", 65))
        if away_stats.get("avg_goals_scored", 0) > 0.8:
            components.append(("Away scoring rate", 65))
        
        if components:
            implied = sum(v for _, v in components) / len(components)
            breakdown = [f"{k}: {v:.1f}%" for k, v in components]
        
        confidence = "MEDIUM" if components else "LOW"
    
    elif market_type == "corners":
        # Corners market
        components = []
        
        home_corners = home_stats.get("avg_corners", 4.5)
        away_corners = away_stats.get("avg_corners", 4.5)
        
        if home_corners and away_corners:
            total_corners = home_corners + away_corners
            components.append(("Avg total corners", total_corners))
            implied = min(total_corners, 15) / 15 * 100  # Map to 0-15 range
            breakdown = [f"Home corners: {home_corners:.1f}", f"Away corners: {away_corners:.1f}"]
        
        confidence = "MEDIUM" if components else "LOW"
    
    elif market_type == "scorer":
        # Player scorer market — use API-FB predictions + form
        implied = 30  # Base rate for any scorer
        breakdown = ["Player market: limited data from API-FB"]
        confidence = "LOW"
        
        if preds and preds.get("correct_score"):
            breakdown.append(f"Predicted score: {preds['correct_score']}")
    
    else:
        # General: use form comparison only
        form_diff = form.get("form_diff", 0)
        implied = 50 + form_diff * 15
        implied = min(max(implied, 20), 80)
        breakdown = [f"Form PPG diff: {form_diff:+.2f}"]
        confidence = "MEDIUM"
    
    # Injury penalty
    if market_type == "match_result":
        home_inj = injuries.get("home_key_injuries", 0)
        away_inj = injuries.get("away_key_injuries", 0)
        if home_inj > 0:
            breakdown.append(f"Home {injuries.get('home_level', 'injured')} injuries (-{home_inj * 3}%)")
        if away_inj > 0:
            breakdown.append(f"Away {injuries.get('away_level', 'injured')} injuries (+{away_inj * 3}%)")
    
    return round(implied, 1), confidence, breakdown


# ── Legacy wrappers ────────────────────────────────────────────────────────────

def get_upcoming_fixtures(days: int = 3, league_ids: list = None) -> list:
    return get_fixtures_for_date_range(days)

def get_team_form(team_name: str, league_id: int = None) -> dict:
    return get_team_form_enhanced(team_name, league_id)

def get_match_prediction(home_team: str, away_team: str) -> dict:
    return get_predictions_enhanced(home_team, away_team)

def get_injuries(date_from: str = None, date_to: str = None, league_id: int = None) -> list:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    two_weeks = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")
    data = _get("/injuries", {"from": date_from or today, "to": date_to or two_weeks})
    return data.get("response", [])
