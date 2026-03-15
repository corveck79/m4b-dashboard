import httpx
import os
from .base import BaseCollector, EarningsResult

# EarnApp auth via brd_sess_id (Bright Data session cookie).
# Vernieuwen: browser > F12 > Application > Cookies > earnapp.com > brd_sess_id
# Vervang ook falcon_id en oauth-refresh-token als nodig.
# brd_sess_id duurt weken; oauth-refresh-token is long-lived.


class EarnAppCollector(BaseCollector):
    platform = "earnapp"

    def __init__(self):
        self.brd_sess_id = os.getenv("EARNAPP_BRD_SESS_ID", "")
        self.oauth_refresh_token = os.getenv("EARNAPP_OAUTH_REFRESH_TOKEN", "")
        self.falcon_id = os.getenv("EARNAPP_FALCON_ID", "")

    async def _get_xsrf_token(self, client: httpx.AsyncClient, base_cookies: dict) -> str | None:
        try:
            r = await client.get(
                "https://earnapp.com/dashboard/api/sec/rotate_xsrf",
                params={"appid": "earnapp", "version": "1.613.719"},
                cookies=base_cookies,
                timeout=15,
            )
            return r.cookies.get("xsrf-token")
        except Exception:
            return None

    async def collect(self) -> EarningsResult:
        if not self.brd_sess_id:
            return EarningsResult(self.platform, 0,
                error="EARNAPP_BRD_SESS_ID not set — haal op via F12 > Cookies > earnapp.com > brd_sess_id")

        try:
            async with httpx.AsyncClient() as client:
                base_cookies = {
                    "auth": "1",
                    "auth-method": "google",
                    "brd_sess_id": self.brd_sess_id,
                    "oauth-refresh-token": self.oauth_refresh_token,
                }
                if self.falcon_id:
                    base_cookies["falcon_id"] = self.falcon_id

                xsrf = await self._get_xsrf_token(client, base_cookies)
                if not xsrf:
                    return EarningsResult(self.platform, 0, error="Could not obtain xsrf-token")

                cookies = {**base_cookies, "xsrf-token": xsrf}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
                    "xsrf-token": xsrf,
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://earnapp.com/dashboard/me/passive-income",
                }

                r = await client.get(
                    "https://earnapp.com/dashboard/api/money",
                    params={"appid": "earnapp", "version": "1.613.719"},
                    cookies=cookies,
                    headers=headers,
                    timeout=15,
                )
                if not r.is_success:
                    return EarningsResult(self.platform, 0,
                        error=f"HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                balance = float(data.get("balance", 0))

                rb = await client.get(
                    "https://earnapp.com/dashboard/api/devices",
                    params={"appid": "earnapp", "version": "1.613.719"},
                    cookies=cookies,
                    headers=headers,
                    timeout=15,
                )
                uploaded = 0
                if rb.status_code == 200:
                    devices = rb.json()
                    if isinstance(devices, list):
                        for d in devices:
                            uploaded += int(d.get("total_bandwidth", 0))

                return EarningsResult(self.platform, balance, bytes_uploaded=uploaded)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
