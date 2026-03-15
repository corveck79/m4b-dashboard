import httpx
import os
from .base import BaseCollector, EarningsResult

BASE = "https://data.traffmonetizer.com/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://app.traffmonetizer.com",
    "Referer": "https://app.traffmonetizer.com/",
}


class TraffmonetizerCollector(BaseCollector):
    platform = "traffmonetizer"

    def __init__(self):
        self._jwt: str | None = os.getenv("TRAFFMONETIZER_JWT", "") or None
        self.email = os.getenv("TRAFFMONETIZER_EMAIL", "")
        self.password = os.getenv("TRAFFMONETIZER_PASSWORD", "")

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self.email or not self.password:
            return False
        try:
            r = await client.post(
                f"{BASE}/auth/login",
                json={"email": self.email, "password": self.password, "g-recaptcha-response": ""},
                headers=HEADERS,
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            token = data.get("data", {}).get("token") or data.get("token")
            if token:
                self._jwt = token
                return True
            return False
        except Exception:
            return False

    async def _get_balance(self, client: httpx.AsyncClient):
        headers = {**HEADERS, "Authorization": f"Bearer {self._jwt}"}
        r = await client.get(f"{BASE}/app_user/get_balance", headers=headers, timeout=15)
        if r.status_code == 401:
            return None  # signal: need re-auth
        if not r.is_success:
            return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        if isinstance(data, dict):
            raw = data.get("data", data)
            balance = float(raw.get("balance", 0))
            if balance > 10:
                balance = balance / 1000
            uploaded = int(raw.get("total_traffic", 0))
        else:
            balance = uploaded = 0
        return EarningsResult(self.platform, balance, bytes_uploaded=uploaded)

    async def collect(self) -> EarningsResult:
        try:
            async with httpx.AsyncClient() as client:
                # 1. Try stored JWT
                if self._jwt:
                    result = await self._get_balance(client)
                    if result is not None:
                        return result
                    # JWT expired (401) — try auto-login
                    self._jwt = None

                # 2. Try auto-login (works if server doesn't enforce reCAPTCHA)
                if await self._login(client):
                    result = await self._get_balance(client)
                    if result is not None:
                        return result

                return EarningsResult(self.platform, 0,
                    error="JWT expired en auto-login mislukt (reCAPTCHA) — update TRAFFMONETIZER_JWT in .env via F12 > Local Storage > app.traffmonetizer.com > token")
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
