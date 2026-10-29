"""HTTP TTS service for a self-hosted Piper Voices API."""

from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass

import aiohttp
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

DEFAULT_PIPER_TTS_BASE_URL = "https://piper-voices-production.up.railway.app"
DEFAULT_PIPER_TTS_TIMEOUT_SECS = 60.0


class PiperTTSError(ValueError):
    """Raised when Piper WAV audio cannot be decoded into PCM."""


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


@dataclass
class PiperHttpTTSSettings(TTSSettings):
    """Settings for PiperHttpTTSService."""

    pass


class PiperHttpTTSService(TTSService):
    """Pipecat TTS service for a Piper HTTP API that returns WAV audio.

    The Railway Piper Voices API accepts ``POST /tts`` with ``{"text": "..."}``
    and returns a complete ``audio/wav`` body. This service decodes that WAV,
    converts it to 16-bit mono PCM, and emits ``TTSAudioRawFrame`` objects.
    """

    Settings = PiperHttpTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_PIPER_TTS_BASE_URL,
        aiohttp_session: aiohttp.ClientSession | None = None,
        request_timeout: float = DEFAULT_PIPER_TTS_TIMEOUT_SECS,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Initialize the Piper HTTP TTS service.

        Args:
            base_url: Piper API origin, without a trailing slash.
            aiohttp_session: Optional shared session. If omitted, this service
                creates and closes its own session.
            request_timeout: Total HTTP timeout in seconds for each TTS request.
            settings: Runtime-updatable TTS settings.
            **kwargs: Additional arguments passed to ``TTSService``.
        """
        default_settings = self.Settings(model=None, voice=None, language=None)
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
        """Start the service and ensure an HTTP session exists."""
        await super().start(frame)
        await self._ensure_session()

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

    async def _ensure_session(self) -> aiohttp.ClientSession:
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

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Synthesize speech from text using the Piper HTTP API.

        Args:
            text: Text to convert to speech.
            context_id: Unique identifier for this TTS context.

        Yields:
            Audio frames, or an error frame when synthesis fails.
        """
        if not text or not text.strip():
            yield ErrorFrame(error="Piper TTS received empty text")
            return

        session = await self._ensure_session()
        payload = {"text": text}
        headers = {"Content-Type": "application/json", "Accept": "audio/wav"}
        timeout = aiohttp.ClientTimeout(total=self._request_timeout)

        try:
            await self.start_ttfb_metrics()
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

                try:
                    pcm, source_sample_rate = decode_wav_to_pcm16_mono(body)
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
        except asyncio.CancelledError:
            raise
        except (TimeoutError, aiohttp.ServerTimeoutError):
            yield ErrorFrame(error="Piper TTS request timed out")
        except aiohttp.ClientError as exc:
            yield ErrorFrame(error=f"Piper TTS request failed: {exc}")
        except Exception as exc:
            logger.exception(f"{self} exception: {exc}")
            yield ErrorFrame(error=f"Piper TTS unknown error: {exc}")
        finally:
            await self.stop_ttfb_metrics()
