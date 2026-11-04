"""Tests for bot startup latency helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bot
import english_teacher as et


class OpeningLessonMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = et._DATA_PATH
        self._orig_store = et._store
        et._DATA_PATH = Path(self._tmpdir.name) / "progress.json"
        et._store = None

    def tearDown(self) -> None:
        et._DATA_PATH = self._orig_path
        et._store = self._orig_store
        self._tmpdir.cleanup()

    def test_default_groq_model_is_current(self) -> None:
        self.assertEqual(bot.DEFAULT_GROQ_MODEL, "openai/gpt-oss-20b")

    def test_opening_message_includes_lesson_json(self) -> None:
        message = bot._opening_lesson_message("john")
        self.assertEqual(message["role"], "user")
        self.assertIn("Do not call get_student_lesson", message["content"])
        payload = message["content"].split("\n", 2)[1]
        lesson = json.loads(payload)
        self.assertEqual(lesson["student_id"], "john")
        self.assertEqual(lesson["current_lesson"], 1)


class MoonshineCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = bot._cached_moonshine_transcriber
        bot._cached_moonshine_transcriber = None

    def tearDown(self) -> None:
        bot._cached_moonshine_transcriber = self._orig

    def test_second_stt_skips_model_reload(self) -> None:
        transcriber = object()
        loads: list[int] = []

        class DummySTT:
            class Settings:
                def __init__(self, **kwargs):
                    self.kwargs = kwargs

            def __init__(self, **kwargs):
                self._transcriber = self._load()

            def _load(self):
                loads.append(1)
                return transcriber

        with patch.object(bot, "MoonshineSTTService", DummySTT):
            first = bot._make_stt()
            second = bot._make_stt()

        self.assertIs(first._transcriber, transcriber)
        self.assertIs(second._transcriber, transcriber)
        self.assertEqual(loads, [1])


class WarmupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._silero = bot._silero_warmed
        bot._silero_warmed = False

    def tearDown(self) -> None:
        bot._silero_warmed = self._silero

    def test_warmup_loads_piper_stt_and_vad(self) -> None:
        with (
            patch.object(bot, "warmup_piper_voice") as piper,
            patch.object(bot, "_make_stt") as stt,
            patch.object(bot, "SileroVADAnalyzer") as vad,
        ):
            bot.warmup_local_models()

        piper.assert_called_once()
        stt.assert_called_once()
        vad.assert_called_once()
        self.assertTrue(bot._silero_warmed)


if __name__ == "__main__":
    unittest.main()
