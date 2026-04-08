from __future__ import annotations

from datetime import datetime

from src import IST

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Label, Static

from src.engine import MonitorEngine
from src.schema import PeerStatus

# SkyTunnel ember palette
ACCENT = "#dc8228"
ACCENT2 = "#f8a83e"
TEAL = "#2ac0a8"
RED = "#d24141"
TEXT_BRIGHT = "#f2ecde"
TEXT_PRIMARY = "#cdc3b2"
TEXT_MUTED = "#948873"
TEXT_DIM = "#605646"
TEXT_FAINT = "#3c352a"
BG = "#0c0b0f"
BG_SECONDARY = "#12101a"
PANEL = "#16141c"
PANEL_STRONG = "#1e1b26"
BORDER = "#2a2520"

BANNER = (
    f"[{ACCENT}]"
    "\u2588\u2580\u2588 \u2588\u2580\u2588 \u2588\u2584\u2591\u2588 \u2588 \u2588\u2580\u2580 \u2588\u2580\u2584\u2580\u2588 \u2588\u2580\u2588 \u2588\u2584\u2591\u2588 \u2588 \u2580\u2588\u2580 \u2588\u2580\u2588\n"
    "\u2588\u2580\u2580 \u2588\u2580\u2588 \u2588\u2591\u2580\u2588 \u2588 \u2588\u2584\u2584 \u2588\u2591\u2580\u2591\u2588 \u2588\u2584\u2588 \u2588\u2591\u2580\u2588 \u2588 \u2591\u2588\u2591 \u2588\u2580\u2584\n"
    "\u2580\u2591\u2580 \u2580\u2591\u2580 \u2580\u2591\u2591\u2580 \u2580 \u2580\u2580\u2580 \u2580\u2591\u2591\u2591\u2580 \u2580\u2580\u2580 \u2580\u2591\u2591\u2580 \u2580 \u2591\u2580\u2591 \u2580\u2591\u2580"
    f"[/]"
)


