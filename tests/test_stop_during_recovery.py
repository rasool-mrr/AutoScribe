"""Stop pressed during a recovery must not poison the route with a false CLI_STUCK row.

recover_engine() returns False when stop_event is set while it waits. _run read that as "the restart
failed", wrote CLI_STUCK to the database and broke. With Resume on, DatabaseManager.is_tested() has no
status filter, so that route is then skipped forever - a client problem permanently recorded as a
route verdict.
"""
import main


class FakeStop:
    def __init__(self):
        self._set = False

    def wait(self, _secs):
        return self._set

    def set(self):
        self._set = True

    def clear(self):
        self._set = False

    def is_set(self):
        return self._set


STUCK = ("Login:       Logged in\n"
         "Connection:  Error: A required VPN process is not responding\n")


class FakePinger:
    def run(self, host, count=5, reply_timeout_ms=2000):
        return {"avg": 40.0, "min": 38.0, "max": 42.0, "loss": 0.0}, None


class FakeApp:
    def __init__(self):
        self.results = []
        self.finished = None

    def post(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def log_message(self, *a, **k):
        pass

    def set_phase(self, *a, **k):
        pass

    def begin_test(self, *a, **k):
        pass

    def set_ping(self, *a, **k):
        pass

    def add_result_row(self, city, node, country, proto, port, status, duration, ping, loss):
        self.results.append({"city": city, "node": node, "status": status})

    def job_finished(self, kept, ok, fail):
        self.finished = (kept, ok, fail)


class FakeDB:
    def __init__(self):
        self.rows = []

    def is_tested(self, *a):
        return False

    def record_result(self, *a):
        self.rows.append(a)


class StopDuringRecovery(main.WindscribeWorker):
    """The engine is stuck and the user presses Stop inside recover_engine()."""

    def __init__(self):
        self.app = FakeApp()
        self.stop_event = FakeStop()
        self.running = False
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.pinger = FakePinger()
        self.db = FakeDB()
        self.restarts = 0

    def run_cli(self, args, timeout=30):
        if args and args[0] == "status":
            return 0, STUCK
        return 0, ""

    def recover_engine(self, wait_seconds=60):
        self.restarts += 1
        self.stop_event.set()      # the user pressed Stop while it was waiting
        return False

    def log(self, msg, tag="INFO"):
        pass

    def phase(self, idx, state, secs=None):
        pass


ONE_LOCATION = [{"city": "Melbourne", "location": "Yarra", "country": "Australia", "continent": "Oceania"}]

OPTS = {"keys": set(), "random_cities": False, "chaos_mode": False, "resume": False,
        "stop_on_success": False, "timeout": 0.3, "settle": 0, "ping_host": "1.1.1.1",
        "ping_count": 1, "profile_name": ""}


def test_stopping_during_recovery_records_nothing(monkeypatch):
    monkeypatch.setattr(main.LocationManager, "load_locations", staticmethod(lambda: ONE_LOCATION))
    worker = StopDuringRecovery()
    worker._run({"stealth": [443]}, dict(OPTS))
    assert worker.app.results == [], f"recorded {worker.app.results} after the user pressed Stop"
    assert worker.db.rows == []


def test_is_tested_ignores_cli_stuck_rows():
    # A stuck client is not a verdict about the route: Resume must re-test it later.
    db = main.DatabaseManager(app=None)
    db.clear_db()
    db.record_result("Yarra", "Melbourne", "Australia", "stealth", 443, "CLI_STUCK", 0, None, None, "p")
    assert db.is_tested("Yarra", "Melbourne", "Australia", "stealth", 443) is False
    db.record_result("Yarra", "Melbourne", "Australia", "stealth", 443, "FAILURE", 0, None, None, "p")
    assert db.is_tested("Yarra", "Melbourne", "Australia", "stealth", 443) is True
