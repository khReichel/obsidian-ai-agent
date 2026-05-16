import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()  # gemini | anthropic | openrouter | groq

GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")

VAULT_PATH    = os.getenv("VAULT_PATH")
DB_PATH       = os.getenv("DB_PATH", "obsidian_agent.db")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-2.0-flash")

_required = {
    "gemini":      ("GEMINI_API_KEY",     GEMINI_API_KEY),
    "anthropic":   ("ANTHROPIC_API_KEY",  ANTHROPIC_API_KEY),
    "openrouter":  ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
    "groq":        ("GROQ_API_KEY",       GROQ_API_KEY),
}

if LLM_PROVIDER not in _required:
    raise ValueError(f"Unbekannter LLM_PROVIDER: '{LLM_PROVIDER}'. Erlaubt: gemini, anthropic, openrouter, groq")

_key_name, _key_value = _required[LLM_PROVIDER]
if not _key_value:
    raise ValueError(f"{_key_name} nicht in .env gefunden!")

if not VAULT_PATH:
    raise ValueError("VAULT_PATH nicht in .env gefunden!")
