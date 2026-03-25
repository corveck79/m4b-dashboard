# M4B Earnings Dashboard — Deploy on Synology DS920+

## 1. Copy files to NAS

```bash
# From your PC
scp -r P:/M4B_Dashboard/ admin@<NAS-IP>:/volume1/docker/m4b-dashboard/
```

Or via File Station: upload the entire folder to `/volume1/docker/m4b-dashboard/`.

## 2. Create data directory

SSH into the NAS:
```bash
mkdir -p /volume1/docker/m4b-dashboard/data
```

## 3. Create .env from example

```bash
cd /volume1/docker/m4b-dashboard
cp .env.example .env
nano .env   # fill in your credentials
```

### EarnApp token retrieval
1. Open browser, go to earnapp.com and log in
2. F12 > Application > Cookies > `oauth-refresh-token` → copy the value

### PacketStream API key
Dashboard > Account > API Key

### Traffmonetizer token
Dashboard > Settings > API Token

## 4. Check Docker network

The M4B stack probably runs on a Docker network. Check:
```bash
docker network ls | grep m4b
```

If the network has a different name, update `docker-compose.yml` at `networks.m4b-net.name`.

If there is no shared network:
```bash
# Remove the networks section from docker-compose.yml and use only port mapping
```

## 5. Build & start

```bash
cd /volume1/docker/m4b-dashboard
docker compose build
docker compose up -d
```

## 6. Verify

```bash
docker logs m4b-dashboard -f
```

Dashboard accessible at: `http://<NAS-IP>:8082`

## 7. Adjust container names

Check what your M4B containers are named:
```bash
docker ps --format "{{.Names}}" | grep -E "honeygain|earnapp|iproyal|packetstream|traffmonetizer"
```

Adjust the `CONTAINER_*` variables in `.env` if the names differ.

## Update

```bash
cd /volume1/docker/m4b-dashboard
docker compose down
docker compose build --no-cache
docker compose up -d
```

## API endpoints (for debugging)

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard UI |
| `GET /api/summary` | Current balances + errors |
| `GET /api/earnings?period=week` | Earnings history (day/week/month) |
| `GET /api/bandwidth?period=week` | Bandwidth history |
| `GET /api/containers` | Latest container status |
| `POST /api/collect` | Manually trigger collection |
| `GET /api/health` | Health check |
