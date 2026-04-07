from __future__ import annotations

import enum
from collections import deque
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

HISTORY_MAXLEN = 100


class PeerStatus(str, enum.Enum):
    ALIVE = "ALIVE"
    DEAD = "DEAD"
    UNKNOWN = "UNKNOWN"


class PeerEntry(BaseModel):
    """On-disk schema for a single peer in peers.json."""

    node_id: str
    alias: Optional[str] = None
    relay_url: Optional[str] = None
    direct_addrs: list[str] = Field(default_factory=list)


class Watchlist(BaseModel):
    """Root model for peers.json."""

    peers: list[PeerEntry] = Field(default_factory=list)


class LatencyRecord(BaseModel):
    """Single heartbeat measurement."""

    timestamp: datetime
    rtt_ms: Optional[float] = None
    status: PeerStatus


class PeerState:
    """
    Runtime state for a monitored peer.

    Not a Pydantic model — holds mutable deque and is never serialized.
    """

    __slots__ = (
        "entry",
        "latency_history",
        "last_seen",
        "consecutive_failures",
        "current_status",
        "cached_node_addr",
    )

    def __init__(self, entry: PeerEntry) -> None:
        self.entry: PeerEntry = entry
        self.latency_history: deque[LatencyRecord] = deque(maxlen=HISTORY_MAXLEN)
        self.last_seen: Optional[datetime] = None
        self.consecutive_failures: int = 0
        self.current_status: PeerStatus = PeerStatus.UNKNOWN
        self.cached_node_addr: object | None = None  # iroh.NodeAddr, cached to avoid FFI churn
