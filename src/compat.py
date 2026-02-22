"""プラットフォーム互換ユーティリティ."""

from __future__ import annotations

import sys


def configure_stdio_encoding() -> None:
    """Windows cp932 環境でも日本語・絵文字を正しく出力するため stdout/stderr を UTF-8 に切り替える."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
