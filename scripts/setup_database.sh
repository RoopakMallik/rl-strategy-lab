#!/usr/bin/env bash
# Creates the database and both roles from .env, applies pending migrations as the writer role,
# and gives the read-only role SELECT on every table and view (including future ones).
# Run as your normal macOS user (the Homebrew Postgres superuser). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export PGHOST="$DATABASE_HOST" PGPORT="$DATABASE_PORT"

psql -v ON_ERROR_STOP=1 -d postgres -q \
  -v writer="$DATABASE_WRITER_USER" -v writer_pw="$DATABASE_WRITER_PASSWORD" \
  -v reader="$DATABASE_READER_USER" -v reader_pw="$DATABASE_READER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'writer', :'writer_pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'writer') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'reader', :'reader_pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'reader') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'writer', :'writer_pw') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'reader', :'reader_pw') \gexec
SQL

database_exists=$(psql -d postgres -tA -v db="$DATABASE_NAME" <<'SQL'
SELECT 1 FROM pg_database WHERE datname = :'db';
SQL
)
if [ "$database_exists" != "1" ]; then
  createdb -O "$DATABASE_WRITER_USER" "$DATABASE_NAME"
fi

# Read-only role: connect, and SELECT on whatever the writer creates from now on.
psql -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" -q \
  -v db="$DATABASE_NAME" -v writer="$DATABASE_WRITER_USER" -v reader="$DATABASE_READER_USER" <<'SQL'
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"writer", :"reader";
-- Only the owner (the writer) may create objects; PostgreSQL 14 and older let everyone.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"reader";
ALTER DEFAULT PRIVILEGES FOR ROLE :"writer" IN SCHEMA public GRANT SELECT ON TABLES TO :"reader";
SQL

.venv/bin/python -m src.database_migrations

# Tables that existed before the default privileges above were set.
psql -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" -q -v reader="$DATABASE_READER_USER" <<'SQL'
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"reader";
SQL
echo "Database $DATABASE_NAME ready (writer: $DATABASE_WRITER_USER, read-only: $DATABASE_READER_USER)."
