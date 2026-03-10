"""プラットフォーム互換ユーティリティ."""

from __future__ import annotations

import sys


def configure_stdio_encoding() -> None:
    """Windows cp932 環境でも日本語・絵文字を正しく出力するため stdout/stderr を UTF-8 に切り替える."""
    stdout = sys.stdout
    if (
        stdout is not None
        and getattr(stdout, "encoding", None)
        and stdout.encoding.lower() != "utf-8"
        and hasattr(stdout, "reconfigure")
    ):
        stdout.reconfigure(encoding="utf-8")

    stderr = sys.stderr
    if (
        stderr is not None
        and getattr(stderr, "encoding", None)
        and stderr.encoding.lower() != "utf-8"
        and hasattr(stderr, "reconfigure")
    ):
        stderr.reconfigure(encoding="utf-8")
