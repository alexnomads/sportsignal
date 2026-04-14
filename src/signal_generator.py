"""
signal_generator.py — Generate trading signals from Limitless market data + RSS sentiment.

Signal logic:
1. Fetch live sports markets from Limitless
2. Fetch sports news from RSS feeds
3. For each market, analyze related news sentiment
4. Calculate implied probability from news
5. Compare to market price → find edge
6. Generate signals ranked by edge/congruence
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from limitless_client import (
    get_active_markets, get_feed_events, format_volume, parse_price, get_sport_tag
)
from sports_rss_client import fetch_all_feeds, fetch_sport_feeds, filter_football_articles, filter_nba_articles


SIGNALS_FILE = Path(__file__).parent.parent / "data" / "signals.json"


# Keywords that indicate YES or NO sentiment
POSITIVE_SIGNALS = [
    "win", "wins", "victory", "score", "scored", "goal", "goals",
    "lead", "leading", "ahead", "champion", "trophy", "title",
    "beat", "defeated", "dominate", "dominant", "strong",
    "confirm", "confirmed", "deal", "signed", "positive"
]

NEGATIVE_SIGNALS = [
    "lose", "loss", "loses", "draw", "drawn", "behind",
    "injury", "injured", "suspended", "ban", "banned",
    "fail", "failed", "crash", "crashed", "eliminated",
    "rumor", "rumoured", "concern", "doubt", "doubtful"
]


def generate_signals(sport_filter: str = None, min_edge: float = 0.10, limit: int = 30) -> dict:
    """
    Generate trading signals by comparing RSS sentiment to Limitless market prices.
    
    Args:
        sport_filter: "Football", "Basketball", or None for both
        min_edge: Minimum edge threshold (0.10 = 10%)
        limit: Max signals to return
    
    Returns:
        Dict with signals list and metadata
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
    
    # Filter articles by sport
    if sport_filter == "Football":
        articles = filter_football_articles(articles)
    elif sport_filter == "Basketball":
        articles = filter_nba_articles(articles)
    
    # Generate signals
    signals = []
    
    for market in markets[:100]:
        signal = _analyze_market(market, articles)
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
        "signals_count": len(signals),
        "signals": signals,
    }
    
    # Save to file
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    return result


def _analyze_market(market: dict, articles: list) -> Optional[dict]:
    """Analyze a single market against RSS articles."""
    
    title = market.get("title", "").lower()
    tags = [t.lower() for t in market.get("tags", []) + market.get("categories", [])]
    slug = market.get("slug", "")
    
    # Extract key entities from title
    keywords = _extract_entities(title)
    
    # Find related articles
    related = []
    for article in articles[:50]:  # Check top 50
        art_text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        
        match_count = 0
        for kw in keywords:
            if kw.lower() in art_text:
                match_count += 1
        
        if match_count >= 1:
            related.append(article)
            if len(related) >= 5:
                break
    
    if not related:
        return None
    
    # Analyze sentiment of related articles
    sentiment_score = _analyze_sentiment(related)
    
    # Get market price
    prices = market.get("prices", [0.5, 0.5])
    try:
        market_yes_pct = float(prices[0]) * 100
    except:
        market_yes_pct = 50
    
    # Calculate edge: news-implied probability vs market price
    news_implied = sentiment_score["implied_probability"]
    edge = abs(news_implied - market_yes_pct)
    
    # Determine direction
    if sentiment_score["score"] > 0:
        direction = "YES"
        recommended_direction = "YES" if news_implied > market_yes_pct else "NO"
    else:
        direction = "NO"
        recommended_direction = "NO" if news_implied < market_yes_pct else "YES"
    
    # Edge calculation: positive edge = market underpriced relative to news
    if recommended_direction == "YES":
        edge = news_implied - market_yes_pct
    else:
        edge = market_yes_pct - news_implied
    
    # Confidence based on article count and sentiment strength
    confidence = _calc_confidence(related, sentiment_score["score"], edge)
    
    # Skip if edge is too small or direction unclear
    if abs(edge) < 5 or abs(sentiment_score["score"]) < 0.1:
        return None
    
    # Build signal
    sport = get_sport_tag(market)
    prices_parsed = parse_price(prices)
    
    signal = {
        "id": f"sig_{slug[:20]}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "market": market.get("title", "Unknown"),
        "slug": slug,
        "url": f"https://limitless.exchange/markets/{slug}",
        "sport": sport,
        "direction": recommended_direction,
        "market_yes_pct": round(market_yes_pct, 1),
        "news_implied_pct": round(news_implied, 1),
        "edge": round(edge, 1),
        "confidence": confidence,
        "volume": format_volume(market.get("volume", "0")),
        "expiration": market.get("expirationDate", "Unknown"),
        "trade_type": market.get("tradeType", "unknown"),
        "related_articles": related[:3],
        "sentiment_breakdown": sentiment_score,
        "keywords": keywords,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    return signal


def _analyze_sentiment(articles: list) -> dict:
    """Analyze sentiment across a list of articles."""
    if not articles:
        return {"score": 0, "positive": 0, "negative": 0, "neutral": 0, "implied_probability": 50}
    
    positive = 0
    negative = 0
    neutral = 0
    
    for article in articles:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        
        pos_count = sum(1 for p in POSITIVE_SIGNALS if p in text)
        neg_count = sum(1 for n in NEGATIVE_SIGNALS if n in text)
        
        if pos_count > neg_count:
            positive += 1
        elif neg_count > pos_count:
            negative += 1
        else:
            neutral += 1
    
    total = len(articles)
    score = (positive - negative) / total if total > 0 else 0
    
    # Convert sentiment to implied probability
    # Score ranges from -1 (all negative) to +1 (all positive)
    # Map to 0-100% where 50% is neutral
    implied_probability = 50 + (score * 50)  # 0-100 range
    implied_probability = max(5, min(95, implied_probability))  # Clamp 5-95%
    
    return {
        "score": round(score, 2),
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "implied_probability": round(implied_probability, 1),
        "article_count": total,
    }


def _calc_confidence(articles: list, sentiment_score: float, edge: float) -> str:
    """Calculate signal confidence level."""
    article_count = len(articles)
    abs_edge = abs(edge)
    
    if article_count >= 3 and abs_edge >= 20:
        return "CRITICAL"
    elif article_count >= 2 and abs_edge >= 15:
        return "HIGH"
    elif article_count >= 1 and abs_edge >= 10:
        return "MEDIUM"
    else:
        return "LOW"


def _extract_entities(title: str) -> list:
    """Extract key entities from market title for article matching."""
    # Common team/player patterns
    entities = []
    
    # Remove common words
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "vs", "vs.", "will", "be", "is", "this", "that", "market", "total", "number", "over", "under"}
    
    words = title.replace("?", "").replace("(", " ").replace(")", " ").replace(",", " ").replace(":", " ").split()
    
    for word in words:
        word = word.strip().lower()
        if len(word) > 2 and word not in stopwords:
            entities.append(word)
    
    return entities[:8]  # Limit to 8 entities


def load_signals() -> dict:
    """Load last generated signals from file."""
    if not SIGNALS_FILE.exists():
        return {"signals": [], "run_id": None}
    try:
        with open(SIGNALS_FILE) as f:
            return json.load(f)
    except:
        return {"signals": [], "run_id": None}
