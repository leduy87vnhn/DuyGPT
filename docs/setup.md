# Setup

## Start Model Runtime

For Ollama:

```bash
ollama serve
ollama list
ollama pull nomic-embed-text
```

## PostgreSQL

One-time setup:

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib postgresql-18-pgvector
sudo -u postgres psql -c "CREATE ROLE duygpt LOGIN PASSWORD '<choose-a-password>';"
sudo -u postgres createdb -O duygpt duygpt
sudo -u postgres psql -d duygpt -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Adjust `postgresql-18-pgvector` if your Postgres major version differs.

## Configure

```bash
cp .env.example .env
```

Edit `.env`:

- set `PGPASSWORD`
- set `MODEL`
- for public deployment, set `REQUIRE_LOGIN=1`
- set `DEVICE_API_KEY` for speaker/device calls

## Start

```bash
./scripts/start.sh
```

Open:

```text
http://127.0.0.1:8383
```

LAN example:

```text
http://192.168.13.105:8383
```

## Admin Account

On first startup, DuyGPT seeds the single admin account from:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=abcd@123
```

Change the password before exposing the service publicly.
