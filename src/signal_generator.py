"""
signal_generator.py — Generate trading signals from Limitless market data + RSS + Twitter.

Signal sources:
1. Limitless sports markets (via API)
2. RSS feeds (BBC Sport, ESPN, Sky Sports)
3. Twitter (FabrizioRomano, OptaJoe, tipsters, clubs)

Signal logic:
1. Fetch live sports markets from Limitless
2. Fetch sports news from RSS + Twitter
3. For each market, analyze related news/tweets
4. Calculate implied probability from sentiment
5. Compare to market price → find edge
6. Generate signals ranked by edge/confidence
"""

import json
import logging
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
        limit=25,
        sort_by="high_value",
        automation_type="sports"
    )
    markets = markets_data.get("data", [])
    
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
    
    logger.info(f"RSS: {len(articles)} articles, Twitter: {twitter_count} tweets, Markets: {len(markets)}")
    
    # Generate signals
    signals = []
    
    for market in markets[:50]:
        signal = _analyze_market(market, articles, tweets)
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
        "signals_count": len(signals),
        "twitter_enabled": TWITTER_AVAILABLE,
        "signals": signals,
    }
    
    # Save to file
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    return result


def _analyze_market(market: dict, articles: list, tweets: list) -> Optional[dict]:
    """Analyze a single market against RSS articles + Twitter."""
    
    title = market.get("title", "").lower()
    tags = [t.lower() for t in market.get("tags", []) + market.get("categories", [])]
    slug = market.get("slug", "")
    
    # Extract key entities
    keywords = _extract_entities(title)
    
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
    
    if not related_articles and not related_tweets:
        return None
    
    # Analyze sentiment
    rss_sentiment = _analyze_rss_sentiment(related_articles)
    twitter_sentiment = _analyze_twitter_sentiment(related_tweets)
    
    # Combine sentiment (Twitter weighted higher if available)
    if len(related_tweets) > 0:
        # Weight: 40% RSS, 60% Twitter
        combined_score = (rss_sentiment["score"] * 0.4) + (twitter_sentiment["score"] * 0.6)
        combined_implied = (rss_sentiment["implied_probability"] * 0.4) + (twitter_sentiment["implied_probability"] * 0.6)
    else:
        combined_score = rss_sentiment["score"]
        combined_implied = rss_sentiment["implied_probability"]
    
    # Get market price
    prices = market.get("prices", [0.5, 0.5])
    try:
        market_yes_pct = float(prices[0]) * 100
    except:
        market_yes_pct = 50
    
    # Calculate edge
    edge = abs(combined_implied - market_yes_pct)
    
    # Determine direction
    if combined_implied > market_yes_pct:
        direction = "YES"
        edge = combined_implied - market_yes_pct
    else:
        direction = "NO"
        edge = market_yes_pct - combined_implied
    
    # Skip if edge too small
    if edge < 5 or abs(combined_score) < 0.1:
        return None
    
    # Confidence based on content + edge
    content_count = len(related_articles) + len(related_tweets)
    confidence = _calc_confidence(content_count, edge, related_tweets)
    
    # Check for special signals
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
        "related_articles": related_articles[:3],
        "related_tweets": [
            {"source": t.source, "title": t.title, "url": t.url, "is_breaking": t.is_breaking}
            for t in related_tweets[:5]
        ],
        "rss_sentiment": rss_sentiment,
        "twitter_sentiment": twitter_sentiment if related_tweets else None,
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


def _calc_confidence(content_count: int, edge: float, tweets: list) -> str:
    """Calculate signal confidence level."""
    has_twitter = len(tweets) > 0
    has_breaking = any(t.is_breaking for t in tweets) if tweets else False
    has_transfer = any(t.is_transfer for t in tweets) if tweets else False
    has_injury = any(t.is_injury for t in tweets) if tweets else False
    
    abs_edge = abs(edge)
    
    # Boost confidence with Twitter signals
    twitter_boost = 1.0
    if has_twitter:
        twitter_boost += 0.5
    if has_breaking or has_transfer:
        twitter_boost += 1.0
    if has_injury:
        twitter_boost += 0.5
    
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
