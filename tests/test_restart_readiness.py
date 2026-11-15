"""A restart is not finished when the CLI merely answers - it must accept a connect again.

Real run, 2026-11-15 23:22: Oslo via udp:443 hit Error 6, the app restarted Windscribe, waited for
"Windscribe is answering again", retried the route and timed out. The user then connected by hand to
Prague and it worked in 8.4 s - the client was healthy, the app had simply sent `connect` while
Windscribe was still coming up, and that request was dropped silently. The result was a 25-second
timeout recorded as a route failure.

The readiness signal cannot be `Disconnected`: that is exactly what the client says while it is still
initializing and still ignoring `connect`.
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


DISC = "Login:       Logged in\nConnection:  Disconnected\n"
NOT_READY = "Login:       Logging in\nConnection:  Disconnected\n"


class InstantStop(FakeStop):
    """Never sleeps, so the probe's real multi-second waits do not slow the suite down."""

    def wait(self, _secs):
        return self._set


class FakeClock:
    """Advances a fixed step per read: the probe's deadline is reached in a few iterations, not seconds."""

    def __init__(self, step=1.0):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


class RestartWorker(main.WindscribeWorker):
    """The client answers `Disconnected` immediately, but ignores connect for N attempts."""

    def __init__(self, ignores_connect_for):
        self.stop_event = InstantStop()
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.ignores_connect_for = ignores_connect_for
        self.connects = 0
        self.in_flight = False
        self.logs = []
        self.now = FakeClock()

    def windscribe_gui_running(self):
        return True

    def run_cli(self, args, timeout=30):
        if args and args[0] == "status":
            if self.in_flight:
                return 0, "Login:       Logged in\nConnection:  Connecting to Oslo\n"
            return 0, DISC
        if args and args[0] == "connect":
            self.connects += 1
            if self.connects > self.ignores_connect_for:
                self.in_flight = True      # this one was actually accepted
            return 0, ""
        if args and args[0] == "disconnect":
            self.in_flight = False
            return 0, ""
        return 0, ""

    def recover_engine(self, wait_seconds=60):
        return True

    def log(self, msg, tag="INFO"):
        self.logs.append((tag, msg))

    def phase(self, idx, state, secs=None):
        pass


def test_recovery_is_not_done_until_connect_is_accepted():
    # recover_engine + a readiness probe that actually tries to connect.
    worker = RestartWorker(ignores_connect_for=2)
    assert worker.wait_until_accepts_connect("best", "udp:443", attempts=5) is True
    assert worker.connects >= 3, "it stopped probing before the client accepted a connect"


def test_a_client_that_never_accepts_is_reported_not_waited_on_forever():
    worker = RestartWorker(ignores_connect_for=99)
    assert worker.wait_until_accepts_connect("best", "udp:443", attempts=3) is False
    assert worker.connects == 3


def test_the_probe_does_not_run_when_the_user_pressed_stop():
    worker = RestartWorker(ignores_connect_for=99)
    worker.stop_event.set()
    assert worker.wait_until_accepts_connect("best", "udp:443", attempts=5) is False


# --- the loop must actually call it: without this the helper could be dead code ---

class LoopApp:
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

    def add_result_row(self, city, node, country, proto, port, status, *rest):
        self.results.append({"city": city, "status": status})

    def job_finished(self, kept, ok, fail):
        self.finished = (kept, ok, fail)


class LoopDB:
    def __init__(self):
        self.rows = []

    def is_tested(self, *a):
        return False

    def record_result(self, *a):
        self.rows.append(a)


class StuckThenHealthy(main.WindscribeWorker):
    """Engine dies once, restart succeeds, and the readiness probe is what makes the retry work."""

    def __init__(self):
        self.app = LoopApp()
        self.stop_event = FakeStop()
        self.running = False
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.pinger = FakePinger()
        self.db = LoopDB()
        self.restarts = 0
        self.probes = 0
        self.now = FakeClock()

    def run_cli(self, args, timeout=30):
        if args and args[0] == "status":
            return 0, ("Login:       Logged in\n"
                       "Connection:  Error: A required VPN process is not responding\n")
        return 0, ""

    def recover_engine(self, wait_seconds=60):
        self.restarts += 1
        return True

    def wait_until_accepts_connect(self, target, route, attempts=5, probe_seconds=6):
        self.probes += 1
        return True


class FakePinger:
    def run(self, host, count=5, reply_timeout_ms=2000):
        return {"avg": 40.0, "min": 38.0, "max": 42.0, "loss": 0.0}, None


def test_the_restart_waits_for_readiness_before_retrying(monkeypatch):
    monkeypatch.setattr(main.LocationManager, "load_locations",
                        staticmethod(lambda: [{"city": "Oslo", "location": "Oslo",
                                               "country": "Norway", "continent": "Europe"}]))
    worker = StuckThenHealthy()
    worker._run({"udp": [443]}, {"keys": set(), "random_cities": False, "chaos_mode": False,
                                 "resume": False, "stop_on_success": False, "timeout": 0.2,
                                 "settle": 0, "ping_host": "1.1.1.1", "ping_count": 1,
                                 "profile_name": ""})
    assert worker.restarts == 1
    assert worker.probes == 1, "the retry ran without checking the client was ready"