class AddPeerModal(ModalScreen[bool]):
    """Modal for adding a new peer to watchlist and trust store."""

    CSS = f"""
    AddPeerModal {{
        align: center middle;
    }}

    #add-peer-box {{
        width: 72;
        height: auto;
        background: {PANEL};
        border: solid {BORDER};
        padding: 1 2;
    }}

    #add-peer-title {{
        height: 1;
        color: {ACCENT};
        text-style: bold;
        margin-bottom: 1;
    }}

    .field-label {{
        height: 1;
        color: {TEXT_DIM};
        margin-top: 1;
    }}

    .field-input {{
        margin-bottom: 0;
    }}

    .field-input > Input {{
        background: {BG};
        color: {ACCENT2};
        border: solid {BORDER};
    }}

    .field-input > Input:focus {{
        border: solid {ACCENT};
    }}

    #add-peer-hint {{
        height: 1;
        color: {TEXT_FAINT};
        margin-top: 1;
    }}

    #add-peer-error {{
        height: 1;
        color: {RED};
        margin-top: 1;
    }}
    """

    BINDINGS = [("escape", "cancel", "cancel")]

    def __init__(self, engine: MonitorEngine) -> None:
        super().__init__()
        self._engine = engine

    def compose(self) -> ComposeResult:
        with Vertical(id="add-peer-box"):
            yield Static(
                f"[{TEXT_FAINT}]--------[/] [{TEXT_DIM}]$ ./add-peer[/] [{TEXT_FAINT}]{'-' * 48}[/]",
                id="add-peer-title",
            )
            yield Label("NODE_ID:", classes="field-label")
            yield Input(placeholder="paste node id here", id="node-id-input", classes="field-input")
            yield Label("ALIAS:", classes="field-label")
            yield Input(placeholder="friendly name (optional)", id="alias-input", classes="field-input")
            yield Static(
                f"[{TEXT_MUTED}]\\[enter][/] [{TEXT_DIM}]submit[/]  "
                f"[{TEXT_MUTED}]\\[esc][/] [{TEXT_DIM}]cancel[/]",
                id="add-peer-hint",
            )
            yield Static("", id="add-peer-error")

    def on_mount(self) -> None:
        self.query_one("#node-id-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "node-id-input":
            self.query_one("#alias-input", Input).focus()
            return

        if event.input.id == "alias-input":
            self._submit()

    def _submit(self) -> None:
        node_id = self.query_one("#node-id-input", Input).value.strip()
        alias = self.query_one("#alias-input", Input).value.strip() or None
        error_widget = self.query_one("#add-peer-error", Static)

        if not node_id:
            error_widget.update(f"[{RED}]node_id cannot be empty[/]")
            return

        err = self._engine.add_peer(node_id, alias)
        if err:
            error_widget.update(f"[{RED}]{err}[/]")
            return

        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class MonitorApp(App):
    """Textual TUI for live peer status monitoring. SkyTunnel aesthetic."""

    TITLE = "panic-monitor"

    CSS = f"""
    Screen {{
        background: {BG};
        color: {TEXT_PRIMARY};
        layout: vertical;
    }}

    #banner {{
        height: auto;
        padding: 1 2 0 2;
        background: {BG};
    }}

    #status-bar {{
        height: 3;
        padding: 1 2;
        background: {PANEL};
    }}

    #status-left {{
        width: 1fr;
        color: {TEXT_MUTED};
    }}

    #status-right {{
        width: auto;
        color: {TEXT_DIM};
    }}

    #cmd-bar {{
        height: 1;
        padding: 0 2;
        background: {PANEL};
        border-bottom: solid {BORDER};
    }}

    #section-header {{
        height: 1;
        padding: 0 2;
        color: {TEXT_DIM};
        background: {BG};
    }}

    #peer-table {{
        height: 1fr;
        max-height: 100%;
        background: {BG};
        padding: 0 1;
    }}

    DataTable {{
        background: {BG};
        color: {TEXT_PRIMARY};
    }}

    DataTable > .datatable--header {{
        background: {PANEL_STRONG};
        color: {ACCENT};
        text-style: bold;
    }}

    DataTable > .datatable--cursor {{
        background: {PANEL_STRONG};
        color: {TEXT_BRIGHT};
    }}

    DataTable > .datatable--even-row {{
        background: {BG};
    }}

    DataTable > .datatable--odd-row {{
        background: {BG_SECONDARY};
    }}

    """

    BINDINGS = [
        ("q", "quit", "quit"),
        ("r", "refresh", "refresh"),
        ("a", "add_peer", "add peer"),
    ]

    def __init__(self, engine: MonitorEngine) -> None:
        super().__init__()
        self._engine = engine
        self._boot_time = datetime.now(IST)

    def compose(self) -> ComposeResult:
        yield Static(BANNER, id="banner")
        with Horizontal(id="status-bar"):
            yield Static("", id="status-left")
            yield Static("", id="status-right")
        yield Static(
            f"  [{TEXT_MUTED}]\\[q][/] [{TEXT_DIM}]quit[/]  "
            f"[{TEXT_MUTED}]\\[r][/] [{TEXT_DIM}]refresh[/]  "
            f"[{TEXT_MUTED}]\\[a][/] [{TEXT_DIM}]add peer[/]",
            id="cmd-bar",
        )
        yield Static("", id="section-header")
        yield DataTable(id="peer-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#peer-table", DataTable)
        table.cursor_type = "row"
        table.add_columns(
            "#", "ALIAS", "NODE ID", "STATUS", "RTT", "LAST SEEN", "FAIL"
        )
        self._refresh_table()
        self.set_interval(2.0, self._refresh_table)

    def action_refresh(self) -> None:
        self._refresh_table()

    def action_add_peer(self) -> None:
        self.push_screen(AddPeerModal(self._engine), self._on_peer_added)

    def _on_peer_added(self, added: bool) -> None:
        if added:
            self._refresh_table()

    def _format_uptime(self) -> str:
        delta = datetime.now(IST) - self._boot_time
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s"

    def _refresh_table(self) -> None:
        table = self.query_one("#peer-table", DataTable)
        table.clear()

        peers = self._engine.get_peer_states()
        alive_count = 0
        dead_count = 0
        unknown_count = 0

        for i, peer in enumerate(peers):
            last = peer.latency_history[-1] if peer.latency_history else None
            rtt = f"{last.rtt_ms:.2f}ms" if last and last.rtt_ms is not None else "---"
            last_seen = peer.last_seen.strftime("%H:%M:%S") if peer.last_seen else "never"

            if peer.current_status == PeerStatus.ALIVE:
                status = f"[{TEAL}]● ALIVE[/]"
                alive_count += 1
            elif peer.current_status == PeerStatus.DEAD:
                status = f"[{RED}]● DEAD[/]"
                dead_count += 1
            else:
                status = f"[{TEXT_DIM}]○ UNKNOWN[/]"
                unknown_count += 1

            fail_str = str(peer.consecutive_failures)
            if peer.consecutive_failures > 0:
                fail_str = f"[{RED}]{fail_str}[/]"
            else:
                fail_str = f"[{TEXT_DIM}]0[/]"

            row_num = f"[{TEXT_FAINT}]{str(i + 1).zfill(2)}[/]"

            table.add_row(
                row_num,
                peer.entry.alias or "---",
                f"[{TEXT_MUTED}]{peer.entry.node_id[:20]}...[/]",
                status,
                rtt,
                last_seen,
                fail_str,
            )

        # Status bar
        total = len(peers)
        node_short = self._engine.node_id[:16]
        uptime = self._format_uptime()

        now = datetime.now(IST).strftime("%H:%M:%S")

        status_left = self.query_one("#status-left", Static)
        status_left.update(
            f"[{TEXT_DIM}]STATUS[/] [{TEAL}]● ONLINE[/]  "
            f"[{TEXT_DIM}]|[/]  "
            f"[{TEXT_DIM}]NODE[/] [{ACCENT2}]{node_short}...[/]  "
            f"[{TEXT_DIM}]|[/]  "
            f"[{TEXT_DIM}]PEERS[/] [{TEXT_BRIGHT}]{total}[/]"
        )

        status_right = self.query_one("#status-right", Static)
        status_right.update(
            f"[{TEXT_DIM}]UPTIME[/] [{TEXT_MUTED}]{uptime}[/]  "
            f"[{TEXT_DIM}]|[/]  "
            f"[{TEXT_FAINT}]@ {now} IST[/]"
        )

        # Section header
        section = self.query_one("#section-header", Static)
        section.update(
            f"[{TEXT_FAINT}]------------[/] "
            f"[{TEXT_DIM}]$ ./watchlist[/] "
            f"[{TEXT_FAINT}]--[/] "
            f"[{TEAL}]{alive_count}[/][{TEXT_DIM}] alive[/] "
            f"[{RED}]{dead_count}[/][{TEXT_DIM}] dead[/] "
            f"[{TEXT_DIM}]{unknown_count} unknown[/] "
            f"[{TEXT_FAINT}]{'─' * 40}[/]"
        )
