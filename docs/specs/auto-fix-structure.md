# auto-fix.yml 構造リファクタリング設計書

## 概要

`auto-fix.yml`（937行、16個の `run: |` ブロック）のシェルスクリプトを外部ファイルに切り出し、`direct_prompt` を外部Markdownファイルに分離する。動作を変えず、保守性・テスト可能性・レビュー品質を向上させる。

**コンセプト**: 「YAMLはオーケストレーションのみ、ロジックはスクリプトに」

## 背景

- アーキテクト分析（[#257 コメント](https://github.com/becky3/ai-assistant/issues/257#issuecomment-3894836004)）で特定された構造的問題への対応
- 前提の Issue #293（エラーハンドリング統一 + ガード集約）は PR #294 で完了済み

### 現在の問題

| 問題 | 影響 |
|------|------|
| YAML内の巨大シェルスクリプト（937行中の大半がシェル） | shellcheck 不可、ローカルテスト不可 |
| `direct_prompt` の3重ネスト（YAML > シェル > bashコードブロック） | シンタックスハイライト不可、変数展開スコープが混乱 |
| レビュー時にYAMLとシェルの境界が不明確 | 目が滑りやすく、エラーハンドリング漏れの温床 |

## 現状分析

### `run: |` ブロック一覧（16個）

| # | ステップ名 | 行数 | 責務 | 外部化 |
|---|-----------|------|------|--------|
| 1 | Get PR number | 35 | PR番号取得（workflow_run → PR特定） | する |
| 2 | Check auto-implement scope | 15 | ブランチ名でスコープ判定 | しない（短い） |
| 3 | Remove auto-implement label | 40 | リンクIssueからラベル除去 | する |
| 4 | Check auto:failed label | 20 | failedラベル有無チェック | しない（短い） |
| 5 | Check loop count | 28 | ループカウント取得 | する |
| 6 | Check review result | 83 | GraphQLでunresolvedスレッド数を取得（リトライ付き） | する |
| 7 | Check forbidden patterns | 66 | 禁止ファイルパターンチェック | する |
| 8 | Evaluate guards | 23 | ガード集約・分岐パス判定 | しない（短い） |
| 9 | Handle loop limit | 15 | ループ上限到達時の通知 | しない（短い、通知のみ） |
| 10 | Handle forbidden | 18 | 禁止パターン検出時の通知 | しない（短い、通知のみ） |
| 11 | Post loop marker | 10 | ループマーカーコメント投稿 | しない（短い、通知のみ） |
| 12 | Auto-fix with Claude | N/A | claude-code-action（uses:） | prompt外部化 |
| 13 | Request re-review | 15 | `/review` コメント投稿 | しない（短い） |
| 14 | Merge check | 77 | マージ条件4項目チェック | する |
| 15 | Merge or dry-run | 69 | マージ実行 or ドライラン | する |
| 16 | Merge conditions not met | 12 | マージ条件未達通知 | しない（短い、通知のみ） |
| 17 | Handle errors | 42 | エラーハンドラ（fallback付き） | する |

**外部化の基準**: 概ね30行以上のロジックを含むブロック、または複雑な制御構造（ループ、リトライ等）を含むもの。短い通知ステップ（`source` + `gh_comment` のみ）はYAML内に残す。

## スクリプト分割設計

### ディレクトリ構造

```text
.github/
  scripts/
    auto-fix/
      _common.sh              # 既存（共通関数）
      get-pr-number.sh         # PR番号取得
      remove-label.sh          # auto-implementラベル除去
      check-loop-count.sh      # ループカウント取得
      check-review-result.sh   # レビュー結果判定（GraphQL + リトライ）
      check-forbidden.sh       # 禁止パターンチェック
      merge-check.sh           # マージ条件チェック
      merge-or-dryrun.sh       # マージ実行 or ドライラン
      handle-errors.sh         # エラーハンドラ
  prompts/
    auto-fix-check-pr.md       # direct_prompt テンプレート
```

### 各スクリプトの責務

#### `get-pr-number.sh`

- **責務**: workflow_run イベントからPR番号を特定
- **入力**: 環境変数 `PULL_REQUESTS_JSON`, `HEAD_BRANCH`
- **出力**: `$GITHUB_OUTPUT` に `number`, `skip` を書き出し
- **元ステップ**: #1 Get PR number
- **エラー方針**: PR未発見 → `skip=true`、API失敗/不正値 → `exit 1`

#### `remove-label.sh`

- **責務**: PR本文からリンクIssueを抽出し、`auto-implement` ラベルを除去
- **入力**: 環境変数 `PR_NUMBER`
- **出力**: なし（副作用のみ）
- **元ステップ**: #3 Remove auto-implement label
- **エラー方針**: ラベル未存在 → notice で続行、API失敗 → warning で続行

#### `check-loop-count.sh`

- **責務**: PR内のループマーカーコメント数をカウント
- **入力**: 環境変数 `PR_NUMBER`
- **出力**: `$GITHUB_OUTPUT` に `loop_count`, `limit_reached` を書き出し
- **元ステップ**: #5 Check loop count
- **エラー方針**: API失敗/不正値 → デフォルト0で続行

#### `check-review-result.sh`

- **責務**: GraphQL APIでunresolvedレビュースレッド数を取得（最大5回リトライ）
- **入力**: 環境変数 `PR_NUMBER`, `GITHUB_REPOSITORY`
- **出力**: `$GITHUB_OUTPUT` に `has_issues` を書き出し
- **元ステップ**: #6 Check review result
- **エラー方針**: 全リトライ失敗 → `exit 1`

#### `check-forbidden.sh`

- **責務**: PRの変更ファイル一覧から禁止パターンを検出
- **入力**: 環境変数 `PR_NUMBER`
- **出力**: `$GITHUB_OUTPUT` に `forbidden`, `forbidden_files` を書き出し
- **元ステップ**: #7 Check forbidden patterns
- **エラー方針**: ファイル一覧取得失敗 → `exit 1`（セキュリティ処理のため安全側）

#### `merge-check.sh`

- **責務**: マージ条件4項目（レビュー・CI・コンフリクト・ラベル）のチェック
- **入力**: 環境変数 `PR_NUMBER`
- **出力**: `$GITHUB_OUTPUT` に `merge_ready`, `reasons` を書き出し
- **元ステップ**: #14 Merge check
- **エラー方針**: API失敗 → 安全側に倒してマージ拒否

#### `merge-or-dryrun.sh`

- **責務**: `AUTO_MERGE_ENABLED` に応じてマージ実行 or ドライラン通知
- **入力**: 環境変数 `PR_NUMBER`, `AUTO_MERGE_ENABLED`, `ACTIONS_URL`
- **出力**: PRコメント投稿（副作用）
- **元ステップ**: #15 Merge or dry-run
- **エラー方針**: マージ失敗 → `auto:failed` 付与 + `exit 1`

#### `handle-errors.sh`

- **責務**: エラー時の `auto:failed` ラベル付与 + PRコメント（フォールバック付き）
- **入力**: 環境変数 `PR_NUMBER`, `COMMON_SCRIPT_PATH`, `ACTIONS_URL`
- **出力**: ラベル付与 + PRコメント（副作用、ベストエフォート）
- **元ステップ**: #17 Handle errors
- **エラー方針**: 全処理がベストエフォート（エラーハンドラ自体は失敗しない）

## 変数受け渡し設計

### 方針

| 情報の種類 | 受け渡し方法 | 理由 |
|-----------|-------------|------|
| GitHub Actions コンテキスト（`${{ }}` 式） | 環境変数（`env:`） | スクリプト内で `${{ }}` は展開できないため |
| ステップ間の出力 | `$GITHUB_OUTPUT` | GitHub Actions 標準の仕組み |
| 認証トークン | 環境変数（`env:` で `GH_TOKEN`） | gh CLI が自動参照 |
| ワークフロー固有の定数 | 環境変数（`env:`） | スクリプトの再利用性を高めるため |

### `${{ }}` 式の環境変数への変換

YAML内の `${{ }}` 式はスクリプト呼び出し前に `env:` ブロックで環境変数に変換する。スクリプト内では環境変数として参照する。

**変換例:**

```yaml
# 変換前（YAMLインライン）
run: |
  PR_NUMBER="${{ steps.pr-info.outputs.number }}"
  gh pr view "$PR_NUMBER" ...

# 変換後（スクリプト呼び出し）
run: bash "$GITHUB_WORKSPACE/.github/scripts/auto-fix/merge-check.sh"
env:
  PR_NUMBER: ${{ steps.pr-info.outputs.number }}
  GH_TOKEN: ${{ github.token }}
  GH_REPO: ${{ github.repository }}
```

**スクリプト側:**

```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"

# 必須環境変数の検証
: "${PR_NUMBER:?PR_NUMBER is required}"

# ロジック
gh pr view "$PR_NUMBER" ...
```

### 必須環境変数の検証パターン

各スクリプトの冒頭で、必須環境変数の存在を `${VAR:?message}` パターンで検証する。

```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"

: "${PR_NUMBER:?PR_NUMBER is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
```

### 環境変数一覧

| 環境変数 | 値の出所 | 使用スクリプト |
|---------|---------|--------------|
| `PR_NUMBER` | `steps.pr-info.outputs.number` | ほぼ全スクリプト |
| `GH_TOKEN` | `github.token` or `secrets.REPO_OWNER_PAT` | ほぼ全スクリプト |
| `GH_REPO` | `github.repository` | ほぼ全スクリプト |
| `PULL_REQUESTS_JSON` | `toJson(github.event.workflow_run.pull_requests)` | `get-pr-number.sh` |
| `HEAD_BRANCH` | `github.event.workflow_run.head_branch` | `get-pr-number.sh` |
| `AUTO_MERGE_ENABLED` | `vars.AUTO_MERGE_ENABLED` | `merge-or-dryrun.sh` |
| `ACTIONS_URL` | `github.server_url/.../runs/github.run_id` | 通知系スクリプト |
| `FORBIDDEN_FILES` | `steps.forbidden-check.outputs.forbidden_files` | 通知ステップ（YAML内） |
| `LOOP_COUNT` | `steps.loop-check.outputs.loop_count` | 通知ステップ（YAML内） |
| `MERGE_REASONS` | `steps.merge-check.outputs.reasons` | 通知ステップ（YAML内） |
| `COMMON_SCRIPT_PATH` | `$GITHUB_WORKSPACE/.github/scripts/auto-fix/_common.sh` | `handle-errors.sh` |

## prompt テンプレート外部化

### 現状の問題

`direct_prompt` は以下の3重ネスト構造:

```text
YAML (auto-fix.yml)
  └─ direct_prompt: | (YAMLリテラルブロック)
       └─ ```bash ... ``` (Markdownコードブロック)
            └─ シェルスクリプト（変数展開あり）
```

- シンタックスハイライトが効かない
- `${{ }}` と `$VAR` の変数展開スコープが混在
- 編集時にネストの把握が困難

### 設計

`direct_prompt` の内容を `.github/prompts/auto-fix-check-pr.md` に外部化する。

**YAMLでの読み込み:**

```yaml
- name: Auto-fix with Claude
  uses: anthropics/claude-code-action@...
  with:
    direct_prompt: |
      ${{ steps.load-prompt.outputs.prompt }}
```

**prompt の読み込みステップ:**

```yaml
- name: Load prompt template
  if: steps.guards.outputs.proceed == 'true' && steps.guards.outputs.path == 'auto_fix'
  id: load-prompt
  run: |
    set -euo pipefail
    TEMPLATE_PATH="$GITHUB_WORKSPACE/.github/prompts/auto-fix-check-pr.md"
    if [ ! -f "$TEMPLATE_PATH" ]; then
      echo "::error::Prompt template not found: $TEMPLATE_PATH"
      exit 1
    fi

    # テンプレート内のプレースホルダーを置換
    PROMPT=$(cat "$TEMPLATE_PATH")
    PROMPT="${PROMPT//\{\{PR_NUMBER\}\}/$PR_NUMBER}"

    # multiline output の設定
    echo "prompt<<PROMPT_EOF" >> "$GITHUB_OUTPUT"
    echo "$PROMPT" >> "$GITHUB_OUTPUT"
    echo "PROMPT_EOF" >> "$GITHUB_OUTPUT"
  env:
    PR_NUMBER: ${{ steps.pr-info.outputs.number }}
```

### テンプレート内の変数展開

`${{ }}` 式はGitHub Actionsのコンテキストでのみ展開されるため、外部ファイルでは使用できない。代わりにプレースホルダー `{{VAR_NAME}}` を使用し、読み込み時にシェルで置換する。

| テンプレート内 | 置換元 |
|--------------|--------|
| `{{PR_NUMBER}}` | `steps.pr-info.outputs.number` |

**テンプレートファイルの形式:**

````markdown
PR #{{PR_NUMBER}} のレビュー指摘に対応してください。
以下の手順を順番に全て実行すること。途中で停止しないこと。

## ステップ 1/8: PR情報の確認

```bash
gh pr view {{PR_NUMBER}} --json title,body,headRefName,baseRefName
...
```
````

### markdownlint 対応

- `.github/prompts/auto-fix-check-pr.md` を markdownlint のチェック対象に追加
- 必要に応じて `.markdownlint-cli2.jsonc` でファイル固有のルール設定を追加

## 等価性担保

### 確認方法

#### 1. 静的等価性チェック

- 各スクリプトの入出力（環境変数、`$GITHUB_OUTPUT`）が元のインラインコードと一致することを目視確認
- チェックリスト:
  - [ ] 全ての `echo "..." >> $GITHUB_OUTPUT` が保持されている
  - [ ] 全ての `exit 1` / `return 1` の条件が同一
  - [ ] `env:` ブロックの環境変数が全て渡されている
  - [ ] `_common.sh` の source パスが正しい

#### 2. shellcheck による品質チェック

外部化により shellcheck が適用可能になるため、隠れていたバグの検出が期待できる。ただし、shellcheck で検出される問題は等価性とは別の品質改善として修正する。

#### 3. 実環境テスト

以下のテスト用Issueで auto-fix パイプラインの動作を確認:

| テストケース | Issue | 期待される分岐パス |
|-------------|-------|------------------|
| 禁止パターン検出 | #271（CLAUDE.md変更） | `forbidden_detected` |
| 通常の実装 + レビュー | #284 or #286 | `auto_fix` → レビューループ |
| マージ条件チェック | レビュー指摘なしのPR | `merge_check` |

#### 4. 差分比較

リファクタリング前後で以下が変わらないことを確認:

- ステップの実行順序
- 各ステップの `if` 条件
- `$GITHUB_OUTPUT` への出力変数名と値のフォーマット
- PRコメントの文面（テンプレートリテラル部分）

## shellcheck 適用方針

### 対象

- `.github/scripts/auto-fix/*.sh` の全ファイル
- 既存の `_common.sh` も含む

### 設定

プロジェクトルートに `.shellcheckrc` を配置:

```text
# GitHub Actions 環境で使用するシェルスクリプト用
shell=bash
# 外部ソースのファイルを追従
external-sources=true
# 未使用変数の警告を抑制（GITHUB_OUTPUT への書き出しパターン）
# 必要に応じて個別に disable
```

### CI への組み込み

`.github/workflows/auto-fix.yml` のテストではなく、既存の CI（pr-review.yml 等）に shellcheck ステップを追加する方針を推奨。ただし、auto-fix.yml 自体のスコープからは外れるため、別 Issue で対応する。

**暫定対応**: PR レビュー時に手動で `shellcheck` を実行。

```bash
shellcheck .github/scripts/auto-fix/*.sh
```

### 抑制が必要な既知パターン

| コード | 理由 | 対応 |
|--------|------|------|
| SC2154 | `$GITHUB_OUTPUT` 等の環境変数がスクリプト外で定義 | `# shellcheck disable=SC2154` or `.shellcheckrc` |
| SC2086 | 意図的な word splitting（該当箇所がある場合） | 個別に `# shellcheck disable=SC2086` |

## `_common.sh` の拡張

### 現在の関数（5個）

| 関数 | 用途 |
|------|------|
| `gh_safe` | 失敗時 `::error::` + `exit 1` |
| `gh_safe_warning` | 失敗時 `::warning::` + `return 1` |
| `gh_best_effort` | 失敗時 `::error::` のみ（`exit` しない） |
| `gh_comment` | PRコメント投稿ラッパー |
| `validate_numeric` | 数値バリデーション |

### 追加候補

| 関数 | 用途 | 追加理由 |
|------|------|---------|
| `require_env` | 必須環境変数の検証 | 各スクリプト冒頭の `${VAR:?}` パターンを共通化 |
| `output` | `$GITHUB_OUTPUT` への書き出しラッパー | `echo "key=value" >> "$GITHUB_OUTPUT"` の繰り返しを簡素化 |

**`require_env` の実装案:**

```bash
# require_env: 必須環境変数の存在を検証
# 用途: スクリプト冒頭で必須パラメータを検証
# 使用例: require_env PR_NUMBER GITHUB_OUTPUT
require_env() {
  local missing=()
  for var in "$@"; do
    if [ -z "${!var:-}" ]; then
      missing+=("$var")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "::error::Missing required environment variables: ${missing[*]}" >&2
    exit 1
  fi
}
```

**`output` の実装案:**

```bash
# output: $GITHUB_OUTPUT にキー=値を書き出し
# 用途: ステップ出力の設定
# 使用例: output "number" "$PR_NUMBER"
output() {
  local key="$1"
  local value="$2"
  echo "$key=$value" >> "$GITHUB_OUTPUT"
}
```

**判断**: `require_env` は追加する。`output` は追加を検討するが、`echo >> $GITHUB_OUTPUT` でも十分簡潔なため、必須ではない。実装時に判断する。

## YAML変換後のイメージ

### 変換前（例: Get PR number）

```yaml
- name: Get PR number from workflow_run
  id: pr-info
  run: |
    set -euo pipefail
    PR_NUMBER=$(echo '${{ toJson(...) }}' | jq -r '...')
    # ... 35行のシェルスクリプト ...
    echo "number=$PR_NUMBER" >> $GITHUB_OUTPUT
  env:
    GH_TOKEN: ${{ github.token }}
    GH_REPO: ${{ github.repository }}
```

### 変換後

```yaml
- name: Get PR number from workflow_run
  id: pr-info
  run: bash "$GITHUB_WORKSPACE/.github/scripts/auto-fix/get-pr-number.sh"
  env:
    GH_TOKEN: ${{ github.token }}
    GH_REPO: ${{ github.repository }}
    PULL_REQUESTS_JSON: ${{ toJson(github.event.workflow_run.pull_requests) }}
    HEAD_BRANCH: ${{ github.event.workflow_run.head_branch }}
```

### YAML内に残すステップ（短い通知系）

以下のステップはスクリプト外部化せず、YAML内に残す:

- Check auto-implement scope（15行、単純な分岐）
- Check auto:failed label（20行、単純なチェック）
- Evaluate guards（23行、step outputs の読み取りのみ）
- Handle loop limit（15行、`source` + `gh_comment`）
- Handle forbidden（18行、`source` + `gh_comment`）
- Post loop marker（10行、`source` + `gh_comment`）
- Request re-review（15行、`source` + `gh_safe`）
- Merge conditions not met（12行、`source` + `gh_comment`）

## 実装手順

### ステップ 1: スクリプトファイルの作成

1. 各スクリプトファイルを `.github/scripts/auto-fix/` に作成
2. 元の `run: |` ブロックからロジックを移植
3. `${{ }}` 式を環境変数参照に置換
4. `source "$(dirname "$0")/_common.sh"` を冒頭に追加
5. 必須環境変数の検証を追加

### ステップ 2: prompt テンプレートの作成

1. `direct_prompt` の内容を `.github/prompts/auto-fix-check-pr.md` に移動
2. `${{ }}` 式を `{{VAR_NAME}}` プレースホルダーに置換
3. prompt 読み込みステップを追加

### ステップ 3: YAML の書き換え

1. 外部化対象のステップを `bash "$GITHUB_WORKSPACE/.github/scripts/auto-fix/XXX.sh"` に置換
2. `env:` ブロックに必要な環境変数を追加
3. YAML内に残すステップはそのまま維持

### ステップ 4: 品質チェック

1. `shellcheck .github/scripts/auto-fix/*.sh` で全スクリプトをチェック
2. `markdownlint` で prompt テンプレートをチェック
3. 等価性チェックリストの確認

### ステップ 5: 実環境テスト

1. テスト用Issueで auto-fix パイプラインを実行
2. 各分岐パスの動作を確認

## 受け入れ条件

- [ ] AC1: `auto-fix.yml` の外部化対象ステップが `.github/scripts/auto-fix/` の独立スクリプトに切り出されている
- [ ] AC2: `direct_prompt` が `.github/prompts/auto-fix-check-pr.md` に外部ファイル化されている
- [ ] AC3: `shellcheck` が全スクリプトに対して通過する
- [ ] AC4: `markdownlint` が prompt テンプレートに対して通過する
- [ ] AC5: 既存の auto-fix ワークフローの動作が変わらないこと（機能的に等価）
- [ ] AC6: `_common.sh` が全スクリプトから正しく source されること
- [ ] AC7: `${{ }}` 式が全て環境変数経由でスクリプトに渡されること
- [ ] AC8: 短い通知ステップ（30行未満）はYAML内に残っていること

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `.github/workflows/auto-fix.yml` | リファクタリング対象のワークフロー |
| `.github/scripts/auto-fix/_common.sh` | 既存の共通関数（拡張対象） |
| `.github/scripts/auto-fix/*.sh` | 新規作成するスクリプト群 |
| `.github/prompts/auto-fix-check-pr.md` | 新規作成する prompt テンプレート |
| `docs/specs/auto-progress.md` | auto-fix の仕様書（本設計書の上位仕様） |

## 参考資料

- [アーキテクト分析（#257 コメント）](https://github.com/becky3/ai-assistant/issues/257#issuecomment-3894836004)
- [Issue #295: 構造リファクタリング](https://github.com/becky3/ai-assistant/issues/295)
- [ShellCheck](https://www.shellcheck.net/)
- [GitHub Actions — ワークフローコマンド](https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions)
