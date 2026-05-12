import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "telegram_agent.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_accounts (
                account_email TEXT PRIMARY KEY,
                bot_token TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_sessions (
                telegram_user_id TEXT PRIMARY KEY,
                account_email TEXT NOT NULL,
                supabase_access_token TEXT,
                supabase_refresh_token TEXT,
                auth_state TEXT DEFAULT 'unauthenticated',
                pending_email TEXT,
                los_agent TEXT DEFAULT '',
                los_mode TEXT DEFAULT 'suggest_actions',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Backward-compatible migration for existing DBs.
        try:
            c.execute("ALTER TABLE telegram_sessions ADD COLUMN los_mode TEXT DEFAULT 'suggest_actions'")
        except sqlite3.OperationalError:
            pass
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS notified_jobs (
                job_id TEXT PRIMARY KEY,
                notified_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def set_bot_token(account_email: str, bot_token: str) -> None:
    email = account_email.strip().lower()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO bot_accounts(account_email, bot_token, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(account_email)
            DO UPDATE SET bot_token=excluded.bot_token, updated_at=CURRENT_TIMESTAMP
            """,
            (email, bot_token.strip()),
        )


def delete_bot_token(account_email: str) -> int:
    email = account_email.strip().lower()
    with _conn() as c:
        cur = c.execute("DELETE FROM bot_accounts WHERE account_email=?", (email,))
        return cur.rowcount


def get_bot_token(account_email: str) -> str | None:
    email = account_email.strip().lower()
    with _conn() as c:
        row = c.execute("SELECT bot_token FROM bot_accounts WHERE account_email=?", (email,)).fetchone()
        return None if not row else str(row["bot_token"])


def list_bot_accounts() -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT account_email FROM bot_accounts ORDER BY account_email ASC").fetchall()
        return [str(r["account_email"]) for r in rows]


def get_session(telegram_user_id: str) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM telegram_sessions WHERE telegram_user_id=?",
            (str(telegram_user_id),),
        ).fetchone()
    if not row:
        return {
            "telegram_user_id": str(telegram_user_id),
            "account_email": "",
            "supabase_access_token": "",
            "supabase_refresh_token": "",
            "auth_state": "unauthenticated",
            "pending_email": "",
            "los_agent": "",
            "los_mode": "suggest_actions",
        }
    out = dict(row)
    # Ensure backwards compatibility if old rows exist before migration
    if "los_agent" not in out:
        out["los_agent"] = ""
    if "los_mode" not in out or not out.get("los_mode"):
        out["los_mode"] = "suggest_actions"
    return out


def upsert_session(telegram_user_id: str, patch: dict[str, Any]) -> None:
    current = get_session(telegram_user_id)
    merged = {**current, **patch}
    with _conn() as c:
        c.execute(
            """
            INSERT INTO telegram_sessions(
                telegram_user_id, account_email, supabase_access_token,
                supabase_refresh_token, auth_state, pending_email, los_agent, los_mode, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_user_id)
            DO UPDATE SET
                account_email=excluded.account_email,
                supabase_access_token=excluded.supabase_access_token,
                supabase_refresh_token=excluded.supabase_refresh_token,
                auth_state=excluded.auth_state,
                pending_email=excluded.pending_email,
                los_agent=excluded.los_agent,
                los_mode=excluded.los_mode,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                str(telegram_user_id),
                str(merged.get("account_email", "") or ""),
                str(merged.get("supabase_access_token", "") or ""),
                str(merged.get("supabase_refresh_token", "") or ""),
                str(merged.get("auth_state", "unauthenticated") or "unauthenticated"),
                str(merged.get("pending_email", "") or ""),
                str(merged.get("los_agent", "") or ""),
                str(merged.get("los_mode", "suggest_actions") or "suggest_actions"),
            ),
        )


def clear_session(telegram_user_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM telegram_sessions WHERE telegram_user_id=?", (str(telegram_user_id),))


def has_notified_job(job_id: str) -> bool:
    with _conn() as c:
        row = c.execute("SELECT 1 FROM notified_jobs WHERE job_id=?", (job_id,)).fetchone()
        return bool(row)

def mark_job_notified(job_id: str) -> None:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO notified_jobs(job_id) VALUES (?)", (job_id,))
