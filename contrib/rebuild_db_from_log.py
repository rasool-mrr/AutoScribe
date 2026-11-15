"""Rebuild the results database from autoscribe.log.

The round-2 test suite deleted the real results (a test opened the user's database instead of a
temp file). Every attempt was logged with its location, route and outcome, so the rows are
reconstructable: the log is the record of what happened, the database is a cache of it.

    python contrib/rebuild_db_from_log.py            # dry run, shows what would be written
    python contrib/rebuild_db_from_log.py --write    # append the recovered rows
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

HEADER_RE = re.compile(
    r"\[(?:\d+/\d+)\]\s+(?P<city>.+?)\s+\((?P<country>[^)]*)\)\s+via\s+(?P<proto>\w+):(?P<port>\d+)")
OUTCOME_RE = re.compile(r"\[(SUCCESS|FAILURE|WARN|INFO|HEADER)\]\s+(.+)")
PING_RE = re.compile(r"Ping avg (\d+) ms.*loss (\d+)%")
CONNECTED_RE = re.compile(r"Connected in ([\d.]+)s")
TIMEOUT_RE = re.compile(r"Timed out on")
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
TAG_RE = re.compile(r"^\[(SUCCESS|FAILURE|WARN|INFO|HEADER)\]\s*")
# The header line carries the city and the region, never the datacenter nickname. That only shows up
# when the route is reported as kept: "staying connected to Seattle – Hendrix · ikev2:500".
KEPT_RE = re.compile(r"staying connected to (?P<name>.+?)\s*·")


def parse(log_path):
    """One row per logged attempt that produced a verdict."""
    rows = []
    pending = None
    nickname = ""

    def finish(status):
        nonlocal pending, nickname
        if pending is None:
            return
        if nickname and " - " not in pending["city"]:
            pending["node"] = nickname
        pending["status"] = status
        rows.append(pending)
        pending, nickname = None, ""

    for raw in open(log_path, encoding="utf-8", errors="replace"):
        line = raw.strip()
        stamp = STAMP_RE.match(line)
        body = line[stamp.end():].strip() if stamp else line
        when = stamp.group(1) if stamp else ""

        tag_m = TAG_RE.match(body)
        tag = tag_m.group(1) if tag_m else ""
        body = body[tag_m.end():] if tag_m else body

        head = HEADER_RE.search(body)
        if head:
            pending = {"city": head.group("city").strip(), "country": head.group("country").strip(),
                       "proto": head.group("proto"), "port": int(head.group("port")),
                       "timestamp": when, "status": None, "duration": 0.0, "ping": None, "loss": None,
                       "node": ""}
            nickname = ""
            continue

        if not pending:
            continue

        kept = KEPT_RE.search(body)
        if kept:
            name = kept.group("name").strip()
            # "Seattle – Hendrix": the UI uses an en dash between city and nickname.
            for dash in (" – ", " - "):
                if dash in name:
                    nickname = name.split(dash)[-1].strip()
                    break
            finish("SUCCESS")
            continue

        c = CONNECTED_RE.search(body)
        if c:
            pending["duration"] = float(c.group(1))
            continue
        p = PING_RE.search(body)
        if p:
            pending["ping"] = float(p.group(1))
            pending["loss"] = float(p.group(2))
            finish("SUCCESS")
            continue
        if TIMEOUT_RE.search(body):
            finish("FAILURE")
            continue
        if tag == "SUCCESS" and "Connected to" in body:
            finish("SUCCESS")
            continue
        if tag == "FAILURE" and ("Tunnel carried no traffic" in body or "carries no traffic" in body):
            finish("FAILURE")

    return rows


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=main.LOG_FILE)
    ap.add_argument("--write", action="store_true", help="actually insert the rows")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        sys.exit(f"log not found: {args.log}")

    rows = parse(args.log)
    if not rows:
        sys.exit("no attempt with a verdict found in the log")

    print(f"{len(rows)} attempts recovered from {os.path.basename(args.log)}")
    for r in rows[:10]:
        loc = r["city"] + (" - " + r["city"].split(" - ")[-1] if " - " in r["city"] else "")
        print(f"  {r['timestamp']}  {r['proto']}:{r['port']:<6} {r['status']:<8} {r['ping'] or ''}  {loc}")
    if len(rows) > 10:
        print(f"  ... {len(rows) - 10} more")

    if not args.write:
        print("\ndry run - pass --write to insert them")
        return 0

    # Direct insert rather than record_result(): that stamps the current time, and these rows must keep
    # the time they actually happened, which is only in the log.
    db = main.DatabaseManager(app=None)
    with db.lock:
        for r in rows:
            city, _, node = r["city"].partition(" - ")
            city = city.strip()
            node = (r.get("node") or node).strip()
            db.cursor.execute(
                "INSERT OR REPLACE INTO tests (location, city, country, protocol, port, status,"
                " duration, ping, packet_loss, profile_name, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (node or city, city, r["country"], r["proto"], r["port"], r["status"],
                 round(r["duration"], 2), r["ping"], r["loss"], "recovered", r["timestamp"]))
        db.conn.commit()
    print(f"\ninserted {len(rows)} rows into {main.DB_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
