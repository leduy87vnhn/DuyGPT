# DuyGPT

DuyGPT is a local ChatGPT-style server and web UI for models already installed on this machine.

> Hướng dẫn build/chạy/sử dụng bằng tiếng Việt: [`HUONG_DAN.md`](HUONG_DAN.md)

It supports:

- Ollama or OpenAI-compatible chat backends
- user accounts and per-user chat history
- persona-based character behavior
- relationship context for Tùng/Giang speaker sessions
- per-user long-term memory
- RAG documents with PostgreSQL + pgvector
- speaker/device text API with `session_id`
- optional image generation backend
- family home assistant agent (reminders, notes, shopping list) with tool-calling, at `/home`
- customer requirement management (CRM) for multi-product consulting work, admin-only, at `/crm` — including versioned proposal docx/pptx attachments and a personal work-schedule/location API

## How to Run

### 1. Requirements

- Python 3.10+
- [Ollama](https://ollama.com) (or another OpenAI-compatible backend such as llama.cpp server, vLLM, LM Studio)
- PostgreSQL with the `pgvector` extension

### 2. Start the model runtime

```bash
ollama serve
ollama pull qwen2.5:32b-instruct-q4_K_M   # or any chat model you plan to use
ollama pull nomic-embed-text              # required for RAG embeddings
```

### 3. Set up PostgreSQL (one-time)

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib postgresql-18-pgvector
sudo -u postgres psql -c "CREATE ROLE duygpt LOGIN PASSWORD '<choose-a-password>';"
sudo -u postgres createdb -O duygpt duygpt
sudo -u postgres psql -d duygpt -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Adjust `postgresql-18-pgvector` if your installed Postgres major version differs.

### 4. Configure

```bash
cp .env.example .env
```

Edit `.env` and at minimum set:

- `PGPASSWORD` — the password chosen above
- `MODEL` — one of your installed Ollama models
- `DEVICE_API_KEY` — if speaker/device endpoints will be used
- `REQUIRE_LOGIN=1` — before exposing the service outside localhost

### 5. Start DuyGPT

```bash
sudo wg-quick up wg0
./scripts/start.sh
```

This creates a `.venv` if missing, installs `requirements.txt`, and runs `app.py`. No manual `pip install` step is needed.

Open:

```text
http://127.0.0.1:8383
```

Default admin login is `admin` / `abcd@123` (from `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`) — change it before exposing the service publicly.

See [Setup](docs/setup.md) for more detail and [Configuration](docs/configuration.md) for all `.env` options.

## Current Runtime

```text
DuyGPT web/API: http://127.0.0.1:8383
HTTPS helper:   https://127.0.0.1:8443
Image backend:  disabled by default
```

Important current `.env` choices:

```env
PORT=8383
REQUIRE_LOGIN=1
IMAGE_PROVIDER=disabled
CHAT_PERSONA_ENABLED=1
USER_MEMORY_ENABLED=1
```

## Documents

- [Setup](docs/setup.md)
- [Configuration](docs/configuration.md)
- [Public Access](docs/public-access.md)
- [Speaker Device API](docs/speaker-api.md)
- [Raspberry Pi Speaker Edge Device](docs/raspberry-pi-speaker.md)
- [Persona, Relationship Context, And Memory](docs/persona-memory.md)
- [Image Generation](docs/image-generation.md)
- [Family Home Assistant (ben_homeassistant)](docs/home-assistant.md)
- [Customer Requirement Management (CRM)](docs/crm.md)

## Speaker API Short Version

For a device that just records audio and wants everything else (transcription,
picking home/work/chatgpt, the reply) handled server-side:

```http
POST /api/voice/assistant
Content-Type: application/json
X-Device-Key: <DEVICE_API_KEY>
```

Body:

```json
{
  "session_id": "speaker-boot-001",
  "filename": "clip.wav",
  "audio_base64": "<base64-encoded audio bytes>"
}
```

For a device with its own speech recognition that only wants a chat reply from
the main persona (no home/work routing):

```http
POST /api/voice/chat
Content-Type: application/json
X-Device-Key: <DEVICE_API_KEY>
```

Body:

```json
{
  "session_id": "speaker-boot-001",
  "text": "Bố ơi con là Tùng. Hôm nay bố đang làm gì?"
}
```

See [Speaker Device API](docs/speaker-api.md) for the full contract.
