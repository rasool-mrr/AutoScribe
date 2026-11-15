"""A second Error 6 on the retry must not throw away the rest of the queue.

Real run, 2026-11-15: Stealth hit Error 6, the app restarted Windscribe and retried, the retry hit
Error 6 again, and the run stopped there - 25 of a much larger plan were recorded and the Log panel
looked empty afterwards. Two separate faults:

1. the second failure did `break`, ending the whole queue for one bad route; and
2. the CLI_STUCK row was posted to the UI but never written to the database, so the run's tail
   vanished from the results once the table was reloaded from disk.

This pins both, plus the on-disk log that makes a lost run readable afterwards.
"""
import main


class _FastClock:
    def __init__(self, step=1.0):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


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
DISC = "Login:       Logged in\nConnection:  Disconnected\n"


def test_cli_stuck_has_a_translated_label():
    # Without a label the results table shows the raw enum name to the user.
    for lang in main.i18n.LANGUAGES:
        assert main.i18n.STRINGS["status_CLI_STUCK"][lang]


def test_the_stuck_engine_is_detected_and_never_connected():
    assert main.WindscribeWorker.engine_is_stuck(STUCK) is True
    assert main.WindscribeWorker.is_connected_output(STUCK) is False
    assert main.WindscribeWorker.engine_is_stuck(DISC) is False


# --- tunnel_carries_traffic: a timed-out status read must not fake a failure ---

class _Seq:
    def __init__(self, items):
        self.items = list(items)

    def pop(self, i=0):
        return self.items.pop(i)


class TrafficWorker(main.WindscribeWorker):
    """Drives tunnel_carries_traffic with a scripted status sequence."""

    def __init__(self, statuses, ping_result=None):
        self.stop_event = FakeStop()
        self.cli_cmd = "fake"
        self._statuses = _Seq(statuses)
        self.pings = _Seq([ping_result]) if ping_result is not None else _Seq([])
        self.status_calls = 0

    def run_cli(self, args, timeout=30):
        self.status_calls += 1
        return self._statuses.pop()

    class _Pinger:
        def __init__(self, outer):
            self.outer = outer

        def run(self, host, count=5, reply_timeout_ms=2000):
            return self.outer.pings.pop()

    @property
    def pinger(self):
        return self._Pinger(self)


OK_PING = ({"avg": 40.0, "min": 38.0, "max": 42.0, "loss": 0.0}, None)
CONNECTED = ("Login:       Logged in\n"
             "Connection:  Connected to Melbourne - Yarra\n")
CLI_TIMEOUT = (-1, "")
DROPPED = "Login:       Logged in\nConnection:  Disconnected\n"


def test_a_timed_out_status_read_after_the_ping_is_not_a_drop():
    # run_cli returns (-1, "") when the CLI itself times out. That is "unknown", not "the tunnel
    # died": treating it as a drop threw away a good ping and recorded a working route as FAILURE.
    w = TrafficWorker([(0, CONNECTED), CLI_TIMEOUT, (0, CONNECTED)], OK_PING)
    carried, result, err = w.tunnel_carries_traffic("1.1.1.1", 2)
    assert carried is True, err
    assert result["avg"] == 40.0


def test_a_readable_disconnected_status_after_the_ping_is_still_a_drop():
    w = TrafficWorker([(0, CONNECTED), (0, DROPPED)], OK_PING)
    carried, _result, err = w.tunnel_carries_traffic("1.1.1.1", 2)
    assert carried is False
    assert "dropped" in err


# --- behaviour of the retry-and-continue path, driven through the real loop ---

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


class StuckWorker(main.WindscribeWorker):
    """The engine dies after `connect` and never comes back, even after a restart."""

    def __init__(self, restart_succeeds=True):
        self.app = FakeApp()
        self.stop_event = FakeStop()
        self.running = False
        self.cli_cmd = "fake"
        self.pinger = FakePinger()
        self.db = FakeDB()
        self.restart_succeeds = restart_succeeds
        self.restarts = 0
        # The readiness probe after a restart sleeps in real seconds; skip it in these tests.
        self.now = _FastClock()

    def wait_until_accepts_connect(self, target, route, attempts=5, probe_seconds=6):
        return self.restart_succeeds

    def run_cli(self, args, timeout=30):
        if args and args[0] == "status":
            return 0, STUCK
        return 0, ""

    def recover_engine(self, wait_seconds=60):
        self.restarts += 1
        return self.restart_succeeds

    def log(self, msg, tag="INFO"):
        pass

    def phase(self, idx, state, secs=None):
        pass


TWO_LOCATIONS = [{"city": "Melbourne", "location": "Yarra", "country": "Australia", "continent": "Oceania"},
                 {"city": "Sydney", "location": "Eshay", "country": "Australia", "continent": "Oceania"}]

OPTS = {"keys": set(), "random_cities": False, "chaos_mode": False, "resume": False,
        "stop_on_success": False, "timeout": 0.3, "settle": 0, "ping_host": "1.1.1.1",
        "ping_count": 1, "profile_name": ""}


def drive(worker, monkeypatch, locations):
    monkeypatch.setattr(main.LocationManager, "load_locations", staticmethod(lambda: locations))
    worker._run({"stealth": [443]}, dict(OPTS))
    return worker


def test_a_route_that_breaks_again_is_recorded_and_the_next_one_is_tried(monkeypatch):
    worker = drive(StuckWorker(), monkeypatch, TWO_LOCATIONS)
    assert len(worker.app.results) == 2, f"only {len(worker.app.results)} of 2 routes were tested"
    assert [r["status"] for r in worker.app.results] == ["CLI_STUCK", "CLI_STUCK"]


def test_cli_stuck_rows_reach_the_database(monkeypatch):
    # The bug: they were posted to the UI only, so reloading the table from disk lost them.
    worker = drive(StuckWorker(), monkeypatch, TWO_LOCATIONS)
    assert len(worker.db.rows) == 2, f"{len(worker.db.rows)} of 2 rows were persisted"
    assert all("CLI_STUCK" in row for row in worker.db.rows)


def test_restarts_are_capped_so_a_broken_client_cannot_spin(monkeypatch):
    worker = drive(StuckWorker(), monkeypatch, TWO_LOCATIONS)
    assert worker.restarts <= main.MAX_STUCK_RECOVERIES


def test_a_failed_restart_stops_without_recording_a_wrong_status(monkeypatch):
    worker = drive(StuckWorker(restart_succeeds=False), monkeypatch, TWO_LOCATIONS)
    assert worker.restarts == 1, "it must not retry a restart that cannot work"
    assert worker.app.finished is not None
    assert all(r["status"] == "CLI_STUCK" for r in worker.app.results)
