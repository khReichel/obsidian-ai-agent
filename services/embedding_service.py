import os
import io
import contextlib
import chromadb

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

with contextlib.redirect_stderr(io.StringIO()):
    from sentence_transformers import SentenceTransformer

from utils import read_markdown, extract_frontmatter, clean_markdown

_EMBED_MODEL = "paraphrase-multilingual-mpnet-base-v2"
with contextlib.redirect_stderr(io.StringIO()):
    _embedder = SentenceTransformer(_EMBED_MODEL)


class EmbeddingService:
    def __init__(self, chroma_path="chroma_store", collection_name="obsidian_notes"):
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def chunk_text(self, text, max_tokens=400, overlap=50):
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = start + max_tokens
            chunks.append(" ".join(words[start:end]))
            start = end - overlap
        return chunks

    def embed_text_local(self, text: str) -> list[float]:
        return _embedder.encode(text, normalize_embeddings=True).tolist()

    def process_embeddings(self, note_id: int, full_path: str):
        md = read_markdown(full_path)
        fm, body = extract_frontmatter(md)
        clean = clean_markdown(body)
        chunks = self.chunk_text(clean)

        self.collection.delete(where={"note_id": note_id})

        for idx, chunk in enumerate(chunks):
            emb = self.embed_text_local(chunk)
            self.collection.add(
                ids=[f"{note_id}_{idx}"],
                embeddings=[emb],
                documents=[chunk],
                metadatas=[{
                    "note_id": note_id,
                    "chunk_index": idx,
                    "path": full_path,
                }],
            )

        print(f"[EMBED] {note_id} → {len(chunks)} chunks")
