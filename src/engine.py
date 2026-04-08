from __future__ import annotations

import asyncio
import signal
from datetime import datetime

from src import IST
from pathlib import Path

import iroh
import iroh.iroh_ffi
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.identity import load_or_create_secret_key
from src.schema import (
    LatencyRecord,
    PeerEntry,
    PeerState,
    PeerStatus,
    Watchlist,
)
from src.trust import TrustManager

HEARTBEAT_ALPN = b"panic-monitor/heartbeat/0"
PROBE_TIMEOUT_SECONDS = 10


class HeartbeatProtocol:
    """Accepts incoming heartbeat probes from other panic-monitor nodes."""

    def __init__(self, trust: TrustManager) -> None:
        self._trust = trust

    async def accept(self, conn) -> None:
        remote = conn.remote_node_id()
        if not self._trust.is_trusted(remote):
            logger.warning("Rejected untrusted probe from {}", remote[:12])
            conn.close(403, b"unauthorized")
            return
        logger.debug("Heartbeat probe accepted from {}", remote[:12])
        await asyncio.sleep(0.1)
        conn.close(0, b"pong")

    async def shutdown(self) -> None:
        logger.debug("Heartbeat protocol shutting down")


class HeartbeatProtocolCreator:
    """Factory required by iroh's protocol registration system."""

    def __init__(self, trust: TrustManager) -> None:
        self._trust = trust

    def create(self, endpoint):
        return HeartbeatProtocol(self._trust)


