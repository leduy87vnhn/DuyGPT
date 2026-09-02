# Configuration

Main config lives in `.env`.

## Server

| Name | Default | Description |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Web server host |
| `PORT` | `8383` | DuyGPT web/API port |
| `SSL_CERT_FILE` / `SSL_KEY_FILE` | empty | Optional HTTPS certificate/key paths |
| `HTTPS_HOST` / `HTTPS_PORT` | `HOST` / `8443` | Optional HTTPS listener |

## Chat Model

| Name | Default | Description |
| --- | --- | --- |
| `PROVIDER` | `ollama` | `ollama` or `openai` |
| `MODEL` | `llama3.1` | Default model |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `OPENAI_BASE_URL` | `http://127.0.0.1:8000/v1` | OpenAI-compatible API base URL |
| `OPENAI_API_KEY` | empty | API key if needed |
| `TEMPERATURE` | `0.7` | Default generation temperature |
| `OLLAMA_NUM_CTX` | empty | Ollama context window override |
| `MAX_TOKENS` | empty | Optional max token limit for OpenAI-compatible servers |

## Public Access

| Name | Default | Description |
| --- | --- | --- |
| `REQUIRE_LOGIN` | `0` | Set to `1` for public deployments |
| `DISABLE_REGISTRATION` | `0` | Set to `1` to close self-registration |
| `DEVICE_API_KEY` | empty | Shared key for speaker/device API calls via `X-Device-Key` |
| `CORS_ORIGIN` | empty | Optional trusted browser origin |

## Database

| Name | Default | Description |
| --- | --- | --- |
| `PGHOST` / `PGPORT` | `127.0.0.1` / `5432` | PostgreSQL host/port |
| `PGDATABASE` / `PGUSER` / `PGPASSWORD` | `duygpt` / `duygpt` / empty | PostgreSQL database/user/password |

## Accounts

| Name | Default | Description |
| --- | --- | --- |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `abcd@123` | Seed values for the single admin account |
| `SESSION_TTL_DAYS` | `30` | Login session lifetime |

## History, Persona, Memory

| Name | Default | Description |
| --- | --- | --- |
| `CHAT_HISTORY_LIMIT` | `50` | Max stored messages per conversation |
| `CHAT_PERSONA_ENABLED` | `1` | Apply persona to normal web chat |
| `USER_MEMORY_ENABLED` | `1` | Enable per-user long-term memory |
| `USER_MEMORY_LIMIT` | `12` | Recent memories injected into prompt |
| `USER_MEMORY_EXTRACT_LIMIT` | `5` | Max memories extracted from one completed turn |
| `DEFAULT_PERSONA_PROMPT` | built-in default | Seeded once into DB |

## RAG

| Name | Default | Description |
| --- | --- | --- |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `nomic-embed-text` / `768` | Ollama embedding model and vector dimension |
| `RAG_TOP_K` | `4` | Retrieved chunks per chat turn |
| `MAX_UPLOAD_MB` | `20` | Max admin document upload size |

## Speaker / Voice

| Name | Default | Description |
| --- | --- | --- |
| `VOICE_DEVICE_USERNAME` | `voice-assistant` | Internal account for speaker sessions |
| `VOICE_CONTEXT_MESSAGES` | `10` | Recent messages replayed per speaker session |
| `STT_MODEL` | `small` | faster-whisper model for `/api/voice/transcribe` |
| `STT_DEVICE` | `auto` | `auto`, `cuda`, or `cpu` |
| `STT_COMPUTE_TYPE` | `default` | faster-whisper compute type |
| `STT_LANGUAGE` | `vi` | Force transcription language; empty auto-detects |
| `STT_REFINE_WITH_LLM` | `1` | Refine transcription with local LLM |

## Image Generation

See [Image Generation](image-generation.md).
