---
name: doc-gen
description: プロジェクトドキュメント（仕様書）の新規作成
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
argument-hint: "spec [feature-name]"
---

## タスク

プロジェクトドキュメントを自動生成する。Issue/PR/コミット履歴から情報を収集し、CLAUDE.mdのルールに従ったフォーマットで出力する。

仕様: docs/specs/agentic/skills/doc-gen-skill.md

## 引数

`$ARGUMENTS` の形式:

- `spec <feature-name>`: 仕様書生成（例: `spec feed-collection`）

## 処理手順

### 共通フロー

1. **引数解析**

   ```bash
   ARGS=($ARGUMENTS)
   DOC_TYPE="${ARGS[0]}"  # spec
   FEATURE_NAME="${ARGS[1]}"  # 機能名
   ```

2. **既存ドキュメントの参照**
   - 同種のドキュメントを1-2件読み込み、フォーマットを理解する

3. **出力ファイル名の決定**
   - CLAUDE.mdの命名規則に従う
   - 既存ファイルがある場合は警告を表示し、上書き確認

4. **ドキュメント生成**
   - テンプレートに従って各セクションを作成
   - 関連情報（Issue/PR/コミット）を調査・反映

5. **ファイル保存**
   - Writeツールでファイルを作成
   - 生成結果を表示

### A. 仕様書生成 (`spec <feature-name>`)

**出力先**: `docs/specs/{category}/{feature-name}.md`

**手順**:

1. カテゴリの決定
   - `docs/specs/style-guide.md`（セクション1: ディレクトリ構成）を参照
   - `features/`（ユーザー向け機能）、`infrastructure/`（基盤・ツール）、`workflows/`（開発プロセス）、`agentic/`（エージェント・スキル）から選択
   - 既存仕様書のカテゴリ分類に従う

2. Issue情報の収集

   ```bash
   # 該当機能のIssueを検索
   gh issue list --search "in:title $FEATURE_NAME" --json number,title,body
   ```

   - Issue本文から要件を抽出
   - コメントから議論内容を収集

3. 関連コードの調査
   - Globツールで機能に関連するファイルを検索: `src/**/*${FEATURE_NAME}*`

4. 仕様書生成（以下のセクションを含む）:
   - **概要**: 機能の簡潔な説明
   - **背景**: なぜこの機能が必要か
   - **ユーザーストーリー**: ユーザー視点での要求
   - **技術仕様**: 入出力、処理フロー
   - **受け入れ条件 (AC)**: チェックボックス形式
   - **使用LLMプロバイダー**: オンライン/ローカル
   - **関連ファイル**: テーブル形式
   - **テスト方針**: テスト戦略

**参考**: `docs/specs/` 配下の既存仕様書とスタイルガイドのテンプレートを踏襲

## エラーハンドリング

- 引数が不正な場合:

  ```
  エラー: 引数が不正です。
  使用方法:
    /doc-gen spec <feature-name>
  ```

- 既存ファイルがある場合:

  ```
  警告: ファイル {path} は既に存在します。
  上書きしますか？ (y/n)
  ```

- Issue/PRが見つからない場合:

  ```
  警告: {feature-name} に関連するIssue/PRが見つかりませんでした。
  手動で情報を入力してドキュメントを作成します。
  ```

## 出力例

```
✓ 仕様書を生成しました: docs/specs/features/notification.md

内容:
- Issue #42 の要件を反映
- 関連ファイル 3件を特定
- 受け入れ条件 5項目を定義

次のステップ:
1. 仕様書をレビュー
2. 実装を開始
```

## 注意事項

- 生成されたドキュメントは必ず人間がレビューし、必要に応じて修正する
- Issue/PRから自動収集できない情報は「TODO」として明示する
- 既存ファイルを上書きする前に必ず確認する
