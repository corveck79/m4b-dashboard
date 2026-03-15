import re
import json
import os
import httpx
from .base import BaseCollector, EarningsResult

# PacketStream auth: JWT uit `auth` cookie (app.packetstream.io).
# Refresh: F12 > Cookies > auth. JWT bevat geen expiry — waarschijnlijk long-lived.
# Balance + reportData zitten ingebakken in dashboard HTML (server-side rendered).

BASE = "https://app.packetstream.io"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"}


class PacketStreamCollector(BaseCollector):
    platform = "packetstream"

    def __init__(self):
        self.jwt = os.getenv("PACKETSTREAM_JWT", "")
        self.cid = os.getenv("PACKETSTREAM_CID", "")
        self.email = os.getenv("PACKETSTREAM_EMAIL", "")
        self.password = os.getenv("PACKETSTREAM_PASSWORD", "")

    async def _login(self, client: httpx.AsyncClient) -> bool:
        """Login via form POST, sla JWT op uit auth cookie."""
        if not self.email or not self.password:
            return False
        try:
            # Haal CSRF token op
            r = await client.get(f"{BASE}/login", headers=HEADERS, timeout=15)
            csrf = r.cookies.get("_csrf", "")
            r2 = await client.post(
                f"{BASE}/login",
                data={"username": self.email, "password": self.password, "_csrf": csrf},
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded",
                         "Referer": f"{BASE}/login"},
                follow_redirects=True,
                timeout=15,
            )
            new_jwt = r2.cookies.get("auth", "")
            if new_jwt:
                self.jwt = new_jwt
                return True
            return False
        except Exception:
            return False

    async def _scrape_balance(self, client: httpx.AsyncClient) -> tuple[float, int] | None:
        """Haal dashboard HTML op en parse balance + bandwidth."""
        try:
            r = await client.get(
                f"{BASE}/dashboard",
                cookies={"auth": self.jwt},
                headers=HEADERS,
                follow_redirects=True,
                timeout=20,
            )
            if r.status_code != 200 or "reportData" not in r.text:
                return None

            html = r.text

            # Probeer balance direct uit HTML te halen (server-rendered)
            # Patroon: window.userData = {...} of data-balance="0.05"
            balance = 0.0
            for pattern in [
                r'window\.userData\s*=\s*(\{[^}]+\})',
                r'"balance"\s*:\s*([\d.]+)',
                r'data-balance="([\d.]+)"',
                r'\$(\d+\.\d{2})</span>',
            ]:
                m = re.search(pattern, html)
                if m:
                    try:
                        val = m.group(1)
                        # Als het JSON is, parse het
                        if val.startswith('{'):
                            obj = json.loads(val)
                            balance = float(obj.get("balance", 0))
                        else:
                            balance = float(val)
                        if balance > 0:
                            break
                    except (ValueError, json.JSONDecodeError):
                        continue

            # Parse reportData voor bandwidth (exitnode traffic)
            uploaded = 0
            m = re.search(r'window\.reportData\s*=\s*(\{.*?\});', html, re.DOTALL)
            if m:
                try:
                    report = json.loads(m.group(1))
                    for tx in report.get("exitnode", []):
                        bw = tx.get("bandwidth", {})
                        uploaded += int(bw.get("up", 0)) + int(bw.get("down", 0))
                except (json.JSONDecodeError, TypeError):
                    pass

            return balance, uploaded
        except Exception:
            return None

    async def collect(self) -> EarningsResult:
        if not self.jwt:
            return EarningsResult(self.platform, 0,
                error="PACKETSTREAM_JWT not set — haal op via F12 > Cookies > app.packetstream.io > auth")

        try:
            async with httpx.AsyncClient() as client:
                result = await self._scrape_balance(client)

                if result is None:
                    # JWT verlopen — probeer auto-login
                    if await self._login(client):
                        result = await self._scrape_balance(client)

                if result is None:
                    return EarningsResult(self.platform, 0,
                        error="Dashboard ophalen mislukt — vernieuw PACKETSTREAM_JWT via F12 > Cookies")

                balance, uploaded = result
                return EarningsResult(self.platform, balance, bytes_uploaded=uploaded)

        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
