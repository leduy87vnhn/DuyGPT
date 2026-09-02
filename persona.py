import os


DEFAULT_WEB_PROMPT = (
    "Bạn là một trợ lý AI chat tên là DuyGPT. "
    "Trả lời tự nhiên, hữu ích, thân thiện, đi thẳng vào trọng tâm."
)

DEFAULT_VOICE_PROMPT = (
    "Bạn là một trợ lý AI giao tiếp bằng giọng nói, tên là DuyGPT. "
    "Trả lời ngắn gọn, tự nhiên, thân thiện, đi thẳng vào trọng tâm, "
    "phù hợp để đọc to thành tiếng cho người nghe."
)

ACTIVE_WEB_KEY = "active_web_persona_id"
ACTIVE_VOICE_KEY = "active_voice_persona_id"


def default_prompt():
    return default_web_prompt()


def default_web_prompt():
    return (
        os.getenv("DEFAULT_WEB_PERSONA_PROMPT", "").strip()
        or os.getenv("DEFAULT_PERSONA_PROMPT", "").strip()
        or DEFAULT_WEB_PROMPT
    )


def default_voice_prompt():
    return (
        os.getenv("DEFAULT_VOICE_PERSONA_PROMPT", "").strip()
        or os.getenv("DEFAULT_PERSONA_PROMPT", "").strip()
        or DEFAULT_VOICE_PROMPT
    )


