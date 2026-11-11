from database.connection import Database


def test_schema_initialises(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    assert db.schema_version() == 1


def test_idempotent_init(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.initialize()
    assert db.schema_version() == 1


def test_tables_exist(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    with db.connection() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    for required in ("candles", "signals", "trades", "experiments", "audit_log"):
        assert required in names