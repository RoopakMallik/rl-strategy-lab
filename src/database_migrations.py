"""Apply the numbered SQL files in sql/migrations/ that have not run yet, in order.

    python -m src.database_migrations

Each file runs in its own transaction (the writer connection autocommits, so each
`conn.transaction()` is a real BEGIN/COMMIT) and is recorded in `schema_migrations`, so a failing
file rolls back alone and this is safe to re-run. To change the schema, add a new file
(e.g. 0004_add_x.sql); never edit an applied one.
"""
from __future__ import annotations

from .database import connect_as_writer
from .settings import PROJECT_ROOT

MIGRATIONS_DIR = PROJECT_ROOT / "sql" / "migrations"


def apply_pending_migrations() -> list[str]:
    applied_now = []
    with connect_as_writer() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    text        PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )""")
        already_applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in already_applied:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    return applied_now


def main() -> None:
    applied = apply_pending_migrations()
    print("Applied: " + ", ".join(applied) if applied else "Database schema is up to date.")


if __name__ == "__main__":
    main()
