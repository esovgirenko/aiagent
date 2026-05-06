import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from .config import settings


def _db_path_from_url(url: str) -> str:
    if not url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// URLs are supported in this MVP")
    return url.replace("sqlite:///", "", 1)


DB_PATH = _db_path_from_url(settings.database_url)


def init_db() -> None:
    Path(os.path.dirname(DB_PATH) or ".").mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                comment TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                ip TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_by TEXT NOT NULL DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(goal_id) REFERENCES goals(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomous_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                plan_text TEXT NOT NULL,
                action_text TEXT NOT NULL,
                verify_status TEXT NOT NULL,
                reflection_text TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(goal_id) REFERENCES goals(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomy_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                created_by TEXT NOT NULL,
                last_error TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        # Lightweight migration for older DBs created before role/is_active fields.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "role" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "is_active" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        conn.commit()


def save_conversation(provider: str, user_message: str, assistant_message: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO conversations(provider, user_message, assistant_message)
            VALUES (?, ?, ?)
            """,
            (provider, user_message, assistant_message),
        )
        conn.commit()
        return int(cur.lastrowid)


def save_feedback(conversation_id: int, score: int, comment: str = "") -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO feedback(conversation_id, score, comment)
            VALUES (?, ?, ?)
            """,
            (conversation_id, score, comment),
        )
        conn.commit()


def get_recent_memories(limit: int = 8) -> List[Tuple[str, str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT provider, user_message, assistant_message
            FROM conversations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def get_feedback_summary(limit: int = 30) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT f.score, c.user_message, c.assistant_message
            FROM feedback f
            JOIN conversations c ON c.id = f.conversation_id
            ORDER BY f.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    if not rows:
        return "No feedback yet."

    good = [r for r in rows if int(r[0]) > 0]
    bad = [r for r in rows if int(r[0]) <= 0]
    return (
        f"Positive feedback: {len(good)}; Negative feedback: {len(bad)}. "
        "Prefer concise, accurate answers. Avoid repeating mistakes from negatively rated replies."
    )


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    if "$" not in stored_hash:
        return False
    salt, digest = stored_hash.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return hmac.compare_digest(candidate, digest)


def get_user(username: str) -> Optional[Tuple[int, str, str, str, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    return (int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]))


def create_user(username: str, password: str, role: str = "user") -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role),
        )
        conn.commit()
        return int(cur.lastrowid)


def ensure_default_user(username: str, password: str) -> None:
    if not username or not password:
        return
    if get_user(username):
        return
    create_user(username, password, role="admin")


def save_audit_log(username: str, action: str, ip: str, details: str = "") -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO audit_logs(username, action, ip, details)
            VALUES (?, ?, ?, ?)
            """,
            (username, action, ip, details),
        )
        conn.commit()


def list_users() -> List[Tuple[int, str, str, int, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, is_active, created_at
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()
    return [(int(r[0]), str(r[1]), str(r[2]), int(r[3]), str(r[4])) for r in rows]


def set_user_active(username: str, is_active: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET is_active = ? WHERE username = ?",
            (is_active, username),
        )
        conn.commit()


def list_audit_logs(limit: int = 100) -> List[Tuple[str, str, str, str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT username, action, ip, details, created_at
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])) for r in rows]


def create_goal(title: str, created_by: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO goals(title, created_by) VALUES (?, ?)",
            (title, created_by),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_or_create_active_goal(title: str, created_by: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM goals WHERE title = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (title,),
        ).fetchone()
        if row:
            return int(row[0])
    return create_goal(title, created_by)


def create_goal_task(goal_id: int, content: str, priority: int = 1) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO goal_tasks(goal_id, content, priority) VALUES (?, ?, ?)",
            (goal_id, content, priority),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_goal_tasks(goal_id: int) -> List[Tuple[int, str, str, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, content, status, priority
            FROM goal_tasks
            WHERE goal_id = ?
            ORDER BY priority DESC, id ASC
            """,
            (goal_id,),
        ).fetchall()
    return [(int(r[0]), str(r[1]), str(r[2]), int(r[3])) for r in rows]


def mark_task_done(task_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE goal_tasks SET status = 'done' WHERE id = ?", (task_id,))
        conn.commit()


def save_autonomous_run(
    goal_id: int,
    provider: str,
    plan_text: str,
    action_text: str,
    verify_status: str,
    reflection_text: str,
    created_by: str,
) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO autonomous_runs(
                goal_id, provider, plan_text, action_text, verify_status, reflection_text, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (goal_id, provider, plan_text, action_text, verify_status, reflection_text, created_by),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_autonomous_runs(limit: int = 30) -> List[Tuple[int, int, str, str, str, str, str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, goal_id, provider, plan_text, action_text, verify_status, reflection_text, created_at
            FROM autonomous_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        (int(r[0]), int(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5]), str(r[6]), str(r[7]))
        for r in rows
    ]


def enqueue_autonomy_goal(goal: str, provider: str, created_by: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO autonomy_queue(goal, provider, created_by) VALUES (?, ?, ?)",
            (goal, provider, created_by),
        )
        conn.commit()
        return int(cur.lastrowid)


def fetch_next_queued_goal() -> Optional[Tuple[int, str, str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id, goal, provider, created_by
            FROM autonomy_queue
            WHERE status = 'queued'
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE autonomy_queue SET status = 'running' WHERE id = ?", (int(row[0]),))
        conn.commit()
    return (int(row[0]), str(row[1]), str(row[2]), str(row[3]))


def mark_queue_item_done(item_id: int) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE autonomy_queue SET status = 'done', last_error = '' WHERE id = ?", (item_id,))
        conn.commit()


def mark_queue_item_failed(item_id: int, error_text: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE autonomy_queue SET status = 'failed', last_error = ? WHERE id = ?",
            (error_text[:1000], item_id),
        )
        conn.commit()


def list_queue_items(limit: int = 50) -> List[Tuple[int, str, str, str, str, str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, goal, provider, status, created_by, last_error, created_at
            FROM autonomy_queue
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        (int(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5]), str(r[6]))
        for r in rows
    ]
