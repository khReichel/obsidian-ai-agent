# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Install dependencies (no requirements.txt — install manually):
```bash
pip install groq pyyaml chromadb python-dotenv
```

Create `.env` from `.env.example` and set:
- `GROQ_API_KEY` — required
- `VAULT_PATH` — path to your Obsidian vault
- `DB_PATH` — SQLite DB path (default: `obsidian_agent.db`)
- `DEFAULT_GROQ_MODEL` — LLM model (default: `llama-3.1-8b-instant`)
- `EMBEDDING_MODEL` — embedding model (default: `llama-3-8b-8192`)

## Commands

```bash
# Run the agent
python agent.py

# Run unit tests
python -m unittest test_utils.py
```

## Architecture

Job-queue orchestration: `agent.py` scans the vault, enqueues work into a SQLite `jobs` table, then processes jobs sequentially (max 10 per run).

**Execution flow:**
1. `init_db()` — create SQLite tables (`notes`, `jobs`) if missing
2. `scan_vault()` — walk `VAULT_PATH`, SHA256-hash each `.md` file, insert new notes or mark changed ones as pending
3. `process_pending_jobs()` — dequeue jobs and dispatch by `job_type`:
   - `full_index`: call Groq LLM → write AI-generated summary/tags/keywords back into YAML frontmatter, then enqueue an `embedding` job
   - `embedding`: chunk text (400-token chunks, 50-token overlap), embed via Groq, persist to ChromaDB under `chroma_store/`
   - `rag_query`: semantic retrieval → LLM synthesis → write a new result note into the vault
   - `auto_link`: find notes with cosine similarity ≥ 0.75, inject links into frontmatter

**Module responsibilities:**
- `agent.py` — orchestrator, vault scan, writeback to markdown
- `core.py` — SQLite connection, schema, Groq client wrapper
- `config.py` — `.env` loading
- `utils.py` — SHA256 hashing, YAML frontmatter extraction, markdown cleaning
- `services/embedding_service.py` — ChromaDB client, chunking, Groq embedding calls
- `services/rag_service.py` — RAG pipeline, similarity search, tag improvement

**Key design constraints:**
- Groq API calls expect JSON-only responses (strict prompt format); parse failures should be treated as job errors.
- Hash-based change detection (`notes.hash_content`) prevents redundant AI calls — only changed files get reprocessed.
- ChromaDB persists to `chroma_store/` (gitignored); deleting it forces a full re-embed on next run.
- `writeback_to_markdown()` reconstructs the full file: new YAML frontmatter block + original body — be careful not to corrupt the body when editing this function.
