# ⚽ SportSignal

**Sports prediction market signals on Base blockchain via Limitless Exchange.**

Live sports markets → RSS sentiment analysis → Trading edge signals.

---

## Features

| Section | Description |
|---------|-------------|
| 📡 **Signals** | Sports markets with edge based on RSS sentiment vs Limitless prices |
| 📊 **Markets** | Live browser for Limitless sports prediction markets |
| 📓 **Journal** | Track your predictions — paper trading without money |

## Tech Stack

- **Streamlit** — Dashboard UI
- **Limitless Exchange API** — Market data (public endpoints, no auth needed for data)
- **RSS Feeds** — BBC Sport, ESPN, Sky Sports, The Athletic
- **Base L2** — Blockchain infrastructure

## Setup

```bash
# Clone
git clone https://github.com/alexnomads/sportsignal.git
cd sportsignal

# Install dependencies
pip install -r requirements.txt

# Run dashboard
streamlit run dashboard.py --server.address 0.0.0.0
```

## API

**Limitless Exchange:** https://api.limitless.exchange

Public endpoints (no auth required for MVP):
- `GET /markets/active?automationType=sports` — Sports markets
- `GET /markets/{slug}` — Market details
- `GET /markets/search` — Search markets

Authenticated (for trading):
- HMAC-SHA256 signing required
- Rate limit: 2 concurrent, 300ms delay

## Sports

Focus: **Football (Soccer)** + **NBA (Basketball)**

RSS sources:
- BBC Sport
- ESPN FC / ESPN NBA
- Sky Sports
- The Athletic

## Deploy

```bash
# VPS setup
sudo apt install python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501

# Auto-start (systemd)
sudo nano /etc/systemd/system/sportsignal.service
```

## Roadmap

- [ ] Add more RSS feeds (ESPN, Bleacher Report, FanSided)
- [ ] Signal generation from historical odds movement
- [ ] Twitter/X sentiment integration
- [ ] Wallet connection for real trading
- [ ] Historical performance tracking
- [ ] Push notifications for high-edge signals

## License

MIT
