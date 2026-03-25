from __future__ import annotations
import os
import httpx
from dataclasses import dataclass, field
from .base import BaseCollector, EarningsResult

# Primary: my.mystnodes.com centralized API (all nodes, USD earnings).
#   Login: POST /api/v2/auth/login {email, password, remember}
#   Refresh: POST /api/v2/auth/refresh {refreshToken}
#   Total earnings: GET /api/v2/node/total-earnings → {earningsTotal: <usd>}
#   Bandwidth: GET /api/v2/node/total-transferred?days=9999 → {transferredTotal: <bytes>}
#
# Fallback: TequilAPI on local node containers (per-node, MYST→USD conversion).
#   MYST_NODES=host1|pass1,host2|pass2,...

_MYSTNODES_BASE = "https://my.mystnodes.com"


@dataclass
class _TequilaNode:
    host: str
    password: str
    token: str = ""

    @property
    def base_url(self) -> str:
        if self.host.startswith("http"):
            return self.host.rstrip("/")
        return f"http://{self.host}:4449"


def _parse_tequila_nodes() -> list[_TequilaNode]:
    """Parse MYST_NODES='host1|pass1,host2|pass2' or single MYST_PASSWORD."""
    nodes_str = os.getenv("MYST_NODES", "")
    if nodes_str:
        nodes = []
        for entry in nodes_str.split(","):
            entry = entry.strip()
            if "|" in entry:
                host, password = entry.split("|", 1)
                nodes.append(_TequilaNode(host=host.strip(), password=password.strip()))
        return nodes
    password = os.getenv("MYST_PASSWORD", "")
    host = os.getenv("MYST_TEQUILAPI_HOST", "")
    if password:
        return [_TequilaNode(host=host or "myst", password=password)]
    return []


