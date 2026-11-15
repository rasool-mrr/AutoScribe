"""The "connected" verdict must survive a flapping tunnel.

Windscribe shows Connected / Disconnected / Connecting in its status text, and while a WireGuard
handshake keeps dying it alternates. A single "Connected" reading used to be enough to record a
SUCCESS, which is exactly the false positive this suite guards against.
"""
import time

import main


class FakeStop:
    """Never blocks and never stops, so the poll loop runs at full speed."""

    def wait(self, _secs):
        return False


class FakeWorker(main.WindscribeWorker):
    """WindscribeWorker without __init__: run_cli, stop_event, log and phase are all it needs."""

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.stop_event = FakeStop()

    def run_cli(self, args, timeout=30):
        return 0, self._statuses.pop(0) if self._statuses else DISCONNECTED

    def log(self, msg, tag="INFO"):
        pass

    def phase(self, idx, state, secs=None):
        pass


CONNECTED = "Login: Logged in\nConnection: Connected\nFirewall: Off\n"
DISCONNECTED = "Login: Logged in\nConnection: Disconnected\nFirewall: Off\n"
CONNECTING = "Login: Logged in\nConnection: Connecting\nFirewall: Off\n"


def test_single_connected_reading_is_not_enough():
    # Connected once, then back to Connecting: the old code returned True on the first poll.
    fake = FakeWorker([CONNECTED, CONNECTING, DISCONNECTED])
    ok, _ = fake.wait_for_connection(start_time=time.time(), timeout=0.2)
    assert ok is False


def test_stable_connected_readings_win():
    fake = FakeWorker([CONNECTING, CONNECTED, CONNECTED, CONNECTED])
    ok, _ = fake.wait_for_connection(start_time=time.time(), timeout=30)
    assert ok is True


def test_connected_text_alone_is_not_a_success():
    # The route only becomes SUCCESS after a ping comes back through the tunnel.
    assert "tunnel_carries_traffic" in dir(main.WindscribeWorker)


def test_flapping_status_variants():
    for text in (CONNECTED, DISCONNECTED, CONNECTING):
        assert main.WindscribeWorker.is_connected_output(text) == (text == CONNECTED)
