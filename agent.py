import os
import time
from datetime import datetime
import yaml
from config import VAULT_PATH
from utils import compute_hash, read_markdown, extract_frontmatter, clean_markdown
from core import connect_db, init_db, call_ai
from services.embedding_service import EmbeddingService
from services.rag_service import RAGService

# Services initialisieren
embedding_service = EmbeddingService()
rag_service = RAGService(embedding_service)

# ---------- DB ----------


def writeback_to_markdown(path: str, ai_result: dict):
    """
    Aktualisiert YAML-Frontmatter und fügt AI-Ergebnisse ein.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Frontmatter extrahieren
    if content.startswith("---"):
        parts = content.split("---", 2)
        yaml_text = parts[1]
        body = parts[2]
        try:
            fm = yaml.safe_load(yaml_text) or {}
        except Exception:
            fm = {}
    else:
        fm = {}
        body = content

    # AI-Felder einfügen/aktualisieren
    fm["ai_summary"] = ai_result.get("summary")
    fm["ai_tags"] = ai_result.get("tags", [])
    fm["ai_keywords"] = ai_result.get("keywords", [])
    fm["ai_confidence"] = ai_result.get("confidence", 0.0)
    fm["ai_indexed_at"] = datetime.utcnow().isoformat()
    # ai_related_notes wird von auto_link als [[Wiki-Links]] befüllt — hier nicht überschreiben

    # YAML neu serialisieren
    new_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)

    # Datei neu zusammensetzen
    new_content = f"---\n{new_yaml}---{body}"

    # Atomar schreiben
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[WRITEBACK] Updated {path}")

# ---------- Vault Scan ----------

def scan_vault():
    conn = connect_db()
    cur = conn.cursor()

    new_count = changed_count = unchanged_count = 0

    for root, dirs, files in os.walk(VAULT_PATH):
        if ".obsidian" in root or "templates" in root:
            continue

        for file in files:
            if not file.endswith(".md"):
                continue

            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, VAULT_PATH)

            stat = os.stat(full_path)
            last_modified = datetime.fromtimestamp(stat.st_mtime)
            content_hash = compute_hash(full_path)

            cur.execute("SELECT id, hash_content FROM notes WHERE path = ?", (rel_path,))
            row = cur.fetchone()

            if row is None:
                cur.execute("""
                    INSERT INTO notes (path, title, hash_content, last_modified_fs, status)
                    VALUES (?, ?, ?, ?, 'pending')
                """, (rel_path, file[:-3], content_hash, last_modified))
                note_id = cur.lastrowid
                cur.execute("INSERT INTO jobs (note_id, job_type) VALUES (?, 'full_index')", (note_id,))
                new_count += 1
            else:
                note_id, old_hash = row
                if old_hash != content_hash:
                    cur.execute("""
                        UPDATE notes
                        SET hash_content = ?, last_modified_fs = ?, status = 'pending'
                        WHERE id = ?
                    """, (content_hash, last_modified, note_id))
                    cur.execute("INSERT INTO jobs (note_id, job_type) VALUES (?, 'full_index')", (note_id,))
                    changed_count += 1
                else:
                    unchanged_count += 1

    conn.commit()
    conn.close()

    total = new_count + changed_count + unchanged_count
    print(f"\n[SCAN] {total} Notizen gefunden — {new_count} neu, {changed_count} geändert, {unchanged_count} unverändert\n")


# ---------- Markdown + Prompt ----------

def build_prompt(clean_text):
    return f"""
Analysiere den folgenden Markdown-Text und gib ein JSON-Objekt zurück.

TEXT:
\"\"\"
{clean_text}
\"\"\"

Gib ein JSON mit folgendem Format zurück:

{{
  "summary": "Kurzfassung in 2-3 Sätzen",
  "tags": ["tag1", "tag2"],
  "keywords": ["keyword1", "keyword2"],
  "related_notes": [],
  "confidence": 0.0
}}

