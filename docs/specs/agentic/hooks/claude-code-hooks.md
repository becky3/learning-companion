# Claude Code Hooks

## 概要

Claude Code の hooks 機能を使用して、デスクトップ通知・操作ガード・コンテキスト保護を提供する。長時間タスクの完了通知、重要な確認時のアラート、破壊的操作やチーム運用時のガードを担う。

## 背景

- 長時間かかるタスクの完了や確認待ち状態をユーザーが見逃すことがある
- エージェントチーム運用時にリーダーが直接ファイル編集しないルールを技術的に制約する必要がある
- 破壊的な GitHub 操作（Issue 削除等）を誤って実行するリスクがある
- コンテキスト圧縮時に重要なルールが失われる問題がある

## 制約

- シェルスクリプトは LF 改行コードで保存すること（CRLF だとエラー）
- フックスクリプトは任意コマンド実行可能なため、信頼できるスクリプトのみ設定する
- `permissions.allow` の自動許可が `PreToolUse` の deny を上書きする可能性がある

## 対象イベント

| イベント | matcher | 用途 |
|---|---|---|
| `PreToolUse` | `Bash` | 破壊コマンドガード |
| `PreToolUse` | `Edit` | リーダーガード |
| `PreToolUse` | `Write` | リーダーガード |
| `PreCompact` | `*` | コンテキスト圧縮前のルール注入 |
| `Notification` | `*` | ユーザー入力待ち通知 |
| `PermissionRequest` | `*` | ツール実行許可待ち通知 |
| `Stop` | `*` | タスク完了通知 |

**設定形式のポイント**:

- イベント名は PascalCase（例: `Stop`, `Notification`）
- 各イベントは配列で、`matcher` と `hooks` を含むオブジェクトを持つ
- パスは相対パスを使用

**Notification イベントの matcher 値**:

- `*`: 全ての通知タイプをキャッチ
- `permission_prompt`: ツール許可ダイアログ表示時
- `idle_prompt`: アイドル状態で入力待機時
- `elicitation_dialog`: 選択肢提示時
- `auth_success`: 認証成功時

## 処理内容

### 通知スクリプト

クロスプラットフォーム対応のデスクトップ通知を行う。

| プラットフォーム | 通知方法 |
|---|---|
| macOS | `osascript` によるネイティブ通知 + サウンド |
| Linux | `notify-send` (libnotify) |
| Windows | PowerShell によるバルーン通知（PowerShell Core 優先、フォールバックあり） |
| その他 | stderr にテキスト出力（フォールバック） |

通知は非同期実行し、Claude Code の動作を阻害しない。

### リーダーガード

エージェントチーム運用時に、リーダーの Edit / Write ツール使用をブロックする。

**入力**: stdin から JSON を受け取り、`permission_mode` フィールドでリーダー／メンバーを判別する。

**判定ロジック**:

1. `permission_mode` が `"bypassPermissions"` または `"acceptEdits"` → メンバー → 通過
2. `~/.claude/teams/` 配下にサブディレクトリなし → チーム非稼働 → 通過
3. チームの config.json から `pattern` を読み取る
   - `pattern` 未設定 → fail-open（通過）
   - `pattern` が `"fixed-theme"` 以外（`"mixed-genius"` 等）→ 通過
4. fixed-theme パターン + リーダー + チーム稼働中 → deny 応答でブロック

**fail-open 設計**: 入力読み取り失敗、環境変数未定義、pattern 未設定等のエラー時はブロックせず通過する。

### 破壊コマンドガード

`gh * delete` 系コマンド（Issue 削除、リポジトリ削除、リリース削除、ラベル削除）を検出してブロックする。

実行が必要な場合はターミナルから直接実行する。

### コンテキスト圧縮前ルール注入

`PreCompact` イベントで、コンテキスト圧縮前に重要なルールを再注入する。圧縮後も保持すべきルール（矛盾がある場合の確認ルール等）を stdout に出力する。

## 関連ドキュメント

- [エージェントチーム共通仕様](../teams/common.md): リーダー管理専任ルール
- `.claude/scripts/notify.sh`: 通知スクリプト
- `.claude/scripts/leader-guard.sh`: リーダーガードスクリプト
- `.claude/scripts/destructive-command-guard.sh`: 破壊コマンドガードスクリプト
- `.claude/scripts/precompact_rule.sh`: コンテキスト圧縮前ルール注入スクリプト
