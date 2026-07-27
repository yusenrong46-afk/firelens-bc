FROM node:22-alpine AS frontend-build

WORKDIR /build/prototype/firelens-rag-ui
COPY prototype/firelens-rag-ui/package.json prototype/firelens-rag-ui/package-lock.json ./
RUN npm ci
COPY prototype/firelens-rag-ui/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

WORKDIR /app

COPY requirements.lock pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir -r requirements.lock \
    && python -m pip install --no-cache-dir --no-deps .

COPY data/processed/firelens_static_corpus.chunks.jsonl ./data/processed/firelens_static_corpus.chunks.jsonl
COPY data/processed/firelens_static_corpus.manifest.json ./data/processed/firelens_static_corpus.manifest.json
COPY data/index/firelens_vectors.npy ./data/index/firelens_vectors.npy
COPY data/index/firelens_vectors.manifest.json ./data/index/firelens_vectors.manifest.json
COPY --from=frontend-build /build/prototype/firelens-rag-ui/dist/client ./prototype/firelens-rag-ui/dist/client

RUN mkdir -p output/traces \
    && useradd --create-home --uid 10001 firelens \
    && chown -R firelens:firelens /app

USER firelens

EXPOSE 10000

CMD ["sh", "-c", "firelens serve --host 0.0.0.0 --port ${PORT:-10000}"]
