"""账号与会话服务（SQLite，标准库实现）。

支持注册、登录与 Token 会话。内置演示账号（用户名 demo，密码由环境变量
DEMO_PASSWORD 设置；未设置时默认 demo123，仅用于本地开发）。密码使用 PBKDF2 加盐哈希存储，
演示账号直接使用服务端环境变量中的 API Key；注册账号在前端填写自己的
API Key（BYOK），后端不存储任何用户的 Key。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_lock = threading.Lock()
_db_path: Optional[Path] = None


def _db() -> sqlite3.Connection:
    """获取数据库连接（自动创建目录）。"""
    global _db_path
    if _db_path is None:
        raw = os.getenv("DATABASE_PATH", "backend/data/users.db")
        _db_path = Path(raw)
        _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据表，并确保演示账号存在。"""
    with _lock:
        conn = _db()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        demo_username = os.getenv("DEMO_USERNAME", "demo")
        demo_password = os.getenv("DEMO_PASSWORD", "demo123")
        salt, password_hash = _hash_password(demo_password)
        existing = conn.execute("SELECT username FROM users WHERE username = ?", (demo_username,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, is_demo, created_at) VALUES (?, ?, ?, 1, ?)",
                (demo_username, password_hash, salt, _now_iso()),
            )
        else:
            # 环境变量是演示账号密码的唯一事实来源：每次启动都同步，
            # 保证云端改密并重新部署后，旧密码立即失效（即使数据库文件被保留）。
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                (password_hash, salt, demo_username),
            )
        conn.commit()
        conn.close()


def register(username: str, password: str) -> dict:
    """注册新账号并返回登录结果。"""
    username = username.strip()
    if not (2 <= len(username) <= 32):
        raise ValueError("用户名长度需为 2-32 个字符")
    if not (4 <= len(password) <= 64):
        raise ValueError("密码长度需为 4-64 个字符")
    salt, password_hash = _hash_password(password)
    with _lock:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, is_demo, created_at) VALUES (?, ?, ?, 0, ?)",
                (username, password_hash, salt, _now_iso()),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在，请换一个") from exc
        finally:
            conn.close()
    return login(username, password)


def login(username: str, password: str) -> dict:
    """校验账号密码，创建会话 Token。"""
    username = username.strip()
    with _lock:
        conn = _db()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
    if row is None or not _verify_password(password, row["salt"], row["password_hash"]):
        raise ValueError("用户名或密码错误")
    token = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with _lock:
        conn = _db()
        conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
        conn.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username, expires_at),
        )
        conn.commit()
        conn.close()
    return {"token": token, "username": username, "is_demo": bool(row["is_demo"]), "expires_at": expires_at}


def get_user(token: str) -> Optional[dict]:
    """按 Token 查找当前登录用户（校验有效期）。"""
    if not token:
        return None
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT s.username AS username, u.is_demo AS is_demo, s.expires_at AS expires_at
            FROM sessions s JOIN users u ON u.username = s.username
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        conn.close()
    if row is None:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if expires < datetime.now(timezone.utc):
        return None
    return {"username": row["username"], "is_demo": bool(row["is_demo"])}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """PBKDF2-SHA256 加盐哈希，返回 (salt, hex_digest)。"""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return salt, digest.hex()


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, digest = _hash_password(password, salt)
    return hmac.compare_digest(digest, expected_hash)
