import json

import pytest

import main


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(main, "CONFIG_FILE", str(path))
    return path


def test_default_settings_cover_every_protocol_and_port():
    s = main.ConfigManager.default_settings()
    assert s["priority_order"] == list(main.DEFAULT_PROTOCOLS)
    for proto, ports in main.DEFAULT_PROTOCOLS.items():
        assert s["protocols"][proto]["enabled"] is True
        assert s["protocols"][proto]["ports"] == {str(p): True for p in ports}


def test_missing_file_gives_defaults(config_file):
    data = main.ConfigManager.load_config()
    assert data["saved_profiles"] == {}
    assert data["cli_path"] == main.DEFAULT_CLI


def test_round_trip_keeps_non_ascii_profile_names(config_file):
    data = main.ConfigManager.load_config()
    data["saved_profiles"]["ایران"] = {"timeout": "30"}
    data["saved_profiles"]["Россия"] = {"timeout": "40"}
    main.ConfigManager.save_config(data)
    loaded = main.ConfigManager.load_config()
    assert loaded["saved_profiles"] == {"ایران": {"timeout": "30"}, "Россия": {"timeout": "40"}}


def test_settings_missing_from_an_older_file_are_filled_in(config_file):
    config_file.write_text(json.dumps({"last_settings": {"timeout": "99"}}), encoding="utf-8")
    data = main.ConfigManager.load_config()
    assert data["last_settings"]["timeout"] == "99"
    assert data["last_settings"]["ping_host"] == "1.1.1.1"
    assert data["language"] == ""
