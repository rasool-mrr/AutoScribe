"""Selecting one cartridge must test that cartridge.

`windscribe-cli connect <city>` picks a random datacenter inside the city, so a run on
"Melbourne - Yarra" used to also test "Melbourne - Port Phillip" and record the result under the
wrong name. 57 of 125 cities have more than one datacenter, so this hit constantly.
"""
import main

STATUS_CONNECTED = ("Login:       Logged in\n"
                    "Connection:  Connected to Melbourne - Yarra\n"
                    "Protocol:    IKEv2:500\n"
                    "IP:          103.137.14.41 (VPN)\n"
                    "Firewall:    Off\n")
STATUS_CHECKING = "Login:       Logged in\nConnection:  Connected to Melbourne - Yarra (checking the connection)\n"
STATUS_OTHER = "Login:       Logged in\nConnection:  Connected to Melbourne - Port Phillip\n"
STATUS_CONNECTING = "Login:       Logged in\nConnection:  Connecting to Melbourne - Yarra\n"


def test_connect_uses_the_nickname_not_the_city():
    loc = {"city": "Melbourne", "location": "Yarra", "country": "Australia"}
    assert main.connect_target(loc) == "Yarra"


def test_connect_falls_back_to_city_when_there_is_no_nickname():
    assert main.connect_target({"city": "Nowhere", "location": "", "country": "X"}) == "Nowhere"


def test_status_server_is_parsed_with_ascii_hyphen():
    # The UI uses an en dash in its own labels; the CLI prints a plain hyphen. Mixing them up would
    # make every comparison fail, so this pins the CLI spelling.
    assert main.WindscribeWorker.connected_server(STATUS_CONNECTED) == "Melbourne - Yarra"
    assert main.cli_server_name("Melbourne", "Yarra") == "Melbourne - Yarra"


def test_parsing_survives_the_extra_status_suffixes():
    assert main.WindscribeWorker.connected_server(STATUS_CHECKING) == "Melbourne - Yarra"


def test_parsing_returns_empty_when_not_connected():
    assert main.WindscribeWorker.connected_server(STATUS_CONNECTING) == ""
    assert main.WindscribeWorker.connected_server("Connection:  Disconnected\n") == ""


def test_a_different_server_is_detected():
    assert main.WindscribeWorker.connected_server(STATUS_OTHER) == "Melbourne - Port Phillip"


def test_nicknames_are_unique_in_the_shipped_server_list():
    # connect_target relies on this: if two pops shared a nickname, the nickname would be ambiguous.
    locations = main.LocationManager.load_locations()
    assert locations, "locations.json did not load"
    nicknames = [l["location"] for l in locations if l["location"]]
    assert len(nicknames) == len(set(n.lower() for n in nicknames))
