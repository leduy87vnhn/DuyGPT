"""Per-account work assistant: meetings (fixed time slot) and tasks (deadline
only, no time slot), plus the chat tool-calling agent.

Location-at-a-point-in-time is exposed as a small lookup API intended for
future voice assistant / Raspberry Pi display integration -- see
current_location(). The schedule itself belongs to the admin account (the
single business owner using the CRM module), not a per-family-member thing.
"""
from datetime import datetime
import json
import llm_tools
import crm


def parse_datetime(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


# --- Meetings (work_schedule: fixed start/end time slot) ---

def _entry_dict(row):
    return {
        "id": row[0],
        "customer_id": row[1],
        "customer_name": row[2],
        "title": row[3],
        "location": row[4],
        "start_at": row[5].isoformat(),
        "end_at": row[6].isoformat(),
        "created_at": row[7].isoformat(),
        "updated_at": row[8].isoformat(),
        "done": row[9],
        "completed_at": row[10].isoformat() if row[10] else None,
    }


_ENTRY_SELECT = (
    "SELECT s.id, c.id, c.name, s.title, s.location, s.start_at, s.end_at, "
    "s.created_at, s.updated_at, s.done, s.completed_at "
    "FROM work_schedule s LEFT JOIN crm_customers c ON c.id = s.customer_id "
    "AND (c.user_id = s.user_id OR EXISTS (SELECT 1 FROM crm_customer_shares sh "
    "WHERE sh.customer_id = c.id AND sh.user_id = s.user_id))"
)


def create_entry(pool, user_id, customer_id, title, location, start_at, end_at):
    if customer_id and not crm.can_access_customer(pool, user_id, customer_id):
        return {"error": "customer not found"}
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    start = parse_datetime(start_at)
    end = parse_datetime(end_at)
    if not start or not end:
        return {"error": "start_at and end_at must be valid ISO 8601 timestamps"}
    if end <= start:
        return {"error": "end_at must be after start_at"}
    with pool.connection() as conn:
        row_id = conn.execute(
            "INSERT INTO work_schedule (user_id, customer_id, title, location, start_at, end_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, customer_id or None, title, (location or "").strip(), start, end),
        ).fetchone()[0]
        row = conn.execute(f"{_ENTRY_SELECT} WHERE s.id = %s", (row_id,)).fetchone()
    return _entry_dict(row)


def list_entries(pool, user_id, start_from=None, start_to=None, limit=200):
    query = f"{_ENTRY_SELECT} WHERE s.user_id = %s"
    params = [user_id]
    if start_from:
        query += " AND s.end_at >= %s"
        params.append(start_from)
    if start_to:
        query += " AND s.start_at <= %s"
        params.append(start_to)
    query += " ORDER BY s.done ASC, s.start_at ASC LIMIT %s"
    params.append(limit)
    with pool.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_entry_dict(row) for row in rows]


def update_entry(pool, user_id, entry_id, customer_id, title, location, start_at, end_at):
    if customer_id and not crm.can_access_customer(pool, user_id, customer_id):
        return {"error": "customer not found"}
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    start = parse_datetime(start_at)
    end = parse_datetime(end_at)
    if not start or not end:
        return {"error": "start_at and end_at must be valid ISO 8601 timestamps"}
    if end <= start:
        return {"error": "end_at must be after start_at"}
    with pool.connection() as conn:
        updated = conn.execute(
            "UPDATE work_schedule SET customer_id = %s, title = %s, location = %s, "
            "start_at = %s, end_at = %s, updated_at = now() WHERE id = %s AND user_id = %s RETURNING id",
            (customer_id or None, title, (location or "").strip(), start, end, entry_id, user_id),
        ).fetchone()
        if not updated:
            return {"error": "schedule entry not found"}
        row = conn.execute(f"{_ENTRY_SELECT} WHERE s.id = %s AND s.user_id = %s", (entry_id, user_id)).fetchone()
    return _entry_dict(row)


def set_entry_done(pool, user_id, entry_id, done):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE work_schedule SET done = %s, completed_at = CASE WHEN %s THEN now() ELSE NULL END "
            "WHERE id = %s AND user_id = %s RETURNING id",
            (done, done, entry_id, user_id),
        ).fetchone()
        if not row:
            return {"error": "schedule entry not found"}
        result = conn.execute(f"{_ENTRY_SELECT} WHERE s.id = %s AND s.user_id = %s", (entry_id, user_id)).fetchone()
    return _entry_dict(result)


