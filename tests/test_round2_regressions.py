"""Gaps found reviewing round 2: each test below failed on the round-2 code."""
import main

CONNECTED = ("Login:       Logged in\n"
             "Connection:  Connected to Melbourne - Yarra\n"
             "Protocol:    IKEv2:500\n")
DISC = "Login:       Logged in\nConnection:  Disconnected\n"
LOCS = [{"city": f"C{i}", "location": f"P{i}", "country": "X", "continent": "Y"} for i in range(6)]


class Stop:
    def __init__(self):
        self._set = False

    def wait(self, _s):
        return self._set

    def set(self):
        self._set = True

    def clear(self):
        self._set = False

    def is_set(self):
        return self._set


class Pinger:
    def run(self, host, count=5, reply_timeout_ms=2000):
        return {"avg": 40.0, "min": 38.0, "max": 42.0, "loss": 0.0}, None


class App:
    def __init__(self):
        self.results = []
        self.finished = None

    def post(self, fn, *a, **k):
        fn(*a, **k)

    def log_message(self, *a, **k):
        pass

    def set_phase(self, *a, **k):
        pass

    def begin_test(self, *a, **k):
        pass

    def set_ping(self, *a, **k):
        pass

    def add_result_row(self, city, node, country, proto, port, status, *rest):
        self.results.append(status)

    def job_finished(self, kept, ok, fail):
        self.finished = (kept, ok, fail)


class DB:
    def __init__(self):
        self.rows = []

    def is_tested(self, *a):
        return False

    def record_result(self, *a):
        self.rows.append(a)


class Base(main.WindscribeWorker):
    def __init__(self):
        self.app = App()
        self.stop_event = Stop()
        self.running = False
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.pinger = Pinger()
        self.db = DB()
        self.restarts = 0
        self.timeout_calls = 0

    def timed_out(self):
        self.consecutive_timeouts += 1
        self.timeout_calls += 1
        return -1, ""

    def answered(self, out):
        self.consecutive_timeouts = 0
        return 0, out

    def log(self, msg, tag="INFO"):
        pass

    def phase(self, idx, state, secs=None):
        pass


def run(worker, monkeypatch, locations):
    monkeypatch.setattr(main.LocationManager, "load_locations", staticmethod(lambda: locations))
    worker._run({"ikev2": [500]}, {"keys": set(), "random_cities": False, "chaos_mode": False,
                                   "resume": False, "stop_on_success": False, "timeout": 0.3,
                                   "settle": 0, "ping_host": "1.1.1.1", "ping_count": 1,
                                   "profile_name": ""})
    return worker


def test_a_timed_out_first_status_read_is_not_a_failed_route():
    class W(Base):
        n = 0

        def run_cli(self, args, timeout=30):
            self.n += 1
            return self.timed_out() if self.n == 1 else self.answered(CONNECTED)

    carried, _r, err = W().tunnel_carries_traffic("1.1.1.1", 1, expected="Melbourne - Yarra")
    assert carried is True, err


def test_a_client_that_cannot_be_restarted_ends_the_run_instead_of_skipping_every_route(monkeypatch):
    class W(Base):
        def run_cli(self, args, timeout=30):
            return self.timed_out()

        def recover_engine(self, wait_seconds=60):
            self.restarts += 1
            return False

    w = run(W(), monkeypatch, LOCS)
    assert w.timeout_calls <= 4, f"{w.timeout_calls} timed-out CLI calls for a dead client"
    assert w.app.finished is not None


def test_a_gui_that_dies_after_connect_is_restarted_not_blamed_on_the_route(monkeypatch):
    class W(Base):
        connected = False
        recovered = False

        def run_cli(self, args, timeout=30):
            if args and args[0] == "connect":
                self.connected = True
                return self.answered("")
            if args and args[0] == "status":
                if self.recovered:
                    return self.answered(CONNECTED if self.connected else DISC)
                if not self.connected:
                    return self.answered(DISC)
                return self.timed_out()
            return self.answered("")

        def recover_engine(self, wait_seconds=60):
            self.restarts += 1
            self.recovered = True
            self.connected = False
            return True

    yarra = [{"city": "Melbourne", "location": "Yarra", "country": "Australia", "continent": "Oceania"}]
    w = run(W(), monkeypatch, yarra)
    assert w.restarts == 1
    assert [r[5] for r in w.db.rows] == ["SUCCESS"], "the dead GUI was recorded as a route failure"


def test_the_restart_cap_also_covers_the_hung_cli_path(monkeypatch):
    # The CLI hangs at the top of every test, the restart "works" each time, and the route itself
    # then runs fine. Only the cap in the hung path stands between that and one restart per test.
    class W(Base):
        target = None

        def run_cli(self, args, timeout=30):
            if args and args[0] == "connect":
                self.target = args[2]
                return self.answered("")
            if args and args[0] == "disconnect":
                self.target = None
                return self.answered("")
            if self.target is None:
                return self.timed_out()                      # not connected yet: the CLI is hung
            city = {"P%d" % i: "C%d" % i for i in range(6)}[self.target]
            return self.answered(f"Login:       Logged in\nConnection:  Connected to {city} - {self.target}\n")

        def recover_engine(self, wait_seconds=60):
            self.restarts += 1
            self.consecutive_timeouts = 0
            return True

    w = run(W(), monkeypatch, LOCS)
    assert w.restarts == main.MAX_STUCK_RECOVERIES, f"{w.restarts} restarts for a client that keeps hanging"
