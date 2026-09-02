import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

PBKDF2_ITERATIONS = 200_000


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password, stored_hash):
    try:
        algo, iterations, salt, digest = stored_hash.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    expected = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
    ).hex()
    return secrets.compare_digest(expected, digest)


def new_session_token():
    return secrets.token_urlsafe(32)


def session_ttl_days():
    return int(os.getenv("SESSION_TTL_DAYS", "30"))


def session_expiry():
    return datetime.now(timezone.utc) + timedelta(days=session_ttl_days())


def create_session(pool, user_id):
    token = new_session_token()
    expires_at = session_expiry()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )
    return token, expires_at


def delete_session(pool, token):
    with pool.connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = %s", (token,))


def get_user_for_token(pool, token):
    if not token:
        return None
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.user_type, u.crm_access FROM sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.token = %s AND s.expires_at > now()",
            (token,),
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "user_type": row[2], "crm_access": row[3]}


def parse_cookie_header(header):
    cookies = {}
    if not header:
        return cookies
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        cookies[key] = value
    return cookies


SESSION_COOKIE_NAME = "duygpt_session"


def session_cookie_header(token, expires_at, clear=False):
    if clear:
        return f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    max_age = max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 0)
    return f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
