# F5: MCP統合（天気予報サンプル）

## 概要

Model Context Protocol (MCP) を活用して、チャットボットが外部ツールを動的に呼び出せる仕組みを導入する。
サンプル実装として天気予報MCPサーバーを構築し、Slackチャットから自然言語で天気を問い合わせられるようにする。

## 背景

- 現在のLearning Companionは、LLMに対して定型的なプロンプトを送信し応答を得るのみで、外部ツールとの連携機能がない
- MCP (Model Context Protocol) はAnthropicが提唱し、OpenAI・Linux Foundation (AAIF) も採用したオープン標準プロトコル
- MCPにより、LLMがツールを動的に発見・呼び出しできるようになり、エージェント的な振る舞いが可能になる
- 天気予報APIをサンプルとすることで、MCPの基本的な統合パターンを検証する

### MCPアーキテクチャの概要

MCPは3層のクライアント・サーバーモデルで構成される：

```
┌─────────────────────────────────────────┐
│           MCP Host（AIアプリ）             │
│  ┌──────────┐  ┌──────────┐             │
│  │MCP Client│  │MCP Client│  ...        │
│  └────┬─────┘  └────┬─────┘             │
└───────┼──────────────┼──────────────────┘
        │              │
  ┌─────▼─────┐  ┌─────▼─────┐
  │MCP Server │  │MCP Server │
  │ (天気予報) │  │ (将来拡張) │
  └───────────┘  └───────────┘
```

- **Host**: Learning Companion（Slackボット）がホストとして機能
- **Client**: MCPサーバーごとに1つのクライアントインスタンスを管理
- **Server**: 外部ツール・リソースを提供するプロセス（今回は天気予報サーバー）

### 一般的なMCP+チャットボット統合パターン

調査の結果、以下のパターンが標準的な実装方法として確認された：

1. **動的ツール発見**: チャットボットが起動時にMCPサーバーからツール一覧を取得し、LLMに利用可能ツールとして登録
2. **LLM主導のツール呼び出し**: ユーザーの質問をLLMに送信する際、利用可能ツール情報を付与 → LLMがツール使用を判断 → 結果をLLMに返送 → 最終応答生成
3. **ツール実行ループ**: LLMがtool_useを返す限りツール呼び出しを繰り返し、テキスト応答が得られるまで継続

## ユーザーストーリー

- ユーザーとして、Slackでボットに「東京の天気を教えて」と聞くと、実際の天気予報データに基づいた回答を得たい
- ユーザーとして、明日の天気や週間予報も自然言語で問い合わせたい
- 開発者として、新しいMCPサーバーを追加するだけで、チャットボットの対応範囲を拡張できるようにしたい

## 入出力仕様

### 入力例

```
ユーザー: @bot 東京の天気を教えて
ユーザー: @bot 大阪の明日の天気は？
ユーザー: @bot 今日は傘が必要？
```

### 処理フロー

```
1. ユーザーがSlackで質問
2. ChatService が会話履歴 + 利用可能ツール情報をLLMに送信
3. LLMが tool_use レスポンスを返す場合:
   a. MCPクライアント経由でツールを実行
   b. ツール結果をLLMに返送
   c. LLMが最終応答を生成（tool_use が無くなるまで繰り返し）
4. LLMがテキスト応答を返す場合:
   → そのまま応答として返す
5. 応答をSlackに投稿
```

### 出力例

```
bot: 東京の天気予報です。
     今日: 晴れ時々くもり、最高気温 15°C / 最低気温 5°C
     明日: くもり、最高気温 12°C / 最低気温 4°C
     傘は今日は必要なさそうですが、明日は念のため持っておくと安心です。
```

## 技術仕様

### 依存パッケージ

```toml
# pyproject.toml に追加
dependencies = [
    "mcp>=1.0,<2",       # MCP Python SDK
]
```

### MCPサーバー: 天気予報 (`src/mcp_servers/weather_server.py`)

天気予報APIから情報を取得するMCPサーバーを実装する。

```python
# FastMCP を使用したサーバー定義
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

@mcp.tool()
async def get_weather(location: str, date: str = "today") -> str:
    """指定された場所の天気予報を取得する.

    Args:
        location: 地域名（例: "東京", "大阪", "札幌"）
        date: 日付指定（"today", "tomorrow", "week"）

    Returns:
        天気予報のテキスト
    """
    # 天気予報APIを呼び出して結果を返す
    ...
```

