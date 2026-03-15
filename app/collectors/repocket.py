import os
import httpx
from .base import BaseCollector, EarningsResult

# NOTE: API endpoints are marked TODO — verify via F12 on app.repocket.co
# after creating an account. Open Network tab, look for requests to
# /api/earning or similar when the dashboard loads.


class RepocketCollector(BaseCollector):
    platform = "repocket"
    _BASE = "https://app.repocket.co/api"  # TODO: confirm via F12

    def __init__(self):
        self._api_key = os.getenv("REPOCKET_API_KEY", "")
        self._email = os.getenv("REPOCKET_EMAIL", "")

    async def collect(self) -> EarningsResult:
        if not self._api_key:
            return EarningsResult(self.platform, 0, error="REPOCKET_API_KEY not set")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self._BASE}/earning",  # TODO: confirm endpoint via F12
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                if not r.is_success:
                    return EarningsResult(
                        self.platform, 0, error=f"HTTP {r.status_code}"
                    )
                data = r.json()
                # TODO: confirm field name via F12 (could be 'balance', 'amount',
                # 'total_earnings', etc.)
                balance = float(data.get("balance", data.get("amount", 0)))
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
