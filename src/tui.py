from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from src.engine import MonitorEngine
from src.schema import PeerStatus


class MonitorApp(App):
    """Textual TUI for live peer status monitoring."""

    TITLE = "panic-monitor"
    CSS = """
    Screen { layout: vertical; }
    #node-bar { height: 3; padding: 1; background: $surface; }
    #peer-table { height: 1fr; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

    def __init__(self, engine: MonitorEngine) -> None:
        super().__init__()
        self._engine = engine

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"  Node ID: {self._engine.node_id}", id="node-bar")
        yield DataTable(id="peer-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#peer-table", DataTable)
        table.add_columns("Alias", "Node ID", "Status", "RTT (ms)", "Last Seen", "Failures")
        self._refresh_table()
        self.set_interval(2.0, self._refresh_table)

    def action_refresh(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#peer-table", DataTable)
        table.clear()

        for peer in self._engine.get_peer_states():
            last = peer.latency_history[-1] if peer.latency_history else None
            rtt = f"{last.rtt_ms:.1f}" if last and last.rtt_ms is not None else "---"
            last_seen = peer.last_seen.strftime("%H:%M:%S") if peer.last_seen else "never"

            status_display = peer.current_status.value
            if peer.current_status == PeerStatus.ALIVE:
                status_display = f"[green]{status_display}[/green]"
            elif peer.current_status == PeerStatus.DEAD:
                status_display = f"[red]{status_display}[/red]"

            table.add_row(
                peer.entry.alias or "---",
                peer.entry.node_id[:16] + "…",
                status_display,
                rtt,
                last_seen,
                str(peer.consecutive_failures),
            )
