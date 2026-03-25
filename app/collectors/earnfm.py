from __future__ import annotations
import os
import httpx
from .base import BaseCollector, EarningsResult

_SUPABASE_URL = "https://sb.earn.fm"
_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "ewogICJyb2xlIjogImFub24iLAogICJpc3MiOiAic3VwYWJhc2UiLAog"
    "ICJpYXQiOiAxNjkyNjU1MjAwLAogICJleHAiOiAxODUwNTA4MDAwCn0."
    "jp-Uj5ro0jj7MHnlE8HHZRsZAFOI1d_T9n_9tnE09vM"
)
_API_BASE = "https://api.earn.fm"


class EarnfmCollector(BaseCollector):
    platform = "earnfm"

    def __init__(self):
        self._email = os.getenv("EARNFM_EMAIL", "")
        self._password = os.getenv("EARNFM_PASSWORD", "")
        self._access_token: str = ""
        self._refresh_token: str = ""

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self._email or not self._password:
            return False
        try:
            r = await client.post(
                f"{_SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={
                    "apikey": _SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                },
                json={"email": self._email, "password": self._password},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._access_token = data.get("access_token", "")
            self._refresh_token = data.get("refresh_token", "")
            return bool(self._access_token)
        except Exception:
            return False

    async def _refresh(self, client: httpx.AsyncClient) -> bool:
        if not self._refresh_token:
            return False
        try:
            r = await client.post(
                f"{_SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                headers={
                    "apikey": _SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                },
                json={"refresh_token": self._refresh_token},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._access_token = data.get("access_token", "")
            self._refresh_token = data.get("refresh_token", self._refresh_token)
            return bool(self._access_token)
        except Exception:
            return False

    async def collect(self) -> EarningsResult:
        if not self._email or not self._password:
            return EarningsResult(
                self.platform, 0,
                error="Set EARNFM_EMAIL + EARNFM_PASSWORD in Settings",
            )

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            if not self._access_token:
                if not await self._login(client):
                    return EarningsResult(
                        self.platform, 0, error="Login failed — check email/password"
                    )

            try:
                headers = {"X-API-Key": self._access_token}
                r = await client.get(
                    f"{_API_BASE}/v2/harvester/view_balance",
                    headers=headers,
                    timeout=15,
                )
                if r.status_code == 401:
                    if not await self._refresh(client):
                        if not await self._login(client):
                            return EarningsResult(
                                self.platform, 0, error="Token refresh failed"
                            )
                    headers["X-API-Key"] = self._access_token
                    r = await client.get(
                        f"{_API_BASE}/v2/harvester/view_balance",
                        headers=headers,
                        timeout=15,
                    )
                if not r.is_success:
                    return EarningsResult(
                        self.platform, 0, error=f"HTTP {r.status_code}"
                    )
                data = r.json().get("data", {})
                balance = float(data.get("totalBalance", 0))
                return EarningsResult(self.platform, balance)
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
