"""The batch runner must survive every branch of one test.

The flapping-tunnel fix added `carried`, but only assigned it inside the `if connected:` branch
and then used it further down for `stop_on_success`. On a failed connection the name did not
exist, so the first failing test raised NameError, the whole run died, and the results table
stopped filling - the app looked broken. This drives _run() over both branches with a fake CLI.
"""
import main

STATUS_DOWN = "Login:       Logged in\nConnection:  Disconnected\n"


class FakePinger:
    def __init__(self, works):
        self.works = works

    def run(self, host, count=5, reply_timeout_ms=2000):
        if self.works:
            return {"avg": 40.0, "min": 38.0, "max": 42.0, "loss": 0.0}, None
        return None, "no reply"


class FakeApp:
    """Stands in for the Tk app: everything the worker posts is recorded instead of drawn."""

    def __init__(self):
        self.results = []
        self.finished = None
        self.logs = []

    def post(self, fn, *args, **kwargs):
        fn(*args, **kwargs)

    def log_message(self, msg, tag="INFO"):
        self.logs.append((tag, msg))

    def set_phase(self, *a, **k):
        pass

    def begin_test(self, *a, **k):
        pass

    def set_ping(self, *a, **k):
        pass

    def add_result_row(self, city, node, country, proto, port, status, duration, ping, loss):
        self.results.append({"city": city, "node": node, "proto": proto, "port": port, "status": status})

    def job_finished(self, kept, ok, fail):
        self.finished = (kept, ok, fail)

    def disconnect_finished(self, *a, **k):
        pass

    def manual_connect_finished(self, *a, **k):
        pass


class FakeStop:
    """Never blocks: the poll loops run at full speed instead of sleeping for real seconds."""

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


class FakeWorker(main.WindscribeWorker):
    """WindscribeWorker wired to fakes: no CLI, no Tk, no real database file.

    The fake CLI is phase-aware, like the real one: it reports Disconnected until `connect` has been
    called, then whatever the scripted status list says. Without that, ensure_disconnected() would
    never see a disconnected state and every test would be skipped.
    """

    def __init__(self, statuses, ping_works):
        self.app = FakeApp()
        self.stop_event = FakeStop()
        self.running = False
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.pinger = FakePinger(ping_works)
        self._statuses = list(statuses)
        self._connected = False
        self.logs = []
        self.db = FakeDB()
        self.calls = []

    def run_cli(self, args, timeout=30):
        self.calls.append(list(args))
        if args and args[0] == "connect":
            self._connected = True
            return 0, ""
        if args and args[0] == "status":
            if not self._connected:
                return 0, STATUS_DOWN
            return 0, self._statuses.pop(0) if self._statuses else STATUS_DOWN
        return 0, ""

    def log(self, msg, tag="INFO"):
        self.logs.append((tag, msg))

    def phase(self, idx, state, secs=None):
        pass


class FakeDB:
    def __init__(self):
        self.rows = []

    def is_tested(self, *a):
        return False

    def record_result(self, *a):
        self.rows.append(a)


OPTS = {
    "keys": set(),
    "random_cities": False,
    "chaos_mode": False,
    "resume": False,
    "stop_on_success": False,
    "timeout": 1,
    "settle": 0,
    "ping_host": "1.1.1.1",
    "ping_count": 1,
    "profile_name": "",
}

ONE_LOCATION = [{"city": "Melbourne", "location": "Yarra", "country": "Australia", "continent": "Oceania"}]


def two_locations():
    return [{"city": "Melbourne", "location": "Yarra", "country": "Australia", "continent": "Oceania"},
            {"city": "Sydney", "location": "Eshay", "country": "Australia", "continent": "Oceania"}]


def drive(worker, monkeypatch, locations=None, work_plan=None, opts=None):
    monkeypatch.setattr(main.LocationManager, "load_locations",
                        staticmethod(lambda: locations or ONE_LOCATION))
    worker._run(work_plan or {"ikev2": [500]}, dict(opts or OPTS))
    return worker


def test_every_location_is_tested_when_they_all_fail(monkeypatch):
    # The regression that broke a whole run: `carried` was only assigned inside `if connected:`
    # and then used later, so the first FAILURE raised NameError, the outer handler swallowed it
    # and the run stopped after one test. Every selected location must still get its result row.
    worker = FakeWorker([], ping_works=False)
    drive(worker, monkeypatch, locations=two_locations())
    assert len(worker.app.results) == 2, f"only {len(worker.app.results)} of 2 tests ran"
    assert [r["status"] for r in worker.app.results] == ["FAILURE", "FAILURE"]
    assert not any("Critical Error" in msg for _tag, msg in worker.logs)


def test_connected_but_no_traffic_is_a_failure(monkeypatch):
    connected = ("Login:       Logged in\n"
                 "Connection:  Connected to Melbourne - Yarra\n"
                 "Protocol:    IKEv2:500\n")
    worker = FakeWorker([connected] * 10, ping_works=False)
    drive(worker, monkeypatch)
    assert worker.app.results[-1]["status"] == "FAILURE"


def test_connected_with_traffic_is_a_success(monkeypatch):
    connected = ("Login:       Logged in\n"
                 "Connection:  Connected to Melbourne - Yarra\n"
                 "Protocol:    IKEv2:500\n")
    worker = FakeWorker([connected] * 10, ping_works=True)
    drive(worker, monkeypatch)
    assert worker.app.results[-1]["status"] == "SUCCESS"


def test_stop_on_success_ignores_a_failed_route(monkeypatch):
    # The option must not end the run on a route that did not carry traffic.
    status_down = "Login:       Logged in\nConnection:  Disconnected\n"
    worker = FakeWorker([status_down] * 20, ping_works=False)
    opts = dict(OPTS, stop_on_success=True)
    monkeypatch.setattr(main.LocationManager, "load_locations", staticmethod(lambda: ONE_LOCATION))
    worker._run({"ikev2": [500]}, opts)
    assert worker.app.finished[0] is None, "stop_on_success kept a failed route"
