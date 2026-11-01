FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng \
    libgomp1 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIPER_TTS_ENGINE=local \
    PIPER_TTS_VOICE=en_GB-cori-medium \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY bot.py english_teacher.py english_teacher_api.py english_teacher_tools.py piper_tts.py ./

RUN PYTHONPATH=. uv run python -c "from piper_tts import ensure_piper_voice; ensure_piper_voice('en_GB-cori-medium')"

EXPOSE 7860

CMD ["sh", "-c", "exec python bot.py --host 0.0.0.0 --port ${PORT:-7860}"]
