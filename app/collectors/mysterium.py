from __future__ import annotations
import os
import httpx
from dataclasses import dataclass
from .base import BaseCollector, EarningsResult

# Mysterium TequilAPI — local REST API on each node container.
# Supports multiple nodes: set MYST_NODES=host1|pass1,host2|pass2,...
# Or single node: MYST_TEQUILAPI_HOST + MYST_PASSWORD (backward compat).
# Auth: POST /tequilapi/auth/authenticate → {"token":"..."}
# Earnings: GET /tequilapi/node/provider/service-earnings → total_tokens.wei
# Exchange: GET /tequilapi/exchange/myst/usd → {"amount": <rate>}


@dataclass
class _Node:
    host: str
    password: str
    token: str = ""

    @property
    def base_url(self) -> str:
        if self.host.startswith("http"):
            return self.host.rstrip("/")
        return f"http://{self.host}:4449"


def _parse_nodes() -> list[_Node]:
    """Parse MYST_NODES='host1|pass1,host2|pass2' or fall back to single node."""
    nodes_str = os.getenv("MYST_NODES", "")
    if nodes_str:
        nodes = []
        for entry in nodes_str.split(","):
            entry = entry.strip()
            if "|" in entry:
                host, password = entry.split("|", 1)
                nodes.append(_Node(host=host.strip(), password=password.strip()))
        return nodes
    # Backward compat: single node
    password = os.getenv("MYST_PASSWORD", "")
    host = os.getenv("MYST_TEQUILAPI_HOST", "")
    if password:
        return [_Node(host=host or "myst", password=password)]
    return []


class MysteriumCollector(BaseCollector):
    platform = "mysterium"

    def __init__(self):
        self._nodes = _parse_nodes()

    async def _login(self, client: httpx.AsyncClient, node: _Node) -> bool:
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

    async def _request(self, client: httpx.AsyncClient, node: _Node, path: str):
        """Authenticated GET, retry once on 401."""
        headers = {"Authorization": f"Bearer {node.token}"}
        r = await client.get(
            f"{node.base_url}{path}", headers=headers, timeout=15,
        )
        if r.status_code == 401:
            node.token = ""
            if not await self._login(client, node):
                return None
            headers["Authorization"] = f"Bearer {node.token}"
            r = await client.get(
                f"{node.base_url}{path}", headers=headers, timeout=15,
            )
        return r

    async def _collect_node(
        self, client: httpx.AsyncClient, node: _Node, myst_usd_rate: float
    ) -> tuple[float, int, str]:
        """Returns (usd_balance, bytes_uploaded, error_or_empty)."""
        if not node.token:
            if not await self._login(client, node):
                return 0, 0, f"{node.host}: login failed"

        # Earnings
        r = await self._request(client, node, "/tequilapi/node/provider/service-earnings")
        if r is None:
            return 0, 0, f"{node.host}: auth failed"
        if not r.is_success:
            return 0, 0, f"{node.host}: HTTP {r.status_code}"

        earnings = r.json()
        total_tokens = earnings.get("total_tokens", {})
        total_wei_str = total_tokens.get("wei", "0") or "0"
        myst_balance = int(total_wei_str) / 1e18
        usd_balance = myst_balance * myst_usd_rate if myst_usd_rate > 0 else myst_balance

        # Bandwidth
        uploaded = 0
        rs = await self._request(client, node, "/tequilapi/sessions/stats-aggregated")
        if rs and rs.is_success:
            stats = rs.json().get("stats", rs.json())
            uploaded = int(stats.get("sumBytesReceived", 0))

        return usd_balance, uploaded, ""

    async def collect(self) -> EarningsResult:
        if not self._nodes:
            return EarningsResult(
                self.platform, 0,
                error="Set MYST_NODES or MYST_PASSWORD in environment"
            )

        async with httpx.AsyncClient(timeout=30) as client:
            # Get exchange rate once (same across all nodes)
            myst_usd_rate = 0.0
            first_node = self._nodes[0]
            if not first_node.token:
                await self._login(client, first_node)
            if first_node.token:
                rx = await self._request(
                    client, first_node, "/tequilapi/exchange/myst/usd"
                )
                if rx and rx.is_success:
                    myst_usd_rate = float(rx.json().get("amount", 0))

            # Collect from all nodes
            total_usd = 0.0
            total_bytes = 0
            errors = []
            for node in self._nodes:
                try:
                    usd, bw, err = await self._collect_node(
                        client, node, myst_usd_rate
                    )
                    total_usd += usd
                    total_bytes += bw
                    if err:
                        errors.append(err)
                except Exception as e:
                    errors.append(f"{node.host}: {e}")

            return EarningsResult(
                self.platform, total_usd,
                bytes_uploaded=total_bytes,
                error="; ".join(errors) if errors else None,
            )
