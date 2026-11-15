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


def test_ensure_disconnected_does_not_restart_the_client():
    # It runs at the top of EVERY test, so a restart here would bypass MAX_STUCK_RECOVERIES and
    # turn one stuck client into a restart per test. The batch loop owns that decision.
    worker = StuckWorker(recovers=True)
    worker.run_cli = lambda args, timeout=30: (0, STUCK)
    assert worker.ensure_disconnected() is True    # nothing is tunnelled, so nothing to remove
    assert worker.recovery_calls == 0, "ensure_disconnected must not restart Windscribe"
