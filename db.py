import os
import secrets
from pathlib import Path

from psycopg_pool import ConnectionPool

from auth import hash_password
import persona

ROOT = Path(__file__).resolve().parent

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        conninfo = (
            f"host={os.getenv('PGHOST', '127.0.0.1')} "
            f"port={os.getenv('PGPORT', '5432')} "
            f"dbname={os.getenv('PGDATABASE', 'duygpt')} "
            f"user={os.getenv('PGUSER', 'duygpt')} "
            f"password={os.getenv('PGPASSWORD', '')}"
        )
        _pool = ConnectionPool(conninfo, min_size=1, max_size=5, open=True)
    return _pool


def bootstrap():
    pool = get_pool()
    schema_sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    with pool.connection() as conn:
        conn.execute(schema_sql)
    persona.ensure_schema(pool)
    seed_admin()
    seed_voice_device()
    seed_persona()


def seed_voice_device():
    pool = get_pool()
    username = os.getenv("VOICE_DEVICE_USERNAME", "voice-assistant")
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, user_type) "
            "VALUES (%s, %s, 'normal_user') ON CONFLICT (username) DO NOTHING",
            (username, hash_password(secrets.token_urlsafe(32))),
        )


def seed_persona():
    persona.update_persona_if_absent(get_pool(), persona.default_prompt())


def seed_admin():
    pool = get_pool()
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "abcd@123")
    with pool.connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE user_type = 'admin_user'"
        ).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO users (username, password_hash, user_type) "
            "VALUES (%s, %s, 'admin_user') ON CONFLICT (username) DO NOTHING",
            (username, hash_password(password)),
        )
