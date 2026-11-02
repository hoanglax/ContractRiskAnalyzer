# Backend image: API + pipeline, with the legal KB, the vector index and the query embedder baked in.
# Build context is the repo root (it needs data/):  docker compose build backend
FROM python:3.12-slim

# poppler-utils: PDF text and page images for OCR. LibreOffice: legacy .doc only (~400 MB; build with
# --build-arg WITH_LIBREOFFICE=0 to skip it, and .doc uploads then fail with a clear error).
ARG WITH_LIBREOFFICE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && if [ "$WITH_LIBREOFFICE" = "1" ]; then apt-get install -y --no-install-recommends libreoffice-writer-nogui; fi \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf
WORKDIR /app/backend

# CPU torch first, so requirements.txt does not pull the multi-GB CUDA build
COPY backend/requirements.txt .
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# The query embedder (must be the model the committed vectors were made with: data/legal_vectors/vec_80m.json).
# Its own layer, so it is downloaded again only when requirements or the model change.
RUN python -c "from transformers import AutoModel, AutoTokenizer; m = 'codefuse-ai/F2LLM-v2-80M'; \
AutoTokenizer.from_pretrained(m); AutoModel.from_pretrained(m)"

# Same layout as the repo (/app/backend, /app/data): the code finds data/ and backend/cache/ by relative path
COPY data/legal_corpus /app/data/legal_corpus
COPY data/legal_vectors /app/data/legal_vectors
COPY data/taxonomy /app/data/taxonomy
COPY backend/application application

# Legal KB (SQLite) -> committed vectors into embedded Qdrant. A few seconds: nothing is embedded here. Fails if the
# corpus changed without re-embedding (kb_sha); the fix is in application/modules/legal_retrieval/dense.py.
# Qdrant is written on the /dev/shm RAM disk and copied in: on the image filesystem it takes ~2 min (per-point commits).
RUN python -m application.modules.legal_retrieval.kb build \
 && python -m application.modules.legal_retrieval.qdrant_store index --tag 80m --committed --store /dev/shm/qdrant \
 && cp -r /dev/shm/qdrant cache/qdrant && rm -rf /dev/shm/qdrant

COPY backend/llm.openrouter.toml llm.openrouter.toml
ENV PIPELINE_LLM_CONFIG=/app/backend/llm.openrouter.toml HF_HUB_OFFLINE=1 RUNS_DIR=/app/runs

EXPOSE 8000
CMD ["uvicorn", "application.main:app", "--host", "0.0.0.0", "--port", "8000"]
