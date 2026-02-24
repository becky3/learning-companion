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

仕様書に記載する内容の基準を定義する。

**例外の扱い**: 各ルールの禁止事項は原則禁止だが、記載しないと仕様の理解が著しく困難になる場合は、プロジェクトオーナーの許可を得た上で例外的に記載できる。

### 6.1 技術詳細

**方針**: What（何をするか）/ Why（なぜそうするか）を中心に書く。How（どう実装するか）は原則書かない。

How を追加する場合は、AI が誤った実装判断をした実績に基づき、制約として追記する。追加時は理由を HTML コメントで記録する:

```markdown
<!-- How追加理由: PR #140 で os.kill の Windows 非互換が検出 -->
```

**許容例**:

- 振る舞いの要件（入出力、制約、不変条件）
- コンポーネント間の関係
- 具体例（エッジケースを含む）
- 「こうしてはいけない」制約

**禁止例**:

- 疑似コード・メソッド実装
- クラス名・メソッドシグネチャ
- 実装ステップ・タスクリスト

### 6.2 設定値

**方針**: 具体値を仕様書にハードコードしない。設定ファイルや環境変数の存在と意味のみ記述する。

**禁止例**:

- ポート番号・URL: `http://localhost:1234`
- 数値定数: `TOOL_LOOP_MAX_ITERATIONS = 10`
- テーブル名・カラム名: `conversations`, `user_profiles`
- ユーザー名: `becky3`
- モデル名: `Claude Sonnet 4.5`
- パラメータ閾値: `α = 0.8 ~ 0.95`

### 6.3 コード

**方針**: プロダクションコードの形式（Python クラス・関数定義・疑似コード等）をそのまま仕様書に貼らない。設計情報は仕様書の形式（自然言語・テーブル・mermaid 図）で表現する。

**許容例**:

- 自然言語での機能・振る舞いの説明
- Markdown テーブルでのデータ構造・項目定義
- mermaid 図（フロー図、クラス図、ER 図等）
- CLI コマンド例（`git checkout -b`, `gh pr create` 等）
- 設定ファイルの構造例（JSON, YAML 等）
- shellcheck ディレクティブ等の書式例

**禁止例**:

- dataclass 定義のコピペ
- クラス・関数の実装コード
- 疑似コード

### 6.4 受け入れ条件（AC）

**方針**: 仕様書に AC を書かない。AC は Issue に記載する。

仕様書に書くべきは「このシステムは常にこうあるべき」という恒久的な要件・制約であり、「この作業が完了したか」の判定基準（AC）は一時的な作業単位である Issue に紐づく。

### 6.5 過去情報

**方針**: 以下の情報を仕様書に書かない。これらは Git や GitHub の機能で管理する。

- 変更履歴（Git で管理）
- 実装ステータス・PR 番号（GitHub で管理）
- 関連 Issue 番号（GitHub Issue のリンク機能で管理）
- 取り消し線付きの旧 AC・完了済み AC

### 6.6 実験データ・コスト見積もり

**方針**: 仕様書に書かない。意思決定の根拠として残す場合は関連 Issue に記録する。

### 6.7 図・表

- **図**（フローチャート、シーケンス図等）: mermaid 形式を使用する。ASCII 図は使用しない
- **表**: Markdown テーブルを使用する

## 7. 文書種別テンプレート

<!-- TODO: Phase 1 で追加予定 -->
