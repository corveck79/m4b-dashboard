import httpx
import os
from .base import BaseCollector, EarningsResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Referer": "https://dashboard.honeygain.com/",
}


class HoneygainCollector(BaseCollector):
    platform = "honeygain"

    def __init__(self):
        self.email = os.getenv("HONEYGAIN_EMAIL", "")
        self.password = os.getenv("HONEYGAIN_PASSWORD", "")
        self._token: str | None = None

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self.email or not self.password:
            return False
        try:
            r = await client.post(
                "https://dashboard.honeygain.com/api/v1/users/tokens",
                json={"email": self.email, "password": self.password},
                headers=HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            self._token = r.json()["data"]["access_token"]
            return True
        except Exception:
            return False

    async def collect(self) -> EarningsResult:
        async with httpx.AsyncClient() as client:
            if not self._token:
                ok = await self._login(client)
                if not ok:
                    return EarningsResult(self.platform, 0, error="Login failed or credentials missing")

            headers = {**HEADERS, "Authorization": f"Bearer {self._token}"}
            try:
                r = await client.get(
                    "https://dashboard.honeygain.com/api/v1/users/balances",
                    headers=headers, timeout=15
                )
                if r.status_code in (401, 403):
                    self._token = None
                    ok = await self._login(client)
                    if not ok:
                        return EarningsResult(self.platform, 0, error="Re-login failed")
                    headers = {**HEADERS, "Authorization": f"Bearer {self._token}"}
                    r = await client.get(
                        "https://dashboard.honeygain.com/api/v1/users/balances",
                        headers=headers, timeout=15
                    )
                r.raise_for_status()
                data = r.json()["data"]
                balance = float(data.get("payout", {}).get("usd_cents", 0)) / 100

                rs = await client.get(
                    "https://dashboard.honeygain.com/api/v1/users/stats/stats_today",
                    headers=headers, timeout=15
                )
                uploaded = 0
                if rs.status_code == 200:
                    stats = rs.json().get("data", {})
                    uploaded = int(stats.get("traffic_bytes", 0))

                return EarningsResult(self.platform, balance, bytes_uploaded=uploaded)
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
