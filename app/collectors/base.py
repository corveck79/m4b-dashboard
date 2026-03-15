from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EarningsResult:
    platform: str
    balance: float
    currency: str = "USD"
    bytes_uploaded: int = 0
    bytes_downloaded: int = 0
    error: str | None = None


class BaseCollector(ABC):
    platform: str = ""

    @abstractmethod
    async def collect(self) -> EarningsResult:
        """Fetch current balance and bandwidth from platform API."""
        ...
