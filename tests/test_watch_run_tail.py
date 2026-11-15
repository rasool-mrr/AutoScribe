"""contrib/watch_run.py must not lose or duplicate lines while following a growing log.

Text-mode f.tell() returns an opaque cookie, not a byte offset, so it cannot be compared with
os.path.getsize(); a line written in two pieces was returned half-read or dropped.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contrib"))

import watch_run  # noqa: E402


def test_a_partial_line_is_returned_whole_by_the_next_read(tmp_path):
    log = tmp_path / "client.log"
    log.write_bytes(b'{"a": 1}\n{"b": ')
    text, offset = watch_run.tail(str(log), 0)
    assert text == '{"a": 1}\n', "the incomplete line must be held back"
    assert offset == len(b'{"a": 1}\n'), "the offset must stay a real byte position"

    with open(log, "ab") as f:
        f.write(b'2}\n')
    text, offset = watch_run.tail(str(log), offset)
    assert text == '{"b": 2}\n', "the held-back line must arrive complete, exactly once"


def test_no_new_bytes_returns_nothing(tmp_path):
    log = tmp_path / "client.log"
    log.write_bytes(b"one\n")
    _, offset = watch_run.tail(str(log), 0)
    text, same = watch_run.tail(str(log), offset)
    assert (text, same) == ("", offset)


def test_a_truncated_file_is_read_from_the_start(tmp_path):
    log = tmp_path / "client.log"
    log.write_bytes(b"a-long-line\n")
    _, offset = watch_run.tail(str(log), 0)
    log.write_bytes(b"x\n")         # the app rotated/truncated it
    text, _ = watch_run.tail(str(log), offset)
    assert text == "x\n"


def test_a_missing_file_is_not_an_error(tmp_path):
    text, offset = watch_run.tail(str(tmp_path / "nope.log"), 0)
    assert (text, offset) == ("", 0)
