# Speaker Device API

APIs for a voice device (Raspberry Pi speaker, etc.) that talks to DuyGPT. There are four endpoints, from simplest device to most capable server:

| Endpoint | Device sends | Device does | Use when |
| --- | --- | --- | --- |
| **`POST /api/voice/assistant`** (recommended) | raw audio clip | plays back `text` (or the optional returned audio) | Device just records on hot-word/silence and wants everything else handled server-side, including which assistant should answer. |
| `POST /api/voice/chat` | recognized text | its own STT, then plays back `text` via TTS | Device already has its own speech recognizer and only wants a chat reply from the main persona (no home/work auto-routing). |
| `POST /api/voice/transcribe` | raw audio clip | its own reply/TTS pipeline | Device wants text only, no reply generation at all. |
| `POST /api/voice/speak` | text | plays back the returned audio | Device (or test client) can't do its own TTS and just wants an MP3 for arbitrary text. |

All four require `X-Device-Key` when `REQUIRE_LOGIN=1`:

```env
DEVICE_API_KEY=<secret>
```

**On TTS placement**: a Raspberry Pi speaker is expected to do TTS itself, locally (`espeak` or `edge-tts` on-device — see [Raspberry Pi Speaker Edge Device](raspberry-pi-speaker.md)), and only needs `text` back. `/api/voice/speak` and `/api/voice/assistant`'s `want_audio` option exist for anything that *can't* do that (a browser test client, a device with no local TTS) — they call the same `edge-tts` service DuyGPT uses server-side, which needs internet. This is the one part of the voice pipeline that isn't on-prem; everything else (STT, routing, the assistants) runs locally.

**Replaces `ai-voice-server`**: the separate `ai-projects/ai-voice-server` FastAPI service (audio in → its own Whisper → raw Ollama call, no persona/memory/RAG/routing → edge-tts → audio out) is now fully covered by `/api/voice/assistant` with `"want_audio": true` — same STT engine, plus persona/memory/RAG/home/work routing that the standalone server never had, plus the same `edge-tts` output. One service (DuyGPT) instead of two; `ai-voice-server` can be retired once you've confirmed the new endpoint covers your use case.

## `POST /api/voice/assistant` — record → recognize → route → reply

This is the endpoint for the "device just records, server does everything" flow: the device records on hot-word or silence-based cutoff, POSTs the audio clip, and DuyGPT:

1. Transcribes it (`faster-whisper`, same engine as `/api/voice/transcribe`) and cleans up the transcript.
2. Classifies which assistant the utterance is for — **Trợ Lý Gia Đình** (`home`), **Trợ Lý Công Việc** (`work`), or the main **ChatGPT** persona (`chatgpt`) as the fallback when it doesn't clearly match either.
3. Runs that assistant (with its tools — reminders/notes/shopping for home, schedule/meetings for work) and gets a reply.
4. Returns the reply text for the device to speak. DuyGPT does not do TTS itself — the device is responsible for turning `text` into audio.

### Request

```http
POST http://<duygpt-host>:8383/api/voice/assistant
Content-Type: application/json
X-Device-Key: <DEVICE_API_KEY>
```

```json
{
  "session_id": "speaker-boot-2026-08-31T10:30:00Z",
  "filename": "clip.wav",
  "audio_base64": "<base64-encoded audio bytes>"
}
```

| Field | Required | Description |
| --- | --- | --- |
| `audio_base64` | yes | Base64-encoded audio clip (wav/mp3/etc. — anything `faster-whisper`/ffmpeg can decode). |
| `filename` | no | Used only to guess the file extension; default `audio.wav`. |
| `session_id` | no | Same session-memory mechanism as `/api/voice/chat` — reuse it across utterances from one boot/session so the assistant remembers recent turns. Omit for a one-off, memory-less request. |
| `want_audio` | no | If `true`, the response also includes the reply as MP3 (base64) — for a device/client with no TTS of its own. Default `false` (text only, cheaper/faster). |