class MonitorEngine:
    """
    Core monitoring engine.

    Owns a single iroh node and an APScheduler instance that drives
    periodic heartbeat probes against every peer in the watchlist.
    """

    def __init__(
        self,
        identity_path: Path,
        peers_path: Path,
        trust: TrustManager,
        interval_seconds: int = 30,
    ) -> None:
        self._identity_path = identity_path
        self._peers_path = peers_path
        self._trust = trust
        self._interval = interval_seconds

        self._iroh: iroh.Iroh | None = None
        self._scheduler: AsyncIOScheduler | None = None
        self._peers: dict[str, PeerState] = {}
        self._node_id_str: str = ""
        self._peers_mtime: float = 0.0
        self.shutdown_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Bring up the iroh node, load peers, and start the scheduler."""
        iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

        secret_key = load_or_create_secret_key(self._identity_path)

        options = iroh.NodeOptions()
        options.secret_key = secret_key
        options.enable_docs = False
        options.protocols = {HEARTBEAT_ALPN: HeartbeatProtocolCreator(self._trust)}

        self._iroh = await iroh.Iroh.memory_with_options(options)
        self._node_id_str = await self._iroh.net().node_id()
        logger.info("Node started  id={}", self._node_id_str)

        self._peers = self._load_peers()
        logger.info("Watchlist loaded  peers={}", len(self._peers))

        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "misfire_grace_time": self._interval,
                "max_instances": 1,
            }
        )
        self._scheduler.add_job(
            self._run_heartbeat_cycle,
            trigger="interval",
            seconds=self._interval,
            id="heartbeat_cycle",
            name="Heartbeat Cycle",
        )
        self._scheduler.start()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)

        logger.info("Engine ready  interval={}s", self._interval)

    async def shutdown(self) -> None:
        """Gracefully tear down the scheduler and iroh node."""
        logger.info("Shutting down engine …")
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=True)
        if self._iroh:
            await self._iroh.node().shutdown()
        logger.info("Engine stopped")

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def _probe_peer(self, peer: PeerState) -> LatencyRecord:
        """Attempt a single connection probe and record the result."""
        now = datetime.now(IST)
        label = peer.entry.alias or peer.entry.node_id[:12]
        conn = None

        try:
            conn = await asyncio.wait_for(
                self._iroh.node().endpoint().connect(
                    peer.cached_node_addr, HEARTBEAT_ALPN
                ),
                timeout=PROBE_TIMEOUT_SECONDS,
            )

            rtt_us = conn.rtt()
            rtt_ms = rtt_us / 1000.0 if rtt_us else None

            record = LatencyRecord(
                timestamp=now,
                rtt_ms=rtt_ms,
                status=PeerStatus.ALIVE,
            )
            peer.last_seen = now
            peer.consecutive_failures = 0
            peer.current_status = PeerStatus.ALIVE
            logger.debug("{}: ALIVE  rtt={:.2f}ms", label, rtt_ms or 0)

        except Exception as exc:
            record = LatencyRecord(
                timestamp=now,
                rtt_ms=None,
                status=PeerStatus.DEAD,
            )
            peer.consecutive_failures += 1
            peer.current_status = PeerStatus.DEAD
            msg = exc.message() if hasattr(exc, "message") else str(exc)
            logger.warning(
                "{}: DEAD  failures={}  reason={}: {}",
                label,
                peer.consecutive_failures,
                type(exc).__name__,
                msg,
            )

        finally:
            if conn is not None:
                conn.close(0, b"heartbeat")

        peer.latency_history.append(record)
        return record

    async def _run_heartbeat_cycle(self) -> None:
        """Probe all peers concurrently and log a summary."""
        if not self._iroh:
            return

        self._check_reload()

        if not self._peers:
            logger.debug("No peers in watchlist — skipping cycle")
            return

        results = await asyncio.gather(
            *(self._probe_peer(p) for p in self._peers.values()),
            return_exceptions=True,
        )

        alive = sum(
            1
            for r in results
            if isinstance(r, LatencyRecord) and r.status == PeerStatus.ALIVE
        )
        dead = sum(
            1
            for r in results
            if isinstance(r, LatencyRecord) and r.status == PeerStatus.DEAD
        )
        errors = sum(1 for r in results if isinstance(r, Exception))

        logger.info(
            "Heartbeat  alive={}/{}  dead={}  errors={}",
            alive,
            len(self._peers),
            dead,
            errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_peers(self) -> dict[str, PeerState]:
        if not self._peers_path.exists():
            logger.warning("peers.json not found at {} — starting with empty watchlist", self._peers_path)
            self._peers_mtime = 0.0
            return {}

        raw = self._peers_path.read_text()
        self._peers_mtime = self._peers_path.stat().st_mtime
        watchlist = Watchlist.model_validate_json(raw)
        peers: dict[str, PeerState] = {}
        for entry in watchlist.peers:
            try:
                pub_key = iroh.PublicKey.from_string(entry.node_id)
            except iroh.iroh_ffi.IrohError:
                logger.error("Skipping peer '{}' — invalid node_id: {}", entry.alias or "?", entry.node_id)
                continue
            state = PeerState(entry)
            state.cached_node_addr = iroh.NodeAddr(
                pub_key, entry.relay_url, entry.direct_addrs,
            )
            peers[entry.node_id] = state
        return peers

    def _check_reload(self) -> None:
        """Re-read peers.json and trusted_peers.json if modified on disk."""
        try:
            self._trust.reload_if_changed()
        except Exception as exc:
            logger.error("Failed to reload trusted_peers.json: {}", exc)

        if self._peers_path.exists():
            mtime = self._peers_path.stat().st_mtime
            if mtime > self._peers_mtime:
                try:
                    logger.info("peers.json changed on disk — reloading")
                    self._peers = self._load_peers()
                    logger.info("Watchlist reloaded  peers={}", len(self._peers))
                except Exception as exc:
                    logger.error("Failed to reload peers.json: {}", exc)

    def get_peer_states(self) -> list[PeerState]:
        """Snapshot of current peer states (consumed by the TUI)."""
        return list(self._peers.values())

    @property
    def node_id(self) -> str:
        return self._node_id_str

    @property
    def trust(self) -> TrustManager:
        return self._trust

    def add_peer(self, node_id: str, alias: str | None = None) -> str | None:
        """Add a peer to both peers.json and trusted_peers.json. Returns error string or None."""
        if not node_id:
            return "Node ID cannot be empty"

        if node_id == self._node_id_str:
            return "Cannot add yourself as a peer"

        try:
            iroh.PublicKey.from_string(node_id)
        except iroh.iroh_ffi.IrohError:
            return "Invalid Node ID"

        # Add to trust store
        self._trust.add_peer(node_id, alias)

        # Add to peers.json
        if self._peers_path.exists():
            raw = self._peers_path.read_text()
            watchlist = Watchlist.model_validate_json(raw)
        else:
            watchlist = Watchlist()

        if any(p.node_id == node_id for p in watchlist.peers):
            return None  # already in watchlist, but trust was added

        watchlist.peers.append(PeerEntry(node_id=node_id, alias=alias))
        self._peers_path.write_text(watchlist.model_dump_json(indent=2))

        # Hot-reload will pick it up on next cycle, but load now for immediate feedback
        self._peers = self._load_peers()
        return None

    def _handle_signal(self, sig: signal.Signals) -> None:
        logger.info("Received {} — requesting shutdown", sig.name)
        self.shutdown_event.set()
