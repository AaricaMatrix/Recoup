"""
db/connection.py

One place that knows the database file path and connection settings, so
every other module (repository.py, migrate.py, seed.py, api_server.py)
gets identical, correctly-configured connections instead of each rolling
its own sqlite3.connect() call slightly differently.
"""

import os
import sqlite3

# Overridable via env var so tests (or a CI run) can point at a throwaway
# database file instead of the real one — same reasoning as every other
# config value in this project living in .env rather than being hardcoded.
DB_PATH = os.getenv("RECOUP_DB_PATH", os.path.join("data", "recoup.db"))


def get_connection():
    """Returns a new sqlite3 connection with the settings this project
    actually needs turned on. Call this per-request/per-script-run rather
    than sharing one long-lived connection across threads — sqlite3
    connections aren't safe to share across threads by default, and Flask's
    dev server can handle requests on more than one.
    """
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Rows behave like dicts (row["amount"] instead of row[4]) — makes
    # every function in repository.py far more readable, and means adding
    # a column later doesn't silently shift every positional index.
    conn.row_factory = sqlite3.Row
    # SQLite has foreign keys OFF by default for backward-compatibility
    # reasons dating back decades — without this pragma, the REFERENCES
    # clauses in the schema are decorative only and never actually enforced.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
