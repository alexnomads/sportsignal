# SportSignal — Agent Brief

## What is SportSignal?

A real-time sports prediction market signal agent. It monitors sports news via RSS feeds, compares sentiment to Limitless Exchange market prices, and surfaces trading opportunities where news implies different odds than the market prices.

## Architecture

```
sportsignal/
├── dashboard.py              ← Streamlit dashboard (3 sections: Signals, Markets, Journal)
├── src/
│   ├── limitless_client.py   ← Limitless API client (HMAC auth, public endpoints)
│   ├── sports_rss_client.py  ← RSS feed fetcher for sports news
│   ├── signal_generator.py   ← Signal logic: sentiment vs price edge
│   ├── predictions_journal.py ← Paper trading journal
│   └── data/
│       └── signals.json      ← Generated signals cache
├── requirements.txt
└── README.md
```

## Key Decisions

1. **No auth needed for market data** — Limitless public endpoints work without token
2. **HMAC auth only for trading** — Not implemented in MVP
3. **RSS first for sentiment** — Twitter API is harder; RSS is free and fast
4. **Focus on Football + NBA** — Alex's priority markets

## Sports RSS Sources

- BBC Sport (Football + Basketball)
- ESPN FC / ESPN NBA
- Sky Sports Football
- The Guardian Football
- The Athletic Football

## Signal Logic

1. Fetch active sports markets from Limitless (sorted by volume)
2. Extract keywords from each market title (teams, players, events)
3. Match RSS articles to markets based on keyword overlap
4. Analyze sentiment of matched articles (positive/negative keywords)
5. Calculate news-implied probability vs market price
6. Generate signal if edge > 10% and confidence is high

## MVP Scope (3 Sections)

### 1. Signals
- Display markets with edge calculation
- Filter by sport (Football/Basketball)
- Sort by edge, volume, newest
- Related articles shown per signal

### 2. Markets
- Live market browser from Limitless API
- Search + filter by sport
- Sort by volume, newest, ending soon
- Click to trade on Limitless

### 3. Journal
- Paper trading log
- Track predictions with YES/NO, entry %, bet amount
- Live price tracking (winning/losing)
- Auto-resolution when market closes
- P&L calculation

## API Credentials

Stored in `src/limitless_client.py`:
- API Key: `oITO-7EMQOcJbwCW`
- Secret: `aRqne6OrWR9ZXnmBmeA48uGEbIUlhsvA1K8Z+hegU0w=` (base64)

## GitHub

https://github.com/alexnomads/sportsignal

## VPS

TBD — need to set up on Alex's VPS

## Operating Rules

- **Boil the ocean** — Complete solutions, not partial
- **Git push after every change**
- **Test before shipping**
- **Real-time data** — Markets update on button click, not polling
