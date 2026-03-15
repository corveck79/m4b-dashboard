import httpx
import os
import random
import string
from .base import BaseCollector, EarningsResult

BASE = "https://api.pawns.app/api/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/74.0.3729.169 Safari/537.36",
    "X-Locale": "EN",
}


def _random_identifier(length: int = 21) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


class IPRoyalCollector(BaseCollector):
    platform = "iproyal"

    def __init__(self):
        self.email = os.getenv("IPROYAL_EMAIL", "")
        self.password = os.getenv("IPROYAL_PASSWORD", "")
        self._token: str | None = None

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self.email or not self.password:
            return False
        try:
            r = await client.post(
                f"{BASE}/users/tokens",
                json={
                    "identifier": _random_identifier(),
                    "email": self.email,
                    "password": self.password,
                    "h_captcha_response": "",
                },
                headers=HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            self._token = r.json().get("access_token")
            return bool(self._token)
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
                    f"{BASE}/users/me/balance-dashboard",
                    headers=headers, timeout=15
                )
                if r.status_code == 401:
                    self._token = None
                    ok = await self._login(client)
                    if not ok:
                        return EarningsResult(self.platform, 0, error="Re-login failed")
                    headers = {**HEADERS, "Authorization": f"Bearer {self._token}"}
                    r = await client.get(
                        f"{BASE}/users/me/balance-dashboard",
                        headers=headers, timeout=15
                    )
                r.raise_for_status()
                data = r.json()
                # balance may be nested or direct
                if isinstance(data, dict):
                    balance = float(
                        data.get("balance", data.get("total_balance", data.get("data", {}).get("balance", 0)))
                    )
                else:
                    balance = 0
                # Normalize if in cents (value > 100 and likely cents)
                if balance > 100:
                    balance = balance / 100

                return EarningsResult(self.platform, balance)
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
