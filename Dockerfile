FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels .

FROM python:3.12-slim AS runner

WORKDIR /app

# Run as non-root user
RUN useradd -u 10001 -m -s /bin/sh appuser

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

USER appuser

EXPOSE 8000

CMD ["uvicorn", "ariba_pam.main:app", "--host", "0.0.0.0", "--port", "8000"]
