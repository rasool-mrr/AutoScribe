"""The probe's ordering must be a hint, not a hardcoded truth.

A probe that invents a protocol:port the client does not support reports "no connection", which is
indistinguishable from a filtered port - the exact false negative that makes this tool useless. So
the list is built from `windscribe-cli ports` and ORDER only reorders it.
"""
import probe_protocols as probe


class FakeRun:
    """Stands in for subprocess.run inside combinations()."""

    def __init__(self, table):
        self.table = table

    def __call__(self, cmd, **kwargs):
        proto = cmd[2]
        return type("R", (), {"stdout": self.table.get(proto, "")})()


def test_every_supported_port_is_probed_once(monkeypatch):
    table = {"wireguard": "443, 80, 53\n", "ikev2": "500\n", "wstunnel": "443\n"}
    monkeypatch.setattr(probe.subprocess, "run", FakeRun(table))
    monkeypatch.setattr(probe.main, "PROTO_NAMES", {"wireguard": "", "ikev2": "", "wstunnel": ""})
    combos = probe.combinations("cli")
    assert sorted(combos) == [("ikev2", 500), ("wireguard", 53), ("wireguard", 80),
                              ("wireguard", 443), ("wstunnel", 443)]


def test_order_only_decides_what_comes_first(monkeypatch):
    table = {"stealth": "443, 3306\n", "tcp": "443\n"}
    monkeypatch.setattr(probe.subprocess, "run", FakeRun(table))
    monkeypatch.setattr(probe.main, "PROTO_NAMES", {"stealth": "", "tcp": ""})
    combos = probe.combinations("cli")
    # stealth:443 is high in ORDER, tcp:443 next, stealth:3306 last.
    assert combos[0] == ("stealth", 443)
    assert combos[-1] == ("stealth", 3306)


def test_an_unknown_combination_is_not_dropped(monkeypatch):
    # A port the client adds later is kept and probed last, not silently ignored.
    table = {"wstunnel": "443\n", "udp": "9999\n"}
    monkeypatch.setattr(probe.subprocess, "run", FakeRun(table))
    monkeypatch.setattr(probe.main, "PROTO_NAMES", {"wstunnel": "", "udp": ""})
    combos = probe.combinations("cli")
    assert ("udp", 9999) in combos
    assert combos[-1] == ("udp", 9999)
