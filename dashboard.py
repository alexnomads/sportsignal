"""
SportSignal Dashboard — Streamlit dashboard for sports prediction market signals.

Merged view: Markets + Signals in one unified table.
Journal: Paper trading log.

Powered by Limitless Exchange API on Base blockchain.
"""

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timezone
from pathlib import Path
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
    page_title="⚽ SportSignal — Sports Markets on Base",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark theme CSS
st.html("""
<style>
    .stApp { background-color: #0a0a0f; color: #e8e8e8; }
    [data-testid="stSidebar"] { background-color: #111118; border-right: 1px solid #222230; }
    .stMetric { background: #111118; border-radius: 8px; padding: 10px 14px; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; color: #ffffff; }
    div[data-testid="stMetricLabel"] { color: #999999; font-size: 0.75rem; opacity: 1 !important; }
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
    /* Fix metric labels */
    section[data-testid="stHorizontalBlock"] .stMetric label,
    section[data-testid="stHorizontalBlock"] div[class*="Metric"] label {
        color: #999 !important;
        opacity: 1 !important;
    }
</style>
""")

# ── Session State ─────────────────────────────────────────────────────────────
defaults = {
    "view_mode": "markets",
    "sport_filter": "All",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style="
    background: linear-gradient(90deg, #0a0a0f 0%, #0f0f1a 100%);
    border-bottom: 1px solid #222230;
    padding: 14px 24px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
">
    <div style="display: flex; align-items: center; gap: 14px;">
        <div style="font-size: 28px;">⚽</div>
        <div>
            <div style="font-size: 22px; font-weight: 700; color: #e8e8e8;">SportSignal</div>
            <div style="font-size: 11px; color: #555; margin-top: 2px;">
                Live markets · Edge analysis · Paper trading on <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="color: #4a90d9;">Limitless Exchange</a>
            </div>
        </div>
    </div>
    <div style="display: flex; gap: 10px; align-items: center;">
        <a href="https://limitless.exchange/markets/sport/all-football?r=MOS8U9NKDK" target="_blank" style="
            display: inline-flex; align-items: center; gap: 6px;
            background: #1a1a2e; border: 1px solid #4a90d9; color: #4a90d9;
            padding: 6px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 600;
        ">⚽ Football</a>
        <a href="https://limitless.exchange/markets/sport/all-basketball?r=MOS8U9NKDK" target="_blank" style="
            display: inline-flex; align-items: center; gap: 6px;
            background: #1a1a1a; border: 1px solid #f97316; color: #f97316;
            padding: 6px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 600;
        ">🏀 Basketball</a>
        <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="
            display: inline-block;
            background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
            color: white; padding: 6px 14px; border-radius: 8px;
            text-decoration: none; font-weight: 600; font-size: 11px;
        ">Trade on Limitless →</a>
    </div>
</div>
""")

# ── Navigation ────────────────────────────────────────────────────────────────
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
# MARKETS VIEW — Unified Markets + Signals table
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.get("view_mode") == "markets":
    
    # ── Controls Row ──────────────────────────────────────────────────────
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
                st.success(f"✅ {result['signals_count']} signals · 🐦 {result['tweets_fetched']} tweets · 📰 {result['articles_fetched']} articles")
                st.rerun()
    
    # ── Load Data ─────────────────────────────────────────────────────────
    data = load_signals()
    signals = data.get("signals", [])
    signal_by_slug = {s.get("slug"): s for s in signals}
    
    with st.spinner("Loading markets..."):
        markets_data = get_active_markets(limit=100, sort_by="high_value", automation_type="sports")
        markets = markets_data.get("data", [])
    
    # ── Enrich Markets with Signal Data ────────────────────────────────────
    enriched = []
    for m in markets:
        slug = m.get("slug", "")
        prices = m.get("prices", [0.5, 0.5])
        try:
            yes_pct = round(float(prices[0]) * 100, 1)
            no_pct = round(float(prices[1]) * 100, 1)
        except:
            yes_pct, no_pct = 50, 50
        
        sig = signal_by_slug.get(slug, {})
        
        enriched.append({
            "slug": slug,
            "title": m.get("title", "Unknown"),
            "sport": get_sport_tag(m),
            "yes_pct": yes_pct,
            "no_pct": no_pct,
            "volume": m.get("volumeFormatted", "$0"),
            "volume_raw": int(m.get("volume", "0") or "0"),
            "expiration": m.get("expirationDate", "N/A"),
            "tags": m.get("tags", [])[:2],
            # Signal
            "has_signal": bool(sig),
            "direction": sig.get("direction"),
            "edge": sig.get("edge", 0),
            "implied_pct": sig.get("news_implied_pct"),
            "confidence": sig.get("confidence", "LOW"),
            "rss_sentiment": sig.get("rss_sentiment", {}),
            "twitter_sentiment": sig.get("twitter_sentiment"),
            "api_football": sig.get("api_football"),
            "related_tweets": sig.get("related_tweets", []),
            "related_articles": sig.get("related_articles", []),
        })
    
    # ── Filter & Sort ──────────────────────────────────────────────────────
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
    
    # ── Stats Row ─────────────────────────────────────────────────────────
    twitter_on = data.get("twitter_enabled", False)
    critical = sum(1 for e in enriched if e.get("confidence") == "CRITICAL")
    high = sum(1 for e in enriched if e.get("confidence") == "HIGH")
    medium = sum(1 for e in enriched if e.get("confidence") == "MEDIUM")
    
    s1, s2, s3, s4, s5, s6 = st.columns([1, 1, 1, 1, 1, 1])
    with s1: st.metric("Markets", len(enriched))
    with s2: st.metric("🔴 Critical", critical)
    with s3: st.metric("🟠 High", high)
    with s4: st.metric("🟡 Medium", medium)
    with s5: st.metric("🐦 Twitter", f"{data.get('tweets_fetched', 0)}" if twitter_on else "Off")
    with s6: st.metric("📰 RSS", data.get("articles_fetched", 0))
    
    if not twitter_on:
        st.info("🐦 Twitter off — add `.twitter_cookies.env` with `AUTH_TOKEN` + `CT0` to enable")
    
    st.divider()
    
    # ── Table Header ──────────────────────────────────────────────────────
    st.html("""
    <div style="
        display: grid;
        grid-template-columns: 40px 1fr 60px 60px 70px 90px 70px 60px 70px;
        gap: 10px;
        padding: 8px 16px;
        color: #999;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    ">
        <div style="text-align:center;">Sport</div>
        <div>Market</div>
        <div style="text-align:right;">YES%</div>
        <div style="text-align:right;">NO%</div>
        <div style="text-align:center;">Edge</div>
        <div style="text-align:center;">Direction</div>
        <div style="text-align:center;">Conf</div>
        <div style="text-align:center;">Sources</div>
        <div style="text-align:right;">Volume</div>
    </div>
    <div style="border-bottom: 1px solid #222; margin-bottom: 8px;"></div>
    """)
    
    # ── Markets Table ──────────────────────────────────────────────────────
    if not enriched:
        st.info("No markets match your filters. Try adjusting.")
    else:
        for e in enriched:
            slug = e.get("slug")
            yes_pct = e.get("yes_pct", 50)
            no_pct = e.get("no_pct", 50)
            edge = e.get("edge", 0)
            conf = e.get("confidence", "LOW")
            direction = e.get("direction")
            
            # Row styling
            if conf == "CRITICAL":
                bg = "rgba(239, 68, 68, 0.07)"
                border_left = "3px solid #ef4444"
            elif conf == "HIGH":
                bg = "rgba(249, 115, 22, 0.05)"
                border_left = "3px solid #f97316"
            elif conf == "MEDIUM":
                bg = "rgba(234, 179, 8, 0.03)"
                border_left = "2px solid #eab308"
            elif edge > 0:
                bg = "rgba(34, 197, 94, 0.03)"
                border_left = "2px solid #16a34a"
            else:
                bg = "transparent"
                border_left = "2px solid #222"
            
            # Edge display
            if edge > 0:
                edge_str = f"+{edge:.1f}%"
                if edge > 20: edge_color = "#ef4444"
                elif edge > 10: edge_color = "#f97316"
                else: edge_color = "#eab308"
            else:
                edge_str = "—"
                edge_color = "#555"
            
            # Direction
            if direction == "YES":
                dir_str = "✅ YES"
                dir_color = "#22c55e"
            elif direction == "NO":
                dir_str = "❌ NO"
                dir_color = "#ef4444"
            else:
                dir_str = "—"
                dir_color = "#555"
            
            # Conf badge
            if conf == "CRITICAL": conf_str = "🔴 CRIT"
            elif conf == "HIGH": conf_str = "🟠 HIGH"
            elif conf == "MEDIUM": conf_str = "🟡 MED"
            else: conf_str = ""
            
            # Sources
            srcs = []
            if (e.get("rss_sentiment") or {}).get("article_count", 0) > 0: srcs.append("📰")
            if (e.get("twitter_sentiment") or {}).get("tweet_count", 0) > 0: srcs.append("🐦")
            if e.get("api_football"): srcs.append("⚽")
            src_str = " ".join(srcs) if srcs else ""
            
            # Sport icon
            sport_icon = "⚽" if e.get("sport") == "Football" else "🏀"
            
            # Build row HTML
            st.html(f"""
            <div style="
                background: {bg};
                border-left: {border_left};
                border-radius: 6px;
                padding: 10px 16px;
                margin-bottom: 6px;
                display: grid;
                grid-template-columns: 40px 1fr 60px 60px 70px 90px 70px 60px 70px;
                gap: 10px;
                align-items: center;
                font-size: 13px;
            ">
                <div style="text-align:center; font-size: 16px;">{sport_icon}</div>
                <div style="font-weight: 500; color: #e8e8e8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    {e.get('title', '')[:55]}
                </div>
                <div style="color: #22c55e; font-weight: 700; text-align:right;">{yes_pct:.1f}%</div>
                <div style="color: #ef4444; font-weight: 700; text-align:right;">{no_pct:.1f}%</div>
                <div style="color: {edge_color}; font-weight: 700; text-align:center;">{edge_str}</div>
                <div style="color: {dir_color}; font-weight: 600; font-size: 12px; text-align:center;">{dir_str}</div>
                <div style="color: #aaa; font-size: 11px; text-align:center;">{conf_str}</div>
                <div style="color: #aaa; font-size: 11px; text-align:center;">{src_str}</div>
                <div style="color: #aaa; font-size: 11px; text-align:right;">{e.get('volume', '$0')}</div>
            </div>
            """)
            
            # Expandable details
            if e.get("has_signal") or e.get("related_tweets") or e.get("related_articles"):
                has_detail = len(e.get("related_tweets", [])) + len(e.get("related_articles", [])) > 0
                detail_label = f"📊 Details · {e.get('title', '')[:40]}... | Edge: {edge:+.1f}%"
                
                with st.expander(detail_label):
                    col_left, col_right = st.columns([3, 1])
                    
                    with col_left:
                        # Edge breakdown table
                        rss_s = e.get("rss_sentiment") or {}
                        tw_s = e.get("twitter_sentiment") or {}
                        api_fb = e.get("api_football")
                        
                        st.markdown("**📐 Edge Calculation**")
                        
                        table_md = "| Component | Value |\n|-----------|-------|\n"
                        table_md += f"| Market YES% (Limitless) | **{yes_pct:.1f}%** |\n"
                        
                        if rss_s.get("article_count", 0) > 0:
                            table_md += f"| 📰 RSS ({rss_s.get('article_count')} articles) | **{rss_s.get('implied_probability', 50):.1f}%** |\n"
                        
                        if tw_s.get("tweet_count", 0) > 0:
                            table_md += f"| 🐦 Twitter ({tw_s.get('tweet_count')} tweets) | **{tw_s.get('implied_probability', 50):.1f}%** |\n"
                        
                        if api_fb and api_fb.get("home_form"):
                            table_md += f"| ⚽ Team Form | Adjusted |\n"
                        
                        if e.get("implied_pct"):
                            table_md += f"| **Implied Probability** | **{e.get('implied_pct'):.1f}%** |\n"
                        
                        table_md += f"| **EDGE** | **+{edge:.1f}%** |\n"
                        st.markdown(table_md)
                        
                        # Team form
                        if api_fb and api_fb.get("home_form"):
                            st.markdown(f"""
                            **⚽ Team Form**
                            - {api_fb.get('home', 'Home')}: `{api_fb.get('home_form', '')}` ({api_fb.get('home_form_score', 0)} pts)
                            - {api_fb.get('away', 'Away')}: `{api_fb.get('away_form', '')}` ({api_fb.get('away_form_score', 0)} pts)
                            """)
                        
                        # Tweets
                        tweets = e.get("related_tweets", [])
                        if tweets:
                            st.markdown(f"**🐦 Related Tweets ({len(tweets)})**")
                            for tw in tweets[:5]:
                                brk = "🔥 " if tw.get("is_breaking") else ""
                                src = tw.get("source", "@?").replace("Twitter/@", "")
                                st.markdown(f"- {brk}[{src}]({tw.get('url', '#')}): {tw.get('title', '')[:80]}")
                        
                        # Articles
                        arts = e.get("related_articles", [])
                        if arts:
                            st.markdown(f"**📰 Related Articles ({len(arts)})**")
                            for art in arts[:3]:
                                st.markdown(f"- [{art.get('source', 'Source')}]({art.get('link', '#')}): {art.get('title', '')[:80]}")
                    
                    with col_right:
                        st.markdown("**📓 Journal**")
                        if st.button("Add to Journal", key=f"addj_{slug}", use_container_width=True):
                            st.session_state["prefill_url"] = f"https://limitless.exchange/markets/{slug}"
                            st.session_state["prefill_prob"] = yes_pct
                            st.session_state["prefill_question"] = e.get("title", "")
                            st.session_state["view_mode"] = "journal"
                            st.success("Added! Go to Journal tab.")
                            st.rerun()
                        
                        st.markdown("")
                        st.markdown("**🔗 Trade**")
                        st.markdown(f"[Open on Limitless →](https://limitless.exchange/markets/{slug}?r=MOS8U9NKDK)")
        
        st.divider()
        st.caption(
            f"Showing {len(enriched)} markets | "
            "Edge = Implied Probability − Market Price | "
            "Sources: 📰 RSS · 🐦 Twitter · ⚽ API-Football | "
            f"Last refresh: {data.get('timestamp', 'N/A')[:19] if data.get('timestamp') else 'Never'}"
        )

# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAL VIEW
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.get("view_mode") == "journal":
    
    st.markdown("## 📓 Predictions Journal")
    st.caption("Track your sports prediction trades — paper trading on Limitless")
    
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
                change = pred.get("price_change_pct")
                bet = pred.get("bet_amount")
                
                if current:
                    current_pct = round(current * 100, 1)
                    is_winning = (direction == "YES" and current > pred.get("entry_price", 0)) or \
                                 (direction == "NO" and current < pred.get("entry_price", 1))
                else:
                    current_pct = None
                    is_winning = None
                
                col_q, col_price, col_del = st.columns([4, 1, 0.3])
                with col_q:
                    url = pred.get("market_url", "")
                    q = pred.get("market_question", "Unknown")
                    if url:
                        st.markdown(f"**{direction}** — [{q[:55]}...]({url})")
                    else:
                        st.markdown(f"**{direction}** — {q[:55]}...")
                    bet_str = f" | 💰 ${bet:.0f}" if bet else ""
                    st.caption(f"Entry: {entry:.1f}%{bet_str} | {pred.get('created_at', '')[:10]}")
                with col_price:
                    if current_pct:
                        color = "#22c55e" if is_winning else ("#ef4444" if is_winning is False else "#8b949e")
                        st.markdown(f"<span style='color:{color};font-weight:bold;'>Now: {current_pct:.1f}%</span>", unsafe_allow_html=True)
                with col_del:
                    if st.button("🗑️", key=f"del_{pred['id']}"):
                        delete_prediction(pred["id"])
                        st.rerun()
                
                if pred.get("notes"):
                    st.caption(f"📝 {pred['notes'][:80]}")
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
    
    # Add form
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
                add_prediction(
                    market_question=q, market_url=url, direction=direction,
                    entry_price=entry_prob / 100, notes=notes,
                    instruments=[i.strip() for i in instruments.split(",") if i.strip()],
                    bet_amount=bet if bet > 0 else None
                )
                st.success(f"✅ **{direction}** @ {entry_prob:.1f}%")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        elif submitted and not url:
            st.warning("Enter a market URL")

# ── Footer ──────────────────────────────────────────────────────────────────
st.divider()
st.html(f"""
<div style="
    background: linear-gradient(135deg, #0f1a2a 0%, #1a1a2e 100%);
    border: 1px solid #2a4a7a;
    border-radius: 10px;
    padding: 14px 20px;
    margin: 8px 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
">
    <div>
        <div style="font-size: 13px; font-weight: 600; color: #e8e8e8;">
            🏆 Earn rewards — trade on Limitless Exchange
        </div>
        <div style="font-size: 11px; color: #666; margin-top: 2px;">
            Sports prediction markets on Base L2 blockchain
        </div>
    </div>
    <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="
        display: inline-block;
        background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
        color: white; padding: 8px 16px; border-radius: 8px;
        text-decoration: none; font-weight: 600; font-size: 12px;
    ">Sign Up + Trade →</a>
</div>
""")
st.caption("SportSignal · Powered by Limitless Exchange on Base L2")