Size limit: `MAX_UPLOAD_MB` (same as other upload endpoints, default 20MB).

### Response

```json
{
  "text": "Đã nhắc bạn đổ rác lúc 7 giờ tối nay.",
  "transcript": "Nhắc tôi đổ rác lúc 7 giờ tối nay",
  "target": "home",
  "conversation_id": 60,
  "session_id": "speaker-boot-2026-08-31T10:30:00Z"
}
```

| Field | Description |
| --- | --- |
| `text` | The reply — speak this through TTS. |
| `transcript` | What DuyGPT understood the user to say (useful for logging/debugging on the device). |
| `target` | Which assistant handled it: `home`, `work`, or `chatgpt`. |
| `conversation_id`, `session_id` | Same session-memory fields as `/api/voice/chat`. |
| `reply_audio_base64`, `reply_audio_format` | Only present when the request had `"want_audio": true` — base64 MP3 of `text`, ready to decode and play. |
| `reply_audio_error` | Only present if `want_audio` was requested but TTS failed (e.g. no internet) — `text` is still valid, just play it via the device's own TTS instead. |

### How routing works

Routing is a small, fast LLM call (thinking mode forced off regardless of `OLLAMA_THINK`, so it stays cheap) that reads the transcript and picks one target:

- **`home`** — reminders, notes, shopping list, family events. Runs the same agent as [`/home`](home-assistant.md), with the same tools.
- **`work`** — work schedule, meetings, customer visit location. Runs the same agent as `/work`.
- **`chatgpt`** — anything else, or anything ambiguous. Falls back to the main chat persona — same logic as `/api/voice/chat` (Voice Chat persona, Tùng/Giang relationship handling, per-user memory, RAG).

There is no confirmation step before an action (e.g. saying "nhắc tôi mua sữa" immediately creates the reminder) — the tools available to `home`/`work` here are the same ones described in [home-assistant.md](home-assistant.md) and the work assistant's own tool set.

Session memory (`session_id` → conversation) is shared across all three targets: if a session switches from a home-flavored utterance to a work-flavored one, the work assistant still sees the prior turns as context.

### Example

```bash
HOST=http://10.0.50.2:8383
DEVICE_KEY=<DEVICE_API_KEY>
SESSION_ID=speaker-demo-001

curl -s "$HOST/api/voice/assistant" \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: $DEVICE_KEY" \
  -d "{\"session_id\":\"$SESSION_ID\",\"filename\":\"clip.wav\",\"audio_base64\":\"$(base64 -w0 clip.wav)\"}"
```

### Error cases

```json
{"error": "authentication required"}
```

```json
{"error": "audio_base64 must not be empty"}
```

```json
{"error": "no speech detected"}
```

(returned when the transcript comes back empty — e.g. the clip was pure silence/noise)

## `POST /api/voice/chat` — text in, main persona reply out

Use this when a speaker device already has text from speech recognition and needs DuyGPT to reply with text for TTS. Unlike `/api/voice/assistant`, this always answers with the main chat persona — it does not route to the home/work assistants.

### Endpoint

```http
POST http://<duygpt-host>:8383/api/voice/chat
Content-Type: application/json
X-Device-Key: <DEVICE_API_KEY>
```

### Request

```json
{
  "session_id": "speaker-boot-2026-07-11T10:30:00Z",
  "text": "Bố ơi con là Tùng. Hôm nay bố đang làm gì?"
}
```

Required fields:

| Field | Description |
| --- | --- |
| `session_id` | Stable ID for one speaker work session. Create a new value each time the speaker boots or starts a fresh session. Reuse it for every utterance in that same session. |
| `text` | The user's utterance as text. The speaker performs speech recognition itself, or sends text from another recognizer. |

Optional fields:

| Field | Description |
| --- | --- |
| `provider` | Override chat provider, normally omit |
| `model` | Override model, normally omit |
| `temperature` | Override response temperature, normally omit |

### Response

