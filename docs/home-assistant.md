# Family Home Assistant (ben_homeassistant)

An on-prem household agent built into DuyGPT: reminders, notes, and a shared shopping list, driven by a tool-calling chat agent. It runs on the exact same LLM (Ollama/OpenAI-compatible) and Postgres database already configured for DuyGPT — no extra service, no extra port.

It is **not** an integration with the Home Assistant smart-home platform. There is currently no real device control (lights, switches, sensors). The module is structured so that can be added later as another tool without changing the chat/agent plumbing.

## Access

```text
http://<duygpt-host>:8383/home
```

Same login/session as the main DuyGPT chat (cookie-based). A user must be logged in; each user's reminders/notes/shopping items are private to their account except the shopping list, which every logged-in household member can add to and check off (it is scoped per-account today, same as the rest — see "Scoping" below if you want it fully shared).

## What the agent can do

The assistant has these tools available in every turn:

| Tool | Purpose |
| --- | --- |
| `get_current_datetime` | Reads server date/time, used to resolve "hôm nay", "ngày mai", etc. before setting a reminder time. |
| `add_reminder` / `list_reminders` / `complete_reminder` / `delete_reminder` | Manage nhắc việc. |
| `add_note` / `list_notes` / `delete_note` | Manage ghi chú. |
| `add_shopping_item` / `list_shopping_items` / `check_off_shopping_item` / `delete_shopping_item` | Manage danh sách mua sắm. |

Example prompts:

- "Nhắc tôi đổ rác lúc 8 giờ tối nay"
- "Có gì cần mua không?"
- "Thêm sữa và trứng vào danh sách mua sắm"
- "Ghi chú: wifi khách là familyguest2026"

The sidebar (reminders / shopping / notes panels) also has quick-add forms and checkboxes that hit the same underlying data directly, without going through the LLM — useful for fast entry or when you just want a plain to-do list.

## API

All endpoints require a logged-in session (cookie), same as `/api/conversations`.

```http
POST /api/home/chat
{"message": "...", "conversation_id": 12}
```

```json
{"reply": "...", "conversation_id": 12, "tool_calls": [{"name": "add_reminder", "arguments": {"content": "đổ rác", "due_at": "2026-08-23T20:00:00"}}]}
```

Conversation history for this module is stored in the same `conversations`/`messages` tables as normal chat, tagged with `kind = 'home'`, and listed separately via:

```http
GET /api/conversations?kind=home
GET /api/conversations/<id>/messages
```

Direct CRUD (used by the sidebar UI, bypassing the LLM):

```http
POST   /api/home/reminders            {"content": "...", "due_at": "2026-08-23T20:00:00"}
PUT    /api/home/reminders/<id>       (marks done)
DELETE /api/home/reminders/<id>

POST   /api/home/notes                {"content": "..."}
DELETE /api/home/notes/<id>

POST   /api/home/shopping             {"content": "...", "quantity": "2 hộp"}
PUT    /api/home/shopping/<id>        (marks purchased)
DELETE /api/home/shopping/<id>

GET    /api/home/summary              -> open reminders, open shopping items, last 5 notes
```

## Configuration

```env
HOME_ASSISTANT_ENABLED=1
HOME_ASSISTANT_MODEL=
HOME_ASSISTANT_MAX_TOOL_ITERATIONS=6
HOME_ASSISTANT_CONTEXT_MESSAGES=20
HOME_ASSISTANT_SYSTEM_PROMPT=
```

`HOME_ASSISTANT_MODEL` lets you point this module at a different, smaller model than the main chat model — useful if your GPU is tight (see the sizing notes below) and you want quicker responses for a simple to-do agent than for the main persona chat. Leave empty to reuse `MODEL`.

Tool calling requires a model that supports it. Qwen2.5-Instruct models served through Ollama support tool calling out of the box. If you swap to a model without tool-calling support, the agent will just never call tools and will answer in plain text instead (no crash, degraded functionality).

## Scoping and multi-user households

Reminders, notes, and shopping items are all stored per `user_id`, same as DuyGPT's existing per-user memory. If you want a fully shared household shopping list/reminders visible to every account instead of per-user, that would need a small schema change (e.g. a `household_id` instead of `user_id`) — ask if you want that switched.

## Roadmap / not yet built

- Real Home Assistant (smart-home platform) integration — device control, sensors. The tool-calling agent loop is already generic (`home_assistant.py: TOOLS` / `TOOL_HANDLERS`), so adding HA-backed tools later is additive.
- Voice access via the Raspberry Pi speaker pipeline (`/api/voice/chat`) is not wired to this module yet; today voice goes to the main chat persona. Routing voice sessions into the home-assistant agent instead is a small follow-up once the Pi hardware is in place.
