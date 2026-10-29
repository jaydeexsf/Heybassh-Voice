FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV HOST=0.0.0.0
EXPOSE 7860

CMD ["sh", "-c", "uv run bot.py --host 0.0.0.0 --port ${PORT:-7860}"]
