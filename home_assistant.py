"""ben_homeassistant: on-prem family assistant agent.

Runs on the same LLM/Postgres already configured for DuyGPT (see app.config()).
Not connected to the Home Assistant smart-home platform -- this is a general
household agent (reminders, notes, shopping list) with tool-calling, ready to
grow into a real smart-home/voice integration later.
"""
import json
import os
from datetime import datetime, timezone

import llm_tools

DEFAULT_SYSTEM_PROMPT = (
    "Bạn là trợ lý gia đình on-prem, chạy hoàn toàn trên máy chủ nội bộ, không gửi dữ liệu ra ngoài. "
    "Bạn giúp các thành viên trong nhà quản lý lịch gia đình, cuộc hẹn, việc cần nhắc, ghi chú và danh sách mua sắm. "
    "Luôn trả lời bằng tiếng Việt, ngắn gọn, tự nhiên, thân thiện như người trong nhà. "
    "Khi người dùng muốn thêm/xem/xóa lịch gia đình, việc nhắc, ghi chú hay món cần mua, hãy dùng đúng công cụ (tool) tương ứng thay vì chỉ trả lời suông. "
    "Nếu người dùng nói thời gian tương đối (vd 'chiều nay', 'ngày mai'), hãy gọi get_current_datetime trước để tính giờ chính xác rồi mới gọi add_reminder với due_at dạng ISO 8601 (vd 2026-08-24T18:00:00). "
    "Nếu không rõ due_at, vẫn có thể thêm nhắc việc mà không cần giờ cụ thể. "
    "Sau khi dùng tool xong, tóm tắt lại kết quả cho người dùng bằng một câu trả lời tự nhiên, không hiển thị JSON thô. "
    "Bạn hiện chưa điều khiển được thiết bị nhà thông minh thật (đèn, công tắc...); nếu được hỏi, hãy nói rõ tính năng đó sẽ được bổ sung sau."
)


def system_prompt():
    return os.getenv("HOME_ASSISTANT_SYSTEM_PROMPT", "").strip() or DEFAULT_SYSTEM_PROMPT


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Lấy ngày giờ hiện tại của máy chủ. Gọi trước khi tính due_at tương đối (hôm nay, ngày mai, tuần sau...).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_family_event",
            "description": "Thêm lịch gia đình, cuộc hẹn hoặc sự kiện vào lịch của tài khoản hiện tại.",
            "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "location": {"type": "string"}, "start_at": {"type": "string", "description": "ISO 8601"}, "end_at": {"type": "string", "description": "ISO 8601"}}, "required": ["title", "start_at", "end_at"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_family_events",
            "description": "Xem lịch gia đình, cuộc hẹn và sự kiện của tài khoản hiện tại.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_family_event",
            "description": "Xóa một sự kiện gia đình theo id.",
            "parameters": {"type": "object", "properties": {"event_id": {"type": "integer"}}, "required": ["event_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Thêm một việc cần nhắc cho người dùng hiện tại.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung việc cần nhắc."},
                    "due_at": {
                        "type": "string",
                        "description": "Thời điểm cần nhắc, dạng ISO 8601 (vd 2026-08-24T18:00:00). Bỏ trống nếu không có giờ cụ thể.",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Liệt kê các việc cần nhắc của người dùng hiện tại.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_done": {
                        "type": "boolean",
                        "description": "True để bao gồm cả việc đã hoàn thành. Mặc định false.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_reminder",
            "description": "Đánh dấu một việc nhắc là đã hoàn thành.",
            "parameters": {
                "type": "object",
                "properties": {"reminder_id": {"type": "integer"}},
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "Xóa hẳn một việc nhắc.",
            "parameters": {
                "type": "object",
                "properties": {"reminder_id": {"type": "integer"}},
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "Lưu một ghi chú cho người dùng hiện tại.",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "Liệt kê các ghi chú gần đây của người dùng hiện tại.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Xóa một ghi chú.",
            "parameters": {
                "type": "object",
                "properties": {"note_id": {"type": "integer"}},
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_shopping_item",
            "description": "Thêm một món vào danh sách mua sắm chung của gia đình.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Tên món cần mua."},
                    "quantity": {"type": "string", "description": "Số lượng/ghi chú, vd '2 chai', '1kg'."},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_shopping_items",
            "description": "Liệt kê danh sách mua sắm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_done": {
                        "type": "boolean",
                        "description": "True để bao gồm cả món đã mua. Mặc định false.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_off_shopping_item",
            "description": "Đánh dấu một món trong danh sách mua sắm là đã mua.",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "integer"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_shopping_item",
            "description": "Xóa một món khỏi danh sách mua sắm.",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "integer"}},
                "required": ["item_id"],
            },
        },
    },
]


