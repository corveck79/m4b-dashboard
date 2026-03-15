import os
import httpx
from .base import BaseCollector, EarningsResult


class ProxyRackCollector(BaseCollector):
    platform = "proxyrack"
    _BASE = "https://peer.proxyrack.com/api"

    def __init__(self):
        self._api_key = os.getenv("PROXYRACK_API_KEY", "")

    async def collect(self) -> EarningsResult:
        if not self._api_key:
            return EarningsResult(self.platform, 0, error="PROXYRACK_API_KEY not set")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self._BASE}/user/earnings",
                    headers={
                        "api_key": self._api_key,
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                # Response may vary: {"earnings": 0.123} or {"balance": 0.123}
                balance = float(
                    data.get("earnings", data.get("balance", data.get("total", 0)))
                )
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
