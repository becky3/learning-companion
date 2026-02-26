"""GitHub Mermaid レンダラー互換性チェックスクリプト.

GitHub の Mermaid レンダラー（古いバージョン）が解釈できない構文を検出する。

仕様: docs/specs/agentic/agents/test-runner-agent.md

検出ルール:
  - [GH001] mermaid ブロック内の `#` 文字（CSS カラーコード `#xxx`/`#xxxxxx` は除外）

使い方:
  uv run python scripts/check_mermaid_compat.py "docs/**/*.md" "*.md" ".claude/**/*.md"
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

from src.compat import configure_stdio_encoding

# CSS カラーコード: スタイルプロパティ値として出現する #RGB or #RRGGBB のみ除外
# (例: fill:#fff, stroke:#000000)
# 単独の #123 等は Issue 番号の可能性があるため除外しない
_CSS_COLOR_RE = re.compile(r"(?<=:)#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")


def _find_mermaid_blocks(text: str) -> list[tuple[int, int]]:
    """Markdown テキストから mermaid コードブロックの行範囲を返す.

    Returns:
        (start_line, end_line) のリスト（1-indexed, 両端含む）
    """
    blocks: list[tuple[int, int]] = []
    lines = text.splitlines()
    in_block = False
    start = 0
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not in_block and stripped.startswith("```mermaid"):
            in_block = True
            start = i
        elif in_block and stripped == "```":
            blocks.append((start, i))
            in_block = False
    return blocks


def _check_hash_in_mermaid(
    filepath: Path, text: str
) -> list[tuple[str, int, str, str]]:
    """mermaid ブロック内の非カラーコード `#` を検出する."""
    violations: list[tuple[str, int, str, str]] = []
    lines = text.splitlines()
    blocks = _find_mermaid_blocks(text)

    for block_start, block_end in blocks:
        for line_no in range(block_start + 1, block_end):  # fence 行を除く
            line = lines[line_no - 1]
            if "#" not in line:
                continue
            # CSS カラーコードを除去した上で `#` が残るか判定
            cleaned = _CSS_COLOR_RE.sub("", line)
            if "#" in cleaned:
                violations.append((
                    str(filepath),
                    line_no,
                    '[GH001] mermaid ブロック内に "#" が含まれています'
                    "（GitHub レンダラーでパースエラーになります）",
                    line.rstrip(),
                ))
    return violations


def main() -> int:
    configure_stdio_encoding()

    parser = argparse.ArgumentParser(
        description="GitHub Mermaid レンダラー互換性チェック"
    )
    parser.add_argument(
        "patterns",
        nargs="+",
        metavar="GLOB_PATTERN",
        help="チェック対象の glob パターン（例: docs/**/*.md）",
    )
    args = parser.parse_args()

    all_violations: list[tuple[str, int, str, str]] = []

    seen: set[Path] = set()
    for pattern in args.patterns:
        for filepath_str in glob.glob(pattern, recursive=True):
            filepath = Path(filepath_str)
            if filepath in seen:
                continue
            seen.add(filepath)
            try:
                text = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"Warning: {filepath}: {exc}", file=sys.stderr)
                continue
            all_violations.extend(_check_hash_in_mermaid(filepath, text))

    for filepath_str, line_no, message, original in all_violations:
        print(f"{filepath_str}:{line_no}: {message}")
        print(f"  {original}")

    if all_violations:
        print(f"\n{len(all_violations)} violation(s) found.")
        return 1

    print("No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
