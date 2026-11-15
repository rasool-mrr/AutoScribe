"""End-to-end proof that auto-recovery works: simulate the dead-engine state, let the worker
recover it, then confirm the CLI answers normally and stays logged in.

This is the only check that proves the feature, because the stuck state comes from Windscribe's own
engine, not from anything a fake can reproduce faithfully.
"""
import argparse
import sys

import os

# Run from contrib/ during development: main.py lives one level up.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class FakeStop:
    def __init__(self):
        self.set_called = False

    def wait(self, _secs):
        return False

    def is_set(self):
        return False

    def clear(self):
        pass

    def set(self):
        pass


class Probe(main.WindscribeWorker):
    """A worker with no app and no database - only the recovery path is exercised."""

    def __init__(self):
        self.cli_cmd = main.DEFAULT_CLI
        self.stop_event = FakeStop()
        self.logs = []
        self.pinger = main.PingRunner()

    def log(self, msg, tag="INFO"):
        print(f"  [{tag}] {msg}")
        self.logs.append((tag, msg))

    def phase(self, *a, **k):
        pass


def main_probe():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes-kill-gui", action="store_true",
                    help="required: this closes and restarts your running Windscribe window")
    args = ap.parse_args()

    if not args.yes_kill_gui:
        print("This probe closes and restarts Windscribe's GUI window to test recovery.")
        print("Re-run with --yes-kill-gui when nothing else is using it.")
        return 2

    w = Probe()

    print("1. CLI reachable?")
    code, out = w.run_cli(["status"], timeout=15)
    print(f"   rc={code}  {out.strip().splitlines()[1] if len(out.strip().splitlines()) > 1 else out.strip()!r}")
    if code == -1:
        print("   CLI is not answering; cannot run this probe.")
        return 1

    print("\n2. Killing Windscribe's GUI to create the state Error 6 leaves behind...")
    recovered = w.recover_engine(wait_seconds=90)

    print(f"\n3. recover_engine() -> {recovered}")
    if not recovered:
        return 1

    code, out = w.run_cli(["status"], timeout=15)
    login = [l for l in out.splitlines() if l.startswith("Login:")]
    conn = [l for l in out.splitlines() if l.startswith("Connection:")]
    print(f"   {login[0].strip() if login else 'no Login line'}")
    print(f"   {conn[0].strip() if conn else 'no Connection line'}")

    ok = (
        recovered
        and code != -1
        and login and "logged in" in login[0].lower()
        and conn and w.is_disconnected_output(out)
        and not w.engine_is_stuck(out)
    )
    print(f"\nRESULT: {'PASS - recovered and still logged in' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main_probe())
