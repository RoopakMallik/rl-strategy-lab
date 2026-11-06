"""The read-only role can read but cannot change anything."""
import psycopg
import pytest

try:
    from src.database import connect_as_reader
    connect_as_reader().close()
except Exception:  # no .env or Postgres not running
    pytest.skip("database not set up", allow_module_level=True)


def test_reader_can_select():
    with connect_as_reader() as conn:
        conn.execute("SELECT count(*) FROM daily_prices").fetchone()


@pytest.mark.parametrize("sql", [
    "INSERT INTO daily_prices VALUES ('X', '2000-01-01', 1, 1, 1, 1, 1)",
    "UPDATE daily_prices SET close = 0",
    "DELETE FROM daily_prices",
    "DROP TABLE daily_prices",
    "CREATE TABLE hack (x int)",
])
def test_reader_cannot_write(sql):
    with connect_as_reader() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(sql)
