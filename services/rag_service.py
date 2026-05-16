from core import call_ai, call_ai_text
from services.embedding_service import EmbeddingService


class RAGService:
    def __init__(self, embedding_service: EmbeddingService):
        self.es = embedding_service
        self.collection = self.es.collection

    def embed_query(self, text: str) -> list[float]:
        return self.es.embed_text_local(text)

    def find_similar_notes(self, note_id: int, k: int = 5, min_score: float = 0.75):
        results = self.collection.get(where={"note_id": note_id}, include=["embeddings"])

        if results["embeddings"] is None or len(results["embeddings"]) == 0:
            return []

        import numpy as np
        emb = np.mean(results["embeddings"], axis=0).tolist()

        sim = self.collection.query(query_embeddings=[emb], n_results=k + 1)

        similar = []
        for doc, meta, dist in zip(sim["documents"][0], sim["metadatas"][0], sim["distances"][0]):
            if meta["note_id"] == note_id:
                continue
            score = 1 - dist
            if score >= min_score:
                similar.append({
                    "note_id": meta["note_id"],
                    "path": meta["path"],
                    "score": score,
                })
        return similar

    def retrieve_context(self, query: str, k: int = 5):
        query_emb = self.embed_query(query)
        results = self.collection.query(query_embeddings=[query_emb], n_results=k)

        return [
            {
                "text": doc,
                "note_id": meta["note_id"],
                "chunk_index": meta["chunk_index"],
                "path": meta["path"],
            }
            for doc, meta in zip(results["documents"][0], results["metadatas"][0])
        ]

    def rag_query(self, query: str, k: int = 5):
        contexts = self.retrieve_context(query, k=k)
        if not contexts:
            return None

        context_text = "\n\n---\n\n".join(
            f"[Chunk {c['note_id']}:{c['chunk_index']}]\n{c['text']}"
            for c in contexts
        )

        prompt = f"""Du bist ein KI-Assistent, der Fragen anhand von Wissensdaten aus Obsidian-Notizen beantwortet.

NUTZERFRAGE:
{query}

KONTEXT:
{context_text}

ANTWORT:
- Nutze ausschließlich den Kontext.
- Keine Halluzinationen."""

        answer = call_ai_text(prompt)
        if not answer:
            return None

        return {"query": query, "answer": answer, "contexts": contexts}

    def improve_tags_with_rag(self, note_text: str, rag_contexts: list):
        context_text = "\n\n".join(c["text"] for c in rag_contexts)
        prompt = f"""Analysiere den folgenden Text und verbessere die Tags basierend auf zusätzlichem Kontext.

TEXT:
{note_text}

KONTEXT:
{context_text}

Gib ein JSON zurück:
{{ "improved_tags": [] }}"""

        result = call_ai(prompt)
        return result.get("improved_tags", []) if result else []
