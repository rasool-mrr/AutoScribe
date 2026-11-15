"""Find the protocol:port that works best on THIS network, on a single server, fast.

Why this exists: testing every location x protocol x port is the slow way round. The protocol/port
that survives the local filtering is a property of the network, not of the server, so it is found
once on one server and then reused for the whole location sweep.

It reuses main.py's own connection handling, so "works" means exactly what the GUI means by it:
the status has to read connected before and after the ping, the server has to be the one asked for,
and a reply has to come back through the tunnel.

    python probe_protocols.py                  # best location, all 36 combinations
    python probe_protocols.py Yarra            # a specific server
    python probe_protocols.py --timeout 12     # short patience for a quick sweep
"""
import argparse
import re
import subprocess
import sys
import time

import os

# Run from contrib/ during development: main.py lives one level up.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

# Most likely to survive filtering first, so a usable answer appears in the first few tries instead
# of after all 36. 443/587/8080/8443 are what real networks leave open; 21/22/123/143/3306 are
# exotic and are tried last because they are almost always filtered.
ORDER = [
    ("wstunnel", 443),
    ("stealth", 443),
    ("stealth", 8443),
    ("tcp", 443),
    ("tcp", 8080),
    ("tcp", 587),
    ("ikev2", 500),
    ("wireguard", 443),
    ("wireguard", 80),
    ("wireguard", 53),
    ("wireguard", 1194),
    ("wireguard", 123),
    ("wireguard", 65142),
    ("udp", 443),
    ("udp", 80),
    ("udp", 53),
    ("udp", 1194),
    ("udp", 54783),
    ("udp", 123),
    ("stealth", 80),
    ("stealth", 587),
    ("stealth", 8080),
    ("stealth", 22),
    ("tcp", 80),
    ("tcp", 1194),
    ("tcp", 54783),
    ("stealth", 21),
    ("stealth", 123),
    ("stealth", 143),
    ("stealth", 3306),
    ("stealth", 54783),
    ("tcp", 21),
    ("tcp", 22),
    ("tcp", 123),
    ("tcp", 143),
    ("tcp", 3306),
]


def combinations(cli):
    """Every protocol:port the installed client actually offers.

    Queried instead of hardcoded: a hardcoded list drifts when Windscribe adds or drops a port, and a
    combination the CLI does not support would be reported as 'no connection' - a false negative that
    looks exactly like filtering. The ORDER list above only decides which ones are tried first.
    """
    found = []
    for proto in main.PROTO_NAMES:
        out = subprocess.run([cli, "ports", proto], capture_output=True, text=True).stdout
        ports = [int(x) for x in re.split(r"[,\s]+", out.strip()) if x.isdigit()]
        found.extend((proto, port) for port in ports)
    rank = {combo: i for i, combo in enumerate(ORDER)}
    return sorted(found, key=lambda c: rank.get(c, len(ORDER)))


class HeadlessApp:
    """main.py only ever talks to the app through post(); this records instead of drawing."""

    def __init__(self, verbose):
        self.verbose = verbose

    def post(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def log_message(self, msg, tag="INFO"):
        if self.verbose:
            print(f"    {tag:8} {msg}", flush=True)

    def set_phase(self, *a, **k):
        pass

    def set_ping(self, *a, **k):
        pass


class NoDB:
    def is_tested(self, *a):
        return False

    def record_result(self, *a):
        pass


def main_probe():
    ap = argparse.ArgumentParser()
    ap.add_argument("server", nargs="?", default="best", help="nickname or city (default: best)")
    ap.add_argument("--timeout", type=float, default=15, help="seconds to wait for a connection")
    ap.add_argument("--pings", type=int, default=2, help="pings per working combo")
    ap.add_argument("--verbose", action="store_true", help="show the CLI conversation")
    args = ap.parse_args()

    cli = main.DEFAULT_CLI
    try:
        subprocess.run([cli, "status"], capture_output=True, timeout=30)
    except FileNotFoundError:
        sys.exit(f"windscribe-cli not found at {cli}")

    app = HeadlessApp(args.verbose)
    worker = main.WindscribeWorker.__new__(main.WindscribeWorker)
    worker.app = app
    worker.cli_cmd = cli
    worker.pinger = main.PingRunner()
    worker.stop_event = main.threading.Event()
    worker.running = False
    worker.db = NoDB()

    print(f"Probing the protocol:port combinations on '{args.server}', "
          f"timeout {args.timeout:.0f}s each\n", flush=True)

    combos = combinations(cli)
    print(f"{len(combos)} combinations supported by this client\n", flush=True)

    good = []
    for i, (proto, port) in enumerate(combos, 1):
        route = f"{proto}:{port}"
        print(f"[{i:2}/{len(combos)}] {route:<16}", end=" ", flush=True)
        t0 = time.time()
        if not worker.ensure_disconnected():
            print("could not disconnect; stopping", flush=True)
            break
        start_ts = worker.now()           # BEFORE connect: the wait must cover the connect call too
        worker.run_cli(["connect", "-n", args.server, route], timeout=args.timeout + 15)
        connected, _ = worker.wait_for_connection(start_ts, args.timeout)
        if not connected:
            print(f"no connection          ({time.time() - t0:4.1f}s)", flush=True)
            worker.run_cli(["disconnect"])
            continue
        carried, result, err = worker.tunnel_carries_traffic("1.1.1.1", args.pings)
        if carried:
            good.append((result["avg"], proto, port, result))
            print(f"WORKS  {result['avg']:6.0f} ms  loss {result['loss']:3.0f}%  "
                  f"({time.time() - t0:4.1f}s)", flush=True)
        else:
            print(f"no traffic: {err[:40]:<40} ({time.time() - t0:4.1f}s)", flush=True)
        worker.run_cli(["disconnect"])

    print()
    if not good:
        print("Nothing worked. Try another server, or raise --timeout: a slow handshake that")
        print("needs longer than the timeout looks exactly like a blocked one.")
        return 1

    good.sort()
    print(f"{len(good)} working combination(s), fastest first:\n")
    print(f"  {'protocol':<12} {'port':<7} {'ping':>8} {'loss':>6}")
    for avg, proto, port, result in good:
        print(f"  {proto:<12} {port:<7} {avg:7.0f}ms {result['loss']:5.0f}%")
    best = good[0]
    print(f"\nUse this for the location sweep:  {best[1]}:{best[2]}")
    print(f"  in the app: Protocols -> keep only {main.PROTO_NAMES[best[1]]}, port {best[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main_probe())