def ensure_schema(pool):
    with pool.connection() as conn:
        conn.execute("ALTER TABLE persona ADD COLUMN IF NOT EXISTS web_system_prompt TEXT")
        conn.execute("ALTER TABLE persona ADD COLUMN IF NOT EXISTS voice_system_prompt TEXT")
        conn.execute(
            "UPDATE persona SET web_system_prompt = system_prompt "
            "WHERE web_system_prompt IS NULL OR btrim(web_system_prompt) = ''"
        )
        conn.execute(
            "UPDATE persona SET voice_system_prompt = %s "
            "WHERE voice_system_prompt IS NULL OR btrim(voice_system_prompt) = ''",
            (default_voice_prompt(),),
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS personas ("
            "id SERIAL PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "description TEXT NOT NULL DEFAULT '', "
            "web_system_prompt TEXT NOT NULL, "
            "voice_system_prompt TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "key TEXT PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS persona_memories ("
            "id SERIAL PRIMARY KEY, "
            "persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE, "
            "source_type TEXT NOT NULL DEFAULT 'note', "
            "filename TEXT NOT NULL DEFAULT '', "
            "content TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS persona_memories_persona_created_idx "
            "ON persona_memories (persona_id, created_at DESC)"
        )
        legacy = conn.execute(
            "SELECT system_prompt, web_system_prompt, voice_system_prompt FROM persona WHERE id = 1"
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
        if count == 0:
            web_prompt = default_web_prompt()
            voice_prompt = default_voice_prompt()
            if legacy:
                web_prompt = legacy[1] or legacy[0] or web_prompt
                voice_prompt = legacy[2] or voice_prompt
            row = conn.execute(
                "INSERT INTO personas (name, description, web_system_prompt, voice_system_prompt) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                ("DuyGPT", "Nhân vật mặc định được migrate từ cấu hình cũ.", web_prompt, voice_prompt),
            ).fetchone()
            set_active_personas_with_conn(conn, row[0], row[0])
        else:
            ensure_active_settings_with_conn(conn)


def setting_int(row):
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def set_setting_with_conn(conn, key, value):
    conn.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (%s, %s, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (key, str(value)),
    )


def first_persona_id_with_conn(conn):
    row = conn.execute("SELECT id FROM personas ORDER BY id ASC LIMIT 1").fetchone()
    return row[0] if row else None


def persona_exists_with_conn(conn, persona_id):
    if not persona_id:
        return False
    row = conn.execute("SELECT id FROM personas WHERE id = %s", (persona_id,)).fetchone()
    return bool(row)


def ensure_active_settings_with_conn(conn):
    fallback_id = first_persona_id_with_conn(conn)
    if not fallback_id:
        return None, None
    web_id = setting_int(conn.execute("SELECT value FROM app_settings WHERE key = %s", (ACTIVE_WEB_KEY,)).fetchone())
    voice_id = setting_int(conn.execute("SELECT value FROM app_settings WHERE key = %s", (ACTIVE_VOICE_KEY,)).fetchone())
    if not persona_exists_with_conn(conn, web_id):
        web_id = fallback_id
        set_setting_with_conn(conn, ACTIVE_WEB_KEY, web_id)
    if not persona_exists_with_conn(conn, voice_id):
        voice_id = fallback_id
        set_setting_with_conn(conn, ACTIVE_VOICE_KEY, voice_id)
    return web_id, voice_id


def set_active_personas_with_conn(conn, web_persona_id, voice_persona_id):
    set_setting_with_conn(conn, ACTIVE_WEB_KEY, web_persona_id)
    set_setting_with_conn(conn, ACTIVE_VOICE_KEY, voice_persona_id)


def active_persona_ids(pool):
    with pool.connection() as conn:
        web_id, voice_id = ensure_active_settings_with_conn(conn)
    return {"web_persona_id": web_id, "voice_persona_id": voice_id}


def list_personas(pool):
    with pool.connection() as conn:
        web_id, voice_id = ensure_active_settings_with_conn(conn)
        rows = conn.execute(
            "SELECT p.id, p.name, p.description, p.web_system_prompt, p.voice_system_prompt, "
            "p.created_at, p.updated_at, COUNT(m.id) "
            "FROM personas p LEFT JOIN persona_memories m ON m.persona_id = p.id "
            "GROUP BY p.id ORDER BY p.id ASC"
        ).fetchall()
    return {
        "active_web_persona_id": web_id,
        "active_voice_persona_id": voice_id,
        "personas": [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "web_system_prompt": row[3],
                "voice_system_prompt": row[4],
                "created_at": row[5].isoformat(),
                "updated_at": row[6].isoformat(),
                "memory_count": row[7],
            }
            for row in rows
        ],
    }


def get_persona_record(pool, persona_id):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, web_system_prompt, voice_system_prompt, created_at, updated_at "
            "FROM personas WHERE id = %s",
            (persona_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "web_system_prompt": row[3],
        "voice_system_prompt": row[4],
        "created_at": row[5].isoformat(),
        "updated_at": row[6].isoformat(),
    }


def create_persona(pool, name, description="", web_system_prompt="", voice_system_prompt=""):
    name = (name or "").strip() or "Nhân vật mới"
    description = (description or "").strip()
    web_prompt = (web_system_prompt or "").strip() or default_web_prompt()
    voice_prompt = (voice_system_prompt or "").strip() or default_voice_prompt()
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO personas (name, description, web_system_prompt, voice_system_prompt) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (name, description, web_prompt, voice_prompt),
        ).fetchone()
    return get_persona_record(pool, row[0])


def update_persona_record(pool, persona_id, name, description, web_system_prompt, voice_system_prompt):
    name = (name or "").strip()
    web_prompt = (web_system_prompt or "").strip()
    voice_prompt = (voice_system_prompt or "").strip()
    if not name:
        raise ValueError("name must not be empty")
    if not web_prompt:
        raise ValueError("web_system_prompt must not be empty")
    if not voice_prompt:
        raise ValueError("voice_system_prompt must not be empty")
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE personas SET name = %s, description = %s, web_system_prompt = %s, "
            "voice_system_prompt = %s, updated_at = now() WHERE id = %s RETURNING id",
            (name, (description or "").strip(), web_prompt, voice_prompt, persona_id),
        ).fetchone()
    return get_persona_record(pool, row[0]) if row else None


def delete_persona(pool, persona_id):
    with pool.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
        if count <= 1:
            raise ValueError("cannot delete the last persona")
        conn.execute("DELETE FROM personas WHERE id = %s", (persona_id,))
        ensure_active_settings_with_conn(conn)


def set_active_personas(pool, web_persona_id, voice_persona_id):
    with pool.connection() as conn:
        if not persona_exists_with_conn(conn, web_persona_id):
            raise ValueError("web_persona_id not found")
        if not persona_exists_with_conn(conn, voice_persona_id):
            raise ValueError("voice_persona_id not found")
        set_active_personas_with_conn(conn, web_persona_id, voice_persona_id)
    return active_persona_ids(pool)


def list_memories(pool, persona_id):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, source_type, filename, content, created_at FROM persona_memories "
            "WHERE persona_id = %s ORDER BY created_at DESC",
            (persona_id,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "source_type": row[1],
            "filename": row[2],
            "content": row[3],
            "created_at": row[4].isoformat(),
        }
        for row in rows
    ]


def add_memory(pool, persona_id, source_type, filename, content):
    content = (content or "").strip()
    if not content:
        raise ValueError("memory content must not be empty")
    with pool.connection() as conn:
        if not persona_exists_with_conn(conn, persona_id):
            raise ValueError("persona not found")
        row = conn.execute(
            "INSERT INTO persona_memories (persona_id, source_type, filename, content) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (persona_id, (source_type or "note").strip(), (filename or "").strip(), content),
        ).fetchone()
    return row[0]