def _parse_due_at(value):
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


# --- Tool implementations (pool, user_id, arguments) -> JSON-serializable dict ---


def get_current_datetime(pool, user_id, arguments):
    now = datetime.now().astimezone()
    return {"now": now.isoformat(), "weekday": now.strftime("%A")}


def _event_dict(row):
    return {"id": row[0], "title": row[1], "location": row[2], "start_at": row[3].isoformat(), "end_at": row[4].isoformat(), "created_at": row[5].isoformat()}


def add_family_event(pool, user_id, arguments):
    title = (arguments.get("title") or "").strip()
    start = _parse_due_at(arguments.get("start_at"))
    end = _parse_due_at(arguments.get("end_at"))
    if not title or not start or not end or end <= start:
        return {"error": "title, start_at và end_at hợp lệ là bắt buộc"}
    with pool.connection() as conn:
        row = conn.execute("INSERT INTO home_calendar_events (user_id, title, location, start_at, end_at) VALUES (%s,%s,%s,%s,%s) RETURNING id,title,location,start_at,end_at,created_at", (user_id, title, (arguments.get("location") or "").strip(), start, end)).fetchone()
    return _event_dict(row)


def list_family_events(pool, user_id, arguments=None):
    with pool.connection() as conn:
        rows = conn.execute("SELECT id,title,location,start_at,end_at,created_at FROM home_calendar_events WHERE user_id=%s ORDER BY start_at ASC LIMIT 200", (user_id,)).fetchall()
    return {"events": [_event_dict(row) for row in rows]}


def delete_family_event(pool, user_id, arguments):
    event_id = int(arguments.get("event_id") or 0)
    with pool.connection() as conn:
        row = conn.execute("DELETE FROM home_calendar_events WHERE id=%s AND user_id=%s RETURNING id", (event_id, user_id)).fetchone()
    return {"deleted": bool(row), "id": event_id}


def add_reminder(pool, user_id, arguments):
    content = (arguments.get("content") or "").strip()
    if not content:
        return {"error": "content is required"}
    due_at = _parse_due_at(arguments.get("due_at"))
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO home_reminders (user_id, content, due_at) VALUES (%s, %s, %s) "
            "RETURNING id, content, due_at, done, created_at",
            (user_id, content, due_at),
        ).fetchone()
    return _reminder_dict(row)


def list_reminders(pool, user_id, arguments):
    include_done = bool(arguments.get("include_done"))
    query = (
        "SELECT id, content, due_at, done, created_at FROM home_reminders WHERE user_id = %s "
        + ("" if include_done else "AND done = FALSE ")
        + "ORDER BY (due_at IS NULL), due_at ASC, created_at ASC LIMIT 50"
    )
    with pool.connection() as conn:
        rows = conn.execute(query, (user_id,)).fetchall()
    return {"reminders": [_reminder_dict(row) for row in rows]}


def complete_reminder(pool, user_id, arguments):
    reminder_id = arguments.get("reminder_id")
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE home_reminders SET done = TRUE, completed_at = now() "
            "WHERE id = %s AND user_id = %s RETURNING id, content, due_at, done, created_at",
            (reminder_id, user_id),
        ).fetchone()
    if not row:
        return {"error": "reminder not found"}
    return _reminder_dict(row)


def delete_reminder(pool, user_id, arguments):
    reminder_id = arguments.get("reminder_id")
    with pool.connection() as conn:
        row = conn.execute(
            "DELETE FROM home_reminders WHERE id = %s AND user_id = %s RETURNING id",
            (reminder_id, user_id),
        ).fetchone()
    return {"deleted": bool(row), "id": reminder_id}


def add_note(pool, user_id, arguments):
    content = (arguments.get("content") or "").strip()
    if not content:
        return {"error": "content is required"}
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO home_notes (user_id, content) VALUES (%s, %s) RETURNING id, content, created_at",
            (user_id, content),
        ).fetchone()
    return _note_dict(row)


def list_notes(pool, user_id, arguments):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM home_notes WHERE user_id = %s "
            "ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
    return {"notes": [_note_dict(row) for row in rows]}


def delete_note(pool, user_id, arguments):
    note_id = arguments.get("note_id")
    with pool.connection() as conn:
        row = conn.execute(
            "DELETE FROM home_notes WHERE id = %s AND user_id = %s RETURNING id",
            (note_id, user_id),
        ).fetchone()
    return {"deleted": bool(row), "id": note_id}


