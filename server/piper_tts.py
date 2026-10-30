"""Piper TTS for Pipecat: local ONNX voices or a remote WAV HTTP API."""

from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import sys
import wave
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

DEFAULT_PIPER_TTS_BASE_URL = "https://piper-voices-production.up.railway.app"
DEFAULT_PIPER_TTS_TIMEOUT_SECS = 60.0
DEFAULT_PIPER_TTS_VOICE = "en_GB-cori-medium"
DEFAULT_PIPER_TTS_ENGINE = "local"
DEFAULT_PIPER_VOICES_DIR = Path(__file__).resolve().parent / "voices"

_VOICE_PATTERN = re.compile(
    r"^(?P<lang_family>[^-]+)_(?P<lang_region>[^-]+)-(?P<voice_name>[^-]+)-(?P<voice_quality>.+)$"
)
_HF_VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "{lang_family}/{lang_code}/{voice_name}/{voice_quality}/"
    "{lang_code}-{voice_name}-{voice_quality}{extension}?download=true"
)


class PiperTTSError(ValueError):
    """Raised when Piper WAV audio cannot be decoded into PCM."""


def _get_aiohttp():
    """Import aiohttp lazily so local TTS does not need OpenSSL."""
    import aiohttp

    return aiohttp


def decode_wav_to_pcm16_mono(wav_bytes: bytes) -> tuple[bytes, int]:
    """Decode a WAV container into 16-bit little-endian mono PCM.

    Args:
        wav_bytes: Complete WAV file bytes.

    Returns:
        A ``(pcm_bytes, sample_rate)`` tuple.

    Raises:
        PiperTTSError: If the payload is empty, not WAV, compressed, or has no samples.
    """
    if not wav_bytes:
        raise PiperTTSError("Empty audio response")
    if not wav_bytes.startswith(b"RIFF") or b"WAVE" not in wav_bytes[:12]:
        raise PiperTTSError("Response is not a WAV audio file")

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            compression = wav_file.getcomptype()
            frames = wav_file.readframes(wav_file.getnframes())
    except wave.Error as exc:
        raise PiperTTSError(f"Malformed WAV audio: {exc}") from exc

    if compression not in ("NONE", "none"):
        raise PiperTTSError(f"Unsupported WAV compression: {compression}")
    if channels < 1:
        raise PiperTTSError("WAV has no audio channels")
    if sample_rate <= 0:
        raise PiperTTSError("WAV has an invalid sample rate")

    pcm = _frames_to_pcm16(frames, sample_width)
    if channels > 1:
        pcm = _downmix_pcm16_to_mono(pcm, channels)
    if not pcm:
        raise PiperTTSError("WAV contained no PCM samples")
    return pcm, sample_rate


def _frames_to_pcm16(frames: bytes, sample_width: int) -> bytes:
    if sample_width == 2:
        return frames
    if sample_width == 1:
        # WAV 8-bit PCM is unsigned.
        out = bytearray(len(frames) * 2)
        for index, sample in enumerate(frames):
            signed = (sample - 128) << 8
            out[index * 2 : index * 2 + 2] = signed.to_bytes(2, "little", signed=True)
        return bytes(out)
    if sample_width == 3:
        count = len(frames) // 3
        out = bytearray(count * 2)
        for index in range(count):
            value = int.from_bytes(frames[index * 3 : index * 3 + 3], "little", signed=True)
            value = max(-32768, min(32767, value >> 8))
            out[index * 2 : index * 2 + 2] = value.to_bytes(2, "little", signed=True)
        return bytes(out)
    if sample_width == 4:
        count = len(frames) // 4
        out = bytearray(count * 2)
        for index in range(count):
            value = int.from_bytes(frames[index * 4 : index * 4 + 4], "little", signed=True)
            value = max(-32768, min(32767, value >> 16))
            out[index * 2 : index * 2 + 2] = value.to_bytes(2, "little", signed=True)
        return bytes(out)
    raise PiperTTSError(f"Unsupported WAV sample width: {sample_width}")


def _downmix_pcm16_to_mono(pcm: bytes, channels: int) -> bytes:
    sample_count = len(pcm) // 2
    if sample_count % channels:
        raise PiperTTSError("PCM length is not a multiple of the channel count")
    frame_count = sample_count // channels
    out = bytearray(frame_count * 2)
    for frame_index in range(frame_count):
        total = 0
        for channel in range(channels):
            offset = (frame_index * channels + channel) * 2
            total += int.from_bytes(pcm[offset : offset + 2], "little", signed=True)
        mixed = total // channels
        out[frame_index * 2 : frame_index * 2 + 2] = mixed.to_bytes(2, "little", signed=True)
    return bytes(out)


async def _iter_chunks(data: bytes, chunk_size: int) -> AsyncIterator[bytes]:
    size = max(chunk_size, 2)
    for index in range(0, len(data), size):
        yield data[index : index + size]


