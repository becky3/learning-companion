"""RobotsTxtChecker テスト

仕様: docs/specs/f9-rag.md
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.robots_txt import RobotsTxtChecker


# テスト用 robots.txt コンテンツ
ROBOTS_TXT_BASIC = """\
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /
"""

ROBOTS_TXT_WITH_CRAWL_DELAY = """\
User-agent: *
Disallow: /secret/
Crawl-delay: 5
"""

ROBOTS_TXT_ALLOW_ALL = """\
User-agent: *
Allow: /
"""

ROBOTS_TXT_DISALLOW_ALL = """\
User-agent: *
Disallow: /
"""


class MockRobotsResponse:
    """robots.txt 取得用のモックレスポンス."""

    def __init__(self, status: int = 200, body: str = "", headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self) -> str:
        return self._body

    def get(self, key: str, default: str = "") -> str:
        """ヘッダー取得（互換性のため）."""
        return self.headers.get(key, default)


class MockRobotsSession:
    """robots.txt 取得用のモックセッション."""

    def __init__(self, status: int = 200, body: str = "", headers: dict[str, str] | None = None) -> None:
        self._status = status
        self._body = body
        self._headers = headers or {}

    async def __aenter__(self) -> "MockRobotsSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    def get(self, url: str, **kwargs: object) -> "MockRobotsContextManager":  # noqa: ARG002
        return MockRobotsContextManager(self._status, self._body, self._headers)


class MockRobotsContextManager:
    """robots.txt 取得用のモックコンテキストマネージャ."""

    def __init__(self, status: int, body: str, headers: dict[str, str] | None = None) -> None:
        self._status = status
        self._body = body
        self._headers = headers or {}

    async def __aenter__(self) -> MockRobotsResponse:
        return MockRobotsResponse(self._status, self._body, self._headers)

    async def __aexit__(self, *args: object) -> None:
        pass


class TestRobotsTxtCheckerBasic:
    """RobotsTxtChecker 基本機能のテスト."""

    def test_get_robots_url(self) -> None:
        """robots.txt URLが正しく構築されること."""
        checker = RobotsTxtChecker()
        assert checker._get_robots_url("https://example.com/page") == "https://example.com/robots.txt"
        assert checker._get_robots_url("https://example.com:8080/path") == "https://example.com:8080/robots.txt"
        assert checker._get_robots_url("http://test.org/a/b/c") == "http://test.org/robots.txt"

    def test_get_host_key(self) -> None:
        """ホストキーが正しく取得されること."""
        checker = RobotsTxtChecker()
        assert checker._get_host_key("https://example.com/page") == "https://example.com"
        assert checker._get_host_key("http://test.org:8080/path") == "http://test.org:8080"

    def test_clear_cache(self) -> None:
        """キャッシュがクリアされること."""
        checker = RobotsTxtChecker()
        checker._cache["test"] = MagicMock()
        assert len(checker._cache) == 1
        checker.clear_cache()
        assert len(checker._cache) == 0


class TestRobotsTxtCheckerIsAllowed:
    """AC71, AC72: robots.txt の取得・解析・Disallow 判定テスト."""

    @pytest.mark.asyncio
    async def test_ac71_robots_txt_is_fetched_and_parsed(self) -> None:
        """AC71: クロール前に対象サイトの robots.txt を取得・解析すること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        ):
            # 許可パスはTrue
            result = await checker.is_allowed("https://example.com/public/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_ac72_disallow_path_is_blocked(self) -> None:
        """AC72: Disallow 指定されたパスへのクロールがスキップされること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        ):
            # /admin/ は Disallow
            result = await checker.is_allowed("https://example.com/admin/settings")
            assert result is False

            # /private/ も Disallow
            result = await checker.is_allowed("https://example.com/private/data")
            assert result is False

    @pytest.mark.asyncio
    async def test_ac72_disallow_all_blocks_everything(self) -> None:
        """AC72: Disallow: / で全パスがブロックされること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_DISALLOW_ALL),
        ):
            result = await checker.is_allowed("https://example.com/any/path")
            assert result is False

    @pytest.mark.asyncio
    async def test_allow_all_permits_everything(self) -> None:
        """Allow: / で全パスが許可されること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_ALLOW_ALL),
        ):
            result = await checker.is_allowed("https://example.com/any/path")
            assert result is True


class TestRobotsTxtCheckerCrawlDelay:
    """AC73: Crawl-delay テスト."""

    @pytest.mark.asyncio
    async def test_ac73_crawl_delay_is_extracted(self) -> None:
        """AC73: robots.txt の Crawl-delay が取得できること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_WITH_CRAWL_DELAY),
        ):
            delay = await checker.get_crawl_delay("https://example.com/page")
            assert delay == 5.0

    @pytest.mark.asyncio
    async def test_ac73_no_crawl_delay_returns_none(self) -> None:
        """AC73: Crawl-delay がない場合はNoneを返すこと."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        ):
            delay = await checker.get_crawl_delay("https://example.com/page")
            assert delay is None


class TestRobotsTxtCheckerFailOpen:
    """AC75: フェイルオープン（取得失敗時にクロール許可）テスト."""

    @pytest.mark.asyncio
    async def test_ac75_404_allows_crawl(self) -> None:
        """AC75: robots.txt が 404 の場合、クロールを許可すること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(404, ""),
        ):
            result = await checker.is_allowed("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_ac75_403_allows_crawl(self) -> None:
        """AC75: robots.txt が 403 の場合、クロールを許可すること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(403, ""),
        ):
            result = await checker.is_allowed("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_ac75_network_error_allows_crawl(self) -> None:
        """AC75: ネットワークエラー時にクロールを許可すること."""
        checker = RobotsTxtChecker()

        import aiohttp

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Connection failed"))

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await checker.is_allowed("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_ac75_timeout_allows_crawl(self) -> None:
        """AC75: タイムアウト時にクロールを許可すること."""
        checker = RobotsTxtChecker()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=TimeoutError("Request timed out"))

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await checker.is_allowed("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_ac75_redirect_allows_crawl_ssrf_protection(self) -> None:
        """AC75: リダイレクト応答時にクロールを許可すること（SSRF対策）."""
        checker = RobotsTxtChecker()

        # 301 redirect
        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(
                301, "", {"Location": "http://internal.local/robots.txt"}
            ),
        ):
            result = await checker.is_allowed("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_ac75_302_redirect_allows_crawl(self) -> None:
        """AC75: 302 リダイレクト時にクロールを許可すること（SSRF対策）."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(
                302, "", {"Location": "http://169.254.169.254/latest/meta-data/"}
            ),
        ):
            result = await checker.is_allowed("https://example.com/page")
            assert result is True


