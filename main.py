from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from src.engine import MonitorEngine
from src.trust import TrustManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="panic-monitor",
        description="P2P health monitoring daemon for the PanicLab ecosystem",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--daemon", action="store_true", help="Run headless daemon")
    mode.add_argument("--tui", action="store_true", help="Launch interactive TUI")
    mode.add_argument("--trust", type=str, metavar="NODE_ID", help="Trust a peer by NodeID")
    mode.add_argument("--untrust", type=str, metavar="NODE_ID", help="Remove a peer from trust store")
    mode.add_argument("--list-trusted", action="store_true", help="List all trusted peers")

    parser.add_argument("--alias", type=str, default=None, help="Alias for --trust")
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Heartbeat interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--peers", type=Path, default=Path("./peers.json"),
        help="Path to peers.json watchlist",
    )
    parser.add_argument(
        "--identity", type=Path, default=Path("./secret.key"),
        help="Path to ed25519 secret key file",
    )
    return parser.parse_args()


def configure_logging(*, tui: bool = False) -> None:
    """Set up loguru. In TUI mode, log to file only to avoid corrupting the terminal."""
    logger.remove()

    if tui:
        logger.add(
            "panic-monitor.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="7 days",
        )
    else:
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>",
            level="DEBUG",
            colorize=True,
        )


async def run_daemon(engine: MonitorEngine) -> None:
    await engine.init()
    await engine.shutdown_event.wait()
    await engine.shutdown()


async def run_tui(engine: MonitorEngine) -> None:
    from src.tui import MonitorApp  # lazy import — avoid loading textual in daemon mode

    await engine.init()
    app = MonitorApp(engine)
    await app.run_async()
    await engine.shutdown()


def cli_main() -> None:
    args = parse_args()
    trust = TrustManager()
    trust.load()

    # Trust management commands — no daemon needed
    if args.trust:
        configure_logging()
        trust.add_peer(args.trust, args.alias)
        return

    if args.untrust:
        configure_logging()
        trust.remove_peer(args.untrust)
        return

    if args.list_trusted:
        peers = trust.list_peers()
        if not peers:
            print("No trusted peers.")
            return
        print(f"{'Alias':<20} {'Node ID':<68} {'Added'}")
        print("-" * 100)
        for p in peers:
            alias = p.alias or "---"
            added = p.added_at.strftime("%Y-%m-%d %H:%M")
            print(f"{alias:<20} {p.node_id:<68} {added}")
        return

    # Daemon / TUI modes
    configure_logging(tui=args.tui)

    engine = MonitorEngine(
        identity_path=args.identity,
        peers_path=args.peers,
        trust=trust,
        interval_seconds=args.interval,
    )

    if args.daemon:
        asyncio.run(run_daemon(engine))
    else:
        asyncio.run(run_tui(engine))


if __name__ == "__main__":
    cli_main()
