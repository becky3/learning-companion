#!/usr/bin/env python3
"""ジャーナルJSONLローリングスクリプト

journal.jsonl が MAX_ENTRIES 件を超えた場合、
古いエントリを journal-archive.jsonl に移動する。

仕様: docs/specs/handoff-skill.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAX_ENTRIES = 10


def load_jsonl(path: Path) -> list[dict[str, object]]:
    """JSONLファイルを読み込み、各行を辞書のリストとして返す。

    空行はスキップする。ファイルが存在しない場合は空リストを返す。
    """
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError as e:
            print(f"Warning: {path}:{line_no}: invalid JSON, skipping: {e}", file=sys.stderr)
    return entries


def save_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    """辞書のリストをJSONLファイルに書き込む。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def roll(memory_dir: Path) -> int:
    """ローリングを実行し、移動したエントリ数を返す。"""
    journal_path = memory_dir / "journal.jsonl"
    archive_path = memory_dir / "journal-archive.jsonl"

    entries = load_jsonl(journal_path)
    if len(entries) <= MAX_ENTRIES:
        return 0

    keep = entries[:MAX_ENTRIES]
    overflow = entries[MAX_ENTRIES:]

    archive = load_jsonl(archive_path)
    # 新しいエントリ(overflow の先頭が最も新しい)をアーカイブの先頭に追加
    updated_archive = overflow + archive

    save_jsonl(journal_path, keep)
    save_jsonl(archive_path, updated_archive)

    return len(overflow)


def main() -> None:
    parser = argparse.ArgumentParser(description="ジャーナルJSONLローリング")
    parser.add_argument(
        "memory_dir",
        type=Path,
        help="メモリディレクトリのパス",
    )
    args = parser.parse_args()

    memory_dir: Path = args.memory_dir
    if not memory_dir.is_dir():
        print(f"Error: ディレクトリが見つかりません: {memory_dir}", file=sys.stderr)
        sys.exit(1)

    moved = roll(memory_dir)
    if moved > 0:
        print(f"{moved} 件のエントリをアーカイブに移動しました")
    else:
        print("ローリング不要（10件以下）")


if __name__ == "__main__":
    main()
