# 学びトピック管理スキル（/topic）

## 概要

レトロスペクティブやMEMORY.mdから学びトピックを自動抽出し、Zenn形式の技術記事を生成するClaude Codeスキル。

## 背景

開発中に得た知見（ハマったこと、解決策、教訓）はレトロスペクティブに記録されているが、これを対外発信できる形式（Zenn記事）に変換するには手間がかかる。自動抽出・記事生成を仕組み化することで:

- レトロに蓄積された学びを効率的に記事化
- 発信のハードルを下げる（「見て選ぶだけ」）
- 記事化状況をトラッキングし、重複を防止

## ユーザーストーリー

- 開発者として、`/topic` でレトロから記事化候補を自動抽出・表示したい
- 開発者として、`/topic <番号>` で選んだトピックの記事を生成したい
- 開発者として、`/topic done <番号> <url>` でZenn公開後に記録を残したい
- 開発者として、`/topic history` で公開済み記事の一覧を確認したい

## 技術仕様

### スキル定義

```yaml
name: topic
description: 学びトピックの自動抽出・Zenn記事生成
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
argument-hint: "[番号|done <番号> <url>|history]"
```

### コマンド体系

| コマンド | 用途 |
|---------|------|
| `/topic` | 候補を自動抽出・表示 |
| `/topic <番号>` | 選んで記事生成 |
| `/topic done <番号> <url>` | 公開記録 |
| `/topic history` | 公開済み一覧 |

### 処理フロー

```mermaid
flowchart TD
    A[/topic 実行] --> B{引数チェック}
    B -->|引数なし| C[トピック抽出]
    B -->|番号| D[記事生成]
    B -->|done| E[公開記録]
    B -->|history| F[履歴表示]

    C --> C1[retro/*.md スキャン]
    C1 --> C2[MEMORY.md スキャン]
    C2 --> C3[優先度スコアリング]
    C3 --> C4[DB登録済み除外]
    C4 --> C5[候補一覧表示]

    D --> D1[トピック情報取得]
    D1 --> D2[ソースセクション読込]
    D2 --> D3[Zenn記事生成]
    D3 --> D4[docs/zenn-drafts/に保存]
    D4 --> D5[DB article_status=draft]

    E --> E1[ステータス更新]
    E1 --> E2[published_at記録]
    E2 --> E3[確認メッセージ]

    F --> F1[DB検索 status=published]
    F1 --> F2[一覧表示]
```

### DB設計

```python
class LearningTopic(Base):
    """学びトピック（自動抽出 + 記事化トラッキング）"""
    __tablename__ = "learning_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # トピック情報（自動抽出）
    topic: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)

    # 記事化ステータス
    article_status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending: 未着手, draft: 下書き中, published: 公開済み

    article_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # メタ情報
    scanned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

### トピック抽出ロジック

**抽出対象:**

- `docs/retro/*.md` — レトロスペクティブ
- `~/.claude/projects/*/memory/MEMORY.md` — Claude Code開発知見

**抽出ルール:**

1. `## 改善点` `## ハマったこと` セクションを検出
2. 配下の `###` 見出しをトピック候補として抽出
3. 優先度スコアリング（下表参照）
4. 既にDB登録済み（`article_status != "pending"`）のトピックは除外

**優先度スコアリング:**

| 条件 | スコア加算 |
|------|-----------|
| セクションに「教訓」が含まれる | +2 |
| セクションに「対応」が含まれる | +1 |
| コードブロックが含まれる | +1 |
| 「問題」「原因」キーワードがある | +1 |

**ソース参照形式:**

`{相対パス}#{セクション番号}`

例: `docs/retro/f2.md#3` は f2.md の3番目の `###` 見出し

### Zenn記事テンプレート

```markdown
---
title: "{タイトル}"
emoji: "{自動選択}"
type: "tech"
topics: ["{tag1}", "{tag2}"]
published: false
---

## TL;DR

{3行で要約}

## 背景

{なぜこの問題に遭遇したか}

## 問題

{何が起きたか}

## 解決策

{どう解決したか、コード例}

## まとめ

{学びのポイント}
```

### 出力先

- 記事ファイル: `docs/zenn-drafts/{topic-slug}.md`
- `published: false` で生成し、レビュー後に手動で `true` に変更

## 使用LLMプロバイダー

**Claude Code (Claude Sonnet 4.5)** — スキル実行環境で使用

**選定理由:**

- トピック抽出・優先度判定にはセクション内容の意味理解が必要
- 記事生成には元の技術的内容を読者向けに再構成する能力が必要
- Claude Codeのスキル機能はメインのClaude Sonnet 4.5エージェントによって実行される

## 受け入れ条件

### 候補表示（`/topic`）

- [ ] AC1: `docs/retro/*.md` からトピック候補が抽出される
- [ ] AC2: 優先度に基づいてソートされた一覧が表示される
- [ ] AC3: 公開済みトピックは候補から除外される

### 記事生成（`/topic <番号>`）

- [ ] AC4: 選択したトピックの記事が `docs/zenn-drafts/` に生成される
- [ ] AC5: 生成される記事がZennフロントマター形式に準拠する
- [ ] AC6: `article_status` が `"draft"` に更新される
- [ ] AC7: 不正な番号の場合にエラーメッセージが表示される

### 公開記録（`/topic done <番号> <url>`）

- [ ] AC8: `article_status` が `"published"` に更新される
- [ ] AC9: `article_url` と `published_at` が記録される
- [ ] AC10: 不正なURLの場合にエラーメッセージが表示される

### 履歴表示（`/topic history`）

- [ ] AC11: 公開済み記事の一覧が表示される
- [ ] AC12: 公開日順（降順）でソートされる

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `.claude/skills/topic/SKILL.md` | topicスキル定義 |
| `src/db/models.py` | LearningTopicモデル |
| `docs/retro/*.md` | 抽出元（レトロスペクティブ） |
| `docs/zenn-drafts/` | 記事出力ディレクトリ |
| `CLAUDE.md` | スキル一覧への登録 |

## テスト方針

Claude Codeスキルは実行時テストが中心となるため、以下を確認:

**DBモデルのテスト:**

- [ ] LearningTopicモデルのCRUD操作が正常に動作する
- [ ] unique制約（topic）が機能する

**スキル実行テスト（手動）:**

- [ ] `/topic` でレトロから候補が抽出される
- [ ] `/topic <番号>` で記事が正しく生成される
- [ ] `/topic done <番号> <url>` で公開記録が保存される
- [ ] `/topic history` で履歴が表示される

## 拡張性

将来的に以下の機能を追加可能:

- my-lifeリポジトリへの export/import 機能
- 自動公開（Zenn GitHub連携）
- 記事品質の自動チェック
- 類似トピックの統合提案

## 参考資料

- [Zenn CLI](https://zenn.dev/zenn/articles/zenn-cli-guide) — Zenn記事のフォーマット
- Issue #203 — 本機能の議論
