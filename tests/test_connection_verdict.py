"""Regression guards for the connection verdict, second pass.

Each case here is a false positive that reached the results table in a real run.
"""
import main

OK = ("Login:       Logged in\n"
      "Connection:  Connected to Melbourne - Yarra\n"
      "Protocol:    IKEv2:500\n"
      "Firewall:    Off\n")


def test_network_interference_is_not_a_connection():
    # The CLI prints this ON the "Connected to ..." line when its own connection check failed.
    text = "Login:       Logged in\nConnection:  Connected to Melbourne - Yarra (network interference detected)\n"
    assert main.WindscribeWorker.is_connected_output(text) is False


def test_checking_the_connection_is_not_a_connection():
    text = "Login:       Logged in\nConnection:  Connected to Tirana - Besa (checking the connection)\n"
    assert main.WindscribeWorker.is_connected_output(text) is False


def test_a_plain_connection_still_passes():
    assert main.WindscribeWorker.is_connected_output(OK) is True


def test_city_only_status_is_not_a_mismatch():
    # Some entries answer with just the city; that proves nothing either way.
    assert main.is_different_server("Melbourne", "Melbourne - Yarra") is False


def test_a_city_only_target_must_still_be_measured_against_the_right_city():
    # connect_target() returns the city when an entry has no nickname, so `expected` can be a bare
    # city. The old rule ("a city-only actual name proves nothing") also accepted a DIFFERENT city,
    # which recorded one city's route as a success for another.
    assert main.is_different_server("Sydney", "Melbourne - Yarra") is True
    assert main.is_different_server("Melbourne", "Melbourne - Yarra") is False
    assert main.is_different_server("Melbourne - Yarra", "Melbourne - Yarra") is False


def test_unknown_status_is_not_a_mismatch():
    assert main.is_different_server("", "Melbourne - Yarra") is False


def test_a_qualified_different_server_is_a_mismatch():
    assert main.is_different_server("Melbourne - Port Phillip", "Melbourne - Yarra") is True


def test_same_server_is_not_a_mismatch():
    assert main.is_different_server("melbourne - yarra", "Melbourne - Yarra") is False
