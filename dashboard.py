"""
SportSignal Dashboard - Streamlit dashboard for sports prediction market signals.
Merged view: Markets + Signals in one unified table. Journal: Paper trading log.
Powered by Limitless Exchange API on Base blockchain.
"""

import os
from pathlib import Path
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timezone
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from limitless_client import get_active_markets, format_volume, get_sport_tag
from signal_generator import generate_signals, load_signals
from predictions_journal import (
    load_journal, add_prediction, get_active_predictions,
    get_resolved_predictions, get_journal_stats, delete_prediction,
    refresh_all_predictions, export_journal_csv
)

# Page config
st.set_page_config(
    page_title="⚽ SportSignal - Sports Markets on Base",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark theme CSS - fonts bumped +3px
st.html("""
<style>
    .stApp { background-color: #0a0a0f; color: #e8e8e8; }
    [data-testid="stSidebar"] { background-color: #111118; border-right: 1px solid #222230; }
    .stMetric { background: #111118; border-radius: 8px; padding: 12px 16px; }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; color: #ffffff; }
    div[data-testid="stMetricLabel"] { color: #999999; font-size: 0.85rem; opacity: 1 !important; }
    div[data-testid="stMetricLabel"] span { color: #999999; opacity: 1 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: #111118; border-radius: 8px 8px 0 0; padding: 8px 16px; }
    .stTabs [aria-selected="true"] { background-color: #1a1a28; }
    .stButton > button { border-radius: 8px; }
    .yes-price { color: #22c55e; font-weight: bold; }
    .no-price { color: #ef4444; font-weight: bold; }
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #0a0a0f; }
    ::-webkit-scrollbar-thumb { background: #333; border-radius: 4px; }
    section[data-testid="stHorizontalBlock"] .stMetric label,
    section[data-testid="stHorizontalBlock"] div[class*="Metric"] label {
        color: #999 !important; opacity: 1 !important;
    }
    /* Market card */
    .mkt-card {
        background: #111118;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 6px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
    }
    .mkt-card.critical { border-left: 3px solid #ef4444; }
    .mkt-card.high     { border-left: 3px solid #f97316; }
    .mkt-card.medium   { border-left: 2px solid #eab308; }
    .mkt-card.default  { border-left: 2px solid #2a2a3a; }
    .mkt-title { flex: 1 1 100%; font-weight: 600; color: #e8e8e8; font-size: 19px; line-height: 1.3; }
    .mkt-sport { font-size: 19px; flex: 0 0 auto; }
    .mkt-yes   { color: #22c55e; font-weight: 800; font-size: 18px; flex: 0 0 auto; }
    .mkt-no    { color: #ef4444; font-weight: 700; font-size: 17px; flex: 0 0 auto; }
    .mkt-edge  { font-weight: 800; font-size: 17px; flex: 0 0 auto; }
    .mkt-dir   { font-weight: 700; font-size: 15px; flex: 0 0 auto; }
    .mkt-conf  { font-size: 16px; flex: 0 0 auto; color: #888; }
    .mkt-sources { font-size: 13px; flex: 0 0 auto; color: #666; }
    .mkt-vol   { font-size: 13px; flex: 0 0 auto; color: #666; }
    .mkt-trade a {
        background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
        color: white; padding: 6px 12px; border-radius: 6px;
        text-decoration: none; font-weight: 700; font-size: 16px; flex: 0 0 auto;
    }
    /* Match Row */
    .match-row {
        background: #111118; border-radius: 10px;
        border: 1px solid #1e1e2a; margin-bottom: 10px; overflow: hidden;
    }
    .match-header {
        display: flex; align-items: center; gap: 8px;
        padding: 10px 16px; background: #14141c;
        border-bottom: 1px solid #1e1e2a; font-size: 17px; flex-wrap: wrap;
    }
    .match-league { color: #f97316; font-weight: 700; white-space: nowrap; }
    .match-teams { color: #ccc; font-weight: 600; flex: 1; }
    .match-meta { color: #555; font-size: 13px; white-space: nowrap; }
    .match-outcomes { display: flex; }
    .mkt-outcome {
        flex: 1; padding: 12px 14px; text-align: center;
        border-right: 1px solid #1e1e2a;
    }
    .mkt-outcome:last-child { border-right: none; }
    .mkt-outcome-team { color: #aaa; font-size: 17px; font-weight: 600; margin-bottom: 4px; }
    .mkt-outcome-pct { color: #22c55e; font-size: 24px; font-weight: 900; }
    .mkt-outcome-edge { font-size: 18px; font-weight: 700; margin-top: 2px; }
    .mkt-outcome-conf { font-size: 17px; margin-top: 2px; }
    .mkt-outcome-dir { font-size: 15px; font-weight: 700; }
    .mkt-outcome-btn {
        display: inline-block; margin-top: 6px;
        background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
        color: white; padding: 5px 12px; border-radius: 5px;
        text-decoration: none; font-weight: 700; font-size: 13px;
        transition: transform 0.15s ease;
    }
    .mkt-outcome-btn:hover { transform: scale(1.08) rotate(-2deg); box-shadow: 0 4px 15px rgba(74,144,217,0.4); }
    .mkt-outcome-pct:hover, .mkt-outcome-edge:hover, .mkt-outcome-conf:hover, .mkt-outcome-team:hover {
        transform: scale(1.08); cursor: help;
    }
    /* WHY reasoning - bigger font */
    .why-row { font-size: 15px; color: #888; margin-top: 4px; line-height: 1.6; text-align: left; }
    .why-rss { color: #f0b429; display: block; }
    .why-tw   { color: #1d9bf0; display: block; }
    .why-api  { color: #22c55e; display: block; }
    .why-imp  { color: #888; display: block; }
    .why-none { color: #444; font-style: italic; }
    .why-detail { color: #666; font-size: 13px; margin-top: 2px; }
    /* Column headers - kept for layout compatibility */
    .match-col-headers { display: flex; border-bottom: 1px solid #1e1e2a; }
    /* News ticker */
    .news-ticker-wrap {
        background: #0d0d14; border-top: 1px solid #1e1e2a;
        padding: 0; overflow: hidden; white-space: nowrap; position: relative;
    }
    .news-ticker-wrap::before, .news-ticker-wrap::after {
        content: ""; position: absolute; top: 0; bottom: 0; width: 30px; z-index: 2; pointer-events: none;
    }
    .news-ticker-wrap::before { left: 0; background: linear-gradient(to right, #0d0d14, transparent); }
    .news-ticker-wrap::after  { right: 0; background: linear-gradient(to left, #0d0d14, transparent); }
    .news-ticker {
        display: inline-block; padding: 8px 0; font-size: 14px; color: #888;
        animation: ticker-scroll 30s linear infinite; white-space: nowrap;
    }
    .news-ticker:hover { animation-play-state: paused; }
    .ticker-item { display: inline; }
    .ticker-src { color: #f97316; font-weight: 700; }
    .ticker-link { color: #6ab0ff; text-decoration: none; }
    .ticker-link:hover { text-decoration: underline; }
    @keyframes ticker-scroll {
        0%   { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    /* No-signal market - show news sources at bottom */
    .mkt-news-row { font-size: 13px; color: #555; margin-top: 4px; flex: 1 1 100%; padding-left: 4px; }
    .mkt-news-row .art-item { color: #888; margin-right: 8px; }
    .mkt-news-row .art-title { color: #aaa; }
    @media (max-width: 600px) {
        .match-outcomes { flex-direction: column; }
        .mkt-outcome { border-right: none; border-bottom: 1px solid #1e1e2a; text-align: left; display: flex; align-items: center; gap: 8px; padding: 8px 14px; }
        .mkt-outcome-team { margin-bottom: 0; }
        .mkt-outcome-pct { font-size: 18px; }
        .mkt-outcome-edge { margin-top: 0; }
        .mkt-outcome-conf { display: none; }
        .mkt-outcome-btn { margin-top: 0; margin-left: auto; }
    }
    @media (min-width: 900px) {
        .mkt-card { flex-wrap: nowrap; align-items: center; }
        .mkt-title { flex: 1 !important; min-width: 0; }
    }
</style>
""")

# Session state
defaults = {"view_mode": "markets", "sport_filter": "All"}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Navigation
nav_cols = st.columns([1, 1])
current_view = st.session_state.get("view_mode", "markets")
with nav_cols[0]:
    if st.button("⚽ Markets", type="primary" if current_view == "markets" else "secondary", use_container_width=True):
        st.session_state["view_mode"] = "markets"
        st.rerun()
with nav_cols[1]:
    if st.button("📓 Journal", type="primary" if current_view == "journal" else "secondary", use_container_width=True):
        st.session_state["view_mode"] = "journal"
        st.rerun()

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# MARKETS VIEW
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.get("view_mode") == "markets":
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1, 1, 1, 1])
    with ctrl1:
        sport_filter = st.selectbox(
            "Sport", ["All", "Football", "Basketball"],
            index=["All", "Football", "Basketball"].index(st.session_state.get("sport_filter", "All")),
            label_visibility="collapsed"
        )
        if sport_filter != st.session_state.get("sport_filter"):
            st.session_state["sport_filter"] = sport_filter
            st.rerun()
    with ctrl2:
        sort_by = st.selectbox("Sort", ["Edge ↓", "Volume ↓", "YES% ↓", "YES% ↑"], index=0, label_visibility="collapsed")
    with ctrl3:
        min_edge = st.slider("Min Edge %", 0, 50, 0, 5, help="Hide markets below this edge", label_visibility="collapsed")
    with ctrl4:
        if st.button("🔄 Refresh", type="primary", use_container_width=True):
            with st.spinner("Fetching markets + signals..."):
                sport = None if sport_filter == "All" else sport_filter
                result = generate_signals(sport_filter=sport, min_edge=0.05)
                st.success(f"✅ {result.get('signals_count', 0)} signals · 🐦 {result.get('tweets_fetched', 0)} tweets · 📰 {result.get('articles_fetched', 0)} articles")
                st.rerun()

    # Load data
    data = load_signals()
    signals = data.get("signals", [])
    signal_by_slug = {s.get("slug"): s for s in signals}

    with st.spinner("Loading markets..."):
        markets_data = get_active_markets(limit=100, sort_by="high_value", automation_type="sports")
        markets = markets_data.get("data", [])

    # Build enriched list
    enriched = []
    for m in markets:
        slug = m.get("slug", "")
        mtype = m.get("marketType", "")
        sub_markets = m.get("markets", [])
        if mtype == "group" and sub_markets:
            for sm in sub_markets:
                sm_slug = sm.get("slug", "")
                sm_prices = sm.get("prices", [0.5, 0.5])
                try:
                    sm_yes = round(float(sm_prices[0]) * 100, 1)
                    sm_no = round(float(sm_prices[1]) * 100, 1)
                except:
                    sm_yes, sm_no = 50, 50
                sig = signal_by_slug.get(sm_slug, {})
                enriched.append({
                    "slug": sm_slug, "title": sm.get("title", ""),
                    "sport": get_sport_tag(m), "yes_pct": sm_yes, "no_pct": sm_no,
                    "volume": m.get("volumeFormatted", "$0"),
                    "volume_raw": int(m.get("volume", "0") or "0"),
                    "expiration": m.get("expirationDate", "N/A"),
                    "tags": m.get("tags", [])[:2],
                    "market_type": "group_sub",
                    "group_title": m.get("title", ""),
                    "group_slug": slug,
                    "trade_url": f"https://limitless.exchange/markets/{sm_slug}?r=MOS8U9NKDK",
                    "has_signal": bool(sig), "direction": sig.get("direction"),
                    "edge": sig.get("edge", 0), "implied_pct": sig.get("news_implied_pct"),
                    "confidence": sig.get("confidence", "LOW"),
                    "rss_sentiment": sig.get("rss_sentiment", {}),
                    "twitter_sentiment": sig.get("twitter_sentiment"),
                    "api_football": sig.get("api_football"),
                    "related_tweets": sig.get("related_tweets", []),
                    "related_articles": sig.get("related_articles", []),
                })
        else:
            prices = m.get("prices", [0.5, 0.5])
            try:
                yes_pct = round(float(prices[0]) * 100, 1)
                no_pct = round(float(prices[1]) * 100, 1)
            except:
                yes_pct, no_pct = 50, 50
            sig = signal_by_slug.get(slug, {})
            enriched.append({
                "slug": slug, "title": m.get("title", "Unknown"),
                "sport": get_sport_tag(m), "yes_pct": yes_pct, "no_pct": no_pct,
                "volume": m.get("volumeFormatted", "$0"),
                "volume_raw": int(m.get("volume", "0") or "0"),
                "expiration": m.get("expirationDate", "N/A"),
                "tags": m.get("tags", [])[:2],
                "market_type": mtype or "standard",
                "trade_url": f"https://limitless.exchange/markets/{slug}?r=MOS8U9NKDK",
                "has_signal": bool(sig), "direction": sig.get("direction"),
                "edge": sig.get("edge", 0), "implied_pct": sig.get("news_implied_pct"),
                "confidence": sig.get("confidence", "LOW"),
                "rss_sentiment": sig.get("rss_sentiment", {}),
                "twitter_sentiment": sig.get("twitter_sentiment"),
                "api_football": sig.get("api_football"),
                "related_tweets": sig.get("related_tweets", []),
                "related_articles": sig.get("related_articles", []),
            })

    # Filter & sort
    if sport_filter != "All":
        enriched = [e for e in enriched if e.get("sport") == sport_filter]
    if min_edge > 0:
        enriched = [e for e in enriched if e.get("edge", 0) >= min_edge]
    if sort_by == "Edge ↓":
        enriched.sort(key=lambda x: x.get("edge", 0), reverse=True)
    elif sort_by == "Volume ↓":
        enriched.sort(key=lambda x: x.get("volume_raw", 0), reverse=True)
    elif sort_by == "YES% ↓":
        enriched.sort(key=lambda x: x.get("yes_pct", 50), reverse=True)
    else:
        enriched.sort(key=lambda x: x.get("yes_pct", 50))

    if not enriched:
        st.info("No markets match your filters. Try adjusting.")
    else:
        from collections import OrderedDict
        match_groups = OrderedDict()
        standard_markets = []
        for e in enriched:
            if e.get("market_type") == "group_sub" and e.get("group_slug"):
                match_groups.setdefault(e.get("group_slug"), []).append(e)
            else:
                standard_markets.append(e)

        # ── Match Rows ──────────────────────────────────────────────────────
        if match_groups:
            for group_slug, outcomes in match_groups.items():
                if not outcomes:
                    continue
                parent = outcomes[0]
                group_title = parent.get("group_title", "")
                sport_icon = "⚽" if parent.get("sport") == "Football" else "🏀"
                volume = parent.get("volume", "$0")
                expiration = parent.get("expiration", "N/A")
                tags = parent.get("tags", [])
                league_tag = next((t for t in tags if any(l in t for l in ["UCL","UEL","UECL","Premier","La Liga","Serie","Bundes","Ligue","NBA"])), tags[0] if tags else "Football")
                league_icon = "🏆" if any(l in league_tag for l in ["UCL","UEL","UECL"]) else "🏀" if "NBA" in league_tag else "⚽"

                def outcome_sort(o):
                    t = o.get("title","").lower()
                    if t == "draw": return 1
                    if parent.get("group_title","").lower().startswith(t): return 0
                    return 2
                outcomes_sorted = sorted(outcomes, key=outcome_sort)

                all_articles = {}
                for o in outcomes_sorted:
                    for a in o.get("related_articles", []):
                        key = a.get("title","")
                        if key and key not in all_articles:
                            all_articles[key] = a

                # Build outcome columns
                outcome_cols = ""
                for o in outcomes_sorted:
                    yes_pct = o.get("yes_pct", 50)
                    edge = o.get("edge", 0)
                    conf = o.get("confidence", "LOW")
                    trade_url = o.get("trade_url")
                    title_short = o.get("title","")[:20]
                    edge_color = "#ef4444" if edge > 20 else "#f97316" if edge > 10 else "#eab308"
                    direction = o.get("direction", "")
                    dir_color = "#22c55e" if direction == "YES" else "#ef4444" if direction == "NO" else "#888"

                    # WHY reasoning - expanded with more detail
                    rss_s = o.get("rss_sentiment") or {}
                    tw_s = o.get("twitter_sentiment") or {}
                    api_fb = o.get("api_football") or {}

                    why_lines = []
                    if rss_s.get("article_count", 0) > 0:
                        rss_imp = rss_s.get("implied_probability", 0)
                        rss_n = rss_s.get("article_count", 0)
                        arts = o.get("related_articles", [])
                        art_titles = " | ".join(a.get("title","")[:35] for a in arts[:2])
                        why_lines.append(f'<span class="why-rss">📰 {rss_n} articles → {rss_imp:.0f}%</span>')
                        if art_titles:
                            why_lines.append(f'<div class="why-detail">"{art_titles}"</div>')
                    if tw_s.get("tweet_count", 0) > 0:
                        tw_imp = tw_s.get("implied_probability", 0)
                        tw_n = tw_s.get("tweet_count", 0)
                        transfers = tw_s.get("transfer_signals", 0)
                        injuries = tw_s.get("injury_signals", 0)
                        tags_list = []
                        if transfers: tags_list.append("transfer")
                        if injuries: tags_list.append("injury")
                        tag_str = f" [{', '.join(tags_list)}]" if tags_list else ""
                        why_lines.append(f'<span class="why-tw">🐦 {tw_n} tweets → {tw_imp:.0f}%{tag_str}</span>')
                    if api_fb.get("api_implied") is not None:
                        api_imp = api_fb.get("api_implied", 0)
                        api_conf = api_fb.get("api_confidence", "LOW")
                        pred_advice = api_fb.get("predictions", {}).get("advice") or ""
                        h2h = api_fb.get("h2h_avg_goals")
                        home_form = api_fb.get("home_form", "") or ""
                        away_form = api_fb.get("away_form", "") or ""
                        why_lines.append(f'<span class="why-api">⚽ API-FB {api_imp:.0f}% ({api_conf})</span>')
                        if pred_advice:
                            why_lines.append(f'<div class="why-detail">💡 {pred_advice}</div>')
                        if h2h:
                            why_lines.append(f'<div class="why-detail">📊 H2H avg goals: {h2h:.1f}</div>')
                        if home_form and away_form:
                            why_lines.append(f'<div class="why-detail">📈 Form: {home_form[:5]} vs {away_form[:5]}</div>')
                    if api_fb.get("pred_home_win") is not None:
                        home_win = api_fb.get("pred_home_win", 0)
                        draw_p = api_fb.get("pred_draw", 0)
                        away_win = api_fb.get("pred_away_win", 0)
                        if home_win > 0:
                            why_lines.append(f'<div class="why-detail">🎯 Pred: {home_win:.0f}% / {draw_p:.0f}% / {away_win:.0f}% (H/D/A)</div>')

                    why_html = '<div class="why-row">' + '<br>'.join(why_lines) + '</div>' if why_lines else '<div class="why-row why-none">No signals detected</div>'

                    conf_str = "🔴" if conf == "CRITICAL" else "🟠" if conf == "HIGH" else "🟡" if conf == "MEDIUM" else ""
                    outcome_cols += f"""
                        <div class="mkt-outcome">
                            <div class="mkt-outcome-team">{title_short}</div>
                            <div class="mkt-outcome-pct">{yes_pct:.0f}%</div>
                            <div class="mkt-outcome-edge" style="color:{edge_color};">+{edge:.0f}%</div>
                            <div class="mkt-outcome-dir" style="color:{dir_color};">{conf_str} {direction or '—'}</div>
                            {why_html}
                            <a class="mkt-outcome-btn" href="{trade_url}" target="_blank">Trade →</a>
                        </div>
                    """

                best_conf = max((o.get("confidence","LOW") for o in outcomes_sorted),
                               key=lambda c: {"LOW":0,"MEDIUM":1,"HIGH":2,"CRITICAL":3}.get(c,0))
                border_color = "#ef4444" if best_conf=="CRITICAL" else "#f97316" if best_conf=="HIGH" else "#2a2a3a"

                news_ticker = ""
                if all_articles:
                    ticker_items = " &nbsp;·&nbsp; ".join(
                        f'<span class="ticker-item"><span class="ticker-src">{a.get("source","RSS")}</span> {a.get("published_ago","")} — {a.get("title","")[:80]}</span>'
                        for a in list(all_articles.values())[:4]
                    )
                    ticker_items += f' &nbsp;·&nbsp; <span class="ticker-item"><span class="ticker-src">Limitless</span> — <a href="https://limitless.exchange/markets/{group_slug}?r=MOS8U9NKDK" target="_blank" class="ticker-link">Trade {group_title[2:40]} on Limitless →</a></span>'
                    ticker_full = ticker_items + ' &nbsp;&nbsp;&nbsp; ' + ticker_items
                    news_ticker = f'<div class="news-ticker-wrap"><div class="news-ticker">{ticker_full}</div></div>'

                st.html(f"""
                <div class="match-row" style="border-left: 3px solid {border_color};">
                    <div class="match-header">
                        <span class="match-league">{league_icon} {league_tag}</span>
                        <span class="match-teams">{group_title[2:60]}</span>
                        <span class="match-meta">💰 {volume} &nbsp;📅 {expiration[:9]}</span>
                    </div>
                    <div class="match-outcomes">{outcome_cols}</div>
                    {news_ticker}
                </div>
                """)

        # ── Standard Market Cards ─────────────────────────────────────────
        if standard_markets:
            if match_groups:
                st.html('<div style="height:16px"></div><div style="font-size:14px; color:#555; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em;">Other Markets</div>')

            for e in standard_markets:
                slug = e.get("slug")
                yes_pct = e.get("yes_pct", 50)
                edge = e.get("edge", 0)
                conf = e.get("confidence", "LOW")
                direction = e.get("direction")
                has_signal = e.get("has_signal", False)

                if conf == "CRITICAL": card_class = "critical"
                elif conf == "HIGH": card_class = "high"
                elif conf == "MEDIUM": card_class = "medium"
                else: card_class = "default"

                if edge > 0:
                    edge_str = f"+{edge:.1f}%"
                    edge_color = "#ef4444" if edge > 20 else "#f97316" if edge > 10 else "#eab308"
                else:
                    edge_str = "-"; edge_color = "#555"

                if direction == "YES": dir_str, dir_color = "✅ YES", "#22c55e"
                elif direction == "NO": dir_str, dir_color = "❌ NO", "#ef4444"
                else: dir_str, dir_color = "—", "#888"

                conf_emoji = "🔴" if conf == "CRITICAL" else "🟠" if conf == "HIGH" else "🟡" if conf == "MEDIUM" else ""

                srcs = []
                rss_n = (e.get("rss_sentiment") or {}).get("article_count", 0)
                tw_n = (e.get("twitter_sentiment") or {}).get("tweet_count", 0)
                if rss_n > 0: srcs.append(f"📰{rss_n}")
                if tw_n > 0: srcs.append(f"🐦{tw_n}")
                if e.get("api_football"): srcs.append("⚽")
                src_str = " ".join(srcs) if srcs else "—"
                src_color = "#f0b429" if rss_n > 0 else "#1d9bf0" if tw_n > 0 else "#555"

                sport_icon = "⚽" if e.get("sport") == "Football" else "🏀"
                trade_url = e.get("trade_url")
                title = e.get("title", "")[:60]

                # Build news row for no-signal markets
                news_row = ""
                if not has_signal:
                    arts = e.get("related_articles", [])
                    tweets = e.get("related_tweets", [])
                    if arts or tweets:
                        news_items = []
                        for a in arts[:3]:
                            news_items.append(f'<span class="art-item">📰 <span class="art-title">{a.get("title","")[:45]}</span></span>')
                        for t in tweets[:2]:
                            news_items.append(f'<span class="art-item">🐦 <span class="art-title">{t.get("title","")[:45]}</span></span>')
                        if news_items:
                            news_row = f'<div class="mkt-news-row">{" &nbsp;".join(news_items)}</div>'

                st.html(f"""
                <div class="mkt-card {card_class}">
                    <div class="mkt-title">{sport_icon} {title}</div>
                    <div class="mkt-yes">{yes_pct:.0f}%</div>
                    <div class="mkt-edge" style="color: {edge_color};">{edge_str}</div>
                    <div class="mkt-dir" style="color: {dir_color};">{conf_emoji} {dir_str}</div>
                    <div class="mkt-sources" style="color:{src_color};">{src_str}</div>
                    <div class="mkt-trade"><a href="{trade_url}" target="_blank">Trade →</a></div>
                    {news_row}
                </div>
                """)

        st.divider()
        st.caption(
            f"Showing {len(enriched)} markets | "
            "Edge = Model Probability - Market Price | "
            "Sources: 📰 RSS · 🐦 Twitter · ⚽ API-Football | "
            f"Last refresh: {data.get('timestamp', 'N/A')[:19] if data.get('timestamp') else 'Never'}"
        )

# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAL VIEW
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.get("view_mode") == "journal":
    st.markdown("## 📓 Predictions Journal")
    st.caption("Track your sports prediction trades - paper trading on Limitless")

    stats = get_journal_stats()
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
    with c1: st.metric("📊 Total", stats["total"])
    with c2: st.metric("⚡ Active", stats["active"])
    with c3: st.metric("✅ Won", stats["won"])
    with c4: st.metric("❌ Lost", stats["lost"])
    with c5: st.metric("🟢 Winning", stats.get("winning", 0))
    with c6: st.metric("🔴 Losing", stats.get("losing", 0))

    col_refresh, col_export = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Refresh", type="primary"):
            with st.spinner("Checking prices..."):
                refresh_all_predictions()
                st.rerun()
    with col_export:
        csv = export_journal_csv()
        if csv:
            st.download_button("📥 Export CSV", csv, "sport_predictions_journal.csv", "text/csv")

    st.divider()
    tab_active, tab_resolved = st.tabs(["⚡ Active", "✅ Resolved"])

    with tab_active:
        active = get_active_predictions()
        if not active:
            st.info("No active predictions. Add one below!")
        else:
            for pred in active:
                direction = pred.get("direction", "YES")
                entry = pred.get("entry_probability", 0)
                current = pred.get("current_price")
                bet = pred.get("bet_amount")
                if current:
                    current_pct = round(current * 100, 1)
                    is_winning = (direction == "YES" and current > pred.get("entry_price", 0)) or \
                                 (direction == "NO" and current < pred.get("entry_price", 1))
                else:
                    current_pct = None; is_winning = None
                col_q, col_price, col_del = st.columns([4, 1, 0.3])
                with col_q:
                    url = pred.get("market_url", "")
                    q = pred.get("market_question", "Unknown")
                    if url: st.markdown(f"**{direction}** - [{q[:55]}...]({url})")
                    else: st.markdown(f"**{direction}** - {q[:55]}...")
                    bet_str = f" | 💰 ${bet:.0f}" if bet else ""
                    st.caption(f"Entry: {entry:.1f}%{bet_str} | {pred.get('created_at', '')[:10]}")
                with col_price:
                    if current_pct:
                        color = "#22c55e" if is_winning else ("#ef4444" if is_winning is False else "#8b949e")
                        st.markdown(f"<span style='color:{color};font-weight:bold;'>Now: {current_pct:.1f}%</span>", unsafe_allow_html=True)
                with col_del:
                    if st.button("🗑️", key=f"del_{pred['id']}"):
                        delete_prediction(pred["id"]); st.rerun()
                if pred.get("notes"): st.caption(f"📝 {pred['notes'][:80]}")
                st.divider()

    with tab_resolved:
        resolved = get_resolved_predictions()
        if not resolved:
            st.info("No resolved predictions yet.")
        else:
            table = []
            for p in resolved:
                entry = p.get("entry_probability", 0)
                exit_p = p.get("exit_price", 0)
                bet = p.get("bet_amount")
                won = p.get("outcome") == "won"
                if bet and bet > 0 and exit_p > 0:
                    shares = bet / entry if entry > 0 else 0
                    pnl = shares * (1 - entry) if won else -shares * entry
                    pnl_str = f"${pnl:+.0f}"
                else:
                    pnl_str = "-"
                table.append({
                    "Dir": p.get("direction", ""),
                    "Question": (p.get("market_question") or "")[:45],
                    "Entry%": entry,
                    "Exit%": round(exit_p * 100, 1) if exit_p else "-",
                    "Bet": f"${bet:.0f}" if bet else "-",
                    "P&L": pnl_str,
                    "Result": "✅ Won" if won else "❌ Lost",
                })
            if table:
                df = pd.DataFrame(table)
                st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    prefill = st.session_state.pop("prefill_url", "") if "prefill_url" in st.session_state else ""
    prefill_prob = st.session_state.pop("prefill_prob", 50) if "prefill_prob" in st.session_state else 50
    prefill_q = st.session_state.pop("prefill_question", "") if "prefill_question" in st.session_state else ""

    with st.expander("**➕ Add Prediction**", expanded=bool(prefill)):
        with st.form("add_pred_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Market URL**")
                url = st.text_input("URL", value=prefill, placeholder="https://limitless.exchange/markets/...", label_visibility="collapsed")
                st.markdown("**Direction**")
                direction = st.radio("Dir", options=["YES", "NO"], index=0, horizontal=True, label_visibility="collapsed")
                st.markdown("**Bet Amount**")
                bet = st.number_input("Bet", min_value=0.0, max_value=10000.0, value=0.0, step=10.0, label_visibility="collapsed")
            with c2:
                st.markdown("**Instruments**")
                instruments = st.text_input("Instruments", placeholder="EPL, Lakers...", label_visibility="collapsed")
                st.markdown("**Notes**")
                notes = st.text_area("Notes", placeholder="Why this prediction?", label_visibility="collapsed", height=120)
            st.markdown("**Entry Probability %**")
            entry_prob = st.slider("Entry", min_value=0.0, max_value=100.0, value=float(prefill_prob), step=0.5)
            submitted = st.form_submit_button("💾 Save", type="primary")
        if submitted and url:
            try:
                q = prefill_q or url.split("/")[-1].replace("-", " ").title()
                add_prediction(market_question=q, market_url=url, direction=direction,
                    entry_price=entry_prob / 100, notes=notes,
                    instruments=[i.strip() for i in instruments.split(",") if i.strip()],
                    bet_amount=bet if bet > 0 else None)
                st.success(f"✅ **{direction}** @ {entry_prob:.1f}%")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        elif submitted and not url:
            st.warning("Enter a market URL")

# Footer
st.divider()
st.html("""
<div style="background: linear-gradient(135deg, #0f1a2a 0%, #1a1a2e 100%);
    border: 1px solid #2a4a7a; border-radius: 10px; padding: 14px 20px; margin: 8px 0;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;">
    <div>
        <div style="font-size: 15px; font-weight: 600; color: #e8e8e8;">🏆 Earn rewards - trade on Limitless Exchange</div>
        <div style="font-size: 13px; color: #666; margin-top: 2px;">Sports prediction markets on Base L2 blockchain</div>
    </div>
    <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="
        display: inline-block; background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
        color: white; padding: 8px 16px; border-radius: 8px;
        text-decoration: none; font-weight: 600; font-size: 14px;">Sign Up + Trade →</a>
</div>
""")
st.caption("SportSignal · Powered by Limitless Exchange on Base L2")
