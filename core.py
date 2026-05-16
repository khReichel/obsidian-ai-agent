import sqlite3
import json
import time
import re
from config import (
    DB_PATH, LLM_PROVIDER, DEFAULT_MODEL,
    GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY,
)

# ---------------------------------------------------------------------------
# Provider-Setup
# ---------------------------------------------------------------------------

if LLM_PROVIDER == "gemini":
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    _gemini_model = genai.GenerativeModel(
        model_name=DEFAULT_MODEL,
        system_instruction="Du gibst ausschließlich JSON zurück. Keine Erklärungen.",
    )

elif LLM_PROVIDER == "anthropic":
    import anthropic as _anthropic_sdk
    _anthropic_client = _anthropic_sdk.Anthropic(api_key=ANTHROPIC_API_KEY)

elif LLM_PROVIDER == "openrouter":
    from openai import OpenAI as _OpenAI
    _openrouter_client = _OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )

elif LLM_PROVIDER == "groq":
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=GROQ_API_KEY)

# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------

def connect_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = connect_db()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        title TEXT,
        hash_content TEXT,
        last_modified_fs DATETIME,
        last_processed_ai DATETIME,
        embedding_version INTEGER DEFAULT 0,
        ai_index_mode TEXT DEFAULT 'full',
        status TEXT DEFAULT 'pending'
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        job_type TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        FOREIGN KEY(note_id) REFERENCES notes(id)
    );
    """)
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict:
    """Versucht JSON zu parsen; bei Fehler wird der erste {...}-Block extrahiert."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw[start:end + 1])
        raise


def _call_gemini(prompt: str, json_mode: bool) -> str:
    model = _gemini_model if json_mode else genai.GenerativeModel(model_name=DEFAULT_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


def _call_anthropic(prompt: str, json_mode: bool) -> str:
    system = "Du gibst ausschließlich JSON zurück. Keine Erklärungen." if json_mode else "Du bist ein präziser, kontextbasierter Assistent."
    message = _anthropic_client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_groq(prompt: str, json_mode: bool) -> str:
    system = "Du gibst ausschließlich JSON zurück. Keine Erklärungen." if json_mode else "Du bist ein präziser, kontextbasierter Assistent."
    max_retries = 5
    wait = 10
    for attempt in range(max_retries):
        try:
            response = _groq_client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=2048,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                match = re.search(r"Please try again in ([\d.]+)s", err_str)
                wait = int(float(match.group(1))) + 2 if match else wait
                if attempt < max_retries - 1:
                    print(f"[GROQ] Rate limited. Warte {wait}s (Versuch {attempt + 1}/{max_retries})…")
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                else:
                    raise
            else:
                raise


def _call_openrouter(prompt: str, json_mode: bool) -> str:
    system = "Du gibst ausschließlich JSON zurück. Keine Erklärungen." if json_mode else "Du bist ein präziser, kontextbasierter Assistent."
    max_retries = 5
    wait = 30  # seconds, default fallback
    for attempt in range(max_retries):
        try:
            response = _openrouter_client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=2048,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                try:
                    match = re.search(r"'retry_after_seconds':\s*([\d.]+)", err_str)
                    wait = int(float(match.group(1))) + 2 if match else wait
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    print(f"[OPENROUTER] Rate limited (429). Warte {wait}s (Versuch {attempt + 1}/{max_retries})…")
                    time.sleep(wait)
                    wait = min(wait * 2, 120)  # exponential backoff, max 2min
                else:
                    raise
            else:
                raise


_DISPATCH = {
    "gemini":     _call_gemini,
    "anthropic":  _call_anthropic,
    "openrouter": _call_openrouter,
    "groq":       _call_groq,
}

# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def call_ai(prompt: str) -> dict | None:
    """LLM-Aufruf mit JSON-Antwort. Gibt ein dict zurück oder None bei Fehler."""
    try:
        raw = _DISPATCH[LLM_PROVIDER](prompt, json_mode=True)
        return _parse_json(raw)
    except Exception as e:
        print(f"[{LLM_PROVIDER.upper()} Error] {e}")
        return None


def call_ai_text(prompt: str) -> str | None:
    """LLM-Aufruf mit Freitext-Antwort (z. B. für RAG). Gibt str zurück oder None bei Fehler."""
    try:
        return _DISPATCH[LLM_PROVIDER](prompt, json_mode=False)
    except Exception as e:
        print(f"[{LLM_PROVIDER.upper()} Error] {e}")
        return None
