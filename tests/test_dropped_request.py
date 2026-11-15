"""A connect request that Windscribe silently dropped must not cost a full timeout.

Windscribe has two ways to refuse a connection and they look identical from `status`:

  * it tries and fails   -> "Connecting to <city>" appears, then "Disconnected"
  * it never tries       -> the status never leaves "Disconnected"

The second one happens when the GUI is showing a modal (e.g. "Manual connection mode failed"), or is
still starting up after a restart. The request is dropped without a word, and the app waited the whole
timeout (25-30 s) before recording a failure - "the bar keeps going back and forth" with nothing in the
log.

A request that was never even picked up can be detected early: after a couple of seconds with no
"Connecting to" in the status, the request went nowhere.
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
CONNECTING = "Login:       Logged in\nConnection:  Connecting to Dublin\n"
CONNECTED = ("Login:       Logged in\n"
             "Connection:  Connected to Dublin - Ireland\n"
             "Protocol:    Stealth:123\n")


class WaitWorker(main.WindscribeWorker):
    def __init__(self, statuses):
        self.stop_event = FakeStop()
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self._s = list(statuses)
        self.polls = 0
        self.now = self._clock()

    def _clock(self):
        """time.time() takes no arguments and advances one second per call."""
        holder = {"t": 0.0}

        def tick(*_args, **_kwargs):
            holder["t"] += 1.0
            return holder["t"]
        return tick

    def run_cli(self, args, timeout=30):
        self.polls += 1
        return 0, self._s.pop(0) if self._s else DISC


def test_a_request_that_was_never_picked_up_is_reported_early():
    # Windscribe never even started: status stays Disconnected. The old code burned the whole timeout.
    worker = WaitWorker([DISC] * 40)
    ok, _dur = worker.wait_for_connection(worker.now(), timeout=30)
    assert ok is False
    assert worker.polls <= 6, f"{worker.polls} polls for a request that was dropped immediately"


def test_a_request_that_is_being_tried_is_still_waited_for():
    # Rejected-by-network looks different: the client does show "Connecting to", so keep waiting.
    sequence = [DISC, CONNECTING] + [CONNECTING] * 20 + [CONNECTED, CONNECTED, CONNECTED]
    worker = WaitWorker(sequence)
    ok, _dur = worker.wait_for_connection(worker.now(), timeout=30)
    assert ok is True, "a slow connection that the client was actually trying was abandoned"


def test_a_normal_connection_still_needs_three_stable_polls():
    worker = WaitWorker([CONNECTED, CONNECTED])
    ok, _dur = worker.wait_for_connection(worker.now(), timeout=30)
    assert ok is False, "two polls must not be enough"
    worker = WaitWorker([CONNECTED] * 3)
    ok, _dur = worker.wait_for_connection(worker.now(), timeout=30)
    assert ok is True
