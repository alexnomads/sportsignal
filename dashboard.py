"""
SportSignal Dashboard — Streamlit dashboard for sports prediction market signals.

Sections:
1. Signals — Sports market opportunities with edge vs RSS sentiment
2. Markets — Live Limitless sports markets browser
3. Journal — Track your predictions (paper trading)

Powered by Limitless Exchange API on Base blockchain.
"""

import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from limitless_client import get_active_markets, get_feed_events, format_volume, parse_price, get_sport_tag
from sports_rss_client import fetch_all_feeds, fetch_sport_feeds, filter_football_articles, filter_nba_articles
from signal_generator import generate_signals, load_signals
from predictions_journal import load_journal, add_prediction, get_active_predictions, get_resolved_predictions, get_journal_stats, delete_prediction, refresh_all_predictions, export_journal_csv

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
    .stApp {
        background-color: #0a0a0f;
        color: #e8e8e8;
    }
    
    [data-testid="stSidebar"] {
        background-color: #111118;
        border-right: 1px solid #222230;
    }
    
    .sport-card {
        background: linear-gradient(135deg, #14141f 0%, #1a1a28 100%);
        border: 1px solid #2a2a3a;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    
    .signal-card {
        background: linear-gradient(135deg, #0f1a14 0%, #141f18 100%);
        border: 1px solid #1a3a28;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    
    .signal-card.critical {
        border-color: #ef4444;
        background: linear-gradient(135deg, #1a0f0f 0%, #1f1414 100%);
    }
    
    .signal-card.high {
        border-color: #f97316;
    }
    
    .stMetric {
        background: #111118;
        border-radius: 8px;
        padding: 8px;
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 1.4rem;
    }
    
    .sport-badge {
        background: #1a1a28;
        border: 1px solid #3a3a50;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 12px;
        display: inline-block;
    }
    
    .football-badge {
        background: #1a1a2e;
        border-color: #4a90d9;
        color: #4a90d9;
    }
    
    .basketball-badge {
        background: #1a1a1a;
        border-color: #f97316;
        color: #f97316;
    }
    
    div[data-testid="stDataFrame"] {
        background: #0a0a0f;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #111118;
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1a1a28;
    }
    
    .yes-price {
        color: #22c55e;
        font-weight: bold;
    }
    
    .no-price {
        color: #ef4444;
        font-weight: bold;
    }
    
    .edge-positive {
        color: #22c55e;
    }
    
    .edge-negative {
        color: #ef4444;
    }
</style>
""")

# ── Session State ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "view_mode": "signals",
        "sport_filter": "All",
        "sort_markets": "Volume",
        "search_query": "",
        "finnhub_quotes": {},
        "bankroll": 100.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── Logo / Header ─────────────────────────────────────────────────────────────
st.html("""
<div style="
    background: linear-gradient(90deg, #0a0a0f 0%, #0f0f1a 100%);
    border-bottom: 1px solid #222230;
    padding: 16px 24px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
">
    <div style="display: flex; align-items: center; gap: 16px;">
        <div style="font-size: 32px;">⚽</div>
        <div>
            <div style="font-size: 24px; font-weight: 700; color: #e8e8e8;">SportSignal</div>
            <div style="font-size: 12px; color: #666; margin-top: 2px;">
                Sports prediction markets on <span style="color: #4a90d9;">Base</span> via 
                <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="color: #4a90d9; text-decoration: none;">Limitless Exchange</a>
            </div>
        </div>
    </div>
    <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="
        display: inline-block;
        background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
        color: white;
        padding: 8px 16px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 600;
        font-size: 12px;
        white-space: nowrap;
    ">Join Limitless →</a>
</div>
""")

# ── Navigation ────────────────────────────────────────────────────────────────
nav_cols = st.columns([1, 1, 1])
current_view = st.session_state.get("view_mode", "signals")

with nav_cols[0]:
    if st.button("📡 Signals", type="primary" if current_view == "signals" else "secondary", use_container_width=True):
        st.session_state["view_mode"] = "signals"
        st.rerun()

with nav_cols[1]:
    if st.button("📊 Markets", type="primary" if current_view == "markets" else "secondary", use_container_width=True):
        st.session_state["view_mode"] = "markets"
        st.rerun()

with nav_cols[2]:
    if st.button("📓 Journal", type="primary" if current_view == "journal" else "secondary", use_container_width=True):
        st.session_state["view_mode"] = "journal"
        st.rerun()

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SIGNALS VIEW
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.get("view_mode") == "signals":
    
    st.markdown("## 📡 Trading Signals")
    
    # Sport category links
    st.html("""
    <div style="display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap;">
        <a href="https://limitless.exchange/markets/sport/all-football?r=MOS8U9NKDK" target="_blank" style="
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #1a1a2e;
            border: 1px solid #4a90d9;
            color: #4a90d9;
            padding: 6px 14px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 12px;
            font-weight: 600;
        ">⚽ Football on Limitless →</a>
        <a href="https://limitless.exchange/markets/sport/all-basketball?r=MOS8U9NKDK" target="_blank" style="
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #1a1a1a;
            border: 1px solid #f97316;
            color: #f97316;
            padding: 6px 14px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 12px;
            font-weight: 600;
        ">🏀 Basketball on Limitless →</a>
    </div>
    """)
    
    st.caption("Sports market opportunities — edge based on RSS sentiment vs Limitless prices")
    
    # Controls row
    ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 1])
    
    with ctrl1:
        sport_filter = st.selectbox(
            "Sport",
            options=["All", "Football", "Basketball"],
            index=["All", "Football", "Basketball"].index(st.session_state.get("sport_filter", "All")),
            label_visibility="collapsed"
        )
        if sport_filter != st.session_state.get("sport_filter"):
            st.session_state["sport_filter"] = sport_filter
            st.rerun()
    
    with ctrl2:
        sort_by = st.selectbox(
            "Sort signals by",
            options=["Edge ↓", "Volume ↓", "Newest"],
            index=0
        )
    
    with ctrl3:
        if st.button("🔄 Refresh Signals", type="primary", use_container_width=True):
            with st.spinner("Fetching markets + RSS feeds..."):
                sport = None if sport_filter == "All" else sport_filter
                result = generate_signals(sport_filter=sport, min_edge=0.05)
                st.success(f"✅ Generated {result['signals_count']} signals from {result['markets_analyzed']} markets")
                st.rerun()
    
    # Load current signals
    data = load_signals()
    signals = data.get("signals", [])
    
    # Filter and sort
    if sport_filter != "All":
        signals = [s for s in signals if s.get("sport") == sport_filter]
    
    if sort_by == "Edge ↓":
        signals.sort(key=lambda x: x.get("edge", 0), reverse=True)
    elif sort_by == "Volume ↓":
        pass  # Already sorted by edge
    else:
        signals.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    
    # Stats
    if signals:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total Signals", len(signals))
        critical = sum(1 for s in signals if s.get("confidence") == "CRITICAL")
        high = sum(1 for s in signals if s.get("confidence") == "HIGH")
        medium = sum(1 for s in signals if s.get("confidence") == "MEDIUM")
        with c2:
            st.metric("🔴 Critical", critical)
        with c3:
            st.metric("🟠 High", high)
        with c4:
            st.metric("🟡 Medium", medium)
    
    st.divider()
    
    # Display signals
    if not signals:
        st.info("No signals yet. Click **Refresh Signals** to generate signals from live data.")
    else:
        for sig in signals:
            conf = sig.get("confidence", "LOW")
            conf_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}.get(conf, "⚪")
            
            edge = sig.get("edge", 0)
            edge_color = "#22c55e" if edge > 0 else "#ef4444"
            edge_prefix = "+" if edge > 0 else ""
            
            yes_pct = sig.get("market_yes_pct", 50)
            dir_emoji = "✅" if sig.get("direction") == "YES" else "❌"
            
            sport_badge = f'<span class="sport-badge {"football-badge" if sig.get("sport") == "Football" else "basketball-badge"}">{sig.get("sport", "Other")}</span>'
            
            with st.container():
                st.markdown(f"""
                <div class="signal-card {'critical' if conf == 'CRITICAL' else ('high' if conf == 'HIGH' else '')}" 
                     style="border-left: 4px solid {'#ef4444' if conf == 'CRITICAL' else ('#f97316' if conf == 'HIGH' else '#6b7280')};">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                        <div>
                            <span style="font-size: 12px; color: #888;">{conf_emoji} {conf}</span>
                            <span style="margin-left: 8px;">{sport_badge}</span>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-size: 24px; font-weight: bold; color: {edge_color};">{edge_prefix}{edge}%</span>
                            <div style="font-size: 11px; color: #666; margin-top: 2px;">EDGE</div>
                        </div>
                    </div>
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 6px;">
                        {dir_emoji} {sig.get('market', 'Unknown')}
                    </div>
                    <div style="display: flex; gap: 16px; font-size: 13px; color: #aaa; margin-bottom: 8px;">
                        <span>Market: <span class="{'yes-price' if yes_pct >= 50 else 'no-price'}">{yes_pct}% YES</span></span>
                        <span>News implied: <span style="color: #fbbf24;">{sig.get('news_implied_pct', 50)}%</span></span>
                        <span>📊 {sig.get('volume', '$0')}</span>
                        <span>🏁 {sig.get('expiration', 'N/A')}</span>
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        <span>🔗 <a href="https://limitless.exchange/markets/{sig.get('slug', '')}?r=MOS8U9NKDK" target="_blank" style="color: #4a90d9;">Trade on Limitless →</a></span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Related articles
                arts = sig.get("related_articles", [])
                if arts:
                    with st.expander(f"📰 Related articles ({len(arts)})"):
                        for art in arts:
                            st.markdown(f"**[{art.get('source', 'Source')}]({art.get('link', '#')})** — {art.get('title', '')[:80]}...")
                            st.caption(f"{art.get('published_ago', '')}")
                            st.divider()
                
                st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# MARKETS VIEW
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.get("view_mode") == "markets":
    
    st.markdown("## 📊 Live Sports Markets")
    
    # Sport category links
    st.html("""
    <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap;">
        <a href="https://limitless.exchange/markets/sport/all-football?r=MOS8U9NKDK" target="_blank" style="
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #1a1a2e;
            border: 1px solid #4a90d9;
            color: #4a90d9;
            padding: 6px 14px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 12px;
            font-weight: 600;
        ">⚽ All Football Markets →</a>
        <a href="https://limitless.exchange/markets/sport/all-basketball?r=MOS8U9NKDK" target="_blank" style="
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #1a1a1a;
            border: 1px solid #f97316;
            color: #f97316;
            padding: 6px 14px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 12px;
            font-weight: 600;
        ">🏀 All Basketball Markets →</a>
    </div>
    """)
    
    st.caption("Browse and search prediction markets on Limitless Exchange (Base)")
    
    # Controls
    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])
    
    with ctrl1:
        search_query = st.text_input(
            "🔍 Search markets...",
            value=st.session_state.get("search_query", ""),
            placeholder="e.g., Barcelona, Lakers, Champions League...",
            label_visibility="collapsed"
        )
        st.session_state["search_query"] = search_query
    
    with ctrl2:
        sport_filter = st.selectbox(
            "Sport",
            options=["All", "Football", "Basketball"],
            index=["All", "Football", "Basketball"].index(st.session_state.get("sport_filter", "All")),
            label_visibility="collapsed"
        )
        if sport_filter != st.session_state.get("sport_filter"):
            st.session_state["sport_filter"] = sport_filter
            st.rerun()
    
    with ctrl3:
        sort_by = st.selectbox(
            "Sort by",
            options=["Volume", "Newest", "Ending Soon"],
            index=["Volume", "Newest", "Ending Soon"].index(st.session_state.get("sort_markets", "Volume"))
        )
        st.session_state["sort_markets"] = sort_by
    
    # Load markets
    sort_map = {"Volume": "high_value", "Newest": "newest", "Ending Soon": "ending_soon"}
    sport_map = {"All": None, "Football": "Football", "Basketball": "Basketball"}
    
    with st.spinner("Loading markets from Limitless..."):
        markets_data = get_active_markets(
            limit=25,
            sort_by=sort_map.get(sort_by, "high_value"),
            automation_type="sports"
        )
        markets = markets_data.get("data", [])
    
    # Filter by sport
    if sport_filter != "All":
        markets = [m for m in markets if sport_filter.lower() in " ".join(m.get("tags", []) + m.get("categories", [])).lower()]
    
    # Filter by search
    if search_query:
        q = search_query.lower()
        markets = [m for m in markets if q in m.get("title", "").lower() or q in m.get("description", "").lower()]
    
    # Stats
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Markets", len(markets))
    
    football_count = sum(1 for m in markets if "football" in " ".join(m.get("tags", []) + m.get("categories", [])).lower())
    bball_count = sum(1 for m in markets if "basketball" in " ".join(m.get("tags", []) + m.get("categories", [])).lower())
    with c2:
        st.metric("⚽ Football", football_count)
    with c3:
        st.metric("🏀 Basketball", bball_count)
    
    st.divider()
    
    # Display markets
    if not markets:
        st.info("No markets found. Try a different filter or search.")
    else:
        for i, market in enumerate(markets[:50]):
            slug = market.get("slug", "")
            title = market.get("title", "Unknown")
            prices = market.get("prices", [0.5, 0.5])
            vol = market.get("volumeFormatted", "0")
            exp = market.get("expirationDate", "Unknown")
            trade_type = market.get("tradeType", "amm")
            tags = market.get("tags", [])[:3]
            
            try:
                yes_pct = round(float(prices[0]) * 100, 1)
                no_pct = round(float(prices[1]) * 100, 1)
            except:
                yes_pct, no_pct = 50, 50
            
            # Sport badge
            sport = get_sport_tag(market)
            badge_class = "football-badge" if sport == "Football" else "basketball-badge"
            
            with st.container():
                mc1, mc2, mc3, mc4 = st.columns([4, 1, 1, 1])
                
                with mc1:
                    st.markdown(f"**{title[:80]}**")
                    st.caption(f"📊 ${vol} | 🏁 {exp} | 🔖 {', '.join(tags[:2])}")
                with mc2:
                    st.markdown(f'<span class="yes-price">{yes_pct}%</span>', unsafe_allow_html=True)
                    st.caption("YES")
                with mc3:
                    st.markdown(f'<span class="no-price">{no_pct}%</span>', unsafe_allow_html=True)
                    st.caption("NO")
                with mc4:
                    if st.button("📓", key=f"addj_mkt_{i}", help="Add to Journal"):
                        url = f"https://limitless.exchange/markets/{slug}"
                        st.session_state["prefill_url"] = url
                        st.session_state["prefill_prob"] = yes_pct
                        st.session_state["prefill_question"] = title
                        st.session_state["view_mode"] = "journal"
                        st.rerun()
                
                # Market link with referral
                st.markdown(f'<span style="font-size: 11px; color: #4a90d9;">🔗 <a href="https://limitless.exchange/market/{slug}?r=MOS8U9NKDK" target="_blank">Trade on Limitless →</a></span>', unsafe_allow_html=True)
                st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAL VIEW
# ═══════════════════════════════════════════════════════════════════════════════
elif st.session_state.get("view_mode") == "journal":
    
    st.markdown("## 📓 Predictions Journal")
    st.caption("Track your sports prediction market trades — paper trading on Limitless")
    
    # Stats row
    stats = get_journal_stats()
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
    with c1: st.metric("📊 Total", stats["total"])
    with c2: st.metric("⚡ Active", stats["active"])
    with c3: st.metric("✅ Won", stats["won"])
    with c4: st.metric("❌ Lost", stats["lost"])
    with c5: st.metric("🟢 Winning", stats.get("winning", 0))
    with c6: st.metric("🔴 Losing", stats.get("losing", 0))
    
    # Refresh button
    col_refresh, col_export = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Refresh", type="primary"):
            with st.spinner("Checking prices..."):
                refresh_all_predictions()
                st.rerun()
    with col_export:
        csv = export_journal_csv()
        if csv:
            st.download_button("📥 Export CSV", csv, "sport_predictions_journal.csv", "text/csv", key="csv_export")
    
    st.divider()
    
    # Tabs
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
    with st.expander("**➕ Add Prediction**", expanded=st.session_state.get("prefill_url", "") != ""):
        default_url = st.session_state.pop("prefill_url", "") if "prefill_url" in st.session_state else ""
        default_prob = st.session_state.pop("prefill_prob", 50) if "prefill_prob" in st.session_state else 50
        default_q = st.session_state.pop("prefill_question", "") if "prefill_question" in st.session_state else ""
        
        with st.form("add_pred_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Market URL**")
                url = st.text_input("URL", value=default_url, placeholder="https://limitless.exchange/markets/...", label_visibility="collapsed")
                st.markdown("**Direction**")
                direction = st.radio("Dir", options=["YES", "NO"], index=0, horizontal=True, label_visibility="collapsed")
                st.markdown("**Bet Amount**")
                bet = st.number_input("Bet", min_value=0.0, max_value=10000.0, value=0.0, step=10.0, label_visibility="collapsed")
            with c2:
                st.markdown("**Instruments (optional)**")
                instruments = st.text_input("Instruments", placeholder="EPL, Lakers...", label_visibility="collapsed")
                st.markdown("**Notes**")
                notes = st.text_area("Notes", placeholder="Why this prediction?", label_visibility="collapsed", height=120)
            
            st.markdown("**Entry Probability %**")
            entry_prob = st.slider("Entry", min_value=0.0, max_value=100.0, value=float(default_prob), step=0.5)
            
            submitted = st.form_submit_button("💾 Save", type="primary")
        
        if submitted and url:
            try:
                q = default_q or url.split("/")[-1].replace("-", " ").title()
                add_prediction(
                    market_question=q,
                    market_url=url,
                    direction=direction,
                    entry_price=entry_prob / 100,
                    notes=notes,
                    instruments=[i.strip() for i in instruments.split(",") if i.strip()],
                    bet_amount=bet if bet > 0 else None
                )
                st.success(f"✅ Saved: **{direction}** @ {entry_prob:.1f}%")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        elif submitted and not url:
            st.warning("Enter a market URL")

# Footer
st.divider()

# Referral banner
st.html("""
<div style="
    background: linear-gradient(135deg, #0f1a2a 0%, #1a1a2e 100%);
    border: 1px solid #2a4a7a;
    border-radius: 12px;
    padding: 16px 24px;
    margin: 8px 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
">
    <div>
        <div style="font-size: 14px; font-weight: 600; color: #e8e8e8; margin-bottom: 4px;">
            🏆 Earn rewards when you trade on Limitless
        </div>
        <div style="font-size: 12px; color: #888;">
            Use our referral link to sign up and start trading sports prediction markets on Base.
        </div>
    </div>
    <div>
        <a href="https://limitless.exchange/?r=MOS8U9NKDK" target="_blank" style="
            display: inline-block;
            background: linear-gradient(135deg, #4a90d9 0%, #6ab0ff 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 13px;
        ">Sign Up + Trade →</a>
    </div>
</div>
""")

st.caption("SportSignal — Powered by Limitless Exchange on Base L2 | Data refreshes on demand")
