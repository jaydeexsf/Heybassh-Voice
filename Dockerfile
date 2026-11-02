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
    MOONSHINE_STT_MODEL=tiny \
    PIPECAT_ICE_SERVERS=stun:stun.l.google.com:19302 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY server/bot.py server/english_teacher.py server/english_teacher_api.py server/english_teacher_tools.py server/piper_tts.py ./

# Bake the British Piper voice so sessions do not download 61MB at startup
RUN PYTHONPATH=. uv run python -c "from piper_tts import ensure_piper_voice; ensure_piper_voice('en_GB-cori-medium')"

# Bake Moonshine STT so the first Connect does not download the ONNX model
RUN PYTHONPATH=. uv run python -c "from pipecat.services.moonshine.stt import MoonshineSTTService; from pipecat.transcriptions.language import Language; MoonshineSTTService(settings=MoonshineSTTService.Settings(model='tiny', language=Language.EN))"

EXPOSE 7860

# Render sets PORT. Default to Daily: SmallWebRTC cannot complete ICE through Render's proxy.
CMD ["sh", "-c", "exec python bot.py --host 0.0.0.0 --port ${PORT:-7860} -t ${PIPECAT_TRANSPORT:-daily}"]
