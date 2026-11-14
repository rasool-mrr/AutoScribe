import pytest

import main

parse = main.PingRunner.parse

CASES = [
    ("linux",
     "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12.3 ms\n"
     "64 bytes from 1.1.1.1: icmp_seq=2 ttl=57 time=13.1 ms", [12.3, 13.1]),
    ("macos", "64 bytes from 1.1.1.1: icmp_seq=0 ttl=57 time=12.345 ms", [12.345]),
    ("windows-en",
     "Reply from 1.1.1.1: bytes=32 time=20ms TTL=57\n"
     "Reply from 1.1.1.1: bytes=32 time<1ms TTL=57\n\n"
     "Approximate round trip times in milli-seconds:\n"
     "    Minimum = 20ms, Maximum = 20ms, Average = 20ms", [20.0, 1.0]),
    ("windows-de", "Antwort von 1.1.1.1: Bytes=32 Zeit=18ms TTL=57", [18.0]),
    ("windows-fr", "Réponse de 1.1.1.1 : octets=32 temps=18 ms TTL=57", [18.0]),
    ("decimal-comma", "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12,5 ms", [12.5]),
    ("ttl-expired", "Reply from 10.0.0.1: TTL expired in transit.", []),
    ("timeout", "Request timed out.", []),
    ("empty", "", []),
]


@pytest.mark.parametrize("output, expected", [(c[1], c[2]) for c in CASES], ids=[c[0] for c in CASES])
def test_parse(output, expected):
    assert parse(output) == expected
