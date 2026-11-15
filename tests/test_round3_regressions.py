"""Found reviewing the final branch; each test failed on it."""
import os

import main
import test_round2_regressions as rr

STUCK = "Login:       Logged in\nConnection:  Error: A required VPN process is not responding\n"
DISC = "Login:       Logged in\nConnection:  Disconnected\n"
YARRA = [{"city": "Melbourne", "location": "Yarra", "country": "Australia", "continent": "Oceania"}]


class Ticker:
    t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


def test_stop_during_the_readiness_probe_records_nothing(monkeypatch):
    class W(rr.Base):
        stuck = True

        def __init__(self):
            super().__init__()
            self.now = Ticker()

        def run_cli(self, args, timeout=30):
            if args and args[0] == "status":
                return self.answered(STUCK if self.stuck else DISC)
            return self.answered("")

        def recover_engine(self, wait_seconds=60):
            self.stuck = False
            return True

        def wait_until_accepts_connect(self, *a, **k):
            self.stop_event.set()          # what the real probe returns when Stop is pressed
            return False

    w = rr.run(W(), monkeypatch, YARRA)
    assert w.db.rows == [], f"recorded {[r[5] for r in w.db.rows]} after the user pressed Stop"


def test_the_hung_cli_restart_also_waits_for_readiness(monkeypatch):
    class W(rr.Base):
        probes = 0
        hung = True

        def __init__(self):
            super().__init__()
            self.now = Ticker()

        def run_cli(self, args, timeout=30):
            if self.hung:
                return self.timed_out()
            return self.answered(DISC if args and args[0] == "status" else "")

        def recover_engine(self, wait_seconds=60):
            self.restarts += 1
            self.hung = False
            self.consecutive_timeouts = 0
            return True

        def wait_until_accepts_connect(self, *a, **k):
            self.probes += 1
            return True

    w = rr.run(W(), monkeypatch, YARRA)
    assert w.restarts == 1
    assert w.probes == 1, "the route ran straight after a restart, into a client that drops connects"


def test_the_suite_cannot_reach_the_users_database():
    # conftest redirects the data files for every test; the real ones live next to main.py.
    assert not os.path.abspath(main.DB_FILE).startswith(os.path.abspath(main.APP_PATH) + os.sep)