def delete_entry(pool, user_id, entry_id):
    with pool.connection() as conn:
        row = conn.execute("DELETE FROM work_schedule WHERE id = %s AND user_id = %s RETURNING id", (entry_id, user_id)).fetchone()
    return {"deleted": bool(row), "id": entry_id}


def current_location(pool, user_id, at=None):
    """Find one user's scheduled location at a moment (default now)."""
    moment = at or datetime.now().astimezone()
    with pool.connection() as conn:
        row = conn.execute(
            f"{_ENTRY_SELECT} WHERE s.user_id = %s AND s.start_at <= %s AND s.end_at >= %s "
            "ORDER BY s.start_at DESC LIMIT 1",
            (user_id, moment, moment),
        ).fetchone()
    if not row:
        return {"at": moment.isoformat(), "found": False}
    entry = _entry_dict(row)
    entry["at"] = moment.isoformat()
    entry["found"] = True
    return entry


# --- Tasks (work_tasks: deadline only, no fixed time slot) ---

def _task_dict(row):
    return {
        "id": row[0],
        "title": row[1],
        "due_at": row[2].isoformat() if row[2] else None,
        "done": row[3],
        "created_at": row[4].isoformat(),
        "completed_at": row[5].isoformat() if row[5] else None,
    }


_TASK_SELECT = "SELECT id, title, due_at, done, created_at, completed_at FROM work_tasks"


def create_task(pool, user_id, title, due_at):
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    due = parse_datetime(due_at) if due_at else None
    with pool.connection() as conn:
        row_id = conn.execute(
            "INSERT INTO work_tasks (user_id, title, due_at) VALUES (%s, %s, %s) RETURNING id",
            (user_id, title, due),
        ).fetchone()[0]
        row = conn.execute(f"{_TASK_SELECT} WHERE id = %s", (row_id,)).fetchone()
    return _task_dict(row)


def list_tasks(pool, user_id, include_done=True, limit=200):
    query = f"{_TASK_SELECT} WHERE user_id = %s"
    params = [user_id]
    if not include_done:
        query += " AND done = FALSE"
    query += " ORDER BY done ASC, due_at ASC NULLS LAST, created_at ASC LIMIT %s"
    params.append(limit)
    with pool.connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_task_dict(row) for row in rows]


def update_task(pool, user_id, task_id, title, due_at):
    title = (title or "").strip()
    if not title:
        return {"error": "title is required"}
    due = parse_datetime(due_at) if due_at else None
    with pool.connection() as conn:
        updated = conn.execute(
            "UPDATE work_tasks SET title = %s, due_at = %s WHERE id = %s AND user_id = %s RETURNING id",
            (title, due, task_id, user_id),
        ).fetchone()
        if not updated:
            return {"error": "task not found"}
        row = conn.execute(f"{_TASK_SELECT} WHERE id = %s", (task_id,)).fetchone()
    return _task_dict(row)


def set_task_done(pool, user_id, task_id, done):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE work_tasks SET done = %s, completed_at = CASE WHEN %s THEN now() ELSE NULL END "
            "WHERE id = %s AND user_id = %s RETURNING id",
            (done, done, task_id, user_id),
        ).fetchone()
        if not row:
            return {"error": "task not found"}
        result = conn.execute(f"{_TASK_SELECT} WHERE id = %s", (task_id,)).fetchone()
    return _task_dict(result)


def delete_task(pool, user_id, task_id):
    with pool.connection() as conn:
        row = conn.execute("DELETE FROM work_tasks WHERE id = %s AND user_id = %s RETURNING id", (task_id, user_id)).fetchone()
    return {"deleted": bool(row), "id": task_id}


# --- Chat tool-calling agent ---