def add_shopping_item(pool, user_id, arguments):
    content = (arguments.get("content") or "").strip()
    if not content:
        return {"error": "content is required"}
    quantity = (arguments.get("quantity") or "").strip()
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO home_shopping_items (user_id, content, quantity) VALUES (%s, %s, %s) "
            "RETURNING id, content, quantity, done, created_at",
            (user_id, content, quantity),
        ).fetchone()
    return _shopping_item_dict(row)


def list_shopping_items(pool, user_id, arguments):
    include_done = bool(arguments.get("include_done"))
    query = (
        "SELECT id, content, quantity, done, created_at FROM home_shopping_items WHERE user_id = %s "
        + ("" if include_done else "AND done = FALSE ")
        + "ORDER BY created_at ASC LIMIT 100"
    )
    with pool.connection() as conn:
        rows = conn.execute(query, (user_id,)).fetchall()
    return {"items": [_shopping_item_dict(row) for row in rows]}


def check_off_shopping_item(pool, user_id, arguments):
    item_id = arguments.get("item_id")
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE home_shopping_items SET done = TRUE WHERE id = %s AND user_id = %s "
            "RETURNING id, content, quantity, done, created_at",
            (item_id, user_id),
        ).fetchone()
    if not row:
        return {"error": "item not found"}
    return _shopping_item_dict(row)


def delete_shopping_item(pool, user_id, arguments):
    item_id = arguments.get("item_id")
    with pool.connection() as conn:
        row = conn.execute(
            "DELETE FROM home_shopping_items WHERE id = %s AND user_id = %s RETURNING id",
            (item_id, user_id),
        ).fetchone()
    return {"deleted": bool(row), "id": item_id}


TOOL_HANDLERS = {
    "get_current_datetime": get_current_datetime,
    "add_family_event": add_family_event,
    "list_family_events": list_family_events,
    "delete_family_event": delete_family_event,
    "add_reminder": add_reminder,
    "list_reminders": list_reminders,
    "complete_reminder": complete_reminder,
    "delete_reminder": delete_reminder,
    "add_note": add_note,
    "list_notes": list_notes,
    "delete_note": delete_note,
    "add_shopping_item": add_shopping_item,
    "list_shopping_items": list_shopping_items,
    "check_off_shopping_item": check_off_shopping_item,
    "delete_shopping_item": delete_shopping_item,
}


def _reminder_dict(row):
    return {
        "id": row[0],
        "content": row[1],
        "due_at": row[2].isoformat() if row[2] else None,
        "done": row[3],
        "created_at": row[4].isoformat(),
    }


def _note_dict(row):
    return {"id": row[0], "content": row[1], "created_at": row[2].isoformat()}


def _shopping_item_dict(row):
    return {
        "id": row[0],
        "content": row[1],
        "quantity": row[2],
        "done": row[3],
        "created_at": row[4].isoformat(),
    }


def summary(pool, user_id):
    reminders = list_reminders(pool, user_id, {})["reminders"]
    items = list_shopping_items(pool, user_id, {})["items"]
    with pool.connection() as conn:
        note_rows = conn.execute(
            "SELECT id, content, created_at FROM home_notes WHERE user_id = %s "
            "ORDER BY created_at DESC LIMIT 5",
            (user_id,),
        ).fetchall()
    return {
        "calendar_events": list_family_events(pool, user_id)["events"],
        "reminders": reminders,
        "shopping_items": items,
        "recent_notes": [_note_dict(row) for row in note_rows],
    }


def _state_system_message(pool, user_id):
    state = summary(pool, user_id)
    lines = ["Trạng thái hiện tại của trợ lý gia đình cho người dùng này (JSON), dùng làm ngữ cảnh, đừng đọc nguyên JSON cho người dùng:"]
    lines.append(json.dumps(state, ensure_ascii=False))
    return {"role": "system", "content": "\n".join(lines)}


def run_agent(cfg, pool, user_id, messages, max_iterations=None):
    """Run the tool-calling agent loop. Returns (reply_text, tool_events)."""
    max_iterations = max_iterations or int(cfg.get("home_assistant_max_tool_iterations", 6))
    model = cfg.get("home_assistant_model") or cfg["model"]

    working_messages = [
        {"role": "system", "content": system_prompt()},
        _state_system_message(pool, user_id),
    ] + list(messages)

    handlers = {name: (lambda arguments, fn=fn: fn(pool, user_id, arguments)) for name, fn in TOOL_HANDLERS.items()}
    return llm_tools.run_tool_loop(cfg, model, working_messages, TOOLS, handlers, max_iterations)
