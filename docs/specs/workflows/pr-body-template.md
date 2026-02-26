# PR Body テンプレート

## 概要

PR 作成時の body を `.github/pull_request_template.md` で標準化し、記載内容の統一と記載漏れの防止を図る仕様。

本仕様は PR body（description）のみを対象とする。PR コメント（レビューサマリー等）には適用しない。

## 背景

- PR body の記載内容が自由記述のため、記載漏れが発生しやすかった
- テンプレートとして構造化することで、記載漏れを防止する
- AI・人間の両方が一貫した形式で PR を作成できるようにする

## 設計方針

| # | 方針 | 根拠 |
|---|------|------|
| 1 | セクション数は 4 つに制限 | 5-7 を超えると形骸化するリスクが高い |
| 2 | テンプレートファイルを SSOT（Single Source of Truth）とする | CLAUDE.md・auto-finalize スキルはテンプレート参照に正規化 |
| 3 | 変更種別の明示が目的 | Change type により変更の意図が伝わる |
| 4 | AI・人間の両方に使いやすく | CLI（`gh pr create --body`）では自動適用されないため、CLAUDE.md にもルールを記載 |

## セクション構成

テンプレートは以下の 4 セクションで構成する。

| セクション | 必須/任意 | 形式 | 説明 |
|-----------|----------|------|------|
| Change type | 必須 | チェックボックス（複数可） | 変更の性質を明示 |
| Summary | 必須 | 箇条書き | 変更内容の概要 |
| Test plan | 推奨（省略可） | チェックリスト | typo 修正・軽微な変更時は省略可 |
| Related issues | 必須 | `Closes #N` | Issue 紐付け |

### 不採用としたセクション

| セクション | 不採用理由 |
|-----------|-----------|
| 変更ファイル一覧 | PR の Files changed タブで確認可能 |
| Breaking changes | 内部ツールであり外部 API を公開していない |
| Screenshots | UI コンポーネントがない（Slack bot + CLI） |
| Reviewer 指定 | Copilot が自動レビューするため不要 |
| Context（背景） | Summary に含められる。セクション数制限のため独立セクションとしない |

## Change type

コミットメッセージの prefix と一致させ、一貫性を保つ。

| 種別 | 対応するコミット prefix | 説明 |
|------|----------------------|------|
| `feat` | `feat(scope):` | 新機能実装 |
| `fix` | `fix:` | バグ修正 |
| `docs` | `docs:` | ドキュメント更新（仕様書・README 等） |
| `docs(pre-impl)` | `docs:` | 設計書先行更新。実装は後続フェーズで行う |
| `refactor` | `refactor:` | リファクタリング（機能変更なし） |
| `ci` | `ci:` | CI/CD・GitHub Actions の改善 |
| `test` | `test:` | テスト追加・修正 |

### docs(pre-impl) の扱い

`docs(pre-impl)` を選択した場合、以下が暗黙的に宣言される:

- 現在のコードとの不整合は意図的である
- 実装は後続フェーズ（別PR）で行う
- 自動レビューはコードとの不整合を検出対象外とすべき

テンプレート内の HTML コメントでこの注記を表示し、記載漏れを防止する。

### 複数種別の選択

複合的な変更の場合:

- 複数のチェックボックスにチェックを入れる
- 主な種別に `★` を付記する
- コミットメッセージの prefix は主な種別に合わせる

## CLI からの利用

`.github/pull_request_template.md` は Web UI からの PR 作成時のみ自動適用される。CLI（`gh pr create --body`）では自動適用されないため、CLAUDE.md の PR 作成指示でテンプレート形式に従う旨を明記している。

## 関連ドキュメント

- `.github/pull_request_template.md` — テンプレート本体（SSOT）
- `CLAUDE.md` — PR body ルール・`gh pr create` の例
- `.claude/skills/auto-finalize/SKILL.md` — auto-finalize スキルの PR 作成手順
- `docs/specs/workflows/git-flow.md` — git-flow 運用仕様
