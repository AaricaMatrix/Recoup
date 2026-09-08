"""
db/migrate.py

Applies every .sql file in db/migrations/, in filename order, that hasn't
already been applied — tracked in the _migrations table (created by
0001_init.sql itself, on a fresh database, via the bootstrap check below).
This is the SQL-file equivalent of `prisma migrate deploy`: a new
teammate (or a fresh Vercel/CI environment) runs one command and ends up
with an up-to-date schema, without ever hand-running SQL.

Usage:
    python -m db.migrate
"""

import os

from db.connection import DB_PATH, get_connection

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def _migrations_table_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'"
    ).fetchone()
    return row is not None


def applied_migrations(conn):
    if not _migrations_table_exists(conn):
        # Fresh database — 0001_init.sql (which creates _migrations itself)
        # hasn't run yet, so nothing counts as applied.
        return set()
    rows = conn.execute("SELECT filename FROM _migrations").fetchall()
    return {row["filename"] for row in rows}


def run():
    conn = get_connection()
    already_applied = applied_migrations(conn)

    pending = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".sql") and f not in already_applied
    )

    if not pending:
        print(f"Database is up to date ({DB_PATH}) — no pending migrations.")
        conn.close()
        return

    for filename in pending:
        path = os.path.join(MIGRATIONS_DIR, filename)
        with open(path) as f:
            sql = f.read()
        print(f"Applying {filename}...")
        # executescript runs the whole file as one batch (needed since a
        # migration file has multiple CREATE TABLE/INDEX statements) and
        # implicitly commits any open transaction first — that's fine here
        # since each migration file is applied as its own unit of work.
        conn.executescript(sql)
        # 0001_init.sql creates _migrations itself, so by the time we reach
        # this INSERT the table is guaranteed to exist, including on a
        # completely fresh database on the very first migration.
        conn.execute(
            "INSERT INTO _migrations (filename, applied_at) VALUES (?, datetime('now'))",
            (filename,),
        )
        conn.commit()

    print(f"Applied {len(pending)} migration(s) -> {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    run()
