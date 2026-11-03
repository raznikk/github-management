# Multi-stage Docker build for gh-iac
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install .

# Production runtime image
FROM python:3.12-slim AS runner

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/gh-iac /usr/local/bin/gh-iac

# Non-root user for security
RUN useradd -m -u 10001 ghiac && \
    chown -R ghiac:ghiac /workspace

USER ghiac

ENTRYPOINT ["gh-iac"]
CMD ["--help"]
