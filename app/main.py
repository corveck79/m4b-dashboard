import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv, find_dotenv

_ENV_FILE = find_dotenv(usecwd=True) or ".env"
load_dotenv(_ENV_FILE)

from . import database as db
from .collectors import ALL_COLLECTORS, make_collectors
from .docker_monitor import collect_docker_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

COLLECT_INTERVAL_MINUTES = int(os.getenv("COLLECT_INTERVAL_MINUTES", "15"))

# In-memory cache of last collection errors/results for status display
_last_collect_errors: dict[str, str] = {}
_last_collect_time: str = "never"


async def run_collection():
    global _last_collect_time
    from datetime import datetime
    _last_collect_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    logger.info("Running data collection...")

    # Earnings & bandwidth from all platforms
    tasks = [c.collect() for c in ALL_COLLECTORS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for collector, result in zip(ALL_COLLECTORS, results):
        if isinstance(result, Exception):
            _last_collect_errors[collector.platform] = str(result)
            logger.error(f"Collector {collector.platform} raised exception: {result}")
            continue

        if result.error:
            _last_collect_errors[collector.platform] = result.error
            logger.warning(f"Collector {collector.platform} error: {result.error}")
        else:
            _last_collect_errors.pop(collector.platform, None)
            await db.upsert_earnings(result.platform, result.balance, result.currency)
            if result.bytes_uploaded or result.bytes_downloaded:
                await db.upsert_bandwidth(result.platform, result.bytes_uploaded, result.bytes_downloaded)

    # Docker stats
    container_stats = await collect_docker_stats()
    for cs in container_stats:
        await db.insert_container_status(
            cs["platform"], cs["container_name"],
            cs["status"], cs["cpu_percent"], cs["memory_mb"]
        )

    logger.info(f"Collection complete. Errors: {_last_collect_errors or 'none'}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_collection, "interval", minutes=COLLECT_INTERVAL_MINUTES, id="collect")
    scheduler.start()

    # Run immediately on startup
    asyncio.create_task(run_collection())

    yield

    scheduler.shutdown()


app = FastAPI(title="M4B Earnings Dashboard", lifespan=lifespan)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/summary")
async def summary():
    data = await db.get_summary()
    data["last_collect"] = _last_collect_time
    data["collect_errors"] = _last_collect_errors
    return JSONResponse(data)


@app.get("/api/earnings")
async def earnings(period: str = "week"):
    if period not in ("day", "week", "month"):
        raise HTTPException(400, "period must be day, week, or month")
    return JSONResponse(await db.get_earnings_history(period))


@app.get("/api/bandwidth")
async def bandwidth(period: str = "week"):
    if period not in ("day", "week", "month"):
        raise HTTPException(400, "period must be day, week, or month")
    return JSONResponse(await db.get_bandwidth_history(period))


@app.get("/api/containers")
async def containers():
    return JSONResponse(await db.get_latest_container_status())


@app.post("/api/collect")
async def trigger_collect():
    """Manually trigger a collection run."""
    asyncio.create_task(run_collection())
    return {"status": "collection triggered"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "last_collect": _last_collect_time}


# ── Settings endpoints ────────────────────────────────────────────────────────

SETTINGS_KEYS = [
    "HONEYGAIN_EMAIL", "HONEYGAIN_PASSWORD", "CONTAINER_HONEYGAIN",
    "EARNAPP_BRD_SESS_ID", "EARNAPP_FALCON_ID", "EARNAPP_OAUTH_REFRESH_TOKEN", "CONTAINER_EARNAPP",
    "IPROYAL_EMAIL", "IPROYAL_PASSWORD", "CONTAINER_IPROYAL",
    "PACKETSTREAM_JWT", "PACKETSTREAM_CID", "PACKETSTREAM_EMAIL", "PACKETSTREAM_PASSWORD", "CONTAINER_PACKETSTREAM",
    "TRAFFMONETIZER_JWT", "TRAFFMONETIZER_EMAIL", "TRAFFMONETIZER_PASSWORD", "CONTAINER_TRAFFMONETIZER",
    "REPOCKET_EMAIL", "REPOCKET_PASSWORD", "REPOCKET_REFRESH_TOKEN", "REPOCKET_API_KEY", "CONTAINER_REPOCKET",
    "EARNFM_API_KEY", "CONTAINER_EARNFM",
    "PROXYRACK_API_KEY", "PROXYRACK_UUID", "CONTAINER_PROXYRACK",
    "BITPING_EMAIL", "BITPING_PASSWORD", "CONTAINER_BITPING",
    "MYST_PASSWORD", "MYST_TEQUILAPI_HOST", "CONTAINER_MYSTERIUM",
    "COLLECT_INTERVAL_MINUTES",
]
MASKED_KEYS = {"HONEYGAIN_PASSWORD", "IPROYAL_PASSWORD", "PACKETSTREAM_PASSWORD", "TRAFFMONETIZER_PASSWORD", "REPOCKET_PASSWORD", "BITPING_PASSWORD", "MYST_PASSWORD"}
_MASK = "••••••••"


def _write_env(updates: dict):
    """Update/insert keys in .env file, preserving existing lines."""
    env_path = Path(_ENV_FILE)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    written = set()
    new_lines = []
    for line in lines:
        m = re.match(r'^([A-Z0-9_]+)=', line)
        if m and m.group(1) in updates and updates[m.group(1)] != _MASK:
            key = m.group(1)
            new_lines.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            new_lines.append(line)

    # Append keys not yet present
    for key, val in updates.items():
        if key not in written and val != _MASK and key in SETTINGS_KEYS:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _reload_collectors():
    """Re-instantiate collectors so they pick up new os.environ values."""
    global ALL_COLLECTORS
    import app.collectors as _col_module
    new = make_collectors()
    ALL_COLLECTORS[:] = new
    _col_module.ALL_COLLECTORS[:] = new


@app.get("/api/settings")
async def get_settings():
    result = {}
    for key in SETTINGS_KEYS:
        val = os.getenv(key, "")
        result[key] = _MASK if (key in MASKED_KEYS and val) else val
    return JSONResponse(result)


@app.post("/api/settings")
async def save_settings(request: Request):
    body = await request.json()
    for key, value in body.items():
        if key in SETTINGS_KEYS and value != _MASK:
            os.environ[key] = str(value)
    _write_env(body)
    _reload_collectors()
    return {"status": "saved"}
