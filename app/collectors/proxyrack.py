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
                # Confirmed endpoints (source: eforce67/privatebot api.py on GitHub):
                # POST https://peer.proxyrack.com/api/balance  -> {"data":{"balance":"$X.XX"}}
                # POST https://peer.proxyrack.com/api/bandwidth -> {"data":{"bandwidth":{...}}}
                # Header: Api-Key (capital A, capital K)
                headers = {
                    "Api-Key": self._api_key,
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                r = await client.post(f"{self._BASE}/balance", headers=headers)
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                raw = data.get("data", {}).get("balance", "0")
                # Strip currency symbol if present (e.g. "$1.23")
                balance = float(str(raw).replace("$", "").strip() or 0)
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