def voice_model_path(voice: str, voices_dir: Path) -> Path:
    """Return the ONNX path for a Piper voice name."""
    return Path(voices_dir) / f"{voice}.onnx"


def huggingface_voice_url(voice: str, extension: str) -> str:
    """Build the Hugging Face download URL for a Piper voice file."""
    match = _VOICE_PATTERN.match(voice.strip())
    if not match:
        raise PiperTTSError(
            f"Voice '{voice}' did not match pattern like 'en_GB-cori-medium'"
        )
    lang_family = match.group("lang_family")
    lang_code = f"{lang_family}_{match.group('lang_region')}"
    return _HF_VOICE_URL.format(
        lang_family=lang_family,
        lang_code=lang_code,
        voice_name=match.group("voice_name"),
        voice_quality=match.group("voice_quality"),
        extension=extension,
    )


def ensure_piper_voice(voice: str, voices_dir: Path | None = None) -> Path:
    """Download a Piper voice model if it is not already on disk.

    Returns:
        Path to the ``.onnx`` model file.
    """
    dest_dir = Path(voices_dir or DEFAULT_PIPER_VOICES_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    model_path = voice_model_path(voice, dest_dir)
    config_path = Path(f"{model_path}.json")
    if model_path.exists() and model_path.stat().st_size > 0 and config_path.exists():
        return model_path

    logger.info(f"Downloading Piper voice {voice} into {dest_dir}")
    _download_file(huggingface_voice_url(voice, ".onnx"), model_path)
    _download_file(huggingface_voice_url(voice, ".onnx.json"), config_path)
    return model_path


def load_piper_voice(model_path: Path):
    """Load a Piper ONNX voice from disk."""
    from piper import PiperVoice

    return PiperVoice.load(model_path)


def synthesize_local_wav(text: str, model_path: Path, voice=None) -> bytes:
    """Synthesize text with a local Piper ONNX voice and return WAV bytes."""
    piper_voice = voice or load_piper_voice(model_path)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        piper_voice.synthesize_wav(text, wav_file)
    return buffer.getvalue()


def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    try:
        if os.name == "nt":
            completed = subprocess.run(
                [
                    "curl.exe",
                    "-fsSL",
                    "--max-time",
                    "300",
                    "-o",
                    str(tmp_path),
                    url,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise PiperTTSError(
                    f"Failed to download {dest.name}: {completed.stderr.strip() or completed.stdout.strip()}"
                )
        else:
            from urllib.request import urlopen

            with urlopen(url, timeout=300) as response, open(tmp_path, "wb") as handle:
                handle.write(response.read())
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise PiperTTSError(f"Downloaded empty file for {dest.name}")
        tmp_path.replace(dest)
    except PiperTTSError:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise PiperTTSError(f"Failed to download {dest.name}: {exc}") from exc


@dataclass
class PiperHttpTTSSettings(TTSSettings):
    """Settings for PiperHttpTTSService."""

    pass


class PiperHttpTTSService(TTSService):
    """Pipecat TTS service for Piper, either local ONNX or a remote HTTP API.

    Local mode loads a downloaded Piper voice (default: British ``en_GB-cori-medium``).
    HTTP mode posts ``{"text", "voice"}`` to ``POST /tts`` and decodes the WAV body.
    """

    Settings = PiperHttpTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_PIPER_TTS_BASE_URL,
        aiohttp_session: Any | None = None,
        request_timeout: float = DEFAULT_PIPER_TTS_TIMEOUT_SECS,
        voice: str = DEFAULT_PIPER_TTS_VOICE,
        engine: str = DEFAULT_PIPER_TTS_ENGINE,
        voices_dir: str | Path | None = None,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Initialize the Piper TTS service.

        Args:
            base_url: Piper API origin, without a trailing slash.
            aiohttp_session: Optional shared session. If omitted, this service
                creates and closes its own session.
            request_timeout: Total HTTP timeout in seconds for each TTS request.
            voice: Piper voice id, such as ``en_GB-cori-medium``.
            engine: ``local`` synthesizes on this machine; ``http`` calls the API.
            voices_dir: Directory for downloaded ``.onnx`` voice files.
            settings: Runtime-updatable TTS settings.
            **kwargs: Additional arguments passed to ``TTSService``.
        """
        default_settings = self.Settings(model=None, voice=voice, language="en-GB")
        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            settings=default_settings,
            **kwargs,
        )

        self._base_url = base_url.rstrip("/")
        self._session = aiohttp_session
        self._session_owner = aiohttp_session is None
        self._request_timeout = request_timeout
        self._voice = (voice or DEFAULT_PIPER_TTS_VOICE).strip()
        self._engine = (engine or DEFAULT_PIPER_TTS_ENGINE).strip().lower()
        self._voices_dir = Path(voices_dir) if voices_dir else DEFAULT_PIPER_VOICES_DIR
        self._model_path: Path | None = None
        self._piper_voice = None

    @property
    def tts_url(self) -> str:
        """Full URL of the Piper TTS endpoint."""
        if self._base_url.endswith("/tts"):
            return self._base_url
        return f"{self._base_url}/tts"

    def can_generate_metrics(self) -> bool:
        """Return whether this service can generate processing metrics."""
        return True

    async def start(self, frame):
        """Start the service and load the local voice or HTTP session."""
        await super().start(frame)
        if self._engine == "local":
            await self._ensure_local_voice()
            logger.info(f"Piper TTS using local British voice {self._voice}")
        else:
            await self._ensure_session()
            logger.info(f"Piper TTS using HTTP voice {self._voice} at {self.tts_url}")

    async def stop(self, frame):
        """Stop the service and close an owned HTTP session."""
        await super().stop(frame)
        await self._close_session()

    async def cancel(self, frame):
        """Cancel the service and close an owned HTTP session."""
        await super().cancel(frame)
        await self._close_session()

    async def cleanup(self):
        """Release HTTP resources at teardown."""
        await super().cleanup()
        await self._close_session()

    async def _ensure_session(self):
        aiohttp = _get_aiohttp()
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._session_owner = True
        return self._session

    async def _close_session(self) -> None:
        if self._session_owner and self._session and not self._session.closed:
            await self._session.close()
        if self._session_owner:
            self._session = None

    async def _ensure_local_voice(self):
        if self._piper_voice is not None:
            return self._piper_voice
        self._model_path = await asyncio.to_thread(
            ensure_piper_voice, self._voice, self._voices_dir
        )
        self._piper_voice = await asyncio.to_thread(load_piper_voice, self._model_path)
        return self._piper_voice

    async def _pcm_frames_from_wav(
        self, wav_bytes: bytes, text: str, context_id: str
    ) -> AsyncGenerator[Frame, None]:
        try:
            pcm, source_sample_rate = decode_wav_to_pcm16_mono(wav_bytes)
        except PiperTTSError as exc:
            yield ErrorFrame(error=f"Piper TTS audio error: {exc}")
            return

        await self.start_tts_usage_metrics(text)
        async for frame in self._stream_audio_frames_from_iterator(
            _iter_chunks(pcm, self.chunk_size),
            in_sample_rate=source_sample_rate,
            context_id=context_id,
        ):
            await self.stop_ttfb_metrics()
            yield frame

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Synthesize speech from text using local Piper or the HTTP API.

        Args:
            text: Text to convert to speech.
            context_id: Unique identifier for this TTS context.

        Yields:
            Audio frames, or an error frame when synthesis fails.
        """
        if not text or not text.strip():
            yield ErrorFrame(error="Piper TTS received empty text")
            return

        try:
            await self.start_ttfb_metrics()
            if self._engine == "local":
                piper_voice = await self._ensure_local_voice()
                try:
                    wav_bytes = await asyncio.to_thread(
                        synthesize_local_wav, text, self._model_path, piper_voice
                    )
                except Exception as exc:
                    logger.exception(f"{self} local synthesis failed: {exc}")
                    yield ErrorFrame(error=f"Piper TTS local synthesis failed: {exc}")
                    return
                async for frame in self._pcm_frames_from_wav(wav_bytes, text, context_id):
                    yield frame
                return

            aiohttp = _get_aiohttp()
            session = await self._ensure_session()
            payload = {"text": text, "voice": self._voice}
            headers = {"Content-Type": "application/json", "Accept": "audio/wav"}
            timeout = aiohttp.ClientTimeout(total=self._request_timeout)

            async with session.post(
                self.tts_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            ) as response:
                body = await response.read()
                if response.status != 200:
                    error_text = body.decode("utf-8", errors="replace") if body else ""
                    yield ErrorFrame(
                        error=(
                            "Piper TTS HTTP error "
                            f"(status: {response.status}, error: {error_text})"
                        )
                    )
                    return
                if not body:
                    yield ErrorFrame(error="Piper TTS returned an empty response")
                    return

                async for frame in self._pcm_frames_from_wav(body, text, context_id):
                    yield frame
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            yield ErrorFrame(error="Piper TTS request timed out")
        except Exception as exc:
            aiohttp = sys.modules.get("aiohttp")
            client_error = getattr(aiohttp, "ClientError", ()) if aiohttp else ()
            timeout_error = getattr(aiohttp, "ServerTimeoutError", ()) if aiohttp else ()
            if timeout_error and isinstance(exc, timeout_error):
                yield ErrorFrame(error="Piper TTS request timed out")
                return
            if client_error and isinstance(exc, client_error):
                yield ErrorFrame(error=f"Piper TTS request failed: {exc}")
                return
            logger.exception(f"{self} exception: {exc}")
            yield ErrorFrame(error=f"Piper TTS unknown error: {exc}")
        finally:
            await self.stop_ttfb_metrics()
