# M4B Earnings Dashboard — Deploy op Synology DS920+

## 1. Bestanden kopieren naar NAS

```bash
# Vanuit je PC
scp -r P:/M4B_Dashboard/ admin@<NAS-IP>:/volume1/docker/m4b-dashboard/
```

Of via File Station: upload de hele map naar `/volume1/docker/m4b-dashboard/`.

## 2. Data directory aanmaken

SSH in op de NAS:
```bash
mkdir -p /volume1/docker/m4b-dashboard/data
```

## 3. .env aanmaken vanuit example

```bash
cd /volume1/docker/m4b-dashboard
cp .env.example .env
nano .env   # vul je credentials in
```

### EarnApp token ophalen
1. Open browser, ga naar earnapp.com en log in
2. F12 > Application > Cookies > `oauth-refresh-token` → kopieer de waarde

### PacketStream API key
Dashboard > Account > API Key

### Traffmonetizer token
Dashboard > Settings > API Token

## 4. Docker network controleren

De M4B stack draait waarschijnlijk op een Docker network. Controleer:
```bash
docker network ls | grep m4b
```

Als het network anders heet, pas `docker-compose.yml` aan bij `networks.m4b-net.name`.

Als er geen shared network is:
```bash
# Verwijder de networks sectie uit docker-compose.yml en gebruik alleen de port mapping
```

## 5. Build & start

```bash
cd /volume1/docker/m4b-dashboard
docker compose build
docker compose up -d
```

## 6. Controleer

```bash
docker logs m4b-dashboard -f
```

Dashboard bereikbaar op: `http://<NAS-IP>:8082`

## 7. Container namen aanpassen

Controleer hoe jouw M4B containers heten:
```bash
docker ps --format "{{.Names}}" | grep -E "honeygain|earnapp|iproyal|packetstream|traffmonetizer"
```

Pas de `CONTAINER_*` variabelen in `.env` aan als de namen afwijken.

## Update

```bash
cd /volume1/docker/m4b-dashboard
docker compose down
docker compose build --no-cache
docker compose up -d
```

## API endpoints (voor debugging)

| Endpoint | Beschrijving |
|---|---|
| `GET /` | Dashboard UI |
| `GET /api/summary` | Actuele balansen + fouten |
| `GET /api/earnings?period=week` | Earnings history (day/week/month) |
| `GET /api/bandwidth?period=week` | Bandwidth history |
| `GET /api/containers` | Laatste container status |
| `POST /api/collect` | Handmatige collectie triggeren |
| `GET /api/health` | Health check |
