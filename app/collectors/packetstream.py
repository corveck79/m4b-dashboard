import re
import json
import os
import httpx
from .base import BaseCollector, EarningsResult

# PacketStream auth: JWT from `auth` cookie (app.packetstream.io).
# Refresh: F12 > Cookies > auth. JWT appears to have no expiry — probably long-lived.
# Balance + reportData are embedded in the dashboard HTML (server-side rendered).

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
        """Login via form POST, store JWT from auth cookie."""
        if not self.email or not self.password:
            return False
        try:
            # Get CSRF token from hidden form field
            r = await client.get(f"{BASE}/login", headers=HEADERS, timeout=15)
            m = re.search(r'name=csrf\s+value=([^\s>]+)', r.text)
            csrf = m.group(1) if m else ""
            r2 = await client.post(
                f"{BASE}/login",
                data={"username": self.email, "password": self.password, "csrf": csrf},
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

            # Try to extract balance directly from HTML (server-rendered)
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
        if not self.jwt and not (self.email and self.password):
            return EarningsResult(self.platform, 0,
                error="Set PACKETSTREAM_EMAIL + PACKETSTREAM_PASSWORD, or PACKETSTREAM_JWT")

        try:
            async with httpx.AsyncClient() as client:
                # Try JWT first if available
                result = None
                if self.jwt:
                    result = await self._scrape_balance(client)

                # If no JWT or JWT expired, try email/password login
                if result is None and self.email and self.password:
                    if await self._login(client):
                        result = await self._scrape_balance(client)

                if result is None:
                    return EarningsResult(self.platform, 0,
                        error="Login requires CAPTCHA — set PACKETSTREAM_JWT from browser (F12 > Cookies > auth)")

                balance, uploaded = result
                return EarningsResult(self.platform, balance, bytes_uploaded=uploaded)

        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
