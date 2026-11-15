import csv
import os

import pytest

import main


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_FILE", str(tmp_path / "results.db"))
    monkeypatch.setattr(main, "REPORTS_DIR", str(tmp_path / "reports"))
    database = main.DatabaseManager()
    yield database
    database.conn.close()


def add(db, node="Expo", city="Montreal", country="Canada East", proto="udp", port=443, status="SUCCESS",
        ping=20.0, loss=0.0, profile="Manual"):
    return db.record_result(node, city, country, proto, port, status, 1.234, ping, loss, profile)


def test_empty_database(db):
    assert db.get_row_count() == 0
    assert db.fetch_results() == []


def test_record_and_is_tested(db):
    assert add(db)
    assert db.is_tested("Expo", "Montreal", "Canada East", "udp", 443)
    assert not db.is_tested("Expo", "Montreal", "Canada East", "udp", 80)
    assert not db.is_tested("Expo", "Montreal", "Canada East", "tcp", 443)


def test_same_route_is_replaced_not_duplicated(db):
    add(db, status="FAILURE", ping=None, loss=None)
    add(db, status="SUCCESS", ping=15.0, loss=0.0)
    rows = db.fetch_results()
    assert len(rows) == 1
    assert rows[0][5] == "SUCCESS"


def test_fetch_results_keeps_insertion_order(db):
    add(db, port=443)
    add(db, port=80)
    add(db, port=53)
    assert [r[4] for r in db.fetch_results()] == [443, 80, 53]


def test_clear_db(db):
    add(db)
    db.clear_db()
    assert db.get_row_count() == 0


def test_export_to_csv(db):
    add(db, port=443)
    add(db, port=80, status="FAILURE", ping=None, loss=None)
    count, path = db.export_to_csv("My Profile!")
    assert count == 2
    assert os.path.basename(path).startswith("1_My_Profile_")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == main.DatabaseManager.EXPORT_COLUMNS
    assert len(rows) == 3


def test_export_reports_any_write_error_instead_of_raising(db, monkeypatch):
    add(db)

    def disk_full(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(main.csv, "writer", disk_full)
    count, message = db.export_to_csv()
    assert count == -1
    assert "No space left on device" in message


def test_export_numbers_increase(db):
    add(db)
    _, first = db.export_to_csv()
    _, second = db.export_to_csv()
    assert os.path.basename(first).startswith("1_")
    assert os.path.basename(second).startswith("2_")
