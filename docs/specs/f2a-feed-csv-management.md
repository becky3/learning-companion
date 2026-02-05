# F2a: Feed CSV管理

## 概要

RSSフィードの管理をSQLite DBからCSVファイルへ移行する。
CSVファイルはテキストエディタで直接編集でき、Git管理やバックアップも容易になる。

## 背景

- DB管理ではフィード編集に専用ツールが必要で面倒
- 一括編集・バックアップ・版管理がしにくい
- 将来的にCSV添付でのフィード一括操作も検討

## ユーザーストーリー

- 管理者として、CSVファイルを直接編集してフィードを追加・変更・削除したい
- 管理者として、既存のSlackコマンド（`@bot feed add/list/delete/enable/disable`）も引き続き使いたい
- 管理者として、フィード設定をGitで版管理したい

## 入出力仕様

### CSVファイル形式

**ファイルパス**: `data/feeds.csv`

```csv
url,name,category,enabled
https://example.com/rss,サンプルフィード,Python,true
https://another.com/feed,別のフィード,Web開発,false
```

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| url | string | ○ | RSSフィードURL（一意キー、空不可） |
| name | string | ○ | フィード表示名 |
| category | string | ○ | カテゴリ名（デフォルト: 一般） |
| enabled | bool | ○ | 有効/無効フラグ（true/false） |

**制約**:
- URLは一意（重複禁止）
- 空行・先頭が`#`の行はスキップ（コメント行として扱う）
- UTF-8エンコーディング

### FeedCsvLoader API

```python
class FeedCsvLoader:
    def __init__(self, csv_path: Path) -> None: ...
    def load_all(self) -> list[FeedData]: ...
    def save_all(self, feeds: list[FeedData]) -> None: ...
    def add(self, feed: FeedData) -> None: ...
    def delete(self, url: str) -> bool: ...
    def update(self, url: str, **kwargs: Any) -> bool: ...
```

### FeedDataモデル

```python
@dataclass
class FeedData:
    url: str
    name: str
    category: str = "一般"
    enabled: bool = True
```

### Articleテーブルとの関連

- `Article`テーブルの`feed_id`（int）を`feed_url`（string）に変更
- Feed削除時の関連Article削除は手動（または別途マイグレーションスクリプト）

## 受け入れ条件

### CSV読み書き

- [ ] AC1: `data/feeds.csv`からフィード一覧を読み込める
- [ ] AC2: フィード一覧を`data/feeds.csv`に書き込める
- [ ] AC3: ファイルが存在しない場合は空リストを返す
- [ ] AC4: 不正なCSV形式の場合は例外をスローする
- [ ] AC5: コメント行（`#`で始まる行）と空行はスキップする

### CRUD操作（FeedCollector経由）

- [ ] AC6: `add_feed`でCSVにフィードを追加できる
- [ ] AC7: 重複URLの追加時にValueErrorをスローする
- [ ] AC8: `delete_feed`でCSVからフィードを削除できる
- [ ] AC9: 存在しないURL削除時にValueErrorをスローする
- [ ] AC10: `enable_feed`/`disable_feed`でenabledフラグを更新できる
- [ ] AC11: `list_feeds`でCSVから有効/無効フィードを取得できる

### Slackコマンド互換

- [ ] AC12: `@bot feed add/list/delete/enable/disable`が引き続き動作する
- [ ] AC13: コマンド応答の形式は変更なし

### 記事収集との統合

- [ ] AC14: `collect_all`がCSVから有効フィードを取得して収集する
- [ ] AC15: Articleは`feed_url`でフィードと紐づく

### マイグレーション

- [ ] AC16: `scripts/migrate_feeds_to_csv.py`で既存DBからCSVへエクスポートできる
- [ ] AC17: マイグレーション後もシステムが正常動作する

## 関連ファイル

| ファイル | 変更内容 |
|---------|----------|
| `data/feeds.csv` | 新規作成（フィードデータ） |
| `src/models/feed_data.py` | 新規作成（FeedDataクラス） |
| `src/services/feed_csv_loader.py` | 新規作成（CSV読み書きロジック） |
| `src/services/feed_collector.py` | FeedCsvLoaderを使用するよう変更 |
| `src/db/models.py` | Feedクラス削除、Article.feed_id→feed_url変更 |
| `src/slack/handlers.py` | 変更なし（I/F維持） |
| `src/scheduler/jobs.py` | 変更なし |
| `scripts/migrate_feeds_to_csv.py` | 新規作成（マイグレーションスクリプト） |
| `tests/test_feed_csv_loader.py` | 新規作成 |
| `tests/test_feed_collector.py` | CSVモック用にテスト修正 |
| `tests/test_db.py` | Feed関連テスト削除/修正 |
| `docs/specs/f2-feed-collection.md` | CSV管理への変更を反映 |
| `docs/specs/overview.md` | DB設計セクション更新 |

## テスト方針

- CSVファイル読み書きのユニットテスト（正常/異常ケース）
- FeedDataモデルのバリデーションテスト
- FeedCollectorのCRUD操作テスト（CSVモック使用）
- Slackコマンドの統合テスト
- マイグレーションスクリプトのテスト（既存DB→CSVの変換確認）

## 実装順序

1. `FeedData`モデル作成
2. `FeedCsvLoader`実装+テスト
3. `FeedCollector`をCSV対応に修正
4. `Article`モデルの`feed_url`対応
5. マイグレーションスクリプト作成
6. 既存テスト修正
7. 仕様書更新

## スコープ外

- CSV添付でのSlack一括操作（別Issue化を推奨）
- feedsテーブルの完全削除（オプション。移行後に手動で可能）
