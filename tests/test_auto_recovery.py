"""Auto-recovery must restart the GUI, remember it is restarted, and give up gracefully.

The real recovery is exercised by verify_recovery.py against the installed client; these tests pin
the decisions: which state triggers a restart, that a restart is not attempted forever, and that a
failed restart stops the run instead of spinning.
"""
import main


class FakeStop:
    def wait(self, _secs):
        return False


class StuckWorker(main.WindscribeWorker):
    """Reports the stuck state and records whether it was asked to recover."""

    def __init__(self, recovers):
        self.stop_event = FakeStop()
        self.recovers = recovers
        self.recovery_calls = 0
        self.logs = []
        self.cli_cmd = main.DEFAULT_CLI

    def log(self, msg, tag="INFO"):
        self.logs.append((tag, msg))

    def phase(self, *a, **k):
        pass

    def recover_engine(self, wait_seconds=60):
        self.recovery_calls += 1
        return self.recovers


STUCK = ("Login:       Logged in\n"
         "Connection:  Error: A required VPN process is not responding\n")


def test_the_recovery_cap_exists_and_is_small():
    # A broken client must not turn a 200-test queue into 200 restarts.
    assert 1 <= main.MAX_STUCK_RECOVERIES <= 5


def test_ensure_disconnected_restarts_a_dead_engine_instead_of_retrying():
    worker = StuckWorker(recovers=True)
    # The status reads back STUCK forever, so without the restart this would loop five times.
    worker.run_cli = lambda args, timeout=30: (0, STUCK)
    assert worker.ensure_disconnected() is True
    assert worker.recovery_calls == 1


def test_a_failed_restart_is_reported_not_looped():
    worker = StuckWorker(recovers=False)
    worker.run_cli = lambda args, timeout=30: (0, STUCK)
    assert worker.ensure_disconnected() is False
    assert worker.recovery_calls == 1
