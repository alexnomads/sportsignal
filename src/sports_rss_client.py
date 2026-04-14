"""
sports_rss_client.py — RSS feed client for sports news.

Sources:
- BBC Sport
- ESPN FC
- Sky Sports Football
- NBA.com
- The Athletic
"""

import feedparser
import re
from datetime import datetime, timezone
from typing import Optional
from dateutil import parser as date_parser


# RSS Feed URLs
RSS_FEEDS = {
    "bbc_sport": {
        "url": "https://feeds.bbci.co.uk/sport/football/rss.xml",
        "sport": "Football",
        "name": "BBC Sport",
    },
    "bbc_basketball": {
        "url": "https://feeds.bbci.co.uk/sport/basketball/rss.xml",
        "sport": "Basketball",
        "name": "BBC Sport",
    },
    "espn_football": {
        "url": "https://www.espn.com/espn/rss/football/news",
        "sport": "Football",
        "name": "ESPN FC",
    },
    "espn_nba": {
        "url": "https://www.espn.com/espn/rss/nba/news",
        "sport": "Basketball",
        "name": "ESPN NBA",
    },
    # Transfermarkt — Transfer news (high signal value)
    "transfermarkt_uk": {
        "url": "https://www.transfermarkt.co.uk/rss/news",
        "sport": "Football",
        "name": "Transfermarkt UK",
    },
    "transfermarkt_it": {
        "url": "https://www.transfermarkt.it/rss/news",
        "sport": "Football",
        "name": "Transfermarkt IT",
    },
    "transfermarkt_es": {
        "url": "https://www.transfermarkt.es/rss/news",
        "sport": "Football",
        "name": "Transfermarkt ES",
    },
    "sky_football": {
        "url": "https://www.skysports.com/rss/12040",
        "sport": "Football",
        "name": "Sky Sports",
    },
    "guardian_football": {
        "url": "https://www.theguardian.com/football/rss",
        "sport": "Football",
        "name": "The Guardian",
    },
    "athletic_football": {
        "url": "https://theathletic.com/rss/football/",
        "sport": "Football",
        "name": "The Athletic",
    },
}


# Keywords for sport filtering
FOOTBALL_KEYWORDS = [
    "football", "soccer", "premier league", "epl", "la liga", "serie a",
    "bundesliga", "ligue 1", "champions league", "europa league",
    "fa cup", "world cup", "euro", "psg", "real madrid", "barcelona",
    "manchester", "liverpool", "arsenal", "chelsea", "bayern", "juventus",
    "messi", "ronaldo", "mbappe", "haaland", "transfer", "match", "goal",
    "atletico", "atletico madrid", "barcelona"
]

NBA_KEYWORDS = [
    "nba", "basketball", "lebron", "lakers", "warriors", "celtics",
    "nets", "clippers", "suns", "bucks", "heat", "76ers", "mavericks",
    "nuggets", "playoffs", "draft", "all-star", " finals", "conference",
    "game ", "points", "triple-double", "dunk", "nba finals"
]


def fetch_feed(feed_key: str) -> list:
    """Fetch a single RSS feed and return articles."""
    feed_info = RSS_FEEDS.get(feed_key)
    if not feed_info:
        return []
    
    try:
        feed = feedparser.parse(feed_info["url"])
        articles = []
        
        for entry in feed.entries[:20]:  # Limit entries
            article = {
                "title": entry.get("title", "No title"),
                "link": entry.get("link", ""),
                "summary": _clean_summary(entry.get("summary", "")),
                "source": feed_info["name"],
                "sport": feed_info["sport"],
                "published": _parse_date(entry.get("published")),
                "published_ago": "",
                "is_breaking": _is_breaking(entry.get("title", "")),
                "keywords": _extract_keywords(entry.get("title", ""), entry.get("summary", "")),
            }
            article["published_ago"] = _time_ago(article["published"])
            articles.append(article)
        
        return articles
    except Exception as e:
        print(f"Error fetching {feed_key}: {e}")
        return []


def fetch_all_feeds() -> dict:
    """Fetch all RSS feeds and return combined results."""
    all_articles = []
    feed_names = []
    
    for feed_key in RSS_FEEDS:
        articles = fetch_feed(feed_key)
        all_articles.extend(articles)
        if articles:
            feed_names.append(feed_key)
    
    # Sort by published date
    all_articles.sort(key=lambda x: x.get("published", datetime.min), reverse=True)
    
    return {
        "articles": all_articles,
        "feeds": feed_names,
        "count": len(all_articles),
    }


def fetch_sport_feeds(sport: str) -> list:
    """Fetch feeds for a specific sport only."""
    articles = []
    for feed_key, info in RSS_FEEDS.items():
        if info["sport"].lower() == sport.lower():
            articles.extend(fetch_feed(feed_key))
    
    articles.sort(key=lambda x: x.get("published", datetime.min), reverse=True)
    return articles


def filter_football_articles(articles: list) -> list:
    """Filter articles to football-related only."""
    return [
        a for a in articles
        if any(kw.lower() in (a.get("title", "") + a.get("summary", "")).lower()
               for kw in FOOTBALL_KEYWORDS)
    ]


def filter_nba_articles(articles: list) -> list:
    """Filter articles to NBA-related only."""
    return [
        a for a in articles
        if any(kw.lower() in (a.get("title", "") + a.get("summary", "")).lower()
               for kw in NBA_KEYWORDS)
    ]


def _clean_summary(summary: str) -> str:
    """Remove HTML tags from summary."""
    if not summary:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', summary)
    # Decode HTML entities
    clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    clean = clean.replace('&quot;', '"').replace('&#39;', "'")
    # Truncate
    if len(clean) > 300:
        clean = clean[:300] + "..."
    return clean.strip()


def _parse_date(date_str: str) -> datetime:
    """Parse RSS date string to datetime."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        return date_parser.parse(date_str).astimezone(timezone.utc)
    except:
        return datetime.now(timezone.utc)


def _time_ago(dt: datetime) -> str:
    """Format datetime as 'Xh ago' or 'Xd ago'."""
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    diff = now - dt
    hours = diff.total_seconds() / 3600
    
    if hours < 1:
        return f"{int(hours * 60)}m ago"
    elif hours < 24:
        return f"{int(hours)}h ago"
    else:
        return f"{int(hours / 24)}d ago"


def _is_breaking(title: str) -> bool:
    """Detect breaking news from title keywords."""
    breaking = ["breaking", "live", "exclusive", "just in", "confirmed"]
    return any(b in title.lower() for b in breaking)


def _extract_keywords(title: str, summary: str) -> list:
    """Extract relevant keywords from article."""
    text = (title + " " + summary).lower()
    keywords = []
    
    teams = [
        "manchester united", "manchester city", "liverpool", "arsenal",
        "chelsea", "tottenham", "real madrid", "barcelona", "atletico madrid",
        "bayern munich", "borussia dortmund", "psg", "juventus", "ac milan",
        "inter milan", "lakers", "warriors", "celtics", "heat", "bucks",
        "suns", "nuggets", "mavericks", "clippers"
    ]
    
    players = [
        "messi", "ronaldo", "mbappe", "haaland", "saka", "bellingham",
        "lebron", "curry", "durant", "giannis", "jokic", "luka",
        "neymar", "vinicius", "bellingham"
    ]
    
    for t in teams:
        if t in text:
            keywords.append(t.title())
    
    for p in players:
        if p in text:
            keywords.append(p.title())
    
    return list(set(keywords))[:5]
