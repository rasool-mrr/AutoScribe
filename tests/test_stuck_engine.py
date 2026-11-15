"""The stuck-engine state must not be mistaken for "still connected".

After an Error 6 abort, Windscribe stops answering 'Disconnected' and reports
'Connection:  Error: A required VPN process is not responding' forever - disconnect, firewall off
and fresh connect calls all change nothing until the GUI is restarted. The old code only accepted
the literal word DISCONNECTED, so ensure_disconnected() retried five times and then reported failure
for every remaining test: the run looked like it had lost the CLI connection.
"""
import main

STUCK = ("Login:       Logged in\n"
         "Connection:  Error: A required VPN process is not responding\n"
         "Firewall:    Off\n")
DISC = "Login:       Logged in\nConnection:  Disconnected\nFirewall:    Off\n"
CONNECTED = ("Login:       Logged in\n"
             "Connection:  Connected to Sofia - Vitoshka\n"
             "Protocol:    IKEv2:500\n")
CONNECTING = "Login:       Logged in\nConnection:  Connecting to Sofia - Vitoshka\n"


def test_stuck_engine_counts_as_disconnected():
    # Nothing is tunnelled in that state, so waiting for the word DISCONNECTED would never end.
    assert main.WindscribeWorker.is_disconnected_output(STUCK) is True


def test_stuck_engine_is_detected_so_the_run_can_stop():
    assert main.WindscribeWorker.engine_is_stuck(STUCK) is True
    assert main.WindscribeWorker.engine_is_stuck(DISC) is False
    assert main.WindscribeWorker.engine_is_stuck(CONNECTED) is False


def test_stuck_is_never_reported_as_connected():
    assert main.WindscribeWorker.is_connected_output(STUCK) is False


def test_a_real_connection_is_still_neither_stuck_nor_disconnected():
    assert main.WindscribeWorker.is_disconnected_output(CONNECTED) is False
    assert main.WindscribeWorker.engine_is_stuck(CONNECTED) is False


def test_connecting_is_not_disconnected():
    assert main.WindscribeWorker.is_disconnected_output(CONNECTING) is False


class FakeStop:
    def wait(self, _secs):
        return False


class FakeWorker(main.WindscribeWorker):
    """Only the disconnect handshake is exercised here."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.stop_event = FakeStop()
        self.calls = 0

    def run_cli(self, args, timeout=30):
        self.calls += 1
        if args and args[0] == "status" and self._outputs:
            return 0, self._outputs.pop(0)
        return 0, STUCK


def test_ensure_disconnected_accepts_the_stuck_state_immediately():
    # One status read and it is done - it must not burn five retries with sleeps.
    worker = FakeWorker([STUCK])
    assert worker.ensure_disconnected() is True
    assert worker.calls == 1