class TestRobotsTxtCheckerCache:
    """AC76: キャッシュテスト."""

    @pytest.mark.asyncio
    async def test_ac76_cache_prevents_duplicate_fetch(self) -> None:
        """AC76: キャッシュが機能し、同一ホストへの重複取得を抑制すること."""
        checker = RobotsTxtChecker()

        mock_session_cls = MagicMock(
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        )

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            mock_session_cls,
        ):
            # 1回目: robots.txt 取得
            await checker.is_allowed("https://example.com/page1")
            first_call_count = mock_session_cls.call_count

            # 2回目: 同一ホストの別パス → キャッシュから取得
            await checker.is_allowed("https://example.com/page2")
            second_call_count = mock_session_cls.call_count

            # キャッシュにより2回目はHTTPリクエストが発生しない
            assert second_call_count == first_call_count

    @pytest.mark.asyncio
    async def test_ac76_cache_expires_after_ttl(self) -> None:
        """AC76: キャッシュがTTL後に期限切れになること."""
        checker = RobotsTxtChecker(cache_ttl=1)

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        ):
            await checker.is_allowed("https://example.com/page")

        # キャッシュのfetched_atを古い値に書き換え
        host_key = "https://example.com"
        entry = checker._cache[host_key]
        entry.fetched_at = time.monotonic() - 2  # TTL超過

        # 期限切れキャッシュは取得し直す
        cached = checker._get_cached(host_key)
        assert cached is None

    @pytest.mark.asyncio
    async def test_ac76_different_hosts_cached_separately(self) -> None:
        """AC76: 異なるホストが別々にキャッシュされること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        ):
            await checker.is_allowed("https://example.com/page")
            await checker.is_allowed("https://other.com/page")

        assert "https://example.com" in checker._cache
        assert "https://other.com" in checker._cache


class TestRobotsTxtCheckerWebCrawlerIntegration:
    """WebCrawler との統合テスト."""

    @pytest.mark.asyncio
    async def test_ac72_crawl_page_blocked_by_robots_txt(self) -> None:
        """AC72: robots.txt でブロックされたURLはcrawl_pageがNoneを返すこと."""
        from src.services.web_crawler import WebCrawler

        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=MockRobotsSession(200, ROBOTS_TXT_BASIC),
        ):
            crawler = WebCrawler(robots_txt_checker=checker)
            # /admin/ はDisallowなのでNone
            page = await crawler.crawl_page("https://example.com/admin/settings")

        assert page is None

    @pytest.mark.asyncio
    async def test_ac74_robots_txt_disabled(self) -> None:
        """AC74: robots_txt_checker=None の場合、robots.txt を無視すること."""
        from tests.test_web_crawler import MockClientSession, SAMPLE_HTML_WITH_ARTICLE
        from src.services.web_crawler import WebCrawler

        # robots_txt_checker を渡さない = robots.txt 無視
        crawler = WebCrawler()

        with patch(
            "src.services.web_crawler.aiohttp.ClientSession",
            return_value=MockClientSession(200, SAMPLE_HTML_WITH_ARTICLE),
        ):
            # /admin/ でもクロールできる
            page = await crawler.crawl_page("https://example.com/admin/settings")

        assert page is not None

    @pytest.mark.asyncio
    async def test_ac73_crawl_delay_respected_in_crawl_pages(self) -> None:
        """AC73: crawl_pages で robots.txt の Crawl-delay が設定値より長い場合はそちらを採用すること."""
        from unittest.mock import AsyncMock as AM
        from src.services.web_crawler import WebCrawler

        # Crawl-delay 5秒、設定値 1秒 → 5秒が採用される
        mock_checker = AM(spec=RobotsTxtChecker)
        mock_checker.is_allowed = AM(return_value=True)
        mock_checker.get_crawl_delay = AM(return_value=5.0)

        crawler = WebCrawler(
            crawl_delay=1.0,
            robots_txt_checker=mock_checker,
        )

        # get_crawl_delay が呼ばれることを確認（crawl_pagesの内部で）
        from tests.test_web_crawler import MockClientSession, SAMPLE_HTML_WITH_ARTICLE

        with patch(
            "src.services.web_crawler.aiohttp.ClientSession",
            return_value=MockClientSession(200, SAMPLE_HTML_WITH_ARTICLE),
        ):
            urls = [
                "https://example.com/page1",
                "https://example.com/page2",
            ]
            pages = await crawler.crawl_pages(urls)

        # get_crawl_delay が呼ばれたことを確認
        assert mock_checker.get_crawl_delay.call_count >= 1
        # ページがクロールされたことを確認
        assert len(pages) >= 1


class TestRobotsTxtCheckerSettings:
    """設定のテスト."""

    def test_settings_defaults(self) -> None:
        """デフォルト設定が正しいこと."""
        from src.config.settings import Settings

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.rag_respect_robots_txt is True
        assert settings.rag_robots_txt_cache_ttl == 3600
