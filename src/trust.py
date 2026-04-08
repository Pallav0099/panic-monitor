from __future__ import annotations

from datetime import datetime

from src import IST
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

DEFAULT_TRUST_PATH = Path("./trusted_peers.json")


class TrustedPeer(BaseModel):
    node_id: str
    alias: Optional[str] = None
    added_at: datetime


class TrustStore(BaseModel):
    peers: list[TrustedPeer] = Field(default_factory=list)


class TrustManager:
    """Manages the trusted peers allowlist. Shared across all PanicLab apps."""

    def __init__(self, path: Path = DEFAULT_TRUST_PATH) -> None:
        self._path = path
        self._store = TrustStore()
        self._trusted_ids: set[str] = set()
        self._last_mtime: float = 0.0

    def load(self) -> None:
        if not self._path.exists():
            logger.info("No trust store found at {} — starting empty", self._path)
            self._last_mtime = 0.0
            return
        raw = self._path.read_text()
        self._store = TrustStore.model_validate_json(raw)
        self._trusted_ids = {p.node_id for p in self._store.peers}
        self._last_mtime = self._path.stat().st_mtime
        logger.info("Trust store loaded  trusted_peers={}", len(self._trusted_ids))

    def reload_if_changed(self) -> bool:
        """Re-read from disk if the file has been modified. Returns True if reloaded."""
        if not self._path.exists():
            return False
        mtime = self._path.stat().st_mtime
        if mtime <= self._last_mtime:
            return False
        logger.info("trusted_peers.json changed on disk — reloading")
        self.load()
        return True

    def save(self) -> None:
        self._path.write_text(self._store.model_dump_json(indent=2))

    def is_trusted(self, node_id: str) -> bool:
        return node_id in self._trusted_ids

    def add_peer(self, node_id: str, alias: str | None = None) -> bool:
        """Add a peer. Returns False if already trusted."""
        if node_id in self._trusted_ids:
            logger.warning("Peer {} is already trusted", node_id[:12])
            return False

        peer = TrustedPeer(
            node_id=node_id,
            alias=alias,
            added_at=datetime.now(IST),
        )
        self._store.peers.append(peer)
        self._trusted_ids.add(node_id)
        self.save()
        logger.info("Trusted peer added: {} ({})", alias or node_id[:12], node_id[:12])
        return True

    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer. Returns False if not found."""
        if node_id not in self._trusted_ids:
            logger.warning("Peer {} is not in the trust store", node_id[:12])
            return False

        self._store.peers = [p for p in self._store.peers if p.node_id != node_id]
        self._trusted_ids.discard(node_id)
        self.save()
        logger.info("Trusted peer removed: {}", node_id[:12])
        return True

    def list_peers(self) -> list[TrustedPeer]:
        return list(self._store.peers)