WICHTIG:
- Gib ausschließlich JSON zurück.
- Keine Erklärungen.
- Keine zusätzlichen Texte.
"""


# ---------- Groq ----------

def process_note_with_ai(full_path: str):
    md = read_markdown(full_path)
    fm, body = extract_frontmatter(md)
    clean = clean_markdown(body)
    prompt = build_prompt(clean)
    return call_ai(prompt)


# ---------- Job Processing ----------

def update_tags_in_note(path: str, tags: list):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    fm, body = extract_frontmatter(content)
    fm["ai_tags"] = list(set(fm.get("ai_tags", []) + tags))
    new_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\n{new_yaml}---{body}")

def process_auto_link_job(note_id, full_path):
    related = rag_service.find_similar_notes(note_id)

    if not related:
        print(f"         Keine ähnlichen Notizen gefunden")
        return

    wiki_links = []
    section = "## Related Notes\n"
    for r in related:
        filename = os.path.basename(r["path"]).replace(".md", "")
        section += f"- [[{filename}]] ({r['score']:.2f})\n"
        wiki_links.append(f"[[{filename}]]")

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    fm, body = extract_frontmatter(content)

    # Body: Related Notes Abschnitt einfügen oder ersetzen
    import re
    if "## Related Notes" in body:
        body = re.sub(r"## Related Notes[\s\S]*?(?=\n## |\Z)", section, body)
    else:
        body += "\n\n" + section

    # Frontmatter: ai_related_notes als Wiki-Links setzen
    fm["ai_related_notes"] = wiki_links

    new_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(f"---\n{new_yaml}---{body}")
    print(f"         {len(related)} verwandte Notizen verlinkt")

def process_rag_job(note_id, full_path):
    print(f"[RAG JOB] {full_path}")
    md = read_markdown(full_path)
    fm, body = extract_frontmatter(md)
    query = body.strip()

    if not query:
        print("[RAG] Leere Query")
        return

    result = rag_service.rag_query(query)
    if not result:
        return

    # RAG Notiz erstellen
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"RAG Query {timestamp}.md"
    rag_note_path = os.path.join(VAULT_PATH, filename)

    rag_fm = {
        "title": f"RAG Query: {query}",
        "created": datetime.utcnow().isoformat(),
        "type": "rag_query"
    }
    rag_body = f"\n# Frage\n{query}\n\n# Antwort\n{result['answer']}\n"
    
    with open(rag_note_path, "w", encoding="utf-8") as f:
        f.write(f"---\n{yaml.safe_dump(rag_fm)}---\n{rag_body}")

    improved_tags = rag_service.improve_tags_with_rag(result['answer'], result['contexts'])
    update_tags_in_note(rag_note_path, improved_tags)

    print(f"[RAG DONE] {rag_note_path}")


def process_pending_jobs():
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT jobs.id, notes.id, notes.path, jobs.job_type
        FROM jobs
        JOIN notes ON jobs.note_id = notes.id
        WHERE jobs.status = 'pending'
        ORDER BY jobs.created_at ASC
        LIMIT 10
    """)
    jobs = cur.fetchall()

    total = len(jobs)
    if total == 0:
        print("[JOBS] Keine offenen Jobs.")
        conn.close()
        return

    print(f"[JOBS] {total} Job(s) in dieser Runde\n")
    done_count = error_count = 0

    for idx, (job_id, note_id, rel_path, job_type) in enumerate(jobs, start=1):
        full_path = os.path.join(VAULT_PATH, rel_path)
        note_name = os.path.basename(rel_path)
        print(f"[{idx}/{total}] {job_type.upper()} → {note_name}")

        cur.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
        conn.commit()

        error = None
        t0 = time.time()

        if job_type == "full_index":
            print(f"         Rufe KI auf …")
            result = process_note_with_ai(full_path)
            if result:
                writeback_to_markdown(full_path, result)
                new_hash = compute_hash(full_path)
                print(f"         Erstelle Embeddings …")
                embedding_service.process_embeddings(note_id, full_path)
                cur.execute("""
                    UPDATE notes
                    SET embedding_version = embedding_version + 1,
                        hash_content = ?
                    WHERE id = ?
                """, (new_hash, note_id))
                cur.execute("INSERT INTO jobs (note_id, job_type) VALUES (?, 'auto_link')", (note_id,))
                conn.commit()
            else:
                error = "AI returned None"

        elif job_type == "rag_query":
            try:
                process_rag_job(note_id, full_path)
            except Exception as e:
                error = str(e)

        elif job_type == "embedding":
            try:
                embedding_service.process_embeddings(note_id, full_path)
            except Exception as e:
                error = str(e)

        elif job_type == "auto_link":
            process_auto_link_job(note_id, full_path)
            new_hash = compute_hash(full_path)
            cur.execute("UPDATE notes SET hash_content = ? WHERE id = ?", (new_hash, note_id))
            conn.commit()

        else:
            error = f"Unbekannter Job-Typ: {job_type}"

        elapsed = time.time() - t0

        if error:
            cur.execute("""
                UPDATE jobs
                SET status = 'error', error_message = ?
                WHERE id = ?
            """, (error, job_id))
            conn.commit()
            print(f"         FEHLER nach {elapsed:.1f}s: {error}\n")
            error_count += 1
            continue

        now = datetime.utcnow().isoformat()
        cur.execute("""
            UPDATE notes
            SET last_processed_ai = ?, status = 'done'
            WHERE id = ?
        """, (now, note_id))
        cur.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (job_id,))
        conn.commit()
        print(f"         OK ({elapsed:.1f}s)\n")
        done_count += 1

    conn.close()

    # Abschluss-Zusammenfassung
    cur_pending = _count_pending_jobs()
    print(f"[DONE] {done_count} erfolgreich, {error_count} Fehler — {cur_pending} Job(s) noch in der Warteschlange")


def _count_pending_jobs() -> int:
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'pending'")
    count = cur.fetchone()[0]
    conn.close()
    return count


if __name__ == "__main__":
    init_db()
    scan_vault()
    while _count_pending_jobs() > 0:
        process_pending_jobs()
    print("Done.")
