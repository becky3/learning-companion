---
paths:
  - "**/*.py"
  - "**/*.sh"
---

# コーディング規約

- 各サービスクラスのdocstringに仕様書パスを記載: `仕様: docs/specs/features/xxx.md`
- テスト名は `test_` プレフィックス + snake_case で、テスト対象の振る舞いがわかる名前をつける（例: `test_rss_feed_is_fetched_and_parsed()`）
- コード品質チェック（ruff, mypy, shellcheck）は test-runner エージェント経由で実行する。ドキュメント品質チェックは `/doc-lint` スキルで実行する
- shellcheck の suppress コメントはディレクティブ行と説明行を分ける:

    ```bash
    # Reason for suppression
    # shellcheck disable=SC2016
    ```

- **フォールバック/暗黙のデフォルト値の禁止**
  - 関数の引数が `None` の場合に settings/env から暗黙に取得するパターンは禁止。呼び出し元が値の出所を決定すること
  - argparse の `default` で具体値を設定するのではなく `required=True` にして明示させること
  - 適用対象: 評価CLI・テストツール・スクリプトの関数引数・argparse
  - 適用対象外: 本番コード（`main.py`）の settings 参照、基盤設定（DB接続先等）、スキル/エージェント定義のデフォルト値
