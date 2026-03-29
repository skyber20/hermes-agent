FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y \
    curl git docker.io \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PROJECT_ENVIRONMENT=/app/venv \
    HERMES_HOME=/app/hermes_data \
    PYTHONUNBUFFERED=1 \
    PATH="/app/venv/bin:$PATH"

RUN mkdir -p /app/hermes_code /app/hermes_data
WORKDIR /app/hermes_code

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra tg

COPY . .

RUN uv sync --frozen --extra tg

CMD ["python", "-m", "gateway.run"]