```json
{
  "text": "Bố đang ở đây với con. Con muốn hỏi bố chuyện gì?",
  "conversation_id": 42,
  "session_id": "speaker-boot-2026-07-11T10:30:00Z"
}
```

The speaker should speak `text` through TTS.

## Session Memory

Both `/api/voice/assistant` and `/api/voice/chat` map each `session_id` to one internal conversation. If the speaker sends the same `session_id`, the server replays recent turns from that session using `VOICE_CONTEXT_MESSAGES`.

Example:

```bash
HOST=http://10.0.50.2:8383
DEVICE_KEY=<DEVICE_API_KEY>
SESSION_ID=speaker-demo-001

curl -s "$HOST/api/voice/chat" \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: $DEVICE_KEY" \
  -d "{\"session_id\":\"$SESSION_ID\",\"text\":\"Bố ơi con là Tùng. Con thích màu xanh dương.\"}"

curl -s "$HOST/api/voice/chat" \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: $DEVICE_KEY" \
  -d "{\"session_id\":\"$SESSION_ID\",\"text\":\"Con vừa nói con thích màu gì?\"}"
```

The second answer should remember the earlier turn because the `session_id` is the same.

## Voice Persona And Relationships

The `chatgpt` fallback (both `/api/voice/assistant` and `/api/voice/chat`) uses the **Voice Chat persona** configured by the admin in the web UI. This is separate from the normal Web AI Chat persona.

It also keeps relationship context:

- If the user says they are `Tùng` or `Giang`, DuyGPT treats the speaker as Duy's child for that session.
- DuyGPT must xưng `bố`.
- DuyGPT must call the user `con`, or by name (`Tùng`/`Giang`) when natural.
- DuyGPT must not call the child `bạn`.
- Wrong: `Bạn có thêm câu hỏi gì không con?`
- Correct: `Con có thêm câu hỏi gì không?`
- Correct: `Tùng có thêm câu hỏi gì không con?`

DuyGPT also sanitizes final replies for this context before returning JSON to the speaker. This relationship handling does not apply to the `home`/`work` targets (those assistants talk business, not "con ơi").

## Error Cases (`/api/voice/chat`)

Missing or wrong device key:

```json
{"error": "authentication required"}
```

Missing text:

```json
{"error": "text must not be empty"}
```

Too-long session id:

```json
{"error": "session_id must be 120 characters or fewer"}
```

## `POST /api/voice/transcribe` — audio in, text only

For a device that wants text only and will generate/apply its own reply logic:

```http
POST /api/voice/transcribe
```

with:

```json
{
  "audio_base64": "<base64-encoded audio bytes>",
  "filename": "clip.wav"
}
```

Response:

```json
{"text": "<cleaned-up transcript>", "raw_text": "<transcript before LLM clean-up, only present if different>"}
```

## `POST /api/voice/speak` — text in, audio out

Pure TTS, for a client that can't synthesize speech itself (e.g. a browser test page). Uses `edge-tts` — needs internet.

```http
POST /api/voice/speak
Content-Type: application/json
X-Device-Key: <DEVICE_API_KEY>
```

```json
{
  "text": "Xin chào, đây là bài kiểm tra giọng nói.",
  "voice": "vi-VN-HoaiMyNeural"
}
```

| Field | Required | Description |
| --- | --- | --- |
| `text` | yes | Text to speak. |
| `voice` | no | An `edge-tts` voice name. Defaults to `EDGE_TTS_VOICE` (`.env`, itself defaulting to `vi-VN-HoaiMyNeural`). Run `edge-tts --list-voices` on the server to see other options (e.g. `vi-VN-NamMinhNeural` for a male voice). |

Response: raw `audio/mpeg` (MP3) bytes — not JSON. Play/save the response body directly.

```bash
curl -s "$HOST/api/voice/speak" \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: $DEVICE_KEY" \
  -d '{"text":"Xin chào"}' \
  -o reply.mp3
```

Error responses (JSON, on failure):

```json
{"error": "text must not be empty"}
```

```json
{"error": "<edge-tts/network failure detail>"}
```