def delete_memory(pool, memory_id):
    with pool.connection() as conn:
        conn.execute("DELETE FROM persona_memories WHERE id = %s", (memory_id,))


def prompt_memories(pool, persona_id, limit=12):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT source_type, filename, content FROM persona_memories WHERE persona_id = %s "
            "ORDER BY created_at DESC LIMIT %s",
            (persona_id, limit),
        ).fetchall()
    return [
        {
            "source_type": row[0],
            "filename": row[1],
            "content": row[2],
        }
        for row in rows
    ]


def format_persona_memory_prompt(memories):
    if not memories:
        return ""
    lines = []
    for item in memories:
        prefix = item["source_type"]
        if item["filename"]:
            prefix = f"{prefix}:{item['filename']}"
        lines.append(f"- [{prefix}] {item['content']}")
    return (
        "Ký ức riêng của nhân vật dưới đây là sự thật nền về chính bạn, "
        "được admin nạp riêng cho persona hiện tại. Dùng khi liên quan, "
        "giữ nhất quán như ký ức/tư liệu cá nhân của bạn:\n" + "\n".join(lines)
    )


def get_personas(pool):
    active = active_persona_ids(pool)
    web_id = active["web_persona_id"]
    voice_id = active["voice_persona_id"]
    web = get_persona_record(pool, web_id)
    voice = get_persona_record(pool, voice_id)
    web_prompt = (web or {}).get("web_system_prompt") or default_web_prompt()
    voice_prompt = (voice or {}).get("voice_system_prompt") or default_voice_prompt()
    return {
        "system_prompt": web_prompt,
        "web_system_prompt": web_prompt,
        "voice_system_prompt": voice_prompt,
        "web_persona_id": web_id,
        "voice_persona_id": voice_id,
    }


def get_active_web_persona(pool):
    persona_id = active_persona_ids(pool)["web_persona_id"]
    record = get_persona_record(pool, persona_id)
    return record or {"id": persona_id, "web_system_prompt": default_web_prompt()}


def get_active_voice_persona(pool):
    persona_id = active_persona_ids(pool)["voice_persona_id"]
    record = get_persona_record(pool, persona_id)
    return record or {"id": persona_id, "voice_system_prompt": default_voice_prompt()}


def get_web_persona(pool):
    return get_active_web_persona(pool)["web_system_prompt"]


def get_voice_persona(pool):
    return get_active_voice_persona(pool)["voice_system_prompt"]


def get_persona(pool):
    return get_web_persona(pool)


def update_persona_if_absent(pool, system_prompt):
    web_prompt = system_prompt or default_web_prompt()
    voice_prompt = default_voice_prompt()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO persona (id, system_prompt, web_system_prompt, voice_system_prompt) "
            "VALUES (1, %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (web_prompt, web_prompt, voice_prompt),
        )
    ensure_schema(pool)


def update_persona(pool, system_prompt):
    update_personas(pool, system_prompt, None)


def update_personas(pool, web_system_prompt, voice_system_prompt):
    web_prompt = (web_system_prompt or "").strip()
    voice_prompt = (voice_system_prompt or "").strip()
    existing = get_personas(pool)
    if not web_prompt:
        web_prompt = existing["web_system_prompt"]
    if not voice_prompt:
        voice_prompt = existing["voice_system_prompt"]
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO persona "
            "(id, system_prompt, web_system_prompt, voice_system_prompt, updated_at) "
            "VALUES (1, %s, %s, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET "
            "system_prompt = EXCLUDED.web_system_prompt, "
            "web_system_prompt = EXCLUDED.web_system_prompt, "
            "voice_system_prompt = EXCLUDED.voice_system_prompt, "
            "updated_at = now()",
            (web_prompt, web_prompt, voice_prompt),
        )
    active = active_persona_ids(pool)
    web_record = get_persona_record(pool, active["web_persona_id"])
    voice_record = get_persona_record(pool, active["voice_persona_id"])
    if web_record:
        update_persona_record(
            pool,
            web_record["id"],
            web_record["name"],
            web_record["description"],
            web_prompt,
            web_record["voice_system_prompt"],
        )
    if voice_record:
        update_persona_record(
            pool,
            voice_record["id"],
            voice_record["name"],
            voice_record["description"],
            voice_record["web_system_prompt"],
            voice_prompt,
        )
