from __future__ import annotations
import os
import httpx
from .base import BaseCollector, EarningsResult

# Mysterium TequilAPI — local REST API on the node container.
# Auth: POST /tequilapi/auth/authenticate {"username":"myst","password":"..."}
#       Returns {"token":"..."} — use as Authorization: Bearer <token>
# Identity: GET /tequilapi/identities → first identity is the active one
# Earnings: GET /tequilapi/sessions/stats-aggregated
# Exchange: GET /tequilapi/exchange/myst/usd → {"amount": <rate>}


class MysteriumCollector(BaseCollector):
    platform = "mysterium"

    def __init__(self):
        self._password = os.getenv("MYST_PASSWORD", "")
        self._host = os.getenv("MYST_TEQUILAPI_HOST", "")
        self._token: str | None = None

    def _base_url(self) -> str:
        host = self._host or "myst"
        if host.startswith("http"):
            return host.rstrip("/")
        return f"http://{host}:4449"

    async def _login(self, client: httpx.AsyncClient) -> bool:
        if not self._password:
            return False
        try:
            r = await client.post(
                f"{self._base_url()}/tequilapi/auth/authenticate",
                json={"username": "myst", "password": self._password},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._token = data.get("token", "")
            return bool(self._token)
        except Exception:
            return False

    async def _request(self, client: httpx.AsyncClient, path: str):
        """Make authenticated GET request, retry once on 401."""
        headers = {"Authorization": f"Bearer {self._token}"}
        r = await client.get(
            f"{self._base_url()}{path}",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 401:
            self._token = None
            if not await self._login(client):
                return None
            headers["Authorization"] = f"Bearer {self._token}"
            r = await client.get(
                f"{self._base_url()}{path}",
                headers=headers,
                timeout=15,
            )
        return r

    async def collect(self) -> EarningsResult:
        if not self._password:
            return EarningsResult(
                self.platform, 0,
                error="Set MYST_PASSWORD in environment"
            )

        async with httpx.AsyncClient(timeout=30) as client:
            if not self._token:
                if not await self._login(client):
                    return EarningsResult(
                        self.platform, 0,
                        error="TequilAPI login failed — check MYST_PASSWORD"
                    )

            try:
                # Get provider service earnings (settled + unsettled)
                r = await self._request(
                    client, "/tequilapi/node/provider/service-earnings"
                )
                if r is None:
                    return EarningsResult(
                        self.platform, 0, error="Auth failed on retry"
                    )
                if not r.is_success:
                    return EarningsResult(
                        self.platform, 0,
                        error=f"service-earnings HTTP {r.status_code}"
                    )
                earnings = r.json()
                # Response: {total_tokens: {wei: "...", ether: "...", human: "..."}, ...}
                total_tokens = earnings.get("total_tokens", {})
                total_wei_str = total_tokens.get("wei", "0") or "0"
                total_wei = int(total_wei_str)
                myst_balance = total_wei / 1e18

                # Convert MYST to USD
                usd_balance = myst_balance
                rx = await self._request(
                    client, "/tequilapi/exchange/myst/usd"
                )
                if rx and rx.is_success:
                    rate_data = rx.json()
                    rate = float(rate_data.get("amount", 0))
                    if rate > 0:
                        usd_balance = myst_balance * rate

                # Get session stats for bandwidth
                uploaded = 0
                rs = await self._request(
                    client, "/tequilapi/sessions/stats-aggregated"
                )
                if rs and rs.is_success:
                    stats = rs.json().get("stats", rs.json())
                    uploaded = int(stats.get("sumBytesReceived", 0))

                return EarningsResult(
                    self.platform, usd_balance,
                    bytes_uploaded=uploaded,
                )
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
