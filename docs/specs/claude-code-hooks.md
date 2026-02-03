# Claude Code Hooks による通知機能

## 概要

Claude Code の hooks 機能を使用して、ツール実行時やタスク完了時にデスクトップ通知や音で知らせる機能を実装。長時間かかるタスクの完了通知や、重要な確認時のアラートを提供する。

## 背景

- 参考記事: https://zenn.dev/is0383kk/articles/5d66a34b0a89be
- Claude Code は hooks 機能により、特定のイベント発生時にカスタムスクリプトを実行可能
- 長時間かかるタスクの完了通知や、重要な確認時のアラートに有用

## ユーザーストーリー

- 開発者として、Claude Code がユーザー確認を待っているときにデスクトップ通知を受け取りたい
- 開発者として、長時間タスクが完了したときに音やデスクトップ通知で知らせてほしい
- 開発者として、通知内容や対象イベントをカスタマイズしたい

## 技術仕様

### 設定ファイル

**ファイル: `.claude/hooks.json`**

```json
{
  "hooks": {
    "user-prompt-submit": {
      "command": ".claude/scripts/notify.sh",
      "args": ["確認が必要です", "Claude Codeが承認を待っています"]
    },
    "task-completed": {
      "command": ".claude/scripts/notify.sh",
      "args": ["タスク完了", "Claude Codeがタスクを完了しました"]
    },
    "tool-call-approved": {
      "command": ".claude/scripts/notify.sh",
      "args": ["ツール実行", "{{tool_name}} を実行中"]
    }
  }
}
```

**対応イベント:**
- `user-prompt-submit`: ユーザーの確認が必要な時（最優先）
- `task-completed`: タスク完了時
- `tool-call-approved`: ツール実行承認時

### 通知スクリプト

**ファイル: `.claude/scripts/notify.sh`**

クロスプラットフォーム対応の bash スクリプト:

- **macOS**: `osascript` によるネイティブ通知 + サウンド
- **Linux**: `notify-send` (libnotify) + オプションでサウンド
- **Windows**: PowerShell によるバルーン通知
- **フォールバック**: 通知コマンドがない環境では `stderr` にテキスト出力

**セキュリティ対策:**
- `set -euo pipefail` によるエラーハンドリング
- シェルインジェクション対策（変数の適切なエスケープ）
- エラー発生時の明示的なメッセージ表示

### 使用方法

`.claude/hooks.json` を編集してイベントや通知内容をカスタマイズ:

```json
{
  "hooks": {
    "user-prompt-submit": {
      "command": ".claude/scripts/notify.sh",
      "args": ["カスタムタイトル", "カスタムメッセージ"]
    }
  }
}
```

## 受け入れ条件

- [x] AC1: `.claude/hooks.json` が存在し、3つのイベントにフックが設定されている
- [x] AC2: `.claude/scripts/notify.sh` が実装され、実行可能権限がある
- [x] AC3: macOS環境でデスクトップ通知が表示される
- [x] AC4: Linux環境で `notify-send` 通知が表示される
- [x] AC5: 通知が表示されない環境でもエラーなく動作する
- [x] AC6: セキュリティ対策（シェルインジェクション対策、エラーハンドリング）が実装されている

## 技術的な注意点

- **セキュリティ**: フックスクリプトは任意コマンド実行可能なため、信頼できるスクリプトのみ設定
- **パフォーマンス**: 通知は非同期実行、Claude Code の動作を阻害しない
- **環境依存**: 各環境での通知コマンド存在確認とフォールバック処理が必須
- **設定の配置**: プロジェクト固有は `.claude/hooks.json`、グローバルは `~/.claude/hooks.json`

## 実装の優先順位

**Phase 1 (MVP)** — 完了:
- macOS + Linux のデスクトップ通知
- `user-prompt-submit` イベント対応
- 基本的な通知スクリプト
- セキュリティ対策

**Phase 2 (拡張)** — 完了:
- Windows対応
- 全イベント対応
- 音による通知追加

**Phase 3 (最適化)** — 未実装:
- 通知のカスタマイズ設定
- 通知頻度制御
- 通知音選択機能

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `.claude/hooks.json` | イベント駆動の通知設定 |
| `.claude/scripts/notify.sh` | クロスプラットフォーム対応の通知スクリプト |

## 参考資料

- [Zenn記事: Claude Codeのhooks機能について](https://zenn.dev/is0383kk/articles/5d66a34b0a89be)
- Issue #35: Hooks使って、確認時に音を鳴らす
- PR #45: 実装プルリクエスト
