"""ICE / TURN helpers for SmallWebRTC on hosted platforms such as Render.

Render's HTTP proxy does not forward UDP to the bot process. STUN-only
SmallWebRTC therefore stays in ICE ``checking`` and the hosted UI retries
the same ``pc_id``. TURN (UDP and, ideally, TLS on 443) is required.
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_STUN_URL = "stun:stun.l.google.com:19302"


def _as_url_list(urls: Any) -> list[str]:
    if urls is None:
        return []
    if isinstance(urls, str):
        return [urls] if urls.strip() else []
    return [str(item) for item in urls if str(item).strip()]


def parse_ice_servers(value: str | list[str] | None) -> list[dict[str, Any]]:
    """Parse PIPECAT_ICE_SERVERS the same way the Pipecat runner does."""
    if not value:
        return []

    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            entries: list[Any] = json.loads(text)
            if not isinstance(entries, list):
                raise ValueError("expected a JSON array of ICE servers")
        elif text.startswith("{"):
            entries = [text]
        else:
            entries = [item.strip() for item in text.split(",") if item.strip()]
    else:
        entries = list(value)

    ice_servers: list[dict[str, Any]] = []
    allowed = {"urls", "username", "credential"}
    for entry in entries:
        if isinstance(entry, str):
            text = entry.strip()
            if not text:
                continue
            if text.startswith("{"):
                entry = json.loads(text)
            else:
                ice_servers.append({"urls": text})
                continue
        if not isinstance(entry, dict):
            raise ValueError(f"expected a URL or a JSON object, got {entry!r}")
        unknown = set(entry) - allowed
        if unknown:
            raise ValueError(f"unsupported ICE server keys: {sorted(unknown)}")
        if not entry.get("urls"):
            raise ValueError("missing 'urls' in ICE server")
        ice_servers.append({key: entry[key] for key in entry if entry[key] is not None})
    return ice_servers


def ice_server_urls(servers: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for server in servers:
        urls.extend(_as_url_list(server.get("urls")))
    return urls


def has_turn(servers: list[dict[str, Any]]) -> bool:
    return any(url.lower().startswith("turn") for url in ice_server_urls(servers))


def ice_candidate_type_counts(sdp: str) -> dict[str, int]:
    counts = {"host": 0, "srflx": 0, "prflx": 0, "relay": 0}
    for line in sdp.splitlines():
        for kind in counts:
            if f" typ {kind}" in line:
                counts[kind] += 1
    return counts


def build_ice_servers(
    existing: str | list[str] | None = None,
    turn_urls: str | None = None,
    turn_username: str | None = None,
    turn_credential: str | None = None,
) -> list[dict[str, Any]]:
    servers = parse_ice_servers(existing)
    urls = {url.lower() for url in ice_server_urls(servers)}
    if DEFAULT_STUN_URL.lower() not in urls:
        servers.insert(0, {"urls": DEFAULT_STUN_URL})

    relay_urls = [item.strip() for item in (turn_urls or "").split(",") if item.strip()]
    username = (turn_username or "").strip()
    credential = (turn_credential or "").strip()
    if relay_urls and username and credential:
        already = {url.lower() for url in ice_server_urls(servers)}
        new_urls = [url for url in relay_urls if url.lower() not in already]
        if new_urls:
            payload: dict[str, Any] = {
                "urls": new_urls if len(new_urls) > 1 else new_urls[0],
                "username": username,
                "credential": credential,
            }
            servers.append(payload)
    return servers


def apply_ice_servers_env(environ: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Merge STUN/TURN into PIPECAT_ICE_SERVERS before the Pipecat runner parses CLI args."""
    env = os.environ if environ is None else environ
    servers = build_ice_servers(
        existing=env.get("PIPECAT_ICE_SERVERS"),
        turn_urls=env.get("TURN_URLS") or env.get("PIPECAT_TURN_URLS"),
        turn_username=env.get("TURN_USERNAME") or env.get("PIPECAT_TURN_USERNAME"),
        turn_credential=env.get("TURN_CREDENTIAL") or env.get("PIPECAT_TURN_CREDENTIAL"),
    )
    env["PIPECAT_ICE_SERVERS"] = json.dumps(servers)
    return servers
