import os
import httpx
from .base import BaseCollector, EarningsResult


class EarnfmCollector(BaseCollector):
    platform = "earnfm"
    # Confirmed from proxy-docs.earn.fm/authentication:
    # Base: https://api.earn.fm/v2, header: X-API-KEY
    _BASE = "https://api.earn.fm/v2"

    def __init__(self):
        self._api_key = os.getenv("EARNFM_API_KEY", "")

    async def collect(self) -> EarningsResult:
        if not self._api_key:
            return EarningsResult(self.platform, 0, error="EARNFM_API_KEY not set")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self._BASE}/reseller/my_info",
                    headers={
                        "X-API-KEY": self._api_key,
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                # Response: {"data": {"sharedDataCenter": N, "residential": N, ...}, "status": 200}
                # Sum all product balances from the data object
                payload = data.get("data", data)
                if isinstance(payload, dict):
                    numeric_vals = [v for v in payload.values() if isinstance(v, (int, float))]
                    balance = float(sum(numeric_vals)) if numeric_vals else 0.0
                else:
                    balance = float(payload or 0)
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
