# M4B Earnings Dashboard

A self-hosted monitoring dashboard for [Money4Band](https://github.com/MRColorR/money4band) passive income stacks. Tracks earnings, bandwidth usage, and Docker container health across all supported platforms — all in one dark-mode UI.

![Dashboard preview](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi) ![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python) ![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat&logo=docker)

---

## Features

- **Real-time balance** per platform with daily delta (what you actually earned today)
- **Bandwidth charts** — upload/download per platform, auto-scales MB/GB
- **Container health** — CPU %, memory, status (running/exited/not found) pulled live from Docker socket
- **Period selector** — view last day / week / month
- **Settings popup** — update API tokens and credentials directly from the browser, no SSH needed
- **Auto-refresh** every 5 minutes + manual "Collect Now" button
- **Dark mode** UI, mobile-friendly

## Supported Platforms

| Platform | Earnings | Bandwidth |
|---|:---:|:---:|
| Honeygain | ✅ | ✅ |
| EarnApp | ✅ | ✅ |
| IPRoyal (Pawns.app) | ✅ | — |
| PacketStream | ✅ | ✅ |
| Traffmonetizer | ✅ | — |

---

## Quick Start (Docker)

### 1. Clone

```bash
git clone https://github.com/corveck79/m4b-dashboard.git
cd m4b-dashboard
```

### 2. Create `.env`

```env
# Honeygain
HONEYGAIN_EMAIL=your@email.com
HONEYGAIN_PASSWORD=yourpassword
CONTAINER_HONEYGAIN=MIES_NAS_honeygain

# EarnApp
EARNAPP_BRD_SESS_ID=your_brd_sess_id
EARNAPP_FALCON_ID=your_falcon_id
EARNAPP_OAUTH_REFRESH_TOKEN=your_refresh_token
CONTAINER_EARNAPP=MIES_NAS_earnapp

# IPRoyal
IPROYAL_EMAIL=your@email.com
IPROYAL_PASSWORD=yourpassword
CONTAINER_IPROYAL=MIES_NAS_iproyal

# PacketStream
PACKETSTREAM_JWT=your_auth_cookie
PACKETSTREAM_CID=your_cid
PACKETSTREAM_EMAIL=your@email.com
PACKETSTREAM_PASSWORD=yourpassword
CONTAINER_PACKETSTREAM=MIES_NAS_packetstream

# Traffmonetizer
TRAFFMONETIZER_JWT=your_jwt_token
TRAFFMONETIZER_EMAIL=your@email.com
TRAFFMONETIZER_PASSWORD=yourpassword
CONTAINER_TRAFFMONETIZER=MIES_NAS_traffmonetizer

# General
COLLECT_INTERVAL_MINUTES=15
```

### 3. Adjust `docker-compose.yml`

Edit the network name to match your M4B stack network:

```bash
docker network ls | grep -i m4b
```

Then update `docker-compose.yml`:
```yaml
networks:
  m4b-net:
    external: true
    name: your_m4b_network_name   # <-- change this
```

### 4. Start

```bash
docker compose up -d --build
```

Open `http://your-nas-ip:8082`

---

## Finding Tokens

Some platforms use short-lived tokens that expire and must be refreshed via the **⚙ Settings** popup in the dashboard:

| Platform | Token | Location |
|---|---|---|
| EarnApp | `brd_sess_id` | F12 → Application → Cookies → `earnapp.com` |
| EarnApp | `oauth-refresh-token` | F12 → Application → Cookies → `earnapp.com` |
| PacketStream | `auth` cookie | F12 → Application → Cookies → `app.packetstream.io` |
| Traffmonetizer | `token` | F12 → Application → Local Storage → `app.traffmonetizer.com` |

---

## Architecture

```
FastAPI (uvicorn)
├── /api/summary          — total balance + daily delta per platform
├── /api/earnings?period= — historical balance per platform per day
├── /api/bandwidth?period=— historical bandwidth per platform per day
├── /api/containers       — latest Docker container stats
├── /api/collect          — manual trigger
└── /api/settings         — GET/POST credentials to .env

Collectors (async, run every N minutes)
├── HoneygainCollector    — REST API
├── EarnAppCollector      — REST API
├── IPRoyalCollector      — REST API (pawns.app)
├── PacketStreamCollector — REST API
└── TraffmonetizerCollector — REST API

Storage: SQLite (aiosqlite)
Scheduling: APScheduler
```

---

## Local Development

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# or: .venv/bin/pip install -r requirements.txt # Linux/Mac

# Copy live .env and fix DB path for local use
cp /path/to/live/.env .env
# Change DB_PATH to local path in .env:
# DB_PATH=./data/m4b_dashboard.db

mkdir data
.venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
```

---

## Updating on NAS

```bash
bash /volume1/docker/m4b-dashboard/update.sh
```

The `update.sh` script runs `git pull` + `docker compose up --build -d`.

---

## License

MIT
