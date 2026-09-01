FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS frontend-build

WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim@sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

WORKDIR /app

ARG RENDER_GIT_COMMIT
ARG FIRELENS_BUILD_COMMIT
ARG FIRELENS_RELEASE_VERSION=1.6.3
ARG FIRELENS_BENCHMARK_ID=firelens_v1_6_2
ARG FIRELENS_RERANK_MODEL=cohere/rerank-4-pro
ARG FIRELENS_GENERATION_MODEL=openai/gpt-5.6-luna
ENV FIRELENS_BUILD_COMMIT=$FIRELENS_BUILD_COMMIT \
    FIRELENS_RELEASE_VERSION=$FIRELENS_RELEASE_VERSION \
    FIRELENS_BENCHMARK_ID=$FIRELENS_BENCHMARK_ID \
    FIRELENS_EMBEDDING_ZDR=required \
    FIRELENS_RERANKING_ZDR=optional \
    FIRELENS_GENERATION_ZDR=required \
    FIRELENS_DATA_COLLECTION=deny \
    FIRELENS_ALLOW_FALLBACKS=false \
    FIRELENS_RERANK_MODEL=$FIRELENS_RERANK_MODEL \
    FIRELENS_GENERATION_MODEL=$FIRELENS_GENERATION_MODEL

COPY requirements.lock pyproject.toml README.md app.py ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir -r requirements.lock \
    && python -m pip install --no-cache-dir --no-deps .

COPY config/runtime_artifact_allowlist.v1.json ./config/runtime_artifact_allowlist.v1.json
COPY scripts/write_runtime_candidate.py ./scripts/write_runtime_candidate.py
COPY data/processed/ ./data/processed/
COPY data/index/ ./data/index/
COPY data/repairs/ ./data/repairs/
COPY data/typed_claims/ ./data/typed_claims/
COPY --from=frontend-build /build/apps/web/dist/client ./apps/web/dist/client

RUN python scripts/write_runtime_candidate.py \
    --output config/runtime_candidate.v1.json \
    --commit "${FIRELENS_BUILD_COMMIT:-$RENDER_GIT_COMMIT}" \
    --benchmark-id "$FIRELENS_BENCHMARK_ID" \
    --release-version "$FIRELENS_RELEASE_VERSION"

RUN mkdir -p output/traces \
    && useradd --create-home --uid 10001 firelens \
    && chown -R firelens:firelens /app

USER firelens

EXPOSE 10000

CMD ["sh", "-c", "firelens serve --host 0.0.0.0 --port ${PORT:-10000}"]
