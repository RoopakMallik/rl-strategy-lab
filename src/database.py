"""Database connections. Writer role for ingest, training and logging; read-only role for queries.

Both connections autocommit: a single statement commits on its own, and anything that must be
saved together goes in `with conn.transaction():`, which commits when the block ends. No
transaction is left open while slow work (such as training) runs.

Rows come back as dicts, so callers use column names, never column positions.
"""
from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from .settings import load_settings


def connect_as_writer() -> psycopg.Connection:
    return psycopg.connect(load_settings().database.writer_conninfo, row_factory=dict_row, autocommit=True)


def connect_as_reader() -> psycopg.Connection:
    """Read-only role: SELECT only, so a bug or a bad prompt cannot change data."""
    return psycopg.connect(load_settings().database.reader_conninfo, row_factory=dict_row, autocommit=True)
