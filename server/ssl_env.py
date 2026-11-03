"""Sanitize TLS env vars that crash some Windows OpenSSL builds."""

from __future__ import annotations

import os


def sanitize_sslkeylogfile(environ: dict[str, str] | None = None) -> str | None:
    """Drop SSLKEYLOGFILE values that are device paths, not files.

    Avast/AVG inject ``SSLKEYLOGFILE=\\\\.\\aswMonFltProxy\\...``. Opening that
    path during ``ssl.create_default_context()`` aborts with OPENSSL_Applink.
    """
    env = os.environ if environ is None else environ
    value = env.get("SSLKEYLOGFILE") or ""
    if not value:
        return None
    normalized = value.replace("/", "\\")
    unsafe = normalized.startswith("\\\\.\\") or "aswMonFltProxy" in normalized
    if not unsafe:
        return None
    env.pop("SSLKEYLOGFILE", None)
    return value
