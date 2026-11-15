"""Ping parsing must not mistake icmp_seq for the latency.

Windows localizes the whole reply line and prints it in the console's OEM code page, so the word
"time" cannot be matched there - that is what BEFORE_TTL_RE is for: the latency is the number just
before "ttl=". On Linux/macOS the same line keeps ASCII but can still be localized, and then
icmp_seq=N appears before ttl=, so BEFORE_TTL_RE picked up the SEQUENCE NUMBER:

    64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 время=12.3 мс   ->  1.0 ms  (wrong)

Every route on such a system was ranked on a fake latency, which is worse than no measurement.
"""
import main


def parse(*lines):
    return main.PingRunner.parse("\n".join(lines))


def test_localized_linux_reply_uses_the_real_latency():
    assert parse("64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 время=12.3 мс") == [12.3]


def test_german_reply_uses_the_real_latency():
    assert parse("64 bytes from 1.1.1.1: icmp_seq=2 ttl=57 Zeit=18.5 ms") == [18.5]


def test_a_sequence_number_is_never_taken_for_the_latency():
    # The failure mode: icmp_seq=7 must not become 7 ms.
    got = parse("64 bytes from 1.1.1.1: icmp_seq=7 ttl=57")
    assert got == [], f"parsed {got} out of a line with no latency in it"


def test_english_and_short_forms_still_work():
    assert parse("64 bytes from 1.1.1.1: icmp_seq=3 ttl=57 time=7.9 ms") == [7.9]
    assert parse("Reply from 1.1.1.1: bytes=32 time<1ms TTL=57") == [1.0]


def test_comma_decimal_separator_still_works():
    assert parse("64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12,3 ms") == [12.3]


def test_the_windows_summary_line_is_not_counted_as_a_reply():
    # "Minimum = 12ms, Maximum = 18ms, Average = 15ms" must not add three numbers.
    lines = ["Reply from 1.1.1.1: bytes=32 time=12ms TTL=57",
             "Reply from 1.1.1.1: bytes=32 time=18ms TTL=57",
             "Minimum = 12ms, Maximum = 18ms, Average = 15ms"]
    assert parse(*lines) == [12.0, 18.0]