**天気予報APIの選定**:
- 第1候補: [Open-Meteo API](https://open-meteo.com/) — 無料、APIキー不要、日本対応
- 第2候補: [天気予報API (livedoor天気互換)](https://weather.tsukumijima.net/) — 日本語対応、地域ID指定

### MCPクライアント管理 (`src/mcp/client_manager.py`)

複数のMCPサーバーを管理し、ツール一覧を統合するクライアントマネージャー。

```python
class MCPClientManager:
    """MCPサーバーへの接続を管理し、ツール一覧を統合する.
    仕様: docs/specs/f5-mcp-integration.md
    """

    async def initialize(self, server_configs: list[MCPServerConfig]) -> None:
        """設定されたMCPサーバーに接続し、利用可能ツールを取得する."""

    async def get_available_tools(self) -> list[dict]:
        """全サーバーのツールをLLM用フォーマットで返す."""

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """指定ツールを実行し、結果を返す."""

    async def cleanup(self) -> None:
        """全接続をクリーンアップする."""
```

### MCPサーバー設定 (`config/mcp_servers.json`)

MCPサーバーの接続設定を外部ファイルで管理する。

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["src/mcp_servers/weather_server.py"],
      "env": {}
    }
  }
}
```

### ChatService の拡張 (`src/services/chat.py`)

既存の `ChatService.respond()` にツール呼び出しループを追加する。

変更点:
1. `MCPClientManager` を注入できるようにする（オプショナル）
2. `respond()` メソッドでツール情報をLLMに渡す
3. LLMが `tool_use` を返した場合、ツール実行 → 結果返送のループを実行
4. MCPClientManager が無い場合は従来通りの動作（後方互換性）

### LLMProvider の拡張 (`src/llm/base.py`)

ツール呼び出しに対応するため、LLMインターフェースを拡張する。

```python
@dataclass
class ToolCall:
    """LLMが要求するツール呼び出し."""
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class ToolResult:
    """ツール実行結果."""
    tool_use_id: str
    content: str

@dataclass
class LLMResponse:
    """LLMからの応答."""
    content: str
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)  # 追加
    stop_reason: str = ""  # 追加: "end_turn" or "tool_use"
```

既存の `complete()` メソッドに加え、ツール対応の新メソッドを追加:

```python
class LLMProvider(abc.ABC):
    @abc.abstractmethod
    async def complete(self, messages: list[Message]) -> LLMResponse:
        """メッセージリストを受け取り、応答を返す."""

    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],
    ) -> LLMResponse:
        """ツール情報付きでLLMに問い合わせる（デフォルトはツールなしにフォールバック）."""
        return await self.complete(messages)
```

### プロバイダー別のツール呼び出し対応

**OpenAIProvider**: OpenAI の Function Calling API を使用
```python
# tools パラメータで関数定義を渡し、
# response.choices[0].message.tool_calls から呼び出しを取得
```

**AnthropicProvider**: Anthropic の Tool Use API を使用
```python
# tools パラメータでツール定義を渡し、
# response.content から type="tool_use" ブロックを取得
```

### 設定の拡張 (`src/config/settings.py`)

```python
class Settings(BaseSettings):
    # MCP
    mcp_servers_config: str = "config/mcp_servers.json"
    mcp_enabled: bool = False  # デフォルト無効（明示的に有効化）
