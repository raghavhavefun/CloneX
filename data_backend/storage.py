import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class MetadataStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    owner_email TEXT NOT NULL DEFAULT 'global',
                    source_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    path_or_url TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    text_length INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )
            # Backward-compatible migrations for existing DBs.
            for stmt in [
                "ALTER TABLE assets ADD COLUMN text_length INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE assets ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE assets ADD COLUMN owner_email TEXT NOT NULL DEFAULT 'global'",
            ]:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    # Column already exists.
                    pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history_events (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS los_items (
                    id TEXT PRIMARY KEY,
                    owner_email TEXT NOT NULL DEFAULT 'global',
                    item_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    source_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS los_agent_messages (
                    id TEXT PRIMARY KEY,
                    owner_email TEXT NOT NULL DEFAULT 'global',
                    agent_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_jobs (
                    id TEXT PRIMARY KEY,
                    created_by_email TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    schedule_at TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_prompt TEXT NOT NULL,
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    error_text TEXT
                )
                """
            )
            for stmt in [
                "ALTER TABLE los_items ADD COLUMN owner_email TEXT NOT NULL DEFAULT 'global'",
                "ALTER TABLE los_agent_messages ADD COLUMN owner_email TEXT NOT NULL DEFAULT 'global'",
            ]:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass
            for stmt in [
                "ALTER TABLE automation_jobs ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'",
            ]:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_events (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_senders (
                    email TEXT PRIMARY KEY,
                    smtp_host TEXT NOT NULL,
                    smtp_port INTEGER NOT NULL,
                    smtp_username TEXT NOT NULL,
                    smtp_from_email TEXT NOT NULL,
                    use_tls INTEGER NOT NULL,
                    password_ciphertext TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    owner_email TEXT NOT NULL DEFAULT 'global',
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def upsert_asset(self, asset: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assets
                (id, owner_email, source_type, name, mime, path_or_url, size_bytes, text_length, chunk_count, status, created_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["id"],
                    asset.get("owner_email", "global"),
                    asset["source_type"],
                    asset["name"],
                    asset["mime"],
                    asset["path_or_url"],
                    int(asset.get("size_bytes", 0)),
                    int(asset.get("text_length", 0)),
                    int(asset.get("chunk_count", 0)),
                    asset["status"],
                    asset["created_at"],
                    asset.get("deleted_at"),
                ),
            )

    def add_event(self, event_id: str, asset_id: str | None, event_type: str, details_json: str):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO history_events (id, asset_id, event_type, details_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, asset_id, event_type, details_json, datetime.utcnow().isoformat()),
            )

    def list_assets(self, owner_email: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if owner_email:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, source_type, name, mime, path_or_url, size_bytes, text_length, chunk_count, status, created_at, deleted_at
                    FROM assets
                    WHERE lower(owner_email) = lower(?)
                    ORDER BY created_at DESC
                    """,
                    (owner_email,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, source_type, name, mime, path_or_url, size_bytes, text_length, chunk_count, status, created_at, deleted_at
                    FROM assets
                    ORDER BY created_at DESC
                    """
                )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "owner_email": r[1],
                "source_type": r[2],
                "name": r[3],
                "mime": r[4],
                "path_or_url": r[5],
                "size_bytes": r[6],
                "text_length": r[7],
                "chunk_count": r[8],
                "status": r[9],
                "created_at": r[10],
                "deleted_at": r[11],
            }
            for r in rows
        ]

    def mark_deleted(self, asset_id: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE assets SET deleted_at = ?, status = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), "deleted", asset_id),
            )

    def get_asset(self, asset_id: str, owner_email: str | None = None) -> dict[str, Any] | None:
        with self._conn() as conn:
            if owner_email:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, source_type, name, mime, path_or_url, size_bytes, text_length, chunk_count, status, created_at, deleted_at
                    FROM assets
                    WHERE id = ? AND lower(owner_email) = lower(?)
                    """,
                    (asset_id, owner_email),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, source_type, name, mime, path_or_url, size_bytes, text_length, chunk_count, status, created_at, deleted_at
                    FROM assets
                    WHERE id = ?
                    """,
                    (asset_id,),
                )
            r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0],
            "owner_email": r[1],
            "source_type": r[2],
            "name": r[3],
            "mime": r[4],
            "path_or_url": r[5],
            "size_bytes": r[6],
            "text_length": r[7],
            "chunk_count": r[8],
            "status": r[9],
            "created_at": r[10],
            "deleted_at": r[11],
        }

    def add_los_item(self, item: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO los_items (id, owner_email, item_type, title, content, group_name, source_mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item.get("owner_email", "global"),
                    item["item_type"],
                    item["title"],
                    item["content"],
                    item["group_name"],
                    item["source_mode"],
                    item["created_at"],
                ),
            )

    def list_los_items(self, owner_email: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if owner_email:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, item_type, title, content, group_name, source_mode, created_at
                    FROM los_items
                    WHERE lower(owner_email) = lower(?)
                    ORDER BY created_at DESC
                    """,
                    (owner_email,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, item_type, title, content, group_name, source_mode, created_at
                    FROM los_items
                    ORDER BY created_at DESC
                    """
                )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "owner_email": r[1],
                "item_type": r[2],
                "title": r[3],
                "content": r[4],
                "group_name": r[5],
                "source_mode": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def add_los_agent_message(self, message: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO los_agent_messages (id, owner_email, agent_name, role, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message["id"],
                    message.get("owner_email", "global"),
                    message["agent_name"],
                    message["role"],
                    message["message"],
                    message["created_at"],
                ),
            )

    def list_los_agent_messages(self, agent_name: str, limit: int = 30, owner_email: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if owner_email:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, agent_name, role, message, created_at
                    FROM los_agent_messages
                    WHERE agent_name = ? AND lower(owner_email) = lower(?)
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (agent_name, owner_email, int(limit)),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT id, owner_email, agent_name, role, message, created_at
                    FROM los_agent_messages
                    WHERE agent_name = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (agent_name, int(limit)),
                )
            rows = cur.fetchall()
        rows = list(reversed(rows))
        return [
            {
                "id": r[0],
                "owner_email": r[1],
                "agent_name": r[2],
                "role": r[3],
                "message": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

    def add_automation_job(self, job: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO automation_jobs
                (id, created_by_email, channel, recipients_json, subject, message, schedule_at, timezone, status, source_prompt, attachments_json, created_at, sent_at, error_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["id"],
                    job["created_by_email"],
                    job["channel"],
                    job["recipients_json"],
                    job["subject"],
                    job["message"],
                    job["schedule_at"],
                    job["timezone"],
                    job["status"],
                    job["source_prompt"],
                    job.get("attachments_json", "[]"),
                    job["created_at"],
                    job.get("sent_at"),
                    job.get("error_text"),
                ),
            )

    def list_automation_jobs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT id, created_by_email, channel, recipients_json, subject, message, schedule_at, timezone, status, source_prompt, attachments_json, created_at, sent_at, error_text
                FROM automation_jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "created_by_email": r[1],
                "channel": r[2],
                "recipients_json": r[3],
                "subject": r[4],
                "message": r[5],
                "schedule_at": r[6],
                "timezone": r[7],
                "status": r[8],
                "source_prompt": r[9],
                "attachments_json": r[10],
                "created_at": r[11],
                "sent_at": r[12],
                "error_text": r[13],
            }
            for r in rows
        ]

    def list_due_automation_jobs(self, now_iso: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT id, created_by_email, channel, recipients_json, subject, message, schedule_at, timezone, status, source_prompt, attachments_json, created_at, sent_at, error_text
                FROM automation_jobs
                WHERE status = 'scheduled' AND schedule_at <= ?
                ORDER BY schedule_at ASC
                LIMIT ?
                """,
                (now_iso, int(limit)),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "created_by_email": r[1],
                "channel": r[2],
                "recipients_json": r[3],
                "subject": r[4],
                "message": r[5],
                "schedule_at": r[6],
                "timezone": r[7],
                "status": r[8],
                "source_prompt": r[9],
                "attachments_json": r[10],
                "created_at": r[11],
                "sent_at": r[12],
                "error_text": r[13],
            }
            for r in rows
        ]

    def update_automation_job_status(self, job_id: str, status: str, sent_at: str | None = None, error_text: str | None = None):
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE automation_jobs
                SET status = ?, sent_at = ?, error_text = ?
                WHERE id = ?
                """,
                (status, sent_at, error_text, job_id),
            )

    def add_automation_event(self, event: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO automation_events (id, job_id, event_type, details_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event["id"],
                    event["job_id"],
                    event["event_type"],
                    event["details_json"],
                    event["created_at"],
                ),
            )

    def upsert_automation_sender(self, sender: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO automation_senders
                (email, smtp_host, smtp_port, smtp_username, smtp_from_email, use_tls, password_ciphertext, password_salt, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM automation_senders WHERE email = ?), ?), ?)
                """,
                (
                    sender["email"],
                    sender["smtp_host"],
                    int(sender["smtp_port"]),
                    sender["smtp_username"],
                    sender["smtp_from_email"],
                    1 if sender["use_tls"] else 0,
                    sender["password_ciphertext"],
                    sender["password_salt"],
                    sender["email"],
                    sender["updated_at"],
                    sender["updated_at"],
                ),
            )

    def get_automation_sender(self, email: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT email, smtp_host, smtp_port, smtp_username, smtp_from_email, use_tls, password_ciphertext, password_salt, created_at, updated_at
                FROM automation_senders
                WHERE lower(email) = lower(?)
                """,
                (email,),
            )
            r = cur.fetchone()
        if not r:
            return None
        return {
            "email": r[0],
            "smtp_host": r[1],
            "smtp_port": int(r[2]),
            "smtp_username": r[3],
            "smtp_from_email": r[4],
            "use_tls": bool(r[5]),
            "password_ciphertext": r[6],
            "password_salt": r[7],
            "created_at": r[8],
            "updated_at": r[9],
        }

    def list_automation_senders(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT email, smtp_host, smtp_port, smtp_username, smtp_from_email, use_tls, created_at, updated_at
                FROM automation_senders
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = cur.fetchall()
        return [
            {
                "email": r[0],
                "smtp_host": r[1],
                "smtp_port": int(r[2]),
                "smtp_username": r[3],
                "smtp_from_email": r[4],
                "use_tls": bool(r[5]),
                "created_at": r[6],
                "updated_at": r[7],
            }
            for r in rows
        ]

    def upsert_contact(self, contact: dict[str, Any]):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO contacts
                (id, owner_email, name, email, created_at, updated_at)
                VALUES (
                    COALESCE((SELECT id FROM contacts WHERE lower(owner_email)=lower(?) AND lower(email)=lower(?)), ?, ?, ?, ?),
                    ?, ?, ?,
                    COALESCE((SELECT created_at FROM contacts WHERE lower(owner_email)=lower(?) AND lower(email)=lower(?)), ?),
                    ?
                )
                """,
                (
                    contact["owner_email"],
                    contact["email"],
                    contact["id"],
                    contact["id"],
                    contact["owner_email"],
                    contact["email"],
                    contact["owner_email"],
                    contact["name"],
                    contact["email"],
                    contact["owner_email"],
                    contact["email"],
                    contact["updated_at"],
                    contact["updated_at"],
                ),
            )

    def list_contacts(self, owner_email: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT id, owner_email, name, email, created_at, updated_at
                FROM contacts
                WHERE lower(owner_email) = lower(?)
                ORDER BY lower(name) ASC, updated_at DESC
                """,
                (owner_email,),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "owner_email": r[1],
                "name": r[2],
                "email": r[3],
                "created_at": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]

    def delete_contact(self, owner_email: str, contact_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM contacts WHERE id = ? AND lower(owner_email) = lower(?)",
                (contact_id, owner_email),
            )
            return int(cur.rowcount or 0) > 0
