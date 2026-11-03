"""Tests for SmallWebRTC ICE / TURN env merging."""

from __future__ import annotations

import json
import unittest

from ice_servers import (
    DEFAULT_STUN_URL,
    apply_ice_servers_env,
    build_ice_servers,
    has_turn,
    ice_candidate_type_counts,
    ice_server_urls,
)


class IceServersTest(unittest.TestCase):
    def test_stun_only_has_no_turn(self) -> None:
        servers = build_ice_servers(existing=DEFAULT_STUN_URL)
        self.assertEqual(ice_server_urls(servers), [DEFAULT_STUN_URL])
        self.assertFalse(has_turn(servers))

    def test_merges_turn_credentials_without_duplicating_stun(self) -> None:
        servers = build_ice_servers(
            existing=DEFAULT_STUN_URL,
            turn_urls="turn:turn.example.com:3478,turns:turn.example.com:443",
            turn_username="user",
            turn_credential="secret",
        )
        self.assertTrue(has_turn(servers))
        self.assertEqual(
            ice_server_urls(servers),
            [
                DEFAULT_STUN_URL,
                "turn:turn.example.com:3478",
                "turns:turn.example.com:443",
            ],
        )
        turn = servers[-1]
        self.assertEqual(turn["username"], "user")
        self.assertEqual(turn["credential"], "secret")

    def test_apply_writes_json_env_without_logging_secrets(self) -> None:
        env = {
            "PIPECAT_ICE_SERVERS": DEFAULT_STUN_URL,
            "TURN_URLS": "turn:turn.example.com:3478",
            "TURN_USERNAME": "user",
            "TURN_CREDENTIAL": "secret",
        }
        servers = apply_ice_servers_env(env)
        written = json.loads(env["PIPECAT_ICE_SERVERS"])
        self.assertEqual(written, servers)
        self.assertTrue(has_turn(written))
        self.assertIn("secret", env["PIPECAT_ICE_SERVERS"])

    def test_sdp_candidate_type_counts(self) -> None:
        sdp = (
            "a=candidate:1 1 UDP 2122260223 10.0.0.1 5000 typ host\r\n"
            "a=candidate:2 1 UDP 1686052607 1.2.3.4 5000 typ srflx raddr 10.0.0.1 rport 5000\r\n"
            "a=candidate:3 1 UDP 41885439 5.6.7.8 3478 typ relay raddr 10.0.0.1 rport 5000\r\n"
        )
        self.assertEqual(
            ice_candidate_type_counts(sdp),
            {"host": 1, "srflx": 1, "prflx": 0, "relay": 1},
        )


if __name__ == "__main__":
    unittest.main()
