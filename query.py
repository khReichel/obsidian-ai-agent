#!/usr/bin/env python3
"""
Interaktive RAG-Abfrage gegen den indizierten Obsidian-Vault.

Verwendung:
    python query.py "Deine Frage hier"
    python query.py              # startet interaktiven Modus
"""

import sys
import os
from config import VAULT_PATH
from core import init_db, call_ai_text
from services.embedding_service import EmbeddingService
from services.rag_service import RAGService

embedding_service = EmbeddingService()
rag_service = RAGService(embedding_service)


def run_query(question: str):
    print(f"\nFrage: {question}")
    print("-" * 60)

    contexts = rag_service.retrieve_context(question, k=5)
    if not contexts:
        print("Keine relevanten Notizen gefunden.")
        return

    print(f"Gefundene Quellen ({len(contexts)}):")
    seen_paths = []
    for c in contexts:
        rel = os.path.relpath(c["path"], VAULT_PATH)
        if rel not in seen_paths:
            seen_paths.append(rel)
            print(f"  · {rel}")

    context_text = "\n\n---\n\n".join(
        f"[{os.path.basename(c['path'])}]\n{c['text']}"
        for c in contexts
    )

    prompt = f"""Du bist ein KI-Assistent, der Fragen anhand von Wissen aus Obsidian-Notizen beantwortet.

FRAGE:
{question}

KONTEXT AUS DEM VAULT:
{context_text}

ANTWORT:
- Nutze ausschließlich den Kontext oben.
- Antworte auf Deutsch, präzise und strukturiert.
- Wenn der Kontext die Frage nicht beantworten kann, sag das klar."""

    print("\nAntwort:")
    print("-" * 60)
    answer = call_ai_text(prompt)
    if answer:
        print(answer)
    else:
        print("Keine Antwort vom Modell erhalten.")
    print()


def interactive_mode():
    print("Obsidian Vault Query — 'exit' zum Beenden\n")
    while True:
        try:
            question = input("Frage: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTschüss!")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            print("Tschüss!")
            break
        run_query(question)


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1:
        run_query(" ".join(sys.argv[1:]))
    else:
        interactive_mode()
