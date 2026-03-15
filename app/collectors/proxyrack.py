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
                headers = {
                    "api_key": self._api_key,
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }
                # Try multiple known endpoint paths
                data = None
                for path in ["/user/earnings", "/earnings", "/user", "/stats"]:
                    r = await client.get(f"{self._BASE}{path}", headers=headers)
                    if r.is_success:
                        data = r.json()
                        break
                if data is None:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                balance = float(
                    data.get("earnings", data.get("balance", data.get("total", 0)))
                )
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
