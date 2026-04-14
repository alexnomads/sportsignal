# ⚽ SportSignal

### Sports prediction market intelligence — find edge before the odds move

[![Powered by Limitless Exchange](https://img.shields.io/badge/Powered%20by-Limitless%20Exchange-6B44FF?labelColor=1a1a2e&style=flat-square)](#)
[![Sports: Football + NBA](https://img.shields.io/badge/Sports-Football%20%2B%20NBA-22c55e?labelColor=1a1a2e&style=flat-square)](#)
[![Chain: Base L2](https://img.shields.io/badge/Chain-Base%20L2-0052ff?labelColor=1a1a2e&style=flat-square)](#)
[![Twitter Sentiment](https://img.shields.io/badge/Sentiment-Twitter%20%2B%20RSS-f97316?labelColor=1a1a2e&style=flat-square)](#)

---

> **The crowd is always wrong at the edges.**
>
> Prediction markets are efficient at 50/50. But in sports — where news breaks, transfers happen, and form changes overnight — the odds lag the information.
>
> SportSignal finds those gaps before they close.

---

## 💚 What It Does

SportSignal monitors live sports prediction markets on [Limitless Exchange](https://limitless.exchange/?r=MOS8U9NKDK) and cross-references them against:

| Source | What It Gives You |
|--------|-------------------|
| 🐦 **Twitter** | Breaking transfers, insider scoops, team announcements from FabrizioRomano, OptaJoe, and 18 more accounts |
| 📰 **RSS Feeds** | Live articles from BBC Sport, ESPN, Sky Sports, The Athletic, Transfermarkt (IT/UK/ES) |
| ⚽ **API-Football** | Team form scores, upcoming fixtures, injury news, head-to-head records |

For each market, it calculates:

```
Edge = Implied Probability (from news) − Market Price (from Limitless)
```

When the gap is large enough → **signal generated** → ranked by edge size → ready to act on.

---

## 🧡 The Edge Formula

```
📐 Edge = What the data suggests − What the market thinks

Sources weighted:
  🐦 Twitter sentiment  ────────  60%
  📰 RSS news sentiment ─────────  40%
  ⚽ API-Football form ──────────  ±10% adjustment
```

**Example:**
> Market price: Bayern vs Real Madrid → **51% YES**
>
> Twitter + RSS + Form data imply: **~72% YES** (Real Madrid in great form, positive news flow)
>
> **Edge: +21%** → Signal fires at CRITICAL confidence

---

## ⚡ Features

### 📊 Unified Markets View
- Every live sports market on Base L2 in one feed
- YES% price, edge size, direction, confidence badge
- Color-coded rows: 🔴 Critical / 🟠 High / 🟡 Medium
- Click any row → full edge breakdown with sources

### 🐦 Twitter Intelligence
- Monitors **20 curated accounts** (transfer journalists, tipsters, club accounts)
- Classifies tweets: 🔥 Breaking / 📋 Transfer / 🏥 Injury / 📈 Betting tip
- Weighted by account reliability (Romano = 2.0x, OptaJoe = 1.8x)

### 📰 News Aggregation
- **9 RSS feeds** updated continuously
- Transfermarkt IT / UK / ES for live transfer market signals
- Sport-specific filtering: Football vs Basketball

### ⚽ API-Football Integration
- Team form scores for the last 5-10 matches
- Upcoming fixtures in next 3 days
- Head-to-head historical records

### 📓 Paper Trading Journal
- Add any market with entry price + direction
- Tracks open positions with live price updates
- Records P&L on resolution
- Export to CSV

---

## 🚀 Live Dashboard

**[→ Open SportSignal](http://187.124.39.207:8502)**

Dashboard shows:
- All live Limitless markets with edge analysis
- Filter by Football / Basketball
- Sort by Edge / Volume / YES%
- One-click add to Journal
- Direct trade links to Limitless

---

## 🛠️ Tech Stack

```
Frontend:     Streamlit (Python)
Sports Data:  RSS (9 feeds) + Twitter/bird CLI + API-Football
Markets:      Limitless Exchange API (Base L2)
Sentiment:    Keyword scoring + account weighting
Deploy:       VPS (systemd auto-restart)
```

---

## 📦 Self-Host

```bash
# Clone
git clone https://github.com/alexnomads/sportsignal.git
cd sportsignal

# Install
pip install -r requirements.txt

# Run
streamlit run dashboard.py --server.port 8502
```

### Optional: Twitter Integration

SportSignal uses [`bird`](https://github.com/steipete/bird) to fetch Twitter without API access.

1. Install bird: `brew install bird` (macOS) or build from source
2. Get your `AUTH_TOKEN` and `CT0` cookies from twitter.com
3. Create `.twitter_cookies.env`:
   ```
   AUTH_TOKEN="your_auth_token_here"
   CT0="your_ct0_token_here"
   ```

Without Twitter cookies → RSS-only mode (still works, fewer signals).

---

## 🔒 Disclaimer

SportSignal is a **paper trading and research tool**. Signals are generated from publicly available data and do not constitute financial advice. Always do your own research before making any trading decisions.

Prediction markets involve risk. Past performance does not guarantee future results.

---

## 📄 License

MIT — use it, fork it, build on it.

---

*Built for sports fans who think in probabilities.*
