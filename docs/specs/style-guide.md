# 仕様書スタイルガイド

Issue: #620 (Phase 1 of #572)

仕様書（`docs/specs/` 配下）の分類・構成・記述ルールを定義する。
全ての仕様書はこのスタイルガイドに準拠すること。

---

## 1. ディレクトリ構造

```
docs/specs/
  features/           → ユーザー向けプロダクト機能
  infrastructure/     → 基盤・内部システム・開発ツール
  workflows/          → 開発プロセス・CI/CD
    github/           → GitHub Actions 関連
  agentic/            → AI エージェント関連
    agents/           → エージェント定義
    skills/           → スキル定義
    teams/            → チーム定義
    hooks/            → フック定義
  style-guide.md      → 本ファイル（スタイルガイド）
  overview.md         → プロジェクト俯瞰
  pr-body-template.md → PR テンプレート仕様
```

### 分類基準

| カテゴリ | 配置先 | 判断基準 |
|---------|--------|---------|
| ユーザー向け機能 | `features/` | ユーザーが直接触る・意識するプロダクト機能 |
| 基盤・ツール | `infrastructure/` | ユーザーが直接意識しない裏側の仕組み、開発ツール |
| 開発プロセス | `workflows/` | 開発フロー・CI/CD・自動化プロセスの定義 |
| GitHub 固有 | `workflows/github/` | GitHub Actions 上で動く仕組み |
| エージェント | `agentic/agents/` | AI エージェントの振る舞い・観点の定義 |
| スキル | `agentic/skills/` | スキルの手順・入出力の定義 |
| チーム | `agentic/teams/` | チーム運用・構成パターンの定義 |
| フック | `agentic/hooks/` | エージェントのフック機能の定義 |
| メタ文書 | `docs/specs/` 直下 | 仕様書全体に関わる横断的な文書 |

### ファイル所属一覧

| カテゴリ | ファイル |
|---------|--------|
| `features/` | chat-response, feed-management, user-profiling, topic-recommend, auto-reply, bot-status, thread-support, slack-formatting |
| `infrastructure/` | mcp-integration, rag-knowledge, cli-adapter, bot-process-guard |
| `workflows/github/` | auto-progress, copilot-auto-fix, claude-code-actions |
| `workflows/` | git-flow |
| `agentic/agents/` | code-review-agent, doc-review-agent, planner-agent, test-runner-agent |
| `agentic/skills/` | check-review-batch-skill, doc-gen-skill, handoff-skill, topic-skill |
| `agentic/teams/` | common, fixed-theme, mixed-genius |
| `agentic/hooks/` | claude-code-hooks |
| ルート直下 | style-guide, overview, pr-body-template |

## 2. ファイル命名規則

### 基本ルール

- **ケバブケース**（ハイフン区切り）を使用: `chat-response.md`
- f番号は使用しない（廃止）
- サフィックス（`-agent`, `-skill`）はディレクトリで種別がわかる場合も維持する
  - 理由: ファイル単体で見ても種別が判別できる

### 命名の原則

- ファイル名だけで機能の概要がわかること
- 略語のみ（`rag`, `mcp`）は避け、補足を付ける（`rag-knowledge`, `mcp-integration`）
- 実装手段ではなく機能の目的を表す名前にする

### f番号からの移行対応表

| 旧名 | 新名 | 変更理由 |
|------|------|---------|
| f1-chat | chat-response | 「応答」機能であることを明示 |
| f2-feed-collection | feed-management | 収集・配信・管理を包含する名前に |
| f3-user-profiling | user-profiling | f番号のみ除去 |
| f4-topic-recommend | topic-recommend | f番号のみ除去 |
| f5-mcp-integration | mcp-integration | f番号のみ除去 |
| f6-auto-reply | auto-reply | f番号のみ除去 |
| f7-bot-status | bot-status | f番号のみ除去 |
| f8-thread-support | thread-support | f番号のみ除去 |
| f9-rag | rag-knowledge | 「ナレッジ」を補足。蓄積+検索を包含 |
| f10-slack-mrkdwn | slack-formatting | Slack 固有用語 "mrkdwn" を一般的な表現に |
| f11-cli-adapter | cli-adapter | f番号のみ除去 |

## 3. コミットメッセージ規約

### 基本形式

```
type(scope): 説明 (#Issue番号)
```

### scope のルール

- 仕様書のファイル名（拡張子なし）を使用する
- 複数機能にまたがる場合はカンマ区切り: `feat(chat-response,thread-support):`
- 仕様書に対応しない変更は従来通り: `docs:`, `chore:`, `ci:` 等

### type 一覧

| type | 用途 |
|------|------|
| `feat` | 新機能・機能追加 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `refactor` | リファクタリング（機能変更なし） |
| `test` | テストの追加・修正 |
| `chore` | ビルド・設定等の雑務 |
| `ci` | CI/CD 関連 |

### 例

```
feat(rag-knowledge): RAG 検索精度を改善 (#123)
feat(chat-response,thread-support): スレッド履歴を応答に統合 (#456)
fix(feed-management): RSS 取得タイムアウト修正 (#789)
docs(git-flow): ブランチ命名規約を更新
```

## 4. PR テンプレートでの記載

PR の Change type や関連仕様の記載には、カテゴリを含むフルパスを使用する:

```
features/chat-response
features/thread-support
infrastructure/rag-knowledge
workflows/github/auto-progress
agentic/agents/code-review-agent
```

## 5. ブランチ命名規約

f番号を使用せず、機能名ベースで命名する:

```
feature/{機能名}-#{Issue番号}
bugfix/{修正内容}-#{Issue番号}
```

### 例

```
feature/rag-knowledge-#123
feature/chat-response-#456
bugfix/feed-timeout-#789
```

## 6. 記述ルール

<!-- TODO: Phase 1 で追加予定 -->

## 7. 文書種別テンプレート

<!-- TODO: Phase 1 で追加予定 -->
