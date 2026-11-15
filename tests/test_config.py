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


def test_failed_save_leaves_the_existing_file_untouched(config_file, monkeypatch):
    """The file holds the user's profiles. A crash halfway through writing must not destroy them."""
    config_file.write_text(json.dumps({"saved_profiles": {"keep": {}}}), encoding="utf-8")

    def broken_dump(data, fp, **kwargs):
        fp.write('{"saved_profiles": {"ha')  # a partial write, then the failure
        raise OSError("disk full")

    monkeypatch.setattr(main.json, "dump", broken_dump)
    main.ConfigManager.save_config({"saved_profiles": {}})
    assert json.loads(config_file.read_text(encoding="utf-8")) == {"saved_profiles": {"keep": {}}}
    assert not (config_file.parent / "config.json.tmp").exists()


def test_save_leaves_no_temporary_file(config_file):
    main.ConfigManager.save_config(main.ConfigManager.load_config())
    assert sorted(p.name for p in config_file.parent.iterdir()) == ["config.json"]


def test_corrupt_file_is_kept_as_a_backup(config_file):
    config_file.write_text('{"saved_profiles": {"precious": ', encoding="utf-8")  # truncated JSON
    data = main.ConfigManager.load_config()
    assert data["saved_profiles"] == {}
    backup = config_file.parent / "config.json.bak"
    assert backup.read_text(encoding="utf-8") == '{"saved_profiles": {"precious": '
    assert not config_file.exists()


def test_settings_missing_from_an_older_file_are_filled_in(config_file):
    config_file.write_text(json.dumps({"last_settings": {"timeout": "99"}}), encoding="utf-8")
    data = main.ConfigManager.load_config()
    assert data["last_settings"]["timeout"] == "99"
    assert data["last_settings"]["ping_host"] == "1.1.1.1"
    assert data["language"] == ""