TOOLS = [
    {"type": "function", "function": {"name": "get_current_datetime", "description": "Lấy ngày giờ hiện tại để đổi các mốc tương đối (\"mai\", \"thứ 5 tuần sau\"...).", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_tasks", "description": "Xem danh sách Việc Cần Làm (công việc có deadline, KHÔNG có giờ họp cố định).", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_meetings", "description": "Xem danh sách Lịch Họp (cuộc họp/hẹn có giờ bắt đầu và kết thúc cụ thể).", "parameters": {"type": "object", "properties": {}}}},
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": (
                "Thêm một Việc Cần Làm mới -- dùng khi người dùng nói về một công việc/deadline cần hoàn thành, "
                "KHÔNG có giờ bắt đầu/kết thúc cụ thể và KHÔNG phải là một cuộc họp/hẹn gặp. "
                "Ví dụ: 'nhắc tôi nộp báo cáo trước thứ 6', 'thêm việc gọi lại cho khách hàng A'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_at": {"type": "string", "description": "Hạn chót, ISO 8601. Có thể để trống nếu không có hạn cụ thể."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_meeting",
            "description": (
                "Thêm một Lịch Họp mới -- dùng khi người dùng nói về một cuộc họp, cuộc hẹn, buổi gặp có "
                "giờ bắt đầu và kết thúc cụ thể (có thể có địa điểm). "
                "Ví dụ: 'đặt lịch họp với khách hàng B lúc 9h sáng mai đến 10h', 'thêm cuộc hẹn tại văn phòng lúc 2h chiều thứ 3'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "location": {"type": "string"},
                    "start_at": {"type": "string", "description": "ISO 8601"},
                    "end_at": {"type": "string", "description": "ISO 8601"},
                },
                "required": ["title", "start_at", "end_at"],
            },
        },
    },
    {"type": "function", "function": {"name": "complete_task", "description": "Đánh dấu một Việc Cần Làm là đã xong.", "parameters": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}}},
    {"type": "function", "function": {"name": "complete_meeting", "description": "Đánh dấu một Lịch Họp là đã xong.", "parameters": {"type": "object", "properties": {"entry_id": {"type": "integer"}}, "required": ["entry_id"]}}},
    {"type": "function", "function": {"name": "delete_task", "description": "Xóa một Việc Cần Làm theo id.", "parameters": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}}},
    {"type": "function", "function": {"name": "delete_meeting", "description": "Xóa một Lịch Họp theo id.", "parameters": {"type": "object", "properties": {"entry_id": {"type": "integer"}}, "required": ["entry_id"]}}},
]


def run_agent(cfg, pool, user_id, messages, max_iterations=6):
    def now(_args):
        value = datetime.now().astimezone()
        return {"now": value.isoformat(), "weekday": value.strftime("%A")}

    handlers = {
        "get_current_datetime": now,
        "list_tasks": lambda _args: {"tasks": list_tasks(pool, user_id)},
        "list_meetings": lambda _args: {"meetings": list_entries(pool, user_id)},
        "add_task": lambda args: create_task(pool, user_id, args.get("title"), args.get("due_at")),
        "add_meeting": lambda args: create_entry(pool, user_id, None, args.get("title"), args.get("location"), args.get("start_at"), args.get("end_at")),
        "complete_task": lambda args: set_task_done(pool, user_id, int(args.get("task_id", 0)), True),
        "complete_meeting": lambda args: set_entry_done(pool, user_id, int(args.get("entry_id", 0)), True),
        "delete_task": lambda args: delete_task(pool, user_id, int(args.get("task_id", 0))),
        "delete_meeting": lambda args: delete_entry(pool, user_id, int(args.get("entry_id", 0))),
    }
    state = json.dumps(
        {"tasks": list_tasks(pool, user_id), "meetings": list_entries(pool, user_id)},
        ensure_ascii=False,
    )
    system = (
        "Bạn là trợ lý công việc. Luôn trả lời ngắn gọn bằng tiếng Việt. "
        "Có 2 loại mục cần phân biệt rõ khi người dùng muốn thêm: "
        "(1) Việc Cần Làm (add_task) -- công việc/deadline, không có giờ họp cụ thể; "
        "(2) Lịch Họp (add_meeting) -- cuộc họp/hẹn có giờ bắt đầu và kết thúc cụ thể. "
        "Tự nhận biết dựa vào nội dung người dùng nói, không hỏi lại trừ khi thực sự không đủ thông tin. "
        "Với thời gian tương đối phải lấy giờ hiện tại trước. Dữ liệu hiện tại: " + state
    )
    return llm_tools.run_tool_loop(cfg, cfg.get("work_assistant_model") or cfg["model"],
                                   [{"role": "system", "content": system}] + list(messages),
                                   TOOLS, handlers, max_iterations)
