import os
import httpx
from .base import BaseCollector, EarningsResult


class EarnfmCollector(BaseCollector):
    platform = "earnfm"
    _BASE = "https://earn.fm/api"

    def __init__(self):
        self._api_key = os.getenv("EARNFM_API_KEY", "")

    async def collect(self) -> EarningsResult:
        if not self._api_key:
            return EarningsResult(self.platform, 0, error="EARNFM_API_KEY not set")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self._BASE}/user/balance",
                    headers={
                        "EARNFM-API-KEY": self._api_key,
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                balance = float(data.get("balance", data.get("amount", 0)))
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
