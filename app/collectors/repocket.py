from __future__ import annotations
import os
import httpx
from pathlib import Path
from .base import BaseCollector, EarningsResult

# Auth: Firebase email+password login.
# Login  → POST identitytoolkit.googleapis.com → idToken (1h) + refreshToken (long-lived)
# Refresh→ POST securetoken.googleapis.com     → new idToken using refreshToken
# The refreshToken is written back to .env so it survives restarts.
#
# Confirmed endpoints:
# Reports: GET https://api.repocket.com/api/reports/current
#          Header: Auth-Token: <idToken>

_FIREBASE_KEY = "AIzaSyBJf6hyw47O-5TrAwQszkwvDEh-Ri6q6SU"
_LOGIN_URL = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={_FIREBASE_KEY}"
)
_REFRESH_URL = (
    f"https://securetoken.googleapis.com/v1/token"
    f"?key={_FIREBASE_KEY}"
)


def _save_refresh_token(token: str) -> None:
    """Persist refresh token to .env so it survives container restarts."""
    try:
        from dotenv import find_dotenv
        env_path = Path(find_dotenv(usecwd=True) or ".env")
        if not env_path.exists():
            return
        lines = env_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("REPOCKET_REFRESH_TOKEN="):
                new_lines.append(f"REPOCKET_REFRESH_TOKEN={token}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"REPOCKET_REFRESH_TOKEN={token}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.environ["REPOCKET_REFRESH_TOKEN"] = token
    except Exception:
        pass


class RepocketCollector(BaseCollector):
    platform = "repocket"
    _BASE = "https://api.repocket.com"

    def __init__(self):
        self._email = os.getenv("REPOCKET_EMAIL", "")
        self._password = os.getenv("REPOCKET_PASSWORD", "")
        self._refresh_token = os.getenv("REPOCKET_REFRESH_TOKEN", "")
        self._id_token: str = ""

    async def _login(self, client: httpx.AsyncClient) -> bool:
        """Full email+password Firebase login. Stores refresh token."""
        if not self._email or not self._password:
            return False
        try:
            r = await client.post(
                _LOGIN_URL,
                json={
                    "returnSecureToken": True,
                    "email": self._email,
                    "password": self._password,
                },
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._id_token = data.get("idToken", "")
            rt = data.get("refreshToken", "")
            if rt:
                self._refresh_token = rt
                _save_refresh_token(rt)
            return bool(self._id_token)
        except Exception:
            return False

    async def _refresh(self, client: httpx.AsyncClient) -> bool:
        """Get a new idToken using the stored refresh token."""
        if not self._refresh_token:
            return False
        try:
            r = await client.post(
                _REFRESH_URL,
                data=f"grant_type=refresh_token&refresh_token={self._refresh_token}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._id_token = data.get("id_token", "")
            rt = data.get("refresh_token", "")
            if rt:
                self._refresh_token = rt
                _save_refresh_token(rt)
            return bool(self._id_token)
        except Exception:
            return False

    async def collect(self) -> EarningsResult:
        if not self._email and not self._refresh_token:
            return EarningsResult(
                self.platform, 0,
                error="Set REPOCKET_EMAIL + REPOCKET_PASSWORD in Settings"
            )

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # Prefer refresh token (silent), fall back to full login
            if not self._id_token:
                ok = await self._refresh(client)
                if not ok:
                    ok = await self._login(client)
                if not ok:
                    return EarningsResult(
                        self.platform, 0,
                        error="Login failed — check email/password in Settings"
                    )

            try:
                headers = {
                    "Auth-Token": self._id_token,
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
                    # Token expired mid-session — refresh and retry once
                    self._id_token = ""
                    ok = await self._refresh(client)
                    if not ok:
                        ok = await self._login(client)
                    if not ok:
                        return EarningsResult(
                            self.platform, 0, error="Token refresh failed"
                        )
                    headers["Auth-Token"] = self._id_token
                    r = await client.get(
                        f"{self._BASE}/api/reports/current",
                        headers=headers,
                    )
                if not r.is_success:
                    return EarningsResult(self.platform, 0, error=f"HTTP {r.status_code}")
                data = r.json()
                # Repocket returns centsCredited in cents — convert to dollars
                cents = float(data.get("centsCredited", 0))
                balance = cents / 100
                return EarningsResult(self.platform, balance)
            except Exception as e:
                return EarningsResult(self.platform, 0, error=str(e))
