import types

import pytest

import main


def test_windows_command_uses_milliseconds():
    assert main.ping_command("1.1.1.1", 5, 2000, "Windows") == ["ping", "-n", "5", "-w", "2000", "1.1.1.1"]


def test_linux_wait_flag_is_whole_seconds():
    assert main.ping_command("1.1.1.1", 5, 2000, "Linux") == ["ping", "-c", "5", "-W", "2", "1.1.1.1"]


def test_linux_wait_flag_is_at_least_one_second():
    assert main.ping_command("1.1.1.1", 3, 500, "Linux")[-2] == "1"


def test_macos_wait_flag_is_milliseconds():
    """BSD/macOS ping takes -W in milliseconds; passing "2" would give every reply a 2 ms deadline."""
    assert main.ping_command("1.1.1.1", 5, 2000, "Darwin") == ["ping", "-c", "5", "-W", "2000", "1.1.1.1"]


@pytest.mark.parametrize("host", ["1.1.1.1", "example.com", "cloudflare-dns.com", "2606:4700:4700::1111",
                                  "fe80::1%eth0", "пример.рф"])
def test_valid_hosts(host):
    assert main.valid_ping_host(host)


@pytest.mark.parametrize("host", ["", "   ", "-f", "--help", "-c1000", "two words", "tab\there"])
def test_invalid_hosts(host):
    """A host starting with "-" would be read by ping as an option."""
    assert not main.valid_ping_host(host)


def fake_ping(monkeypatch, stdout):
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **kw: types.SimpleNamespace(stdout=stdout, returncode=0))


def test_runner_statistics(monkeypatch):
    fake_ping(monkeypatch, "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=10 ms\n"
                           "64 bytes from 1.1.1.1: icmp_seq=2 ttl=57 time=20 ms\n"
                           "64 bytes from 1.1.1.1: icmp_seq=3 ttl=57 time=30 ms")
    result, error = main.PingRunner().run("1.1.1.1", count=5)
    assert error is None
    assert (result["min"], result["avg"], result["max"]) == (10.0, 20.0, 30.0)
    assert result["loss"] == pytest.approx(40.0)


def test_runner_loss_is_never_negative_with_duplicate_replies(monkeypatch):
    fake_ping(monkeypatch, "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=10 ms\n"
                           "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=11 ms (DUP!)")
    result, _ = main.PingRunner().run("1.1.1.1", count=1)
    assert result["loss"] == 0.0


def test_runner_without_replies(monkeypatch):
    fake_ping(monkeypatch, "Request timed out.")
    assert main.PingRunner().run("1.1.1.1") == (None, "no replies")


def test_runner_refuses_an_option_like_host_without_running_ping(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("ping must not be started")

    monkeypatch.setattr(main.subprocess, "run", boom)
    assert main.PingRunner().run("-f") == (None, "invalid ping host")
