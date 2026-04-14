"""
group_market_scraper.py — Scrapes match-winner sub-market prices from Limitless HTML pages.

Match-winner markets (marketType="group") contain sub-markets:
- "Bayern München" → YES/NO
- "Draw" → YES/NO
- "Real Madrid" → YES/NO

API `/markets/active` returns prices:[] for group markets.
Real prices are embedded in HTML as JSON in `self.__next_f.push()` chunks.

Regex pattern (raw bytes): \"prices\":[X,Y]
"""

import requests
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def scrape_group_market(slug: str) -> list:
    """
    Fetch a group market page and extract sub-market prices.
    
    Returns list of sub-market dicts:
      {
        "outcome": "Bayern M��nchen" | "Draw" | "Real Madrid",
        "yes_pct": 62.9,
        "no_pct": 37.0,
        "slug": "bayern-munchen-1775034007384",
        "volume": "$1,273.30",
        "volume_raw": 1273299978,
      }
    Returns [] if scrape fails or no sub-markets found.
    """
    url = f"https://limitless.exchange/markets/{slug}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        if r.status_code != 200:
            return []
    except Exception as e:
        logger.warning(f"Failed to fetch {slug}: {e}")
        return []
    
    content = r.content  # raw bytes
    
    # Pattern: \"prices\":[X,Y]
    price_pat = rb'\\"prices\\":\[([0-9.]+),([0-9.]+)\]'
    prices = re.findall(price_pat, content)
    
    # Pattern: \"title\":\"NAME\"
    title_pat = rb'\\"title\\":\\"([^\\]+)\\"'
    titles = re.findall(title_pat, content)
    
    # Pattern: \"slug\":\"NAME\"
    slug_pat = rb'\\"slug\\":\\"([^\\]+)\\"'
    slugs = re.findall(slug_pat, content)
    
    # Pattern: \"volume\":\"RAW\"
    vol_pat = rb'\\"volume\\":\\"([0-9.]+)\\"'
    volumes_raw = re.findall(vol_pat, content)
    
    if not prices or not titles:
        return []
    
    # Build results — titles and slugs include the group market entry first
    # titles[0] = group title, titles[1:] = sub-market titles
    # slugs[0] = group slug, slugs[1:] = sub-market slugs
    results = []
    n_sub = len(prices)  # number of sub-markets
    
    # Titles list: first entry is group title, skip it
    # Titles after that are sub-market titles
    sub_titles = [t.decode() for t in titles[1:1+n_sub]]
    sub_slugs = [s.decode() for s in slugs[1:1+n_sub]]
    
    for i, price_bytes in enumerate(prices[:n_sub]):
        yes_p = float(price_bytes[0])
        no_p = float(price_bytes[1])
        title = sub_titles[i] if i < len(sub_titles) else f"Outcome {i+1}"
        sub_slug = sub_slugs[i] if i < len(sub_slugs) else ""
        
        results.append({
            "outcome": title,
            "yes_pct": yes_p,
            "no_pct": no_p,
            "slug": sub_slug,
            "trade_url": f"https://limitless.exchange/markets/{sub_slug}?r=MOS8U9NKDK" if sub_slug else "",
        })
    
    logger.info(f"Scraped {slug}: {len(results)} sub-markets")
    return results


def enrich_markets_with_sub_prices(markets: list) -> list:
    """
    Take a list of markets from the Limitless API.
    For each marketType="group" market, fetch sub-market prices from HTML.
    Add a 'sub_markets' key to those group entries.
    """
    group_markets = [m for m in markets if m.get("marketType") == "group"]
    
    if not group_markets:
        return markets
    
    for m in group_markets:
        slug = m.get("slug", "")
        if slug:
            sub_markets = scrape_group_market(slug)
            if sub_markets:
                m["sub_markets"] = sub_markets
                # Update group-level price to first sub-market (Bayern/Home) or average
                if sub_markets:
                    m["_display_prices"] = sub_markets[0].get("yes_pct", 50)
    
    return markets
