---
name: check-review-batch
description: 自動マージIssueの全PRをチェックし、対応概要・問題点・動作確認事項を報告する
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[issue-number]"
---

## タスク

`auto:review-batch` ラベル付きIssue（自動マージレビューIssue）に記録されたPRを一括チェックし、各PRの対応概要・問題点の有無・動作確認が必要な事項をレポートする。

仕様: docs/specs/check-review-batch-skill.md

## 手順

### 1. 対象Issueの特定

- `$ARGUMENTS` が指定されていればその番号を使う
- 未指定なら `auto:review-batch` ラベルのOpen Issueを自動検索:

  ```bash
  gh issue list --label "auto:review-batch" --state open \
    --json number,title --jq '.[0]'
  ```

- 見つからない場合は「`auto:review-batch` ラベルのOpen Issueが見つかりません」と表示して終了

### 2. Issue内容の取得

```bash
# Issue body の取得
gh issue view <Issue番号> --json body,title --jq '{title, body}'

# 全コメントの取得
gh issue view <Issue番号> --json comments --jq '.comments[].body'
```

### 3. PR番号の抽出

Issue body および全コメントのテキストから `## PR #(\d+):` パターンでPR番号を抽出する。

```bash
# body + comments から PR番号を抽出
gh issue view <Issue番号> --json body,comments --jq '
  [.body, (.comments[].body // empty)] | join("\n")
' | sed -n 's/.*## PR #\([0-9][0-9]*\):.*/\1/p'
```

PR番号が1件も見つからない場合は「PRが記録されていません」と表示して終了。

### 4. 各PRのチェック

抽出した各PR番号に対して以下を実行:

#### 4a. PR基本情報の取得

```bash
gh pr view <PR番号> --json title,state,mergedAt,headRefName,baseRefName,body
```

#### 4b. 変更ファイル一覧の取得

```bash
gh pr view <PR番号> --json files --jq '.files[].path'
```

#### 4c. 変更種別の判定

コミットメッセージまたはPRタイトルのプレフィックスから判定:

- `feat` / `fix` / `docs` / `ci` / `refactor` / `test`
- 判定できない場合は変更ファイルパスから推定:
  - `src/` の変更 → `feat`
  - `docs/` のみ → `docs`
  - `.github/` のみ → `ci`

#### 4d. PR差分の取得と変更内容の分析

```bash
gh pr diff <PR番号>
```

差分を読み、変更内容を簡潔に要約する（2〜3文程度）。

#### 4e. 問題点の検出

差分を分析し、以下の観点で問題点を検出する:

- **セキュリティ**: 入力検証不足、認証・認可のバイパス、インジェクション脆弱性
- **エラーハンドリング**: `except: pass` や例外の握り潰し
- **テスト不足**: `src/` の変更に対応するテストファイルの有無
- **既存機能への影響**: 公開APIの変更、設定ファイルの構造変更

問題がなければ「問題なし」と報告する。

#### 4f. 動作確認事項の判定

変更ファイルのパスに基づいて動作確認事項を自動判定する:

| 変更パス | 動作確認事項 |
| --- | --- |
| `src/services/` | Bot起動確認（`uv run python -m src.main`）、該当サービスの動作確認 |
| `src/bot/` | Bot起動確認、Slackでの動作確認 |
| `src/utils/` | 関連する機能の動作確認 |
| `.github/workflows/` | ワークフローの動作確認（次回トリガー時に確認） |
| `docs/` のみ | 動作確認不要（ドキュメントのみの変更） |
| `CLAUDE.md` のみ | 動作確認不要（開発ルールのみの変更） |
| `config/` | Bot起動確認、設定反映の確認 |
| `pyproject.toml` | 依存関係の確認、Bot起動確認 |

### 5. サマリーレポートの生成

以下のフォーマットでレポートを出力:

```markdown
## 自動マージレビュー: Issue #N のチェック結果

対象Issue: #N (タイトル)
PR数: X件

---

### PR #123: PRタイトル

**対応概要:**

- 変更種別: feat
- 変更ファイル:
  - `src/services/example.py`
  - `tests/test_example.py`
- 概要: 変更内容の簡潔な説明

**問題点:**

- なし / 問題の説明

**動作確認事項:**

- [ ] Bot起動確認（`uv run python -m src.main`）
- [ ] エラーログに異常がないこと

---

（各PRを繰り返し）

---

### 総評

- 全X件のPRをチェック
- 問題点が検出されたPR: N件 / なし
- 動作確認が必要なPR: N件
- ドキュメントのみの変更: N件（動作確認不要）
```

### 6. 確認完了の案内

レポート末尾に以下を表示:

```text
確認完了後、Issue #N をクローズしてください:
gh issue close <Issue番号>
```
