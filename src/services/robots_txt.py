"""robots.txt 解析・遵守チェッカー

仕様: docs/specs/f9-robots-txt.md
Issue: #160

RFC 9309 準拠:
- User-agent マッチング（大文字小文字不問）
- Allow / Disallow ルールの最長一致
- ワイルドカード (*) と終端 ($) のサポート
- robots.txt 取得失敗時は全URL許可（fail-open）
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class _Rule:
    """robots.txt の個別ルール."""

    path: str
    allow: bool


@dataclass
class _RobotsTxtData:
    """パース済み robots.txt データ."""

    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None


@dataclass
class _CachedRobotsTxt:
    """キャッシュされた robots.txt データ."""

    data: _RobotsTxtData
    fetched_at: float  # time.monotonic()


class RobotsTxtChecker:
    """robots.txt の取得・解析・キャッシュを行うチェッカー.

    仕様: docs/specs/f9-robots-txt.md

    RFC 9309 準拠:
    - User-agent マッチング（大文字小文字不問）
    - Allow / Disallow ルールの最長一致
    - ワイルドカード (*) と終端 ($) のサポート
    - robots.txt 取得失敗時は全URL許可（fail-open）
    """

    def __init__(
        self,
        user_agent: str = "AIAssistantBot/1.0",
        cache_ttl: int = 3600,
        timeout: float = 10.0,
    ) -> None:
        """RobotsTxtCheckerを初期化する.

        Args:
            user_agent: クローラーのUser-Agent名
            cache_ttl: キャッシュの有効期間（秒）
            timeout: robots.txt取得時のHTTPタイムアウト（秒）
        """
        self._user_agent = user_agent
        self._cache_ttl = cache_ttl
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._cache: dict[str, _CachedRobotsTxt] = {}

    async def is_allowed(self, url: str) -> bool:
        """指定URLへのアクセスが robots.txt で許可されているか判定する.

        Args:
            url: 判定するURL

        Returns:
            True: アクセス許可、False: アクセス禁止
        """
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        data = await self._get_robots_data(origin)
        return self._check_path(data, path)

    def get_crawl_delay(self, url: str) -> float | None:
        """指定URLのドメインの Crawl-delay 値を取得する（キャッシュ済みの場合のみ）.

        Args:
            url: 対象URL

        Returns:
            Crawl-delay の値（秒）。未設定またはキャッシュなしの場合は None
        """
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._cache.get(origin)
        if cached is None:
            return None
        return cached.data.crawl_delay

    def clear_cache(self) -> None:
        """キャッシュを全クリアする."""
        self._cache.clear()

    async def _get_robots_data(self, origin: str) -> _RobotsTxtData:
        """robots.txt データを取得する（キャッシュ付き）.

        Args:
            origin: オリジン（scheme + netloc）

        Returns:
            パース済み robots.txt データ
        """
        now = time.monotonic()
        cached = self._cache.get(origin)
        if cached is not None and (now - cached.fetched_at) < self._cache_ttl:
            return cached.data

        # HTTP取得
        data = await self._fetch_and_parse(origin)
        self._cache[origin] = _CachedRobotsTxt(data=data, fetched_at=now)
        return data

    async def _fetch_and_parse(self, origin: str) -> _RobotsTxtData:
        """robots.txt をHTTP取得してパースする.

        取得失敗時は全URL許可のデータを返す（fail-open）。

        Args:
            origin: オリジン（scheme + netloc）

        Returns:
            パース済み robots.txt データ
        """
        robots_url = f"{origin}/robots.txt"
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(robots_url) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "robots.txt not available: %s (status=%d)",
                            robots_url,
                            resp.status,
                        )
                        return _RobotsTxtData()
                    text = await resp.text()
        except TimeoutError:
            logger.debug("robots.txt fetch timed out: %s", robots_url)
            return _RobotsTxtData()
        except aiohttp.ClientError as e:
            logger.debug("robots.txt fetch failed: %s - %s", robots_url, e)
            return _RobotsTxtData()
        except Exception:
            logger.debug("robots.txt fetch unexpected error: %s", robots_url, exc_info=True)
            return _RobotsTxtData()

        return self._parse(text)

    def _parse(self, text: str) -> _RobotsTxtData:
        """robots.txt テキストをパースする.

        RFC 9309 準拠のパース:
        - User-agent グループの識別
        - 自身の User-Agent に一致するグループを優先
        - 一致しない場合は * グループを使用

        Args:
            text: robots.txt の内容

        Returns:
            パース済みデータ
        """
        # グループを解析: { user_agents: [...], rules: [...], crawl_delay: ... }
        groups: list[dict[str, list[str] | list[_Rule] | float | None]] = []
        current_agents: list[str] = []
        current_rules: list[_Rule] = []
        current_crawl_delay: float | None = None
        in_group = False

        for line in text.splitlines():
            # コメント除去
            line = line.split("#", maxsplit=1)[0].strip()
            if not line:
                continue

            # ディレクティブ解析
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()

            if key == "user-agent":
                if in_group and current_rules:
                    # 前のグループを保存
                    groups.append({
                        "agents": current_agents,
                        "rules": current_rules,
                        "crawl_delay": current_crawl_delay,
                    })
                    current_agents = []
                    current_rules = []
                    current_crawl_delay = None
                current_agents.append(value.lower())
                in_group = True

            elif key == "disallow" and in_group:
                if value:
                    current_rules.append(_Rule(path=value, allow=False))
                # 空の Disallow は「全URL許可」（ルールを追加しない）

            elif key == "allow" and in_group:
                if value:
                    current_rules.append(_Rule(path=value, allow=True))

            elif key == "crawl-delay" and in_group:
                try:
                    current_crawl_delay = float(value)
                except ValueError:
                    pass

        # 最後のグループを保存
        if in_group and current_agents:
            groups.append({
                "agents": current_agents,
                "rules": current_rules,
                "crawl_delay": current_crawl_delay,
            })

        # 自身の User-Agent に一致するグループを検索
        ua_lower = self._user_agent.lower()
        matched_group: dict[str, list[str] | list[_Rule] | float | None] | None = None
        wildcard_group: dict[str, list[str] | list[_Rule] | float | None] | None = None

        for group in groups:
            agents = group["agents"]
            assert isinstance(agents, list)
            for agent in agents:
                assert isinstance(agent, str)
                if agent == ua_lower:
                    matched_group = group
                    break
                if agent == "*":
                    wildcard_group = group
            if matched_group is not None:
                break

        # 一致するグループを選択
        selected = matched_group or wildcard_group
        if selected is None:
            return _RobotsTxtData()

        rules = selected["rules"]
        assert isinstance(rules, list)
        crawl_delay = selected["crawl_delay"]
        assert crawl_delay is None or isinstance(crawl_delay, float)

        return _RobotsTxtData(
            rules=rules,  # type: ignore[arg-type]
            crawl_delay=crawl_delay,
        )

    def _check_path(self, data: _RobotsTxtData, path: str) -> bool:
        """パスがルールで許可されているか判定する.

        RFC 9309 準拠: 最長一致ルールを適用。同一長さの場合は Allow を優先。

        Args:
            data: パース済み robots.txt データ
            path: 判定するパス

        Returns:
            True: 許可、False: 禁止
        """
        if not data.rules:
            return True

        # 全ルールの中から最長一致を探す
        best_match_length = -1
        best_match_allow = True

        for rule in data.rules:
            match_length = self._match_path(rule.path, path)
            if match_length < 0:
                continue
            # より長いマッチが優先。同一長さの場合は Allow を優先（RFC 9309）
            if match_length > best_match_length or (
                match_length == best_match_length and rule.allow
            ):
                best_match_length = match_length
                best_match_allow = rule.allow

        if best_match_length < 0:
            # マッチするルールなし → 許可
            return True

        return best_match_allow

    @staticmethod
    def _match_path(pattern: str, path: str) -> int:
        """パターンとパスのマッチングを行う.

        RFC 9309 準拠:
        - * は0文字以上の任意の文字列にマッチ
        - $ はパターンの終端（パスの末尾と一致する必要がある）
        - マッチした場合はパターンの有効長を返す（最長一致の比較用）
        - マッチしない場合は -1 を返す

        Args:
            pattern: robots.txt のパスパターン
            path: 判定するパス

        Returns:
            マッチした場合のパターン有効長、マッチしない場合は -1
        """
        # $ 終端チェック
        anchor_end = pattern.endswith("$")
        if anchor_end:
            pattern = pattern[:-1]

        # パターンを正規表現に変換
        # * → .* 、それ以外はエスケープ
        parts = pattern.split("*")
        regex_parts = [re.escape(part) for part in parts]
        regex_str = ".*".join(regex_parts)

        if anchor_end:
            regex_str += "$"

        try:
            match = re.match(regex_str, path)
        except re.error:
            return -1

        if match is None:
            return -1

        # パターンの有効長（* と $ を除いた文字数）を返す
        effective_length = len(pattern.replace("*", ""))
        return effective_length
