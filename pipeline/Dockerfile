FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# 의존성 레이어 캐시 — pyproject.toml / uv.lock 만 먼저 복사.
COPY pipeline/pyproject.toml pipeline/uv.lock ./pipeline/
RUN cd pipeline && uv sync --no-dev --frozen --no-install-project

# ──────────────────────────────────────────────
FROM python:3.12-slim-bookworm

WORKDIR /app

# builder 의 .venv 복사
COPY --from=builder /app/pipeline/.venv /app/pipeline/.venv

# 소스 복사 (data/ 는 compose volume mount 로 주입)
COPY pipeline/ ./pipeline/

ENV PATH="/app/pipeline/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "pipeline.api:app", "--host", "0.0.0.0", "--port", "8000"]
