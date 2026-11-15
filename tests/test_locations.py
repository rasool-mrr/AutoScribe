import json

import pytest

import main

SAMPLE = {"data": {"locations": {
    "1": {"name": "Canada East", "continent": "North America", "pops": [
        {"name": "Montreal - Expo", "status": 1},
        {"name": "Toronto", "status": 1},
        {"name": "Offline - Node", "status": 0},
        {"name": "   ", "status": 1},
    ]},
    "2": {"name": "US East", "continent": "North America", "pops": [
        {"name": "New York - Empire", "status": 1},
    ]},
}}}


@pytest.fixture
def locations_file(tmp_path, monkeypatch):
    path = tmp_path / "locations.json"
    monkeypatch.setattr(main, "LOCATIONS_FILE", str(path))
    return path


def test_missing_file_gives_empty_list(locations_file):
    assert main.LocationManager.load_locations() == []


def test_load_skips_offline_and_nameless_pops(locations_file):
    locations_file.write_text(json.dumps(SAMPLE), encoding="utf-8")
    locs = main.LocationManager.load_locations()
    assert [(loc["city"], loc["location"]) for loc in locs] == [("Montreal", "Expo"), ("Toronto", ""),
                                                                ("New York", "Empire")]


def test_corrupt_file_gives_empty_list(locations_file):
    locations_file.write_text("{not json", encoding="utf-8")
    assert main.LocationManager.load_locations() == []


def test_loc_helpers():
    loc = {"country": "Canada East", "city": "Montreal", "location": "Expo", "continent": "North America"}
    assert main.loc_key(loc) == "Canada East|Montreal|Expo"
    assert main.loc_name("Montreal", "Expo") == "Montreal – Expo"
    assert main.loc_name("Toronto", "") == "Toronto"


def test_matches_region():
    us = {"country": "US East", "continent": "North America"}
    ca = {"country": "Canada East", "continent": "North America"}
    assert main.matches_region(us, "All") and main.matches_region(ca, "All")
    assert main.matches_region(us, "USA") and not main.matches_region(ca, "USA")
    assert main.matches_region(ca, "North America")
    assert not main.matches_region(ca, "Europe")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("payload", [b'{"data": {"locations": {}}}', b'{"data": {}}',
                                     b'{"data": {"locations": {"1": {"name": "X", "pops": []}}}}'])
def test_download_rejects_empty_lists_and_keeps_old_file(locations_file, monkeypatch, payload):
    locations_file.write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setattr(main.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(payload))
    with pytest.raises(ValueError):
        main.LocationManager.download()
    assert json.loads(locations_file.read_text(encoding="utf-8")) == SAMPLE


def test_download_replaces_file_with_valid_list(locations_file, monkeypatch):
    locations_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResponse(json.dumps(SAMPLE).encode("utf-8")))
    main.LocationManager.download()
    assert json.loads(locations_file.read_text(encoding="utf-8")) == SAMPLE
