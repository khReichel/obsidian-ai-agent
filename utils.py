import os
import hashlib
import re
import yaml

def compute_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def read_markdown(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def extract_frontmatter(md_text):
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            yaml_text = parts[1]
            body = parts[2]
            try:
                fm = yaml.safe_load(yaml_text) or {}
            except Exception:
                fm = {}
            return fm, body
    return {}, md_text

def clean_markdown(md_text):
    # Codeblöcke entfernen
    md_text = re.sub(r"```.*?```", "", md_text, flags=re.DOTALL)
    # Inline-Code entfernen
    md_text = re.sub(r"`[^`]+`", "", md_text)
    # HTML-Tags entfernen
    md_text = re.sub(r"<[^>]+>", "", md_text)
    # Zu viele Zeilenumbrüche reduzieren
    md_text = re.sub(r"\n{3,}", "\n\n", md_text)
    return md_text.strip()
