# Persona, Relationship Context, And Memory

## Personas

The admin manages multiple personas from the **Personas** panel in the sidebar.

Each persona has:

- `name`: display name for the admin UI.
- `description`: short admin note.
- `web_system_prompt`: used when this persona is selected for normal web chat.
- `voice_system_prompt`: used when this persona is selected for `/api/voice/chat`.
- private persona memories: notes, diary text, markdown/text/PDF chunks, or image memories with admin descriptions.

The admin chooses which persona is active for:

- **Web AI Chat uses**: normal web chat.
- **Voice Chat uses**: speaker/API voice sessions with `session_id`.

When `CHAT_PERSONA_ENABLED=1`, the persona applies to:

- normal web chat only

Voice chat always uses the active Voice Chat persona.

Good persona content usually includes:

- Identity: name, role, age/era if relevant, background, worldview.
- Voice: how the character speaks, humor level, directness, emotional warmth.
- Self-memory: facts the character knows about itself and should keep consistent.
- Boundaries: what it should refuse, avoid, or redirect.
- Interaction style: how it asks questions, how long answers should be, how it handles uncertainty.

Keep it concise. A half page to one page is usually better than a long biography because context space is limited.

For Voice Chat, prefer an even tighter persona because every answer should be easy to speak aloud.

## Persona Memory

Persona memory is different from per-user memory. It belongs to the character itself and is loaded only when that persona is active.

Use it for:

- diary entries
- stable personal history
- important relationships
- biographical facts
- admin-written image descriptions
- notes about voice, humor, values, and boundaries

The admin can add memory from the UI with text, `.txt`, `.md`, `.pdf`, or image files. Text/PDF files are split into chunks. Images are stored as image memory plus the admin's description; the current backend does not perform automatic OCR or vision captioning.

The number of persona memories added to the prompt is controlled by:

```env
PERSONA_MEMORY_LIMIT=12
```

## Identity Questions

DuyGPT treats persona as identity. For questions like:

- `bạn là ai`
- `chú là ai`
- `anh là ai`
- `tên bạn là gì`

it should answer only with:

- name
- job/role
- location if present in the persona

It should not volunteer family details unless the user asks about family or personal life.

Web chat identity comes from the Web AI Chat persona. Voice chat identity comes from the Voice Chat persona.

## Relationship Context

If a conversation says the current speaker is `Tùng` or `Giang`, DuyGPT treats that speaker as Duy's child for that session.

Rules:

- DuyGPT xưng `bố`.
- DuyGPT calls the user `con`, or by name (`Tùng`/`Giang`) when natural.
- DuyGPT must not call the child `bạn`.
- Wrong: `Bạn có thêm câu hỏi gì không con?`
- Correct: `Con có thêm câu hỏi gì không?`
- Correct: `Tùng có thêm câu hỏi gì không con?`

The backend also sanitizes final replies for this child context, so accidental `bạn ... con` phrasing is rewritten before it reaches the web UI or speaker device.

The child name is inferred from recent user messages, for example:

```text
Bố ơi con là Tùng.
Giang đây.
Tùng muốn hỏi bố...
```

## User Memory

For logged-in users, DuyGPT extracts durable facts from completed turns and stores them in `user_memories`.

Examples of useful memories:

- preferences
- stable personal details
- ongoing projects
- explicit `hãy nhớ rằng...` requests

DuyGPT skips secrets such as passwords, tokens, payment details, and one-off tasks.

Config:

```env
USER_MEMORY_ENABLED=1
USER_MEMORY_LIMIT=12
USER_MEMORY_EXTRACT_LIMIT=5
```

## Persona API

Login as admin:

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8383/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "abcd@123"}'
```

Read active legacy persona fields:

```bash
curl -s -b cookies.txt http://127.0.0.1:8383/api/admin/persona
```

Update active legacy persona fields:

```bash
curl -s -b cookies.txt -X PUT http://127.0.0.1:8383/api/admin/persona \
  -H "Content-Type: application/json" \
  --data-binary @persona.json
```

where `persona.json` is:

```json
{
  "web_system_prompt": "...persona for web chat...",
  "voice_system_prompt": "...persona for speaker sessions..."
}
```

Backward compatibility: `system_prompt` is still accepted as the web persona field, but new clients should send both `web_system_prompt` and `voice_system_prompt`.

New multi-persona API:

```bash
curl -s -b cookies.txt http://127.0.0.1:8383/api/admin/personas
```

Create persona:

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8383/api/admin/personas \
  -H "Content-Type: application/json" \
  -d '{"name":"Duy bản sao","description":"Bản sao cá nhân","web_system_prompt":"...","voice_system_prompt":"..."}'
```

Update persona:

```bash
curl -s -b cookies.txt -X PUT http://127.0.0.1:8383/api/admin/personas/2 \
  -H "Content-Type: application/json" \
  --data-binary @persona.json
```

Set active personas:

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8383/api/admin/personas/active \
  -H "Content-Type: application/json" \
  -d '{"web_persona_id":2,"voice_persona_id":2}'
```

Add persona memory:

```bash
curl -s -b cookies.txt -X POST http://127.0.0.1:8383/api/admin/personas/2/memories \
  -H "Content-Type: application/json" \
  -d '{"source_type":"note","content":"Duy thích trả lời ngắn, ấm áp, và hay xưng bố với Tùng/Giang."}'
```

## Context Window Caveat

Persona, relationship context, user memory, RAG context, recent conversation history, and the reply all share the model context window. A long persona can crowd out useful conversation history.

Prefer a compact, high-signal persona over a long biography.

Practical guidance:

- Web persona: about 500-1500 Vietnamese words is usually comfortable.
- Voice persona: about 300-800 Vietnamese words is usually better.
- Try not to exceed about 2000-3000 tokens unless the model context window is large and you intentionally want less chat history.
- Long persona text increases prompt processing time and KV-cache memory. On local Ollama models this can increase RAM/VRAM use and slow token generation.
