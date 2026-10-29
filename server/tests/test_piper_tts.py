"""Tests for the Piper HTTP TTS integration."""

from __future__ import annotations

import asyncio
import io
import sys
import types
import unittest
import wave
from unittest.mock import MagicMock


def _install_aiohttp_stub() -> None:
    """Install a tiny aiohttp stub so unit tests can import the TTS service.

    Creating a real ``ssl.SSLContext`` aborts some Windows OpenSSL builds with
    ``OPENSSL_Applink``. These tests inject a fake session and never open TLS.
    """
    module = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientConnectionError(ClientError):
        pass

    class ServerTimeoutError(TimeoutError):
        pass

    class ClientTimeout:
        def __init__(self, total=None, **kwargs):
            self.total = total

    class ClientSession:
        closed = False

        async def close(self):
            self.closed = True

    module.ClientError = ClientError
    module.ClientConnectionError = ClientConnectionError
    module.ServerTimeoutError = ServerTimeoutError
    module.ClientTimeout = ClientTimeout
    module.ClientSession = ClientSession
    sys.modules["aiohttp"] = module


if sys.platform == "win32":
    _install_aiohttp_stub()

import aiohttp
from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame

from piper_tts import (
    PiperHttpTTSService,
    PiperTTSError,
    decode_wav_to_pcm16_mono,
)


def _pack_pcm16(samples: list[int]) -> bytes:
    return b"".join(value.to_bytes(2, "little", signed=True) for value in samples)


def _make_wav(
    samples: list[int],
    *,
    sample_rate: int = 22050,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    if sample_width == 1:
        frames = bytes((sample + 128) & 0xFF for sample in samples)
    elif sample_width == 2:
        frames = _pack_pcm16(samples)
    elif sample_width == 4:
        frames = b"".join((sample << 16).to_bytes(4, "little", signed=True) for sample in samples)
    else:
        raise ValueError(f"Unsupported sample width for test helper: {sample_width}")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, status: int, body: bytes, content_type: str = "audio/wav"):
        self.status = status
        self._body = body
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.posts: list[dict] = []
        self.closed = False

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def _service(session: FakeSession, sample_rate: int = 16000) -> PiperHttpTTSService:
    tts = PiperHttpTTSService(
        base_url="https://piper.example",
        aiohttp_session=session,  # type: ignore[arg-type]
        request_timeout=5.0,
    )
    tts._sample_rate = sample_rate
    tts.start_tts_usage_metrics = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(0))  # type: ignore[method-assign]
    tts.start_ttfb_metrics = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(0))  # type: ignore[method-assign]
    tts.stop_ttfb_metrics = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(0))  # type: ignore[method-assign]
    return tts


class DecodeWavTests(unittest.TestCase):
    def test_decodes_mono_pcm16_and_sample_rate(self):
        samples = [0, 1000, -1000, 32767, -32768]
        wav_bytes = _make_wav(samples, sample_rate=22050)
        pcm, rate = decode_wav_to_pcm16_mono(wav_bytes)
        self.assertEqual(rate, 22050)
        self.assertEqual(pcm, _pack_pcm16(samples))

    def test_downmixes_stereo_to_mono(self):
        # Interleaved L/R: (1000, 3000), (-2000, 0)
        wav_bytes = _make_wav([1000, 3000, -2000, 0], channels=2, sample_rate=16000)
        pcm, rate = decode_wav_to_pcm16_mono(wav_bytes)
        self.assertEqual(rate, 16000)
        self.assertEqual(pcm, _pack_pcm16([2000, -1000]))

    def test_converts_unsigned_8bit_to_pcm16(self):
        wav_bytes = _make_wav([0, 64, -64], sample_width=1, sample_rate=8000)
        pcm, rate = decode_wav_to_pcm16_mono(wav_bytes)
        self.assertEqual(rate, 8000)
        self.assertEqual(pcm, _pack_pcm16([0, 64 << 8, -64 << 8]))

    def test_empty_and_malformed_audio_raise(self):
        with self.assertRaises(PiperTTSError):
            decode_wav_to_pcm16_mono(b"")
        with self.assertRaises(PiperTTSError):
            decode_wav_to_pcm16_mono(b"not a wav file")
        with self.assertRaises(PiperTTSError):
            decode_wav_to_pcm16_mono(b"RIFF????WAVE")


class PiperHttpTTSServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_text_to_tts_endpoint_and_emits_audio_frames(self):
        samples = [123, -456, 789, -1011]
        wav_bytes = _make_wav(samples, sample_rate=16000)
        session = FakeSession(FakeResponse(200, wav_bytes))
        tts = _service(session, sample_rate=16000)

        frames = [frame async for frame in tts.run_tts("Hello from Piper.", "ctx-1")]

        self.assertEqual(len(session.posts), 1)
        self.assertEqual(session.posts[0]["url"], "https://piper.example/tts")
        self.assertEqual(session.posts[0]["json"], {"text": "Hello from Piper."})
        self.assertEqual(session.posts[0]["headers"]["Content-Type"], "application/json")

        audio_frames = [frame for frame in frames if isinstance(frame, TTSAudioRawFrame)]
        self.assertTrue(audio_frames)
        self.assertFalse(any(isinstance(frame, ErrorFrame) for frame in frames))
        combined = b"".join(frame.audio for frame in audio_frames)
        self.assertEqual(combined, _pack_pcm16(samples))
        self.assertEqual(audio_frames[0].sample_rate, 16000)
        self.assertEqual(audio_frames[0].num_channels, 1)
        self.assertEqual(audio_frames[0].context_id, "ctx-1")

    async def test_http_error_yields_error_frame(self):
        session = FakeSession(FakeResponse(422, b'{"error":"Invalid request."}'))
        tts = _service(session)
        frames = [frame async for frame in tts.run_tts("Hello", "ctx-2")]
        self.assertTrue(any(isinstance(frame, ErrorFrame) for frame in frames))
        self.assertFalse(any(isinstance(frame, TTSAudioRawFrame) for frame in frames))
        self.assertIn("422", frames[0].error)

    async def test_timeout_yields_error_frame(self):
        session = FakeSession(error=TimeoutError())
        tts = _service(session)
        frames = [frame async for frame in tts.run_tts("Hello", "ctx-3")]
        self.assertEqual(len(frames), 1)
        self.assertIsInstance(frames[0], ErrorFrame)
        self.assertIn("timed out", frames[0].error)

    async def test_empty_response_yields_error_frame(self):
        session = FakeSession(FakeResponse(200, b""))
        tts = _service(session)
        frames = [frame async for frame in tts.run_tts("Hello", "ctx-4")]
        self.assertIsInstance(frames[0], ErrorFrame)
        self.assertIn("empty", frames[0].error.lower())

    async def test_malformed_wav_yields_error_frame(self):
        session = FakeSession(FakeResponse(200, b"this is not wav"))
        tts = _service(session)
        frames = [frame async for frame in tts.run_tts("Hello", "ctx-5")]
        self.assertIsInstance(frames[0], ErrorFrame)
        self.assertIn("audio error", frames[0].error.lower())

    async def test_client_error_yields_error_frame(self):
        session = FakeSession(error=aiohttp.ClientConnectionError("unreachable"))
        tts = _service(session)
        frames = [frame async for frame in tts.run_tts("Hello", "ctx-6")]
        self.assertIsInstance(frames[0], ErrorFrame)
        self.assertIn("failed", frames[0].error.lower())

    async def test_strips_trailing_slash_from_base_url(self):
        session = FakeSession(FakeResponse(200, _make_wav([1, 2], sample_rate=16000)))
        tts = PiperHttpTTSService(
            base_url="https://piper.example/",
            aiohttp_session=session,  # type: ignore[arg-type]
        )
        tts._sample_rate = 16000
        tts.start_tts_usage_metrics = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(0))  # type: ignore[method-assign]
        tts.start_ttfb_metrics = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(0))  # type: ignore[method-assign]
        tts.stop_ttfb_metrics = MagicMock(side_effect=lambda *args, **kwargs: asyncio.sleep(0))  # type: ignore[method-assign]
        await anext(tts.run_tts("Hi", "ctx-7"))
        self.assertEqual(session.posts[0]["url"], "https://piper.example/tts")

    async def test_empty_text_yields_error_frame(self):
        session = FakeSession()
        tts = _service(session)
        frames = [frame async for frame in tts.run_tts("   ", "ctx-8")]
        self.assertEqual(session.posts, [])
        self.assertEqual(len(frames), 1)
        self.assertIsInstance(frames[0], ErrorFrame)
        self.assertIn("empty", frames[0].error.lower())


if __name__ == "__main__":
    unittest.main()
