import sqlite3
import os
import threading
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads.db')

class DownloadLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        # Use check_same_thread=False because we guard with our own lock
        return sqlite3.connect(DB_PATH, check_same_thread=False)

    def _init_db(self):
        with self._lock:
            con = self._connect()
            try:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        url           TEXT NOT NULL,
                        youtube_title TEXT NOT NULL,
                        filename      TEXT NOT NULL,
                        byte_size     INTEGER DEFAULT 0,
                        downloaded_at TEXT NOT NULL,
                        is_removed    INTEGER NOT NULL DEFAULT 0
                    )
                """)
                con.commit()
            finally:
                con.close()

    def add_entry(self, url: str, youtube_title: str, filename: str, byte_size: int = 0):
        """Insert a new completed download. Returns the new row id."""
        now = datetime.now().isoformat(sep=' ', timespec='seconds')
        with self._lock:
            con = self._connect()
            try:
                cur = con.execute(
                    "INSERT INTO downloads (url, youtube_title, filename, byte_size, downloaded_at, is_removed) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (url, youtube_title, filename, byte_size, now)
                )
                con.commit()
                return cur.lastrowid
            finally:
                con.close()

    def get_visible_entries(self):
        """Return all rows where is_removed=0, newest first."""
        with self._lock:
            con = self._connect()
            try:
                cur = con.execute(
                    "SELECT id, url, youtube_title, filename, byte_size, downloaded_at "
                    "FROM downloads WHERE is_removed=0 ORDER BY id DESC"
                )
                rows = cur.fetchall()
                return [
                    {
                        'id': r[0],
                        'url': r[1],
                        'youtube_title': r[2],
                        'filename': r[3],
                        'byte_size': r[4],
                        'downloaded_at': r[5],
                    }
                    for r in rows
                ]
            finally:
                con.close()

    def remove_entry(self, entry_id: int):
        """Soft-delete: set is_removed=1.  Does NOT touch the file."""
        with self._lock:
            con = self._connect()
            try:
                con.execute("UPDATE downloads SET is_removed=1 WHERE id=?", (entry_id,))
                con.commit()
            finally:
                con.close()
