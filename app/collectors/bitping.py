import os
import httpx
from .base import BaseCollector, EarningsResult

# The node operator API lives at nodes.bitping.com (NOT api.bitping.com).
# Login: POST /auth/login → sets HttpOnly JWT cookie.
# Earnings: GET /api/v2/payouts/earnings → {usdEarnings: "0.123"}
# Auth: Authorization: Bearer <jwt> extracted from cookie.


class BitpingCollector(BaseCollector):
    platform = "bitping"
    _BASE = "https://nodes.bitping.com"

    def __init__(self):
        self._email = os.getenv("BITPING_EMAIL", "")
        self._password = os.getenv("BITPING_PASSWORD", "")
        self._token: str | None = None

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self._email or not self._password:
            return False
        try:
            r = await client.post(
                f"{self._BASE}/auth/login",
                json={"email": self._email, "password": self._password},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            if not r.is_success:
                return False
            # JWT is set as HttpOnly cookie named "token"
            self._token = r.cookies.get("token")
            return bool(self._token)
        except Exception:
            return False

    async def collect(self) -> EarningsResult:
        if not self._email or not self._password:
            return EarningsResult(self.platform, 0, error="Set BITPING_EMAIL + BITPING_PASSWORD")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            if not self._token:
                if not await self._login(client):
                    return EarningsResult(self.platform, 0, error="Login failed — check email/password")

            headers = {
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
            try:
                r = await client.get(
                    f"{self._BASE}/api/v2/payouts/earnings",
                    headers=headers,
                    timeout=15,
                )
                if r.status_code == 401:
                    self._token = None
                    if not await self._login(client):
                        return EarningsResult(self.platform, 0, error="Re-login failed")
                    headers["Authorization"] = f"Bearer {self._token}"
                    r = await client.get(
                        f"{self._BASE}/api/v2/payouts/earnings",
                        headers=headers,
                        timeout=15,
                    )
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                balance = float(data.get("usdEarnings", 0))
                return EarningsResult(self.platform, balance)
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
