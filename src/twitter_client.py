"""
twitter_client.py — Fetch football/sports tweets via bird CLI

Uses @steipete/bird with auth_token + ct0 cookies to pull
latest tweets from curated football accounts.

Accounts:
- Transfers: @FabrizioRomano, @David_Ornstein, @DiMarzio, @GuillemBalague
- Betting Tips: @AndyRobsonTips, @JamesMurphyTips, @pinchbet
- Stats/Analytics: @OptaJoe, @FootRankings
- Leagues/Clubs: @premierleague, @LaLiga, @SerieA, @RealMadrid, @FCBarcelona, @ManUtd, @FCBayern
- Specialist: @meatmansoccer
"""

import os
import re
import subprocess
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TWITTER_ACCOUNTS = [
    # Transfers & Breaking News
    "FabrizioRomano",
    "David_Ornstein",
    "DiMarzio",
    "GuillemBalague",
    
    # Betting Tips & Analysis
    "AndyRobsonTips",
    "JamesMurphyTips",
    "pinchbet",
    
    # Stats & Analytics
    "OptaJoe",
    "FootRankings",
    
    # Leagues & Clubs
    "premierleague",
    "LaLiga",
    "SerieA",
    "RealMadrid",
    "FCBarcelona",
    "ManUtd",
    "FCBayern",
    "PSG",
    "Inter",
    "juventusfc",
    "LFC",
    
    # Specialists
    "meatmansoccer",
]

# Source weight — accounts with highest signal quality get more weight
SOURCE_WEIGHTS = {
    "FabrizioRomano": 2.0,   # "Here we go" is market-moving
    "David_Ornstein": 2.0,   # Most trusted PL reporter
    "DiMarzio": 1.8,         # Sky Italy, deep Serie A
    "GuillemBalague": 1.5,   # La Liga expert
    
    "OptaJoe": 1.8,          # Data-driven, market-relevant stats
    "FootRankings": 1.5,     # Projections & simulations
    
    "AndyRobsonTips": 1.5,   # High-volume consistent tipster
    "JamesMurphyTips": 1.5,  # Value bets focus
    "pinchbet": 1.3,         # Popular clean picks
    
    "premierleague": 1.3,    # Official announcements
    "LaLiga": 1.2,
    "SerieA": 1.2,
    "RealMadrid": 1.2,
    "FCBarcelona": 1.2,
    "ManUtd": 1.2,
    "FCBayern": 1.2,
    "LFC": 1.2,
    "PSG": 1.1,
    "Inter": 1.1,
    "juventusfc": 1.1,
    
    "meatmansoccer": 1.3,    # Under-radar leagues
}

MAX_TWEETS_PER_ACCOUNT = 10
MAX_AGE_HOURS = 24  # Sports news has longer shelf life than geo

# ---------------------------------------------------------------------------
# Cookie file
# ---------------------------------------------------------------------------
COOKIE_FILE = Path(__file__).parent.parent / ".twitter_cookies.env"

