import aiosqlite
import os
from datetime import datetime, date

DB_PATH = os.getenv("DB_PATH", "/data/m4b_dashboard.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                balance REAL NOT NULL,
                daily_delta REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                date TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bandwidth (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                bytes_uploaded INTEGER DEFAULT 0,
                bytes_downloaded INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS container_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                container_name TEXT NOT NULL,
                status TEXT,
                cpu_percent REAL DEFAULT 0,
                memory_mb REAL DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_earnings_platform_date ON earnings(platform, date);
            CREATE INDEX IF NOT EXISTS idx_bandwidth_platform_date ON bandwidth(platform, date);
            CREATE INDEX IF NOT EXISTS idx_container_status_ts ON container_status(timestamp);
        """)
        await db.commit()


async def upsert_earnings(platform: str, balance: float, currency: str = "USD"):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        # Get yesterday's last balance to compute delta
        async with db.execute(
            "SELECT balance FROM earnings WHERE platform=? AND date<? ORDER BY timestamp DESC LIMIT 1",
            (platform, today)
        ) as cursor:
            row = await cursor.fetchone()
            prev_balance = row[0] if row else 0.0

        # Check if we already have a record for today
        async with db.execute(
            "SELECT id FROM earnings WHERE platform=? AND date=?",
            (platform, today)
        ) as cursor:
            existing = await cursor.fetchone()

        delta = balance - prev_balance if prev_balance else 0.0

        if existing:
            await db.execute(
                "UPDATE earnings SET balance=?, daily_delta=?, timestamp=CURRENT_TIMESTAMP WHERE platform=? AND date=?",
                (balance, delta, platform, today)
            )
        else:
            await db.execute(
                "INSERT INTO earnings (platform, balance, daily_delta, currency, date) VALUES (?,?,?,?,?)",
                (platform, balance, delta, currency, today)
            )
        await db.commit()


async def upsert_bandwidth(platform: str, uploaded: int, downloaded: int):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM bandwidth WHERE platform=? AND date=?",
            (platform, today)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            await db.execute(
                "UPDATE bandwidth SET bytes_uploaded=?, bytes_downloaded=?, timestamp=CURRENT_TIMESTAMP WHERE platform=? AND date=?",
                (uploaded, downloaded, platform, today)
            )
        else:
            await db.execute(
                "INSERT INTO bandwidth (platform, bytes_uploaded, bytes_downloaded, date) VALUES (?,?,?,?)",
                (platform, uploaded, downloaded, today)
            )
        await db.commit()


async def insert_container_status(platform: str, container_name: str, status: str, cpu: float, memory_mb: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO container_status (platform, container_name, status, cpu_percent, memory_mb) VALUES (?,?,?,?,?)",
            (platform, container_name, status, cpu, memory_mb)
        )
        await db.commit()


async def get_earnings_history(period: str = "week") -> list[dict]:
    """Returns earnings per platform per day for the given period (day/week/month)."""
    period_days = {"day": 1, "week": 7, "month": 30}.get(period, 7)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT platform, date, balance, daily_delta, currency
            FROM earnings
            WHERE date >= date('now', ?)
            ORDER BY date ASC, platform ASC
        """, (f"-{period_days} days",)) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_bandwidth_history(period: str = "week") -> list[dict]:
    period_days = {"day": 1, "week": 7, "month": 30}.get(period, 7)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT platform, date, bytes_uploaded, bytes_downloaded
            FROM bandwidth
            WHERE date >= date('now', ?)
            ORDER BY date ASC, platform ASC
        """, (f"-{period_days} days",)) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_latest_container_status() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT cs.*
            FROM container_status cs
            INNER JOIN (
                SELECT platform, MAX(timestamp) AS max_ts
                FROM container_status
                GROUP BY platform
            ) latest ON cs.platform = latest.platform AND cs.timestamp = latest.max_ts
            ORDER BY cs.platform ASC
        """) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_summary() -> dict:
    """Latest balance per platform + totals."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.platform, e.balance, e.daily_delta, e.currency, e.date
            FROM earnings e
            INNER JOIN (
                SELECT platform, MAX(date) AS max_date FROM earnings GROUP BY platform
            ) latest ON e.platform = latest.platform AND e.date = latest.max_date
        """) as cursor:
            rows = await cursor.fetchall()
    platforms = [dict(r) for r in rows]
    total = sum(p["balance"] for p in platforms)
    total_today = sum(p["daily_delta"] for p in platforms)
    return {"platforms": platforms, "total_balance": total, "total_today": total_today}
