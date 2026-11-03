"""Tests for Windows SSLKEYLOGFILE sanitization."""

from __future__ import annotations

import unittest

from ssl_env import sanitize_sslkeylogfile


class SslEnvTest(unittest.TestCase):
    def test_clears_avast_device_path(self) -> None:
        env = {"SSLKEYLOGFILE": r"\\.\aswMonFltProxy\abc"}
        removed = sanitize_sslkeylogfile(env)
        self.assertEqual(removed, r"\\.\aswMonFltProxy\abc")
        self.assertNotIn("SSLKEYLOGFILE", env)

    def test_keeps_normal_keylog_file(self) -> None:
        env = {"SSLKEYLOGFILE": r"C:\logs\sslkeys.log"}
        removed = sanitize_sslkeylogfile(env)
        self.assertIsNone(removed)
        self.assertEqual(env["SSLKEYLOGFILE"], r"C:\logs\sslkeys.log")

    def test_noop_when_unset(self) -> None:
        env: dict[str, str] = {}
        self.assertIsNone(sanitize_sslkeylogfile(env))


if __name__ == "__main__":
    unittest.main()