class MysteriumCollector(BaseCollector):
    platform = "mysterium"

    def __init__(self):
        self._email = os.getenv("MYSTNODES_EMAIL", "") or os.getenv("MYST_EMAIL", "")
        self._password = os.getenv("MYSTNODES_PASSWORD", "") or os.getenv("MYST_CLOUD_PASSWORD", "")
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._tequila_nodes = _parse_tequila_nodes()

    # ── mystnodes.com auth ───────────────────────────────────────────

    async def _cloud_login(self, client: httpx.AsyncClient) -> bool:
        if not self._email or not self._password:
            return False
        try:
            r = await client.post(
                f"{_MYSTNODES_BASE}/api/v2/auth/login",
                json={"email": self._email, "password": self._password, "remember": True},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._access_token = data.get("accessToken", "")
            self._refresh_token = data.get("refreshToken", "")
            return bool(self._access_token)
        except Exception:
            return False

    async def _cloud_refresh(self, client: httpx.AsyncClient) -> bool:
        if not self._refresh_token:
            return False
        try:
            r = await client.post(
                f"{_MYSTNODES_BASE}/api/v2/auth/refresh",
                json={"refreshToken": self._refresh_token},
                timeout=15,
            )
            if not r.is_success:
                return False
            data = r.json()
            self._access_token = data.get("accessToken", "")
            self._refresh_token = data.get("refreshToken", self._refresh_token)
            return bool(self._access_token)
        except Exception:
            return False

    async def _cloud_request(self, client: httpx.AsyncClient, path: str, params: dict | None = None):
        """Authenticated GET with auto-refresh on 401."""
        headers = {"Authorization": f"Bearer {self._access_token}"}
        r = await client.get(
            f"{_MYSTNODES_BASE}{path}", headers=headers, params=params, timeout=15,
        )
        if r.status_code == 401:
            ok = await self._cloud_refresh(client)
            if not ok:
                ok = await self._cloud_login(client)
            if not ok:
                return None
            headers["Authorization"] = f"Bearer {self._access_token}"
            r = await client.get(
                f"{_MYSTNODES_BASE}{path}", headers=headers, params=params, timeout=15,
            )
        return r

    async def _collect_cloud(self, client: httpx.AsyncClient) -> EarningsResult | None:
        """Try mystnodes.com centralized API. Returns None if unavailable."""
        if not self._email or not self._password:
            return None

        if not self._access_token:
            if not await self._cloud_login(client):
                return None

        try:
            # Total earnings (already in USD)
            r = await self._cloud_request(client, "/api/v2/node/total-earnings")
            if r is None or not r.is_success:
                return None
            balance = float(r.json().get("earningsTotal", 0))

            # Total bandwidth
            uploaded = 0
            rb = await self._cloud_request(
                client, "/api/v2/node/total-transferred", params={"days": 9999}
            )
            if rb and rb.is_success:
                uploaded = int(rb.json().get("transferredTotal", 0))

            return EarningsResult(self.platform, balance, bytes_uploaded=uploaded)
        except Exception:
            return None

    # ── TequilAPI fallback ───────────────────────────────────────────

    async def _tequila_login(self, client: httpx.AsyncClient, node: _TequilaNode) -> bool:
        try:
            r = await client.post(
                f"{node.base_url}/tequilapi/auth/authenticate",
                json={"username": "myst", "password": node.password},
                timeout=15,
            )
            if not r.is_success:
                return False
            node.token = r.json().get("token", "")
            return bool(node.token)
        except Exception:
            return False

    async def _tequila_request(self, client: httpx.AsyncClient, node: _TequilaNode, path: str):
        headers = {"Authorization": f"Bearer {node.token}"}
        r = await client.get(f"{node.base_url}{path}", headers=headers, timeout=15)
        if r.status_code == 401:
            node.token = ""
            if not await self._tequila_login(client, node):
                return None
            headers["Authorization"] = f"Bearer {node.token}"
            r = await client.get(f"{node.base_url}{path}", headers=headers, timeout=15)
        return r

    async def _collect_tequila(self, client: httpx.AsyncClient) -> EarningsResult | None:
        """Fallback: query local TequilAPI nodes and aggregate."""
        if not self._tequila_nodes:
            return None

        # Exchange rate (from first reachable node)
        myst_usd_rate = 0.0
        for node in self._tequila_nodes:
            if not node.token:
                await self._tequila_login(client, node)
            if node.token:
                rx = await self._tequila_request(client, node, "/tequilapi/exchange/myst/usd")
                if rx and rx.is_success:
                    myst_usd_rate = float(rx.json().get("amount", 0))
                    break

        total_usd = 0.0
        total_bytes = 0
        errors = []
        for node in self._tequila_nodes:
            try:
                if not node.token:
                    if not await self._tequila_login(client, node):
                        errors.append(f"{node.host}: login failed")
                        continue
                r = await self._tequila_request(
                    client, node, "/tequilapi/node/provider/service-earnings"
                )
                if r is None or not r.is_success:
                    errors.append(f"{node.host}: earnings fetch failed")
                    continue
                total_tokens = r.json().get("total_tokens", {})
                wei = int(total_tokens.get("wei", "0") or "0")
                myst = wei / 1e18
                total_usd += myst * myst_usd_rate if myst_usd_rate > 0 else myst

                rs = await self._tequila_request(
                    client, node, "/tequilapi/sessions/stats-aggregated"
                )
                if rs and rs.is_success:
                    stats = rs.json().get("stats", rs.json())
                    total_bytes += int(stats.get("sumBytesReceived", 0))
            except Exception as e:
                errors.append(f"{node.host}: {e}")

        if total_usd > 0 or not errors:
            return EarningsResult(
                self.platform, total_usd,
                bytes_uploaded=total_bytes,
                error="; ".join(errors) if errors else None,
            )
        return EarningsResult(
            self.platform, 0, error="TequilAPI: " + "; ".join(errors)
        )

    # ── Main collect ─────────────────────────────────────────────────

    async def collect(self) -> EarningsResult:
        if not self._email and not self._tequila_nodes:
            return EarningsResult(
                self.platform, 0,
                error="Set MYSTNODES_EMAIL + MYSTNODES_PASSWORD, or MYST_NODES / MYST_PASSWORD"
            )

        async with httpx.AsyncClient(timeout=30) as client:
            # Primary: mystnodes.com cloud API
            result = await self._collect_cloud(client)
            if result is not None:
                return result

            # Fallback: local TequilAPI
            result = await self._collect_tequila(client)
            if result is not None:
                return result

            return EarningsResult(
                self.platform, 0,
                error="Both mystnodes.com and TequilAPI failed"
            )
