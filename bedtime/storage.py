"""SQLite connection helper.

Tries WAL, falls back to a rollback journal. WAL fails on NFS/SMB and some
container volumes, which is how the test suite found this.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from .observability.tracing import LOG

_WARNED: set = set()
_WARN_LOCK = threading.Lock()


class StorageUnavailable(RuntimeError):
    """The database cannot be opened. Caller should degrade, not crash."""

def _warn_once(key: str, message: str, *args):
    with _WARN_LOCK:
        if key in _WARNED:
            return
        _WARNED.add(key)
    LOG.warning(message, *args)


def connect(db_path: Path, timeout: float = 10.0,
            foreign_keys: bool = False):
    """Open SQLite, preferring WAL, falling back to a rollback journal."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        _warn_once(f"wal:{db_path}",
                   "WAL unsupported on this filesystem for %s; using rollback journal", db_path)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.Error:
            pass
    if foreign_keys:
        try:
            conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error:
            pass
    return conn


# NOTE: probe() creates and drops a table every time. Slightly wasteful but it
# is the only way to be sure the volume is actually writable, not just present.
def probe(db_path: Path, foreign_keys: bool = False):
    db_path = Path(db_path)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with connect(db_path, foreign_keys=foreign_keys) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _probe (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT OR REPLACE INTO _probe (id) VALUES (1)")
            conn.execute("DROP TABLE _probe")
        return db_path
    except (sqlite3.Error, OSError) as exc:
        raise StorageUnavailable(f"{db_path}: {exc}") from exc
