import os
import httpx
from .base import BaseCollector, EarningsResult


class BitpingCollector(BaseCollector):
    platform = "bitping"
    _BASE = "https://api.bitping.com/v2"

    def __init__(self):
        self._email = os.getenv("BITPING_EMAIL", "")
        self._password = os.getenv("BITPING_PASSWORD", "")
        self._token: str | None = None

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self._email or not self._password:
            return False
        try:
            r = await client.post(
                f"{self._BASE}/users/login",
                json={"email": self._email, "password": self._password},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._token = data.get("token", data.get("access_token", data.get("jwt")))
            return bool(self._token)
        except Exception:
            return False

    async def collect(self) -> EarningsResult:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            if not self._token:
                ok = await self._login(client)
                if not ok:
                    return EarningsResult(self.platform, 0, error="Login failed or credentials missing")

            headers = {
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
            try:
                # Try multiple known endpoint paths for node operator earnings
                data = None
                for path in ["/nodes/earnings", "/user/earnings", "/earnings", "/nodes/balance"]:
                    r = await client.get(f"{self._BASE}{path}", headers=headers, timeout=15)
                    if r.status_code == 401:
                        self._token = None
                        ok = await self._login(client)
                        if not ok:
                            return EarningsResult(self.platform, 0, error="Re-login failed")
                        headers["Authorization"] = f"Bearer {self._token}"
                        r = await client.get(f"{self._BASE}{path}", headers=headers, timeout=15)
                    if r.is_success:
                        data = r.json()
                        break
                if data is None:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                balance = float(
                    data.get("balance", data.get("earnings", data.get("total", 0)))
                )
                return EarningsResult(self.platform, balance)
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
