"""Mutations that used to survive the suite.

Each of these changes breaks real behaviour, and the whole 116-test suite still passed after it. They
are pinned here by exercising the *wiring*, not just the helper the wiring calls:

  * the post-ping status check inside tunnel_carries_traffic
  * the server-mismatch check inside tunnel_carries_traffic (only the helper was tested)
  * the '(network interference detected)' suffix handling in connected_server
  * the MAX_STUCK_RECOVERIES cap (the old test used two locations, so it could never reach it)
"""
import main

CONNECTED = ("Login:       Logged in\n"
             "Connection:  Connected to Melbourne - Yarra\n"
             "Protocol:    Stealth:443\n")
DROPPED = "Login:       Logged in\nConnection:  Disconnected\n"
INTERFERENCE = ("Login:       Logged in\n"
                "Connection:  Connected to Melbourne - Yarra (network interference detected)\n")
CHECKING = ("Login:       Logged in\n"
            "Connection:  Connected to Melbourne - Yarra (checking the connection)\n")
OTHER_SERVER = ("Login:       Logged in\n"
                "Connection:  Connected to Melbourne - Port Phillip\n")


class Seq:
    def __init__(self, items):
        self.items = list(items)

    def pop(self, i=0):
        return self.items.pop(i)

    def __bool__(self):
        return bool(self.items)


class FakePinger:
    def __init__(self, result):
        self.result = result

    def run(self, host, count=5, reply_timeout_ms=2000):
        return self.result


OK_PING = ({"avg": 40.0, "min": 38.0, "max": 42.0, "loss": 0.0}, None)


class TrafficWorker(main.WindscribeWorker):
    """Scripted status sequence, one canned ping result."""

    def __init__(self, statuses, ping_result=OK_PING):
        self.cli_cmd = "fake"
        self.pinger = FakePinger(ping_result)
        self._statuses = Seq(statuses)
        self.consecutive_timeouts = 0

    def run_cli(self, args, timeout=30):
        return self._statuses.pop()

    @property
    def stop_event(self):
        class Never:
            def wait(self, _s):
                return False

            def is_set(self):
                return False

            def clear(self):
                pass

            def set(self):
                pass
        return Never()

    def log(self, msg, tag="INFO"):
        pass


def test_tunnel_carries_traffic_rejects_a_tunnel_that_died_during_the_ping():
    # Mutation killed: removing the post-ping status check made this return True.
    worker = TrafficWorker([(0, CONNECTED), (0, DROPPED)])
    carried, _result, err = worker.tunnel_carries_traffic("1.1.1.1", 2)
    assert carried is False, "a tunnel that dropped during the ping was accepted"
    assert "dropped" in err


def test_tunnel_carries_traffic_rejects_a_different_server():
    # Mutation killed: only is_different_server() was tested before, never this wiring.
    worker = TrafficWorker([(0, OTHER_SERVER)])
    carried, _result, err = worker.tunnel_carries_traffic("1.1.1.1", 2, expected="Melbourne - Yarra")
    assert carried is False, "a route connected to the wrong server was accepted"
    assert "instead of" in err


def test_tunnel_carries_traffic_accepts_the_right_server():
    worker = TrafficWorker([(0, CONNECTED), (0, CONNECTED)])
    carried, _result, _err = worker.tunnel_carries_traffic("1.1.1.1", 2, expected="Melbourne - Yarra")
    assert carried is True


def test_network_interference_is_not_connected():
    # Mutation killed: dropping the suffix handling in is_connected_output made this True.
    assert main.WindscribeWorker.is_connected_output(INTERFERENCE) is False


def test_checking_the_connection_is_not_connected():
    assert main.WindscribeWorker.is_connected_output(CHECKING) is False


def test_connected_server_strips_the_interference_suffix():
    # Mutation killed: removing the suffix strip left '... (network interference detected)' in the
    # name, which then compared unequal to every expected server.
    assert main.WindscribeWorker.connected_server(INTERFERENCE) == "Melbourne - Yarra"
    assert main.WindscribeWorker.connected_server(CHECKING) == "Melbourne - Yarra"


# --- the recovery cap: needs enough locations to actually reach it ---

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


class StuckForever(main.WindscribeWorker):
    def __init__(self):
        self.app = FakeApp()
        self.stop_event = FakeStop()
        self.running = False
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.pinger = FakePinger(OK_PING)
        self.db = FakeDB()
        self.restarts = 0

    def run_cli(self, args, timeout=30):
        if args and args[0] == "status":
            return 0, STUCK
        return 0, ""

    def recover_engine(self, wait_seconds=60):
        self.restarts += 1
        return True          # the restart always "works", the engine always dies again

    def log(self, msg, tag="INFO"):
        pass

    def phase(self, idx, state, secs=None):
        pass


OPTS = {"keys": set(), "random_cities": False, "chaos_mode": False, "resume": False,
        "stop_on_success": False, "timeout": 0.2, "settle": 0, "ping_host": "1.1.1.1",
        "ping_count": 1, "profile_name": ""}


def five_locations():
    return [{"city": f"City{i}", "location": f"Pop{i}", "country": "Australia", "continent": "Oceania"}
            for i in range(5)]


def test_the_cap_is_actually_enforced(monkeypatch):
    # With two locations the loop can never reach the cap, which is why the old cap test was useless.
    monkeypatch.setattr(main.LocationManager, "load_locations", staticmethod(five_locations))
    worker = StuckForever()
    worker._run({"stealth": [443]}, dict(OPTS))
    assert worker.restarts == main.MAX_STUCK_RECOVERIES, (
        f"{worker.restarts} restarts for a permanently broken client")
    assert worker.app.finished is not None, "the run never finished"
