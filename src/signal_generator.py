"""
signal_generator.py - Generate trading signals from Limitless + RSS + Twitter + API-Football.

Signal sources:
1. Limitless sports markets (via API)
2. RSS feeds (BBC Sport, ESPN, Sky Sports, Transfermarkt)
3. Twitter (FabrizioRomano, OptaJoe, tipsters, clubs)
4. API-Football (fixtures, injuries, predictions)

Signal logic:
1. Fetch live sports markets from Limitless
2. Fetch sports news from RSS + Twitter
3. For each market, analyze related news/tweets
4. Calculate implied probability from sentiment + API data
5. Compare to market price → find edge
6. Generate signals ranked by edge/confidence
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from limitless_client import (
    get_active_markets, format_volume, parse_price, get_sport_tag
)
from sports_rss_client import fetch_all_feeds, fetch_sport_feeds, filter_football_articles, filter_nba_articles

logger = logging.getLogger(__name__)

SIGNALS_FILE = Path(__file__).parent.parent / "data" / "signals.json"

# Try to import Twitter client
try:
    from twitter_client import fetch_all_sports_tweets, Tweet
    TWITTER_AVAILABLE = True
except ImportError:
    TWITTER_AVAILABLE = False
    Tweet = None
    logger.info("Twitter client not available")

# Try to import API-Football client
try:
    from api_football_client import get_upcoming_fixtures, get_team_form, get_match_prediction, get_cached, set_cached
    # Opt-in via env var (rate limit: 100 calls/day — expensive with 47 markets)
    API_FOOTBALL_AVAILABLE = os.environ.get("API_FOOTBALL_ENABLED", "false").lower() == "true"
except ImportError:
    API_FOOTBALL_AVAILABLE = False
    logger.info("API-Football client not available")


# Keyword mapping: RSS article sentiment
POSITIVE_SIGNALS = [
    "win", "wins", "victory", "score", "scored", "goal", "goals",
    "lead", "leading", "ahead", "champion", "trophy", "title",
    "beat", "defeated", "dominate", "dominant", "strong",
    "confirm", "confirmed", "deal", "signed", "positive",
    "impressive", "clinical", "back on track", "boost"
]

NEGATIVE_SIGNALS = [
    "lose", "loss", "loses", "draw", "drawn", "behind",
    "injury", "injured", "suspended", "ban", "banned",
    "fail", "failed", "crash", "crashed", "eliminated",
    "rumor", "rumoured", "concern", "doubt", "doubtful",
    "setback", "blow", "struggling", "poor form"
]


def generate_signals(sport_filter: str = None, min_edge: float = 0.10, limit: int = 30) -> dict:
    """
    Generate trading signals by comparing RSS + Twitter sentiment to Limitless market prices.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Fetch markets
    markets_data = get_active_markets(
        limit=100,
        sort_by="high_value",
        automation_type="sports"
    )
    markets = markets_data.get("data", [])

    # Expand group markets into sub-markets for signal analysis
    expanded_markets = []
    for m in markets:
        sub_markets = m.get("markets", [])
        if m.get("marketType") == "group" and sub_markets:
            # Use sub-market slugs and titles for signal matching
            for sm in sub_markets:
                sm_copy = dict(m)
                sm_copy["slug"] = sm.get("slug", "")
                sm_copy["title"] = sm.get("title", "")
                sm_copy["prices"] = sm.get("prices", [0.5, 0.5])
                sm_copy["marketType"] = "group_sub"
                sm_copy["group_title"] = m.get("title", "")
                expanded_markets.append(sm_copy)
        else:
            m["marketType"] = m.get("marketType", "standard")
            expanded_markets.append(m)

    markets = expanded_markets

    # Fetch RSS feeds
    if sport_filter:
        articles = fetch_sport_feeds(sport_filter)
    else:
        feeds_data = fetch_all_feeds()
        articles = feeds_data.get("articles", [])

    if sport_filter == "Football":
        articles = filter_football_articles(articles)
    elif sport_filter == "Basketball":
        articles = filter_nba_articles(articles)

    # Fetch Twitter
    tweets = []
    twitter_count = 0
    if TWITTER_AVAILABLE:
        try:
            tweets = fetch_all_sports_tweets()
            twitter_count = len(tweets)
            logger.info(f"Fetched {twitter_count} tweets")
        except Exception as e:
            logger.warning(f"Twitter fetch failed: {e}")

    # Fetch API-Football fixtures
    api_fixtures = []
    api_football_count = 0
    if API_FOOTBALL_AVAILABLE:
        try:
            # Get upcoming fixtures for next 3 days
            api_fixtures = get_upcoming_fixtures(days=3)
            api_football_count = len(api_fixtures)
            logger.info(f"Fetched {api_football_count} fixtures from API-Football")
        except Exception as e:
            logger.warning(f"API-Football fetch failed: {e}")

    logger.info(f"RSS: {len(articles)}, Twitter: {twitter_count}, API-Football: {api_football_count}, Markets: {len(markets)}")

    # Generate signals
    signals = []

    for market in markets[:50]:
        signal = _analyze_market(market, articles, tweets, api_fixtures)
        if signal and signal.get("edge", 0) >= min_edge * 100:
            signals.append(signal)

    # Sort by edge descending
    signals.sort(key=lambda x: x.get("edge", 0), reverse=True)
    signals = signals[:limit]

    # Build result
    result = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sport_filter": sport_filter,
        "markets_analyzed": len(markets),
        "articles_fetched": len(articles),
        "tweets_fetched": twitter_count,
        "api_football_fetched": api_football_count,
        "signals_count": len(signals),
        "twitter_enabled": TWITTER_AVAILABLE,
        "api_football_enabled": API_FOOTBALL_AVAILABLE,
        "signals": signals,
    }

    # Save to file
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)

    return result


