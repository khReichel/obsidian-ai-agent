# Obsidian AI Agent

Automatically analyzes and tags Obsidian notes using AI, creates semantic embeddings, and answers questions about your entire vault (RAG). Embeddings run fully locally — only LLM calls go to an external API.

---

## Architecture

```mermaid
flowchart TD
    V["📁 Obsidian Vault\n(.md files)"]
    WCH["⏱️ watcher.py\nevery 30 min"]

    subgraph agent["agent.py — Orchestrator"]
        S["Vault Scanner\nSHA256 Hashing"]
        W["Job Worker"]
    end

    subgraph services["Services"]
        LLM["☁️ LLM API\n(Groq / Gemini / Anthropic / OpenRouter)\nSummary · Tags · Keywords"]
        EMB["🖥️ sentence-transformers\n(local, offline)\nEmbeddings"]
    end

    subgraph storage["Persistence"]
        DB[("SQLite\nnotes + jobs")]
        CHROMA[("ChromaDB\nchroma_store/")]
    end

    Q["query.py\nRAG CLI"]
    ANS["💬 Answer\nin terminal"]

    WCH -->|"triggers automatically"| agent
    V -->|"new / changed"| S
    S -->|"enqueue job"| DB
    DB -->|"pending jobs"| W
    W -->|"full_index"| LLM
    LLM -->|"write frontmatter\nback to vault"| V
    W -->|"embedding"| EMB
    EMB -->|"store vectors"| CHROMA
    CHROMA -->|"semantic search"| Q
    Q -->|"context + question"| LLM
    LLM --> ANS
```

---

## Quick Start with Docker (recommended)

### 1. Clone the repository

```bash
git clone <repo-url>
cd obsidianAutomation
```

### 2. Create `.env`

Copy `.env.example` to `.env` and fill in your values:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...          # https://console.groq.com → API Keys

HOST_VAULT_PATH=/path/to/your/ObsidianVault
```

> `VAULT_PATH` and `DB_PATH` are set automatically by Docker — you can omit or leave those lines as-is.

### 3. Build the image (once, ~5 minutes)

```bash
docker compose build
```

The embedding model (~400 MB) is baked into the image so the first run starts immediately.

### 4. Start the watcher (recommended)

```bash
docker compose up watcher -d
```

The watcher runs continuously in the background and re-indexes the vault every 30 minutes. New notes are picked up as soon as you save them in Obsidian — no manual action needed.

**Adjust interval** — in `.env`:
```env
WATCH_INTERVAL_MINUTES=15
```

**View logs:**
```bash
docker compose logs watcher -f
```

**Stop watcher:**
```bash
docker compose stop watcher
```

> Alternatively: `docker compose up agent` for a one-off run without continuous operation.

### 5. Query the vault

```bash
# Single question
docker compose run --rm query python query.py "What are my key insights on productivity?"

# Interactive mode (multiple questions)
docker compose run --rm --profile query query
```

---

## Installation without Docker (Python)

### Requirements

- Python 3.11+
- API key for one of the supported providers

### Install dependencies

```bash
pip install -r requirements.txt
```

### Create `.env`

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
DEFAULT_MODEL=llama-3.1-8b-instant
VAULT_PATH=/path/to/your/vault
DB_PATH=obsidian_agent.db
```

### Run

```bash
# Index the vault
python agent.py

# Query the vault
python query.py "Your question"
python query.py              # interactive mode
```

---

## LLM Providers

| Provider | `LLM_PROVIDER` | Recommended Model | Cost |
|---|---|---|---|
| **Groq** | `groq` | `llama-3.1-8b-instant` | free (30 req/min) |
| **Groq** | `groq` | `llama-3.3-70b-versatile` | free, slower |
| **Google Gemini** | `gemini` | `gemini-2.0-flash` | free (1500 req/day) |
| **Anthropic** | `anthropic` | `claude-haiku-4-5` | ~€1–2/month |
| **OpenRouter** | `openrouter` | `meta-llama/llama-3.1-8b-instruct` | ~$0/month |

API Keys:
- Groq: [console.groq.com](https://console.groq.com)
- Gemini: [aistudio.google.com](https://aistudio.google.com)
- Anthropic: [console.anthropic.com](https://console.anthropic.com)
- OpenRouter: [openrouter.ai](https://openrouter.ai)

---

## What the agent does

| Feature | Description |
|---|---|
| **Auto-Tagging** | Analyzes new/changed notes and writes `ai_summary`, `ai_tags`, `ai_keywords` into the YAML frontmatter automatically |
| **Embeddings** | Splits notes into chunks and creates local vectors offline (~400 MB model, cached once) |
| **Auto-Linking** | Finds semantically similar notes (cosine similarity ≥ 0.75), writes `[[Wiki-Links]]` into the body (`## Related Notes`) and frontmatter (`ai_related_notes`) — Obsidian displays them automatically in the graph |
| **RAG Query** | Answers questions about the entire vault via `query.py` — semantic search + AI synthesis |
| **Processing order** | Per note: `full_index` → embeddings → `auto_link` — all automatic in one pass |
| **Manual changes** | Your own `tags:` and `[[Links]]` in the body are preserved; only `ai_*` fields are managed by the agent |
| **Change detection** | SHA256 hashing prevents unnecessary AI calls for unchanged notes |
| **Rate-limit retry** | Automatically waits on 429 errors and retries with exponential backoff |
| **Auto-Watcher** | Runs continuously in the background, indexes new notes automatically at a configurable interval |

---

## Project Structure

```
agent.py                  Orchestrator: vault scan + job worker
watcher.py                Continuous operation: runs agent.py at a configurable interval
query.py                  RAG CLI: query the vault interactively
core.py                   Provider dispatch, DB connection, call_ai()
config.py                 .env loading, provider validation
utils.py                  Markdown parsing, SHA256 hashing
services/
  embedding_service.py    Local embeddings + ChromaDB
  rag_service.py          RAG pipeline, similarity search
Dockerfile                Container build
docker-compose.yml        agent / watcher / query as services
requirements.txt          Python dependencies
```

---

## Tests

```bash
python -m unittest test_utils.py
```
