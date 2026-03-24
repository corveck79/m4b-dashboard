from __future__ import annotations
import os
from .base import BaseCollector, EarningsResult

# EarnFM heeft GEEN publieke API voor node operators (bandwidth sellers).
# De API op proxy-docs.earn.fm/reseller is uitsluitend voor proxy-inkopers/resellers
# (demand side), niet voor bandwidth-aanbieders (supply side).
# Earnings zijn alleen zichtbaar via het dashboard op app.earn.fm.
# Container monitoring werkt wel via Docker stats.


class EarnfmCollector(BaseCollector):
    platform = "earnfm"

    def __init__(self):
        self._api_key = os.getenv("EARNFM_API_KEY", "")

    async def collect(self) -> EarningsResult:
        return EarningsResult(
            self.platform, 0,
            error="earn.fm heeft geen API voor node operators — zie app.earn.fm voor earnings"
        )