def load_cookies() -> dict:
    if not COOKIE_FILE.exists():
        logger.warning("No .twitter_cookies.env — Twitter feeds disabled")
        return {}
    env = {}
    with open(COOKIE_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    return env

def save_cookies(auth_token: str, ct0: str):
    with open(COOKIE_FILE, "w") as f:
        f.write(f'AUTH_TOKEN="{auth_token}"\n')
        f.write(f'CT0="{ct0}"\n')
    os.chmod(COOKIE_FILE, 0o600)

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class Tweet:
    source: str
    title: str
    summary: str
    published: datetime
    url: str
    bullish_score: float = 0.0   # Supports YES
    bearish_score: float = 0.0   # Supports NO
    is_breaking: bool = False
    is_transfer: bool = False
    is_injury: bool = False
    is_betting_tip: bool = False
    matched_keywords: list = field(default_factory=list)
    
    def get_age_hours(self) -> float:
        return (datetime.utcnow() - self.published).total_seconds() / 3600

# ---------------------------------------------------------------------------
# Keyword scoring for sports/football
# ---------------------------------------------------------------------------

# Terms that push YES (market resolves positive)
BULLISH_TERMS = {
    # Transfers — positive news
    "here we go": 5, "deal agreed": 4, "deal done": 4, "signs for": 4,
    "completes move": 4, "agreement reached": 4, "medical": 3, "agreed": 3,
    "sign new": 3, "renews": 3, "extends contract": 3, "extension": 3,
    "happy to confirm": 4, "official soon": 3, "sealed": 4,
    
    # Match form — team performing well
    "in great form": 3, "unbeaten": 3, "winning streak": 3, "back to winning": 3,
    "impressive": 2, "dominant": 2, "clinical": 2, "back on track": 3,
    "confidence": 2, "momentum": 2, "in good shape": 2,
    
    # Team news — positive
    "returns": 2, "back from injury": 2, "fit again": 2, "available": 2,
    "fully fit": 2, "ready to play": 2, "starting": 2,
    "boost": 2, "positive news": 2, "good news": 2,
    
    # Manager/coach signals
    "tactical masterclass": 2, "well set up": 2, "prepared": 2,
    
    # Betting tips — backing YES
    "back": 2, "backing": 2, "value on": 2, "tip": 1, "tips": 1,
    "prediction": 1, "predict": 1, "favourite": 2, "should win": 2,
    "expected to": 2, "likely": 1, "odds on": 2,
    
    # Stats positive
    "xg": 1, "expected goals": 1, "best": 1, "top": 1,
    "leading": 1, "ahead": 1, "leads": 1,
    
    # Score predictions
    "to win": 2, "wins": 1, "victory": 2, "beat": 2,
    "clean sheet": 2, "to score": 2, "scores": 1,
}

# Terms that push NO (market resolves negative)
BEARISH_TERMS = {
    # Transfers — negative news
    "pulls out": 4, "deal collapses": 4, "fall through": 4, "not happen": 4,
    "rejected": 3, "turned down": 3, "refused": 3, "snubbed": 3,
    "leaves": 2, "departing": 2, "sold": 2, "loan deal": 2,
    "not renew": 3, "leaves club": 2, "exit": 2,
    
    # Injuries — negative
    "injury": 3, "injured": 3, "injury concern": 3, "injury blow": 3,
    "out injured": 3, "out for": 3, "doubt": 3, "unlikely": 2,
    "suspended": 3, "suspension": 2, "ban": 2, "banned": 2,
    "fitness doubt": 3, "may miss": 2, "to miss": 2, "missing": 2,
    "knock": 2, "strain": 2, "tear": 3, "fracture": 3,
    
    # Match form — team struggling
    "poor form": 3, "struggling": 2, "inconsistent": 2, "bad run": 3,
    "defeat": 2, "loss": 2, "losing": 2, "defeated": 2,
    "below par": 2, "concern": 2, "worries": 2,
    
    # Team news — negative
    "ruled out": 3, "unavailable": 3, "not fit": 2, "not ready": 2,
    "not in squad": 2, "not traveling": 2, "stays on": 1,
    "setback": 2, "blow": 2, "bad news": 2, "negative": 2,
    
    # Manager/coach signals
    "under pressure": 2, "struggle": 2, "difficult": 2,
    
    # Betting tips — backing NO
    "oppose": 2, "against": 1, "lay": 2, "laying": 2,
    "fade": 2, "not to": 2, "avoid": 2,
    "not expected": 2, "unlikely": 2, "no value": 1,
    
    # Score predictions
    "draw": 1, "to draw": 1, "will draw": 1,
    "not win": 2, "won't win": 2, "struggle to": 2,
    
    # Cards/fouls/fluff
    "card": 1, "yellow": 1, "red card": 2, "sent off": 2,
    "foul": 1, "offside": 1, "penalty": 1,
}

# Special indicators
TRANSFER_KEYWORDS = ["transfer", "sign", "deal", "move", "medical", "contract", "renewal", "depart", "agree"]
INJURY_KEYWORDS = ["injury", "fitness", "suspension", "knock", "strain", "out for", "ruled out", "doubt", "unfit"]
BETTING_KEYWORDS = ["tip", "prediction", "back", "lay", "odds", "value", "bet", "acca", "picks", " selections"]

BREAKING_TERMS = ["breaking", "exclusive", "just in", "confirmed", "official", 
                  "here we go", "sources:", "understand", "can confirm"]


def score_tweet(text: str) -> tuple[float, float, bool, bool, bool, bool, list]:
    """Score tweet for bullish/bearish/breaking/transfer/injury/betting."""
    full = text.lower()
    
    bull = 0.0
    bear = 0.0
    matched = []
    
    # Check multi-word phrases first
    for phrase, weight in {**BULLISH_TERMS, **BEARISH_TERMS}.items():
        if phrase in full:
            if phrase in BULLISH_TERMS:
                bull += weight
            else:
                bear += weight
            matched.append(phrase)
    
    # Single word matching
    words = set(re.findall(r'\b\w{4,}\b', full))
    for w in words:
        if w not in matched:
            if w in BULLISH_TERMS:
                bull += BULLISH_TERMS[w]
                matched.append(w)
            elif w in BEARISH_TERMS:
                bear += BEARISH_TERMS[w]
                matched.append(w)
    
    is_breaking = any(b in full for b in BREAKING_TERMS)
    is_transfer = any(k in full for k in TRANSFER_KEYWORDS)
    is_injury = any(k in full for k in INJURY_KEYWORDS)
    is_betting = any(k in full for k in BETTING_KEYWORDS)
    
    return bull, bear, is_breaking, is_transfer, is_injury, is_betting, matched


def parse_datetime(date_str: str) -> Optional[datetime]:
    """Parse Twitter date: 'Mon Mar 30 20:00:11 +0000 2026'"""
    try:
        return datetime.strptime(date_str.strip(), "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), "%a %b %d %H:%M:%S %Y")
        except ValueError:
            return None


def clean_text(text: str) -> str:
    """Clean tweet text."""
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r'https?://\S+', '', text)  # Remove URLs
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def fetch_user_tweets(username: str, count: int = 10) -> List[Tweet]:
    """Fetch latest tweets from a user using bird CLI."""
    cookies = load_cookies()
    if not cookies.get("AUTH_TOKEN") or not cookies.get("CT0"):
        return []
    
    env = os.environ.copy()
    env["AUTH_TOKEN"] = cookies["AUTH_TOKEN"]
    env["CT0"] = cookies["CT0"]
    
    try:
        result = subprocess.run(
            ["bird", "user-tweets", f"@{username}", "-n", str(count)],
            capture_output=True, text=True, timeout=45,
            env=env, cwd="/tmp"
        )
        output = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"bird failed for @{username}: {e}")
        return []
    
    tweets = []
    cutoff = datetime.utcnow() - timedelta(hours=MAX_AGE_HOURS)
    
    # Parse blocks separated by dashed lines
    blocks = re.split(r'─{20,}', output)
    
    for block in blocks:
        block = block.strip()
        if not block or block.startswith("ℹ️"):
            continue
        
        lines = block.split('\n')
        
        tweet_text = ""
        tweet_url = ""
        tweet_date = ""
        is_retweet = False
        
        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith("🖼️") or line.startswith("🎬"):
                continue
            if line.startswith("🔗"):
                tweet_url = line.replace("🔗", "").strip()
            elif line.startswith("📅"):
                tweet_date = line.replace("📅", "").strip()
            elif line.startswith("RT "):
                is_retweet = True
            else:
                tweet_text += " " + line
        
        if not tweet_text.strip() or not tweet_date or is_retweet:
            continue
        
        tweet_text = clean_text(tweet_text)
        if not tweet_text:
            continue
        
        title = tweet_text[:100].rsplit('. ', 1)[0] if '. ' in tweet_text[:100] else tweet_text[:100]
        
        published = parse_datetime(tweet_date)
        if published is None:
            continue
        
        if published.tzinfo is not None:
            published = published.replace(tzinfo=None)
        
        if published < cutoff:
            continue
        
        bull, bear, breaking, transfer, injury, betting, matched = score_tweet(tweet_text)
        
        # Include tweets with any score OR breaking/transfer news
        if bull == 0 and bear == 0 and not breaking and not transfer and not betting:
            continue
        
        # Apply source weight
        source = f"Twitter/@{username}"
        weight = SOURCE_WEIGHTS.get(username, 1.0)
        bull = round(bull * weight, 2)
        bear = round(bear * weight, 2)
        
        tweets.append(Tweet(
            source=f"Twitter/@{username}",
            title=title,
            summary=tweet_text,
            published=published,
            url=tweet_url,
            bullish_score=bull,
            bearish_score=bear,
            is_breaking=breaking,
            is_transfer=transfer,
            is_injury=injury,
            is_betting_tip=betting,
            matched_keywords=matched,
        ))
    
    return tweets


def fetch_all_sports_tweets() -> List[Tweet]:
    """Fetch tweets from all configured accounts."""
    all_tweets = []
    cookies = load_cookies()
    
    if not cookies.get("AUTH_TOKEN"):
        logger.info("Twitter cookies not configured — Twitter feeds disabled")
        return []
    
    for account in TWITTER_ACCOUNTS:
        try:
            tweets = fetch_user_tweets(account, count=MAX_TWEETS_PER_ACCOUNT)
            all_tweets.extend(tweets)
            if tweets:
                logger.info(f"  [Twitter] @{account}: {len(tweets)} relevant tweets")
            import time
            time.sleep(2)  # Polite delay
        except Exception as e:
            logger.warning(f"  [Twitter] @{account}: {e}")
            import time
            time.sleep(1)
    
    logger.info(f"  [Twitter] Total: {len(all_tweets)} tweets from {len(TWITTER_ACCOUNTS)} accounts")
    return all_tweets
