"""Persistent tag catalog. It is intentionally never used by the polling path."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .tags import TagDefinition, create_tag, load_tags


class TagStore:
    def __init__(self, database: Path) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self.connection = sqlite3.connect(database)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                name TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                data_type TEXT NOT NULL,
                client_access TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def load_all(self) -> list[TagDefinition]:
        rows = self.connection.execute(
            "SELECT name, address, data_type, client_access FROM tags ORDER BY name"
        ).fetchall()
        return [create_tag(*row) for row in rows]

    def upsert(self, tag: TagDefinition, source: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT INTO tags(name, address, data_type, client_access, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                address=excluded.address, data_type=excluded.data_type,
                client_access=excluded.client_access, source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (tag.name, tag.address, tag.data_type, tag.client_access, source, now, now),
        )
        self.connection.commit()

    def remove(self, name: str) -> bool:
        cursor = self.connection.execute("DELETE FROM tags WHERE name = ?", (name,))
        self.connection.commit()
        return cursor.rowcount == 1

    def import_csv(self, path: Path) -> int:
        tags = load_tags(path)
        now = datetime.now(timezone.utc).isoformat()
        self.connection.executemany(
            """
            INSERT INTO tags(name, address, data_type, client_access, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'csv', ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                address=excluded.address, data_type=excluded.data_type,
                client_access=excluded.client_access, source=excluded.source,
                updated_at=excluded.updated_at
            """,
            [(tag.name, tag.address, tag.data_type, tag.client_access, now, now) for tag in tags],
        )
        self.connection.commit()
        return len(tags)

    def backup(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = directory / f"tags-{stamp}.db"
        # Open fresh connections here: this method is called through
        # asyncio.to_thread, so it must not reuse the event-loop connection.
        source = sqlite3.connect(self.database)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return destination
