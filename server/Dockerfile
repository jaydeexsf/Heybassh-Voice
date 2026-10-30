FROM dailyco/pipecat-base:latest

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

ENV PIPER_TTS_ENGINE=local
ENV PIPER_TTS_VOICE=en_GB-cori-medium

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Agent modules (copy next to bot.py; do not COPY the whole tree over /app)
COPY ./bot.py ./english_teacher.py ./english_teacher_api.py ./english_teacher_tools.py ./piper_tts.py ./
COPY ./voices/README.md ./voices/README.md

# Bake the British Piper voice so sessions do not download 61MB at startup
RUN PYTHONPATH=. uv run python -c "from piper_tts import ensure_piper_voice; ensure_piper_voice('en_GB-cori-medium')"
