from __future__ import annotations
import os
import httpx
from .base import BaseCollector, EarningsResult

# Auth: Repocket uses Firebase/Google OAuth — no email+password API login available.
# Users must extract their auth-token JWT from browser (F12 → Network → api.repocket.co request).
# Set REPOCKET_API_KEY to that JWT value.
#
# Confirmed endpoints (source: hibenji/repocket_stats + 0xSums/SVB on GitHub):
# Reports: GET https://api.repocket.co/api/reports/current?withReferralBonusesFix=true
#          Header: auth-token: <JWT>
# The JWT is a Firebase ID token (Google OAuth); it expires after ~1 hour.
# When it expires, re-extract from browser and update via Settings.


class RepocketCollector(BaseCollector):
    platform = "repocket"
    _BASE = "https://api.repocket.com"

    def __init__(self):
        self._api_key = os.getenv("REPOCKET_API_KEY", "")

    async def collect(self) -> EarningsResult:
        if not self._api_key:
            return EarningsResult(
                self.platform, 0,
                error="REPOCKET_API_KEY not set (extract auth-token from browser F12)"
            )
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                headers = {
                    "Auth-Token": self._api_key,
                    "accept": "application/json, text/plain, */*",
                    "origin": "https://repocket.com",
                    "referer": "https://repocket.com/",
                    "device-os": "web",
                    "x-app-version": "web",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
                }
                r = await client.get(
                    f"{self._BASE}/api/reports/current",
                    headers=headers,
                )
                if r.status_code == 401:
                    return EarningsResult(
                        self.platform, 0,
                        error="auth-token expired — re-extract from browser F12 and update Settings"
                    )
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                balance = float(
                    data.get("totalEarnings",
                    data.get("balance",
                    data.get("amount",
                    data.get("total", 0))))
                )
                return EarningsResult(self.platform, balance)
        except Exception as e:
            return EarningsResult(self.platform, 0, error=str(e))