def _analyze_market(market: dict, articles: list, tweets: list, api_fixtures: list = None) -> Optional[dict]:
    """Analyze a single market against RSS articles + Twitter + API-Football."""

    title = market.get("title", "")
    title_lower = title.lower()
    tags = [t.lower() for t in market.get("tags", []) + market.get("categories", [])]
    slug = market.get("slug", "")
    market_type_val = market.get("marketType", "standard")

    # Detect market type
    market_type = _detect_market_type(title_lower)

    # For group sub-markets, use group_title for keyword matching (Bayern München alone → no match)
    group_title = market.get("group_title", "")
    match_title = group_title if group_title else title

    # Extract key entities from the full match title for better signal matching
    keywords = _extract_entities(match_title.lower())

    # Find related content
    related_articles = []
    related_tweets = []

    # Check RSS articles
    for article in articles[:50]:
        art_text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        match_count = sum(1 for kw in keywords if kw.lower() in art_text)
        if match_count >= 1:
            related_articles.append(article)

    # Check Twitter tweets
    for tweet in tweets[:100]:
        tweet_text = (tweet.title + " " + tweet.summary).lower()
        match_count = sum(1 for kw in keywords if kw.lower() in tweet_text)
        if match_count >= 1:
            related_tweets.append(tweet)

    # ── API-Football ────────────────────────────────────────────────────────
    api_football_data = None
    api_implied = None
    api_confidence = "LOW"
    api_breakdown = []

    if API_FOOTBALL_AVAILABLE:
        try:
            from api_football_client import (
                detect_market_type, extract_teams_from_market_title,
                find_fixture, get_market_relevant_data,
                calculate_implied_probability, get_upcoming_fixtures
            )

            # Try to extract teams from market title
            home_team, away_team = extract_teams_from_market_title(title)

            # If no teams found, try keyword matching
            if not home_team or not away_team:
                from api_football_client import normalize_team_name
                fixtures = api_fixtures or get_upcoming_fixtures(days=3)

                for fix in fixtures[:50]:
                    teams = fix.get("teams", {})
                    fix_home = teams.get("home", {}).get("name", "")
                    fix_away = teams.get("away", {}).get("name", "")

                    h_match = any(kw in fix_home.lower() for kw in keywords if len(kw) >= 3)
                    a_match = any(kw in fix_away.lower() for kw in keywords if len(kw) >= 3)

                    if h_match and a_match:
                        home_team = fix_home
                        away_team = fix_away
                        break
                    elif fix_home and (h_match or any(fix_home.lower() in kw for kw in keywords)):
                        home_team = fix_home
                    elif fix_away and (a_match or any(fix_away.lower() in kw for kw in keywords)):
                        away_team = fix_away

            if home_team and away_team:
                # Get all relevant API-FB data
                api_football_data = get_market_relevant_data(home_team, away_team, market_type)

                # Calculate implied probability for this market type
                api_implied, api_confidence, api_breakdown = calculate_implied_probability(
                    api_football_data, market_type
                )

                logger.debug(f"API-FB [{market_type}]: {home_team} vs {away_team} → implied={api_implied}%, conf={api_confidence}")

        except Exception as e:
            logger.warning(f"API-FB error: {e}")

    # Skip if no content AND no API data
    if not related_articles and not related_tweets and api_implied is None:
        return None

    # ── Sentiment Analysis ───────────────────────────────────────────────────
    rss_sentiment = _analyze_rss_sentiment(related_articles)
    twitter_sentiment = _analyze_twitter_sentiment(related_tweets)

    # Combine RSS + Twitter sentiment
    if len(related_tweets) > 0:
        sentiment_implied = (
            rss_sentiment["implied_probability"] * 0.4 +
            twitter_sentiment["implied_probability"] * 0.6
        )
        sentiment_score = (
            rss_sentiment["score"] * 0.4 +
            twitter_sentiment["score"] * 0.6
        )
    else:
        sentiment_implied = rss_sentiment["implied_probability"]
        sentiment_score = rss_sentiment["score"]

    # ── Final Implied Probability ────────────────────────────────────────────
    # Weight: API-FB predictions most reliable when available
    if api_implied is not None and api_confidence in ("HIGH", "MEDIUM"):
        if api_confidence == "HIGH":
            # API-FB predictions dominate (e.g. AI predictions with advice)
            combined_implied = api_implied * 0.6 + sentiment_implied * 0.4
        else:
            # Balanced
            combined_implied = api_implied * 0.5 + sentiment_implied * 0.5
    else:
        # No strong API-FB data - use sentiment only
        combined_implied = sentiment_implied

    # ── Edge Calculation ───────────────────────────────────────────────────
    prices = market.get("prices", [0.5, 0.5])
    try:
        market_yes_pct = float(prices[0]) * 100
    except:
        market_yes_pct = 50

    # Calculate edge
    if combined_implied > market_yes_pct:
        direction = "YES"
        edge = combined_implied - market_yes_pct
    else:
        direction = "NO"
        edge = market_yes_pct - combined_implied

    # Skip if edge too small
    if edge < 5 or abs(sentiment_score) < 0.1 and api_implied is None:
        return None

    # Confidence
    content_count = len(related_articles) + len(related_tweets)
    confidence = _calc_confidence(
        content_count, edge, related_tweets,
        api_data=api_football_data,
        api_confidence=api_confidence
    )

    # Special signals
    is_breaking = any(t.is_breaking for t in related_tweets)
    is_transfer = any(t.is_transfer for t in related_tweets)
    is_injury = any(t.is_injury for t in related_tweets)
    is_betting_tip = any(t.is_betting_tip for t in related_tweets)

    sport = get_sport_tag(market)

    signal = {
        "id": f"sig_{slug[:20]}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "market": market.get("title", "Unknown"),
        "slug": slug,
        "url": f"https://limitless.exchange/markets/{slug}",
        "sport": sport,
        "direction": direction,
        "market_yes_pct": round(market_yes_pct, 1),
        "news_implied_pct": round(combined_implied, 1),
        "edge": round(edge, 1),
        "confidence": confidence,
        "volume": format_volume(market.get("volume", "0")),
        "expiration": market.get("expirationDate", "Unknown"),
        "trade_type": market.get("tradeType", "unknown"),
        "market_type": market_type_val,
        "market_sub_type": market_type,
        "related_articles": related_articles[:3],
        "related_tweets": [
            {"source": t.source, "title": t.title, "url": t.url, "is_breaking": t.is_breaking}
            for t in related_tweets[:5]
        ],
        "rss_sentiment": rss_sentiment,
        "twitter_sentiment": twitter_sentiment if related_tweets else None,
        "api_football": {
            "home_team": api_football_data.get("home_team") if api_football_data else None,
            "away_team": api_football_data.get("away_team") if api_football_data else None,
            "market_type": market_type_val,
            "market_sub_type": market_type,
            "api_implied": api_implied,
            "api_confidence": api_confidence,
            "api_breakdown": api_breakdown,
            # Form data
            "home_form": api_football_data.get("home_form", {}).get("overall", {}).get("form", "") if api_football_data else None,
            "away_form": api_football_data.get("away_form", {}).get("overall", {}).get("form", "") if api_football_data else None,
            "home_form_score": api_football_data.get("form_comparison", {}).get("home_form_score", 0) if api_football_data else 0,
            "away_form_score": api_football_data.get("form_comparison", {}).get("away_form_score", 0) if api_football_data else 0,
            "home_ppg": api_football_data.get("form_comparison", {}).get("home_ppg", 0) if api_football_data else 0,
            "away_ppg": api_football_data.get("form_comparison", {}).get("away_ppg", 0) if api_football_data else 0,
            "form_diff": api_football_data.get("form_comparison", {}).get("form_diff", 0) if api_football_data else 0,
            # H2H data
            "h2h_avg_goals": api_football_data.get("h2h", {}).get("avg_goals") if api_football_data else None,
            "h2h_btts_rate": api_football_data.get("h2h", {}).get("btts_rate") if api_football_data else None,
            "h2h_home_win_rate": api_football_data.get("h2h", {}).get("home_win_rate") if api_football_data else None,
            # Recent stats
            "home_avg_goals": api_football_data.get("home_stats", {}).get("avg_goals_scored") if api_football_data else None,
            "away_avg_goals": api_football_data.get("away_stats", {}).get("avg_goals_scored") if api_football_data else None,
            "home_avg_corners": api_football_data.get("home_stats", {}).get("avg_corners") if api_football_data else None,
            "away_avg_corners": api_football_data.get("away_stats", {}).get("avg_corners") if api_football_data else None,
            # Injuries
            "home_injuries": api_football_data.get("injuries", {}).get("home_count", 0) if api_football_data else 0,
            "away_injuries": api_football_data.get("injuries", {}).get("away_count", 0) if api_football_data else 0,
            "home_injury_level": api_football_data.get("injuries", {}).get("home_level", "none") if api_football_data else "none",
            "away_injury_level": api_football_data.get("injuries", {}).get("away_level", "none") if api_football_data else "none",
            # Predictions
            "predictions": api_football_data.get("predictions", {}).get("advice") if api_football_data else None,
            "pred_home_win": api_football_data.get("predictions", {}).get("win_probs", {}).get("home_win") if api_football_data else None,
            "pred_draw": api_football_data.get("predictions", {}).get("win_probs", {}).get("draw") if api_football_data else None,
            "pred_away_win": api_football_data.get("predictions", {}).get("win_probs", {}).get("away_win") if api_football_data else None,
            "pred_correct_score": api_football_data.get("predictions", {}).get("correct_score") if api_football_data else None,
        } if api_football_data else None,
        "is_breaking": is_breaking,
        "is_transfer": is_transfer,
        "is_injury": is_injury,
        "is_betting_tip": is_betting_tip,
        "keywords": keywords,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return signal


def _analyze_rss_sentiment(articles: list) -> dict:
    """Analyze RSS article sentiment."""
    if not articles:
        return {"score": 0, "positive": 0, "negative": 0, "implied_probability": 50}

    positive = 0
    negative = 0

    for article in articles:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()

        pos_count = sum(1 for p in POSITIVE_SIGNALS if p in text)
        neg_count = sum(1 for n in NEGATIVE_SIGNALS if n in text)

        if pos_count > neg_count:
            positive += 1
        elif neg_count > pos_count:
            negative += 1

    total = len(articles)
    score = (positive - negative) / total if total > 0 else 0
    implied_probability = 50 + (score * 50)
    implied_probability = max(5, min(95, implied_probability))

    return {
        "score": round(score, 2),
        "positive": positive,
        "negative": negative,
        "implied_probability": round(implied_probability, 1),
        "article_count": total,
    }


def _analyze_twitter_sentiment(tweets: list) -> dict:
    """Analyze Twitter tweet sentiment."""
    if not tweets:
        return {"score": 0, "bullish": 0, "bearish": 0, "implied_probability": 50}

    bullish = 0
    bearish = 0

    for tweet in tweets:
        bull = tweet.bullish_score
        bear = tweet.bearish_score

        if bull > bear:
            bullish += 1
        elif bear > bull:
            bearish += 1

    total = len(tweets)
    score = (bullish - bearish) / total if total > 0 else 0
    implied_probability = 50 + (score * 50)
    implied_probability = max(5, min(95, implied_probability))

    return {
        "score": round(score, 2),
        "bullish": bullish,
        "bearish": bearish,
        "implied_probability": round(implied_probability, 1),
        "tweet_count": total,
        "transfer_signals": sum(1 for t in tweets if t.is_transfer),
        "injury_signals": sum(1 for t in tweets if t.is_injury),
        "betting_tips": sum(1 for t in tweets if t.is_betting_tip),
        "breaking_news": sum(1 for t in tweets if t.is_breaking),
    }


def _detect_market_type(title_lower: str) -> str:
    """Detect market type from title."""
    if any(k in title_lower for k in ["over 2.5", "under 2.5", "total goals", "total score"]): return "total_goals"
    if any(k in title_lower for k in ["both teams", " btts", "each team", " to score", "both score", "each of the"]): return "btts"
    if any(k in title_lower for k in ["corner", "corners"]): return "corners"
    if any(k in title_lower for k in ["yellow", "red card", "cards", "bookings"]): return "cards"
    if any(k in title_lower for k in ["score", "win the", "wins the", "winner", "qualify", "advance", "relegat"]): return "match_result"
    if any(k in title_lower for k in ["scorer", "brace", "hat-trick", "goalscorer", "trick", "first goal"]): return "scorer"
    if any(k in title_lower for k in ["assist", "most assist"]): return "assists"
    if any(k in title_lower for k in ["half", "1st half", "2nd half", "ht/f"]): return "half_result"
    if any(k in title_lower for k in ["penalty", "red card", "send off", "offside"]): return "special"
    return "general"


def _calc_confidence(content_count: int, edge: float, tweets: list, api_data: dict = None, api_confidence: str = "LOW") -> str:
    """Calculate signal confidence level."""
    has_twitter = len(tweets) > 0
    has_breaking = any(t.is_breaking for t in tweets) if tweets else False
    has_transfer = any(t.is_transfer for t in tweets) if tweets else False
    has_injury = any(t.is_injury for t in tweets) if tweets else False

    abs_edge = abs(edge)

    # Boost confidence with Twitter signals and API-Football
    twitter_boost = 1.0
    if has_twitter: twitter_boost += 0.5
    if has_breaking or has_transfer: twitter_boost += 1.0
    if has_injury: twitter_boost += 0.5

    # API-FB boosts
    if api_data:
        if api_confidence == "HIGH": twitter_boost += 1.5
        elif api_confidence == "MEDIUM": twitter_boost += 0.8
        if api_data.get("predictions"): twitter_boost += 0.5
        if api_data.get("h2h"): twitter_boost += 0.3
        if api_data.get("injuries", {}).get("home_key_injuries", 0) > 0: twitter_boost += 0.3
        if api_data.get("injuries", {}).get("away_key_injuries", 0) > 0: twitter_boost += 0.3

    effective_edge = abs_edge * twitter_boost

    if content_count >= 3 and effective_edge >= 25:
        return "CRITICAL"
    elif content_count >= 2 and effective_edge >= 18:
        return "HIGH"
    elif content_count >= 1 and effective_edge >= 12:
        return "MEDIUM"
    else:
        return "LOW"


def _extract_entities(title: str) -> list:
    """Extract key entities from market title."""
    entities = []

    stopwords = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "vs", "vs.",
        "will", "be", "is", "this", "that", "market", "total", "number",
        "over", "under", "more", "than", "during", "match", "game", "day",
        "time", "minute", "first", "second", "half", "regular"
    }

    words = title.replace("?", "").replace("(", " ").replace(")", " ").replace(",", " ").replace(":", " ").split()

    for word in words:
        word = word.strip().lower()
        if len(word) > 2 and word not in stopwords:
            entities.append(word)

    return entities[:8]


def load_signals() -> dict:
    """Load last generated signals from file."""
    if not SIGNALS_FILE.exists():
        return {"signals": [], "run_id": None}
    try:
        with open(SIGNALS_FILE) as f:
            return json.load(f)
    except:
        return {"signals": [], "run_id": None}
