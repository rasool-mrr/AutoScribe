"""Watch one AutoScribe run and say what actually happened, line by line.

Run this in one window, start the test in the app, then read the report. It reads the same logs
Windscribe writes, so it sees what the app saw - including the failures the app cannot name.

    python watch_run.py                 # watch until you press Ctrl+C
    python watch_run.py --minutes 20    # stop by itself after 20 minutes
"""
import argparse
import json
import os
import re
import sys
import time

CLIENT_LOG = os.path.expandvars(r"%LOCALAPPDATA%\Windscribe\Windscribe2\client.log")
OPENVPN_LOG = os.path.expandvars(r"%LOCALAPPDATA%\Windscribe\Windscribe2\openvpn.log")

# The failures worth naming. Everything else in the log is noise at this level.
SIGNALS = [
    (re.compile(r"verifyOpenVpnPeer: could not find owner PID", re.I),
     "ERROR 6 (Windscribe bug): it aborted its own OpenVPN before running"),
    (re.compile(r"Handshake did not complete", re.I),
     "WireGuard handshake got no answer - the port is blocked or filtered"),
    (re.compile(r"Connection timed out", re.I),
     "connect timed out at the client side"),
    (re.compile(r"network interference detected", re.I),
     "Windscribe's own check says the tunnel is being tampered with"),
    (re.compile(r"Could not contact DNS servers|Timeout while contacting DNS", re.I),
     "DNS is not answering - the tunnel or the resolver is broken"),
    (re.compile(r"Location does not exist|is disabled", re.I),
     "server unavailable in your plan / disabled"),
]

PROTO_RE = re.compile(r'protocolDesc\\":\\"(\w+)\\"')


def tail(path, offset):
    """New bytes of a growing file, decoded loosely. Returns (text, new_offset)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", offset
    if size < offset:              # the app truncated/rotated it
        offset = 0
    if size == offset:
        return "", offset
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        return f.read(), f.tell()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=0, help="stop after N minutes (0 = until Ctrl+C)")
    args = ap.parse_args()

    if not os.path.exists(CLIENT_LOG):
        sys.exit(f"Windscribe log not found: {CLIENT_LOG}")

    start = time.time()
    deadline = start + args.minutes * 60 if args.minutes else None

    print(f"Watching {CLIENT_LOG}")
    print("Start the test in AutoScribe now. Ctrl+C to stop.\n")

    c_off = os.path.getsize(CLIENT_LOG)
    o_off = os.path.getsize(OPENVPN_LOG) if os.path.exists(OPENVPN_LOG) else 0

    proto = "?"
    port = "?"
    counts = {}
    events = []

    try:
        while True:
            if deadline and time.time() > deadline:
                break
            text, c_off = tail(CLIENT_LOG, c_off)
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                msg = j.get("msg", "")
                ts = j.get("tm", "")[11:19]

                if "Connecting to IP" in msg:
                    m = PROTO_RE.search(msg)
                    if m:
                        proto = m.group(1)
                    mp = re.search(r"port (\d+)", msg)
                    if mp:
                        port = mp.group(1)
                    print(f"  {ts}  connecting  {proto}:{port}")
                    continue

                if "AdapterUtils_win" in msg or "Binding v" in msg:
                    continue

                for pattern, meaning in SIGNALS:
                    if pattern.search(msg):
                        key = meaning.split(":")[0]
                        counts[key] = counts.get(key, 0) + 1
                        events.append((ts, proto, port, meaning))
                        print(f"  {ts}  {proto}:{port:<6} {meaning}")
                        break

            otext, o_off = tail(OPENVPN_LOG, o_off)
            for line in otext.splitlines():
                low = line.lower()
                if "initialization sequence completed" in low:
                    print("           openvpn: connected")
                elif "auth_failed" in low or "authentication failed" in low:
                    print("           openvpn: AUTH FAILED")

            time.sleep(2)
    except KeyboardInterrupt:
        pass

    elapsed = time.time() - start
    print(f"\n--- {elapsed / 60:.1f} minutes watched ---")
    if not events:
        print("No failure signal in the log. Either the run went cleanly, or the app never connected.")
    else:
        print(f"{len(events)} failure signal(s):\n")
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:3}x  {name}")


if __name__ == "__main__":
    main()
