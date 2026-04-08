# panic-monitor

A P2P health monitoring daemon for the PanicLab ecosystem. Monitors a watchlist of peers using iroh heartbeat probes over QUIC. No IPs, no DNS, no port forwarding required. Nodes are identified by ed25519 public keys and discovered automatically via relay servers and NAT hole punching.

Part of the PanicLab suite: panic-monitor, panic-chat, panic-share, panic-split, panic-call.

## Architecture

```
panic-monitor/
  main.py                 Entrypoint (CLI argument parsing, mode dispatch)
  src/
    schema.py             Pydantic models (PeerEntry, Watchlist, LatencyRecord, PeerState)
    identity.py           ed25519 secret key generation and persistence
    trust.py              Shared trust store (allowlist for all PanicLab apps)
    engine.py             iroh node, APScheduler heartbeat loop, protocol handler
    tui.py                Textual live dashboard
  peers.json              Watchlist (which peers to monitor)
  trusted_peers.json      Trust store (which peers are allowed to connect)
  secret.key              ed25519 private key (auto-generated on first run)
  panic-monitor.service   systemd unit file
```

### How it works

1. On startup, the daemon loads (or generates) an ed25519 keypair. The public key is the Node ID.
2. An iroh node is created with a registered heartbeat protocol handler (ALPN: `panic-monitor/heartbeat/0`).
3. APScheduler fires a heartbeat cycle every N seconds (default 30).
4. Each cycle probes all peers in `peers.json` concurrently via `asyncio.gather()`.
5. A probe establishes a QUIC connection to the peer, reads RTT, and closes.
6. Incoming probes from other nodes are accepted only if the remote Node ID is in `trusted_peers.json`.
7. Both `peers.json` and `trusted_peers.json` are hot-reloaded on each cycle (mtime-based, no restart needed).

### Data flow

```
Outbound (prober):
  scheduler -> _run_heartbeat_cycle() -> _probe_peer(peer) -> endpoint.connect() -> conn.rtt() -> LatencyRecord

Inbound (responder):
  iroh router -> ALPN match -> HeartbeatProtocol.accept(conn) -> trust check -> respond or reject
```

### Memory bounds

- `PeerState.latency_history` uses `deque(maxlen=100)` per peer. At 30s intervals this is ~50 minutes of history.
- `PeerState` uses `__slots__` to prevent attribute sprawl.
- iroh FFI objects (`NodeAddr`) are cached per peer at load time, not recreated every cycle.
- systemd unit enforces `MemoryMax=200M` and `MemoryHigh=180M`.

## Requirements

- Python 3.12+
- Linux (Arch) or macOS

## Setup

```
git clone <repo-url>
cd panic-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Commands

### Run the daemon (headless)

```
python main.py --daemon [--interval SECONDS] [--peers PATH] [--identity PATH]
```

Starts the monitoring loop. Logs to stderr. Handles SIGTERM/SIGINT for clean shutdown.

| Flag         | Default         | Description                    |
|--------------|-----------------|--------------------------------|
| `--interval` | 30              | Heartbeat interval in seconds  |
| `--peers`    | `./peers.json`  | Path to watchlist file         |
| `--identity` | `./secret.key`  | Path to ed25519 key file       |

### Run the TUI (interactive dashboard)

```
python main.py --tui [--interval SECONDS] [--peers PATH] [--identity PATH]
```

Same monitoring engine, but with a live-updating table showing peer status, RTT, and failure counts. Logs to `panic-monitor.log` instead of stderr. Press `q` to quit.

### Trust a peer

```
python main.py --trust <NODE_ID> [--alias NAME]
```

Adds a Node ID to `trusted_peers.json`. The daemon will accept heartbeat probes from this peer. Both sides must trust each other for bidirectional monitoring.

### Remove trust

```
python main.py --untrust <NODE_ID>
```

Removes a Node ID from the trust store. The daemon will reject future probes from this peer.

### List trusted peers

```
python main.py --list-trusted
```

Prints all trusted peers with their alias, Node ID, and the date they were added.

## Configuration files

### peers.json

Defines which peers to actively monitor. Only `node_id` is required.

```json
{
  "peers": [
    {
      "node_id": "6bc938e7ea576bbef5ee02061ec3787f90ca43907c475b4139571db09b57f98a",
      "alias": "mac-mini",
      "relay_url": "https://relay.iroh.network.",
      "direct_addrs": ["192.168.1.50:11204"]
    }
  ]
}
```

| Field          | Required | Default behavior if omitted                  |
|----------------|----------|----------------------------------------------|
| `node_id`      | yes      |                                               |
| `alias`        | no       | Logs show truncated Node ID                  |
| `relay_url`    | no       | iroh discovers via DNS automatically         |
| `direct_addrs` | no       | iroh discovers via relay and hole punching   |

### trusted_peers.json

Managed by the `--trust` and `--untrust` commands. Do not edit manually unless you know the format.

### secret.key

32-byte ed25519 private key. Auto-generated on first run with `chmod 600`. Do not share this file. The corresponding public key is the Node ID printed in the startup log.

## Quick start (two machines)

```
# Machine A
python main.py --daemon --interval 10
# Log shows: Node started  id=AAA...

# Machine B
python main.py --daemon --interval 10
# Log shows: Node started  id=BBB...

# Machine A: trust B, add B to watchlist
python main.py --trust BBB... --alias machine-b
# Edit peers.json: add {"node_id": "BBB...", "alias": "machine-b"}

# Machine B: trust A, add A to watchlist
python main.py --trust AAA... --alias machine-a
# Edit peers.json: add {"node_id": "AAA...", "alias": "machine-a"}

# Both daemons hot-reload within one interval. No restart needed.
# Logs show: ALIVE rtt=X.XXms
```

## systemd deployment

```
sudo cp panic-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now panic-monitor
journalctl -u panic-monitor -f
```

Edit `ExecStart` in the unit file to match your install path and venv Python binary.

## Trust model

The trust layer is designed to be shared across all PanicLab apps. Trusting a peer for panic-monitor also trusts them for panic-chat, panic-share, and other future apps that read `trusted_peers.json`. Revoking trust revokes across all apps.

iroh's TLS 1.3 handshake cryptographically verifies that a connecting peer holds the private key for the claimed Node ID. The trust store adds an authorization layer on top: even if a connection is authenticated, it is rejected unless the Node ID is explicitly trusted.