```

### 新規ファイル一覧

| ファイル | 用途 |
|---------|------|
| `src/mcp/__init__.py` | MCPモジュール |
| `src/mcp/client_manager.py` | MCPクライアント管理 |
| `src/mcp_servers/__init__.py` | MCPサーバーモジュール |
| `src/mcp_servers/weather_server.py` | 天気予報MCPサーバー |
| `config/mcp_servers.json` | MCPサーバー設定 |
| `tests/test_mcp_client_manager.py` | MCPクライアントのテスト |
| `tests/test_weather_server.py` | 天気予報サーバーのテスト |
| `tests/test_chat_with_tools.py` | ツール呼び出し統合テスト |

### 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `pyproject.toml` | `mcp` 依存追加 |
| `src/llm/base.py` | `ToolCall`, `ToolResult` 追加、`complete_with_tools` 追加 |
| `src/llm/openai_provider.py` | `complete_with_tools` 実装 |
| `src/llm/anthropic_provider.py` | `complete_with_tools` 実装 |
| `src/services/chat.py` | ツール呼び出しループ追加 |
| `src/config/settings.py` | MCP設定項目追加 |
| `src/main.py` | MCPClientManager初期化追加 |
| `.env.example` | MCP関連環境変数追加 |

## 受け入れ条件

### MCPサーバー

- [ ] **AC1**: 天気予報MCPサーバーが起動し、`get_weather` ツールを公開すること
- [ ] **AC2**: `get_weather` ツールが地域名と日付を受け取り、天気予報テキストを返すこと
- [ ] **AC3**: 外部天気予報API（Open-Meteo または 天気予報API）から実データを取得すること

### MCPクライアント

- [ ] **AC4**: `MCPClientManager` がMCPサーバーに接続し、利用可能ツール一覧を取得できること
- [ ] **AC5**: `MCPClientManager.call_tool()` でツールを実行し、結果を取得できること
- [ ] **AC6**: 複数のMCPサーバーを同時に管理できること（将来拡張のため）
- [ ] **AC7**: サーバー接続失敗時にエラーログを出力し、ツールなしで続行すること（グレースフルデグラデーション）

### LLMプロバイダー拡張

- [ ] **AC8**: `LLMProvider.complete_with_tools()` がツール情報をLLMに渡せること
- [ ] **AC9**: OpenAIProvider が Function Calling に対応すること
- [ ] **AC10**: AnthropicProvider が Tool Use に対応すること
- [ ] **AC11**: ツール非対応のプロバイダー（LMStudio等）は `complete_with_tools()` が従来の `complete()` にフォールバックすること

### チャット統合

- [ ] **AC12**: ユーザーが天気について質問すると、LLMがツールを呼び出して実データで回答すること
- [ ] **AC13**: ツール呼び出しが不要な通常の質問は、従来通り応答すること（後方互換性）
- [ ] **AC14**: ツール実行中にエラーが発生した場合、エラー内容をLLMに伝え、適切な応答を生成すること
- [ ] **AC15**: MCP無効時（`mcp_enabled=False`）は従来通りの動作をすること

### 設定・運用

- [ ] **AC16**: `config/mcp_servers.json` でMCPサーバーの追加・変更が可能であること
- [ ] **AC17**: `MCP_ENABLED` 環境変数でMCP機能のON/OFFを制御できること

## 使用LLMプロバイダー

| タスク | プロバイダー | 理由 |
|--------|-------------|------|
| ツール呼び出し判断 + 応答生成 | オンライン (OpenAI/Anthropic) | tool_use / function_calling が必要 |
| 天気予報データ取得 | なし（HTTP API直接呼び出し） | LLM不要 |

## テスト方針

### ユニットテスト

| テスト | 対応AC |
|--------|--------|
| `test_ac1_weather_server_exposes_tool` | AC1 |
| `test_ac2_get_weather_returns_forecast` | AC2 |
| `test_ac3_weather_api_fetches_real_data` | AC3 |
| `test_ac4_client_manager_connects_and_lists_tools` | AC4 |
| `test_ac5_client_manager_calls_tool` | AC5 |
| `test_ac7_graceful_degradation_on_connection_failure` | AC7 |
| `test_ac8_complete_with_tools_passes_tools` | AC8 |
| `test_ac9_openai_function_calling` | AC9 |
| `test_ac10_anthropic_tool_use` | AC10 |
| `test_ac11_lmstudio_fallback_to_complete` | AC11 |

### 統合テスト

| テスト | 対応AC |
|--------|--------|
| `test_ac12_chat_responds_with_weather_data` | AC12 |
| `test_ac13_chat_backward_compatible` | AC13 |
| `test_ac14_tool_error_handled_gracefully` | AC14 |
| `test_ac15_mcp_disabled_mode` | AC15 |

### テスト戦略

- MCPサーバーのテスト: `mcp.server.fastmcp` のテストユーティリティを使用
- MCPクライアントのテスト: MCPサーバーをモック化してツール呼び出しを検証
- LLMプロバイダーのテスト: LLM応答をモック化してtool_use解析を検証
- 統合テスト: LLM・MCPサーバー両方をモック化してフロー全体を検証

## 実装ステップ

### Step 1: 基盤（LLMプロバイダー拡張）
1. `src/llm/base.py` に `ToolCall`, `ToolResult`, `complete_with_tools` を追加
2. `OpenAIProvider.complete_with_tools()` を実装
3. `AnthropicProvider.complete_with_tools()` を実装
4. テスト作成

### Step 2: MCPサーバー（天気予報）
1. `src/mcp_servers/weather_server.py` を作成
2. 天気予報API連携を実装
3. テスト作成

### Step 3: MCPクライアント
1. `src/mcp/client_manager.py` を作成
2. サーバー接続・ツール発見・ツール実行を実装
3. テスト作成

### Step 4: チャット統合
1. `ChatService.respond()` にツール呼び出しループを追加
2. `src/main.py` にMCPClientManager初期化を追加
3. 設定項目を追加
4. 統合テスト作成

## 参考資料

- [MCP公式ドキュメント - アーキテクチャ](https://modelcontextprotocol.io/docs/learn/architecture)
- [MCP公式ドキュメント - クライアント構築](https://modelcontextprotocol.io/quickstart/client)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Chatbot実装例](https://github.com/3choff/mcp-chatbot)
- [参考記事: MCPサーバー構築 (Qiita)](https://qiita.com/k_ide/items/11c04869f9a179258618)
- [Open-Meteo API](https://open-meteo.com/)
- [天気予報API (livedoor天気互換)](https://weather.tsukumijima.net/)
