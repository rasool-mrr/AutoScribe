"""A hung CLI must be recognised as stuck, not retried for eight minutes per test.

When Windscribe's GUI is dead the CLI does not fail: it blocks. run_cli returns (-1, "") after its
30-second timeout, so `engine_is_stuck("")` was False and auto-recovery never fired. Measured with
the fake below: ensure_disconnected made 16 CLI calls - about eight minutes at 30 s each - and then
returned False, skipping the test. That is the exact situation the recovery was written for.
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


class HungWorker(main.WindscribeWorker):
    """Its CLI never answers: every call times out, exactly like a dead GUI."""

    def __init__(self):
        self.stop_event = FakeStop()
        self.cli_cmd = "fake"
        self.consecutive_timeouts = 0
        self.calls = 0
        self.recoveries = 0

    def run_cli(self, args, timeout=30):
        self.calls += 1
        self.consecutive_timeouts += 1
        return -1, ""

    def recover_engine(self, wait_seconds=60):
        self.recoveries += 1
        return True

    def log(self, msg, tag="INFO"):
        pass


def test_two_consecutive_timeouts_count_as_stuck():
    # engine_is_stuck only ever saw real status text; silence is the hung-CLI case.
    worker = HungWorker()
    assert worker.engine_is_hung() is False
    worker.run_cli(["status"])
    assert worker.engine_is_hung() is False
    worker.run_cli(["status"])
    assert worker.engine_is_hung() is True


def test_a_single_timeout_is_not_stuck():
    # One slow call is normal under load; only a run of them means the process is gone.
    worker = HungWorker()
    worker.run_cli(["status"])
    assert worker.engine_is_hung() is False


def test_ensure_disconnected_does_not_burn_the_budget_on_a_hung_cli():
    # Five retries with three-second waits plus 30-second timeouts is ~8 minutes for one test.
    worker = HungWorker()
    assert worker.ensure_disconnected() is False
    assert worker.calls <= 3, f"{worker.calls} CLI calls against a hung client"


def test_an_answering_cli_is_never_hung():
    worker = HungWorker()
    worker.consecutive_timeouts = 0
    assert worker.engine_is_hung() is False
