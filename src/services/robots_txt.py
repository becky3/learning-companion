"""robots.txt の取得・解析・判定

仕様: docs/specs/f9-rag.md
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    """robots.txt キャッシュエントリ."""

    parser: RobotFileParser
    crawl_delay: float | None
    fetched_at: float


class RobotsTxtChecker:
    """robots.txt の取得・解析・判定を行う.

    仕様: docs/specs/f9-rag.md
    """

    def __init__(
        self,
        user_agent: str = "*",
        timeout: float = 10.0,
        cache_ttl: int = 3600,
    ) -> None:
        """RobotsTxtCheckerを初期化する.

        Args:
            user_agent: robots.txt 判定に使用する User-Agent 文字列
            timeout: robots.txt 取得のHTTPタイムアウト秒数
            cache_ttl: robots.txt キャッシュの有効期間（秒）
        """
        self._user_agent = user_agent
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._cache_ttl = cache_ttl
        self._cache: dict[str, _CacheEntry] = {}

    def _get_robots_url(self, url: str) -> str:
        """URLからrobots.txtのURLを構築する.

        Args:
            url: 対象URL

        Returns:
            robots.txt の URL
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _get_host_key(self, url: str) -> str:
        """URLからホストキーを取得する.

        Args:
            url: 対象URL

        Returns:
            ホストキー（scheme://netloc）
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_cached(self, host_key: str) -> _CacheEntry | None:
        """キャッシュからエントリを取得する（TTL超過の場合はNone）.

        Args:
            host_key: ホストキー

        Returns:
            有効なキャッシュエントリ、またはNone
        """
        entry = self._cache.get(host_key)
        if entry is None:
            return None
        if time.monotonic() - entry.fetched_at > self._cache_ttl:
            del self._cache[host_key]
            return None
        return entry

    async def _fetch_and_parse(self, url: str) -> _CacheEntry:
        """robots.txt を取得・解析してキャッシュに保存する.

        取得失敗時はフェイルオープン（全URL許可）のパーサーを返す。

        Args:
            url: 対象URL（robots.txt のURLではなく、クロール対象のURL）

        Returns:
            キャッシュエントリ
        """
        host_key = self._get_host_key(url)
        robots_url = self._get_robots_url(url)

        parser = RobotFileParser()
        crawl_delay: float | None = None

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(robots_url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        parser.parse(text.splitlines())
                        # Crawl-delay の取得
                        try:
                            delay = parser.crawl_delay(self._user_agent)
                            if delay is not None:
                                crawl_delay = float(delay)
                        except AttributeError:
                            pass
                    else:
                        # 404, 403 等: robots.txt がない場合は全許可
                        logger.debug(
                            "robots.txt not found (status=%d): %s",
                            resp.status,
                            robots_url,
                        )
                        parser.allow_all = True  # type: ignore[attr-defined]
        except (aiohttp.ClientError, TimeoutError):
            # ネットワークエラー/タイムアウト: フェイルオープン
            logger.debug(
                "Failed to fetch robots.txt (fail-open): %s",
                robots_url,
                exc_info=True,
            )
            parser.allow_all = True  # type: ignore[attr-defined]
        except Exception:
            logger.warning(
                "Unexpected error fetching robots.txt (fail-open): %s",
                robots_url,
                exc_info=True,
            )
            parser.allow_all = True  # type: ignore[attr-defined]

        entry = _CacheEntry(
            parser=parser,
            crawl_delay=crawl_delay,
            fetched_at=time.monotonic(),
        )
        self._cache[host_key] = entry
        return entry

    async def _get_entry(self, url: str) -> _CacheEntry:
        """キャッシュ済みまたは新規取得したエントリを返す.

        Args:
            url: 対象URL

        Returns:
            キャッシュエントリ
        """
        host_key = self._get_host_key(url)
        cached = self._get_cached(host_key)
        if cached is not None:
            return cached
        return await self._fetch_and_parse(url)

    async def is_allowed(self, url: str) -> bool:
        """URLへのクロールが robots.txt で許可されているかを判定する.

        Args:
            url: 判定するURL

        Returns:
            許可されている場合は True
        """
        entry = await self._get_entry(url)
        # allow_all が設定されている場合（取得失敗時のフェイルオープン）
        if getattr(entry.parser, "allow_all", False):
            return True
        return entry.parser.can_fetch(self._user_agent, url)

    async def get_crawl_delay(self, url: str) -> float | None:
        """robots.txt で指定された Crawl-delay を取得する.

        Args:
            url: 対象URL

        Returns:
            Crawl-delay の値（秒）、未指定の場合はNone
        """
        entry = await self._get_entry(url)
        return entry.crawl_delay

    def clear_cache(self) -> None:
        """キャッシュをクリアする."""
        self._cache.clear()
