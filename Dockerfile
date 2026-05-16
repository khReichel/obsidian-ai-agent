FROM python:3.11-slim

WORKDIR /app

# System-Abhängigkeiten für sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Embedding-Modell beim Build cachen (verhindert Download beim ersten Start)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')"

CMD ["python", "agent.py"]
