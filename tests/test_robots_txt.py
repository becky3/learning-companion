"""RobotsTxtChecker テスト

仕様: docs/specs/f9-robots-txt.md
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.services.robots_txt import RobotsTxtChecker, _RobotsTxtData, _Rule


# ========================================
# テスト用 robots.txt サンプル
# ========================================

ROBOTS_TXT_BASIC = """\
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /admin/public/
"""

ROBOTS_TXT_SPECIFIC_UA = """\
User-agent: AIAssistantBot
Disallow: /bot-blocked/

User-agent: *
Disallow: /general-blocked/
"""

ROBOTS_TXT_WITH_CRAWL_DELAY = """\
User-agent: *
Disallow: /secret/
Crawl-delay: 5
"""

ROBOTS_TXT_WILDCARD = """\
User-agent: *
Disallow: /search*results
Disallow: /*.pdf$
Allow: /search
"""

ROBOTS_TXT_EMPTY_DISALLOW = """\
User-agent: *
Disallow:
"""

ROBOTS_TXT_NO_MATCHING_UA = """\
User-agent: SomeOtherBot
Disallow: /blocked/
"""

ROBOTS_TXT_COMMENTS = """\
# This is a comment
User-agent: *  # all bots
Disallow: /private/  # private area
Allow: /private/public/  # but this is ok
"""

ROBOTS_TXT_MULTIPLE_UA_GROUPS = """\
User-agent: AIAssistantBot
User-agent: AnotherBot
Disallow: /multi-blocked/

User-agent: *
Disallow: /general/
"""

ROBOTS_TXT_CASE_INSENSITIVE_UA = """\
User-agent: aiassistantbot
Disallow: /case-test/
"""


# ========================================
# モック HTTP レスポンス
# ========================================

class MockAiohttpResponse:
    """モック aiohttp レスポンス."""

    def __init__(self, status: int = 200, text: str = "") -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> "MockAiohttpResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class MockAiohttpSession:
    """モック aiohttp セッション."""

    def __init__(self, response: MockAiohttpResponse) -> None:
        self._response = response
        self.last_url: str = ""

    def get(self, url: str, **kwargs: object) -> MockAiohttpResponse:  # noqa: ARG002
        self.last_url = url
        return self._response

    async def __aenter__(self) -> "MockAiohttpSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


def _make_mock_session(status: int = 200, text: str = "") -> MockAiohttpSession:
    """モックセッションを作成する."""
    return MockAiohttpSession(MockAiohttpResponse(status, text))


# ========================================
# パースのテスト
# ========================================

class TestRobotsTxtParsing:
    """robots.txt パースのテスト."""

    def test_ac1_basic_parsing(self) -> None:
        """AC1: robots.txt をパースしてルールを取得できること."""
        checker = RobotsTxtChecker()
        data = checker._parse(ROBOTS_TXT_BASIC)
        assert len(data.rules) == 3
        assert data.rules[0].path == "/private/"
        assert data.rules[0].allow is False
        assert data.rules[1].path == "/admin/"
        assert data.rules[1].allow is False
        assert data.rules[2].path == "/admin/public/"
        assert data.rules[2].allow is True

    def test_ac2_wildcard_user_agent(self) -> None:
        """AC2: User-agent * のルールが適用されること."""
        checker = RobotsTxtChecker(user_agent="UnknownBot")
        data = checker._parse(ROBOTS_TXT_BASIC)
        assert len(data.rules) > 0

    def test_ac3_specific_user_agent_priority(self) -> None:
        """AC3: 自身の User-Agent に一致するグループが優先されること."""
        checker = RobotsTxtChecker(user_agent="AIAssistantBot")
        data = checker._parse(ROBOTS_TXT_SPECIFIC_UA)
        # AIAssistantBot グループのルールが適用される
        assert len(data.rules) == 1
        assert data.rules[0].path == "/bot-blocked/"

    def test_ac3_specific_ua_case_insensitive(self) -> None:
        """AC3: User-Agent マッチングが大文字小文字不問であること."""
        checker = RobotsTxtChecker(user_agent="AIAssistantBot")
        data = checker._parse(ROBOTS_TXT_CASE_INSENSITIVE_UA)
        assert len(data.rules) == 1
        assert data.rules[0].path == "/case-test/"

    def test_ac11_empty_disallow(self) -> None:
        """AC11: 空の Disallow が全URL許可として扱われること."""
        checker = RobotsTxtChecker()
        data = checker._parse(ROBOTS_TXT_EMPTY_DISALLOW)
        # 空の Disallow はルールとして追加されない
        assert len(data.rules) == 0

    def test_no_matching_user_agent(self) -> None:
        """マッチする User-Agent がない場合、全URLが許可されること."""
        checker = RobotsTxtChecker(user_agent="AIAssistantBot")
        data = checker._parse(ROBOTS_TXT_NO_MATCHING_UA)
        # * も自身のUAもないため、ルールなし
        assert len(data.rules) == 0

    def test_comments_stripped(self) -> None:
        """コメントが正しく除去されること."""
        checker = RobotsTxtChecker()
        data = checker._parse(ROBOTS_TXT_COMMENTS)
        assert len(data.rules) == 2
        assert data.rules[0].path == "/private/"
        assert data.rules[1].path == "/private/public/"

    def test_crawl_delay_parsed(self) -> None:
        """AC14: Crawl-delay が正しくパースされること."""
        checker = RobotsTxtChecker()
        data = checker._parse(ROBOTS_TXT_WITH_CRAWL_DELAY)
        assert data.crawl_delay == 5.0

    def test_crawl_delay_invalid_value(self) -> None:
        """不正な Crawl-delay 値が無視されること."""
        checker = RobotsTxtChecker()
        data = checker._parse("User-agent: *\nCrawl-delay: abc\n")
        assert data.crawl_delay is None

    def test_multiple_user_agents_in_group(self) -> None:
        """複数の User-agent 行を持つグループが正しくパースされること."""
        checker = RobotsTxtChecker(user_agent="AIAssistantBot")
        data = checker._parse(ROBOTS_TXT_MULTIPLE_UA_GROUPS)
        assert len(data.rules) == 1
        assert data.rules[0].path == "/multi-blocked/"

    def test_empty_robots_txt(self) -> None:
        """空の robots.txt が全URL許可になること."""
        checker = RobotsTxtChecker()
        data = checker._parse("")
        assert len(data.rules) == 0
        assert data.crawl_delay is None


# ========================================
# パスマッチングのテスト
# ========================================

class TestRobotsTxtPathMatching:
    """パスマッチングのテスト."""

    def test_ac6_disallow_blocks_path(self) -> None:
        """AC6: Disallow 指定されたパスがブロックされること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[_Rule(path="/private/", allow=False)])
        assert checker._check_path(data, "/private/page") is False
        assert checker._check_path(data, "/private/") is False

    def test_ac6_disallow_does_not_block_other_paths(self) -> None:
        """AC6: Disallow 指定されていないパスは許可されること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[_Rule(path="/private/", allow=False)])
        assert checker._check_path(data, "/public/page") is True
        assert checker._check_path(data, "/") is True

    def test_ac7_allow_permits_path(self) -> None:
        """AC7: Allow 指定されたパスが許可されること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[
            _Rule(path="/admin/", allow=False),
            _Rule(path="/admin/public/", allow=True),
        ])
        assert checker._check_path(data, "/admin/public/page") is True

    def test_ac8_longest_match_wins(self) -> None:
        """AC8: Allow と Disallow が競合する場合、最長一致のルールが優先されること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[
            _Rule(path="/admin/", allow=False),
            _Rule(path="/admin/public/", allow=True),
        ])
        # /admin/public/ は最長一致で Allow
        assert checker._check_path(data, "/admin/public/page") is True
        # /admin/secret はDisallowのみマッチ
        assert checker._check_path(data, "/admin/secret") is False

    def test_ac8_same_length_allow_wins(self) -> None:
        """AC8: 同一長さの場合は Allow が優先されること（RFC 9309）."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[
            _Rule(path="/page", allow=False),
            _Rule(path="/page", allow=True),
        ])
        assert checker._check_path(data, "/page") is True

    def test_ac9_wildcard_pattern(self) -> None:
        """AC9: ワイルドカード * パターンが正しくマッチすること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[
            _Rule(path="/search*results", allow=False),
        ])
        assert checker._check_path(data, "/search/some/results") is False
        assert checker._check_path(data, "/searchresults") is False
        assert checker._check_path(data, "/search") is True

    def test_ac10_end_anchor_pattern(self) -> None:
        """AC10: 終端 $ パターンが正しくマッチすること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[
            _Rule(path="/*.pdf$", allow=False),
        ])
        assert checker._check_path(data, "/document.pdf") is False
        assert checker._check_path(data, "/document.pdf?query=1") is True
        assert checker._check_path(data, "/document.html") is True

    def test_no_rules_allows_all(self) -> None:
        """ルールなしの場合、全URLが許可されること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData()
        assert checker._check_path(data, "/anything") is True

    def test_no_matching_rules_allows(self) -> None:
        """マッチするルールがない場合、URLが許可されること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[_Rule(path="/private/", allow=False)])
        assert checker._check_path(data, "/other/page") is True

    def test_root_disallow_blocks_all(self) -> None:
        """Disallow: / が全パスをブロックすること."""
        checker = RobotsTxtChecker()
        data = _RobotsTxtData(rules=[_Rule(path="/", allow=False)])
        assert checker._check_path(data, "/any/path") is False
        assert checker._check_path(data, "/") is False


# ========================================
# HTTP 取得・キャッシュのテスト
# ========================================

class TestRobotsTxtFetching:
    """robots.txt HTTP取得のテスト."""

    @pytest.mark.asyncio
    async def test_ac1_fetch_and_parse(self) -> None:
        """AC1: robots.txt をHTTP経由で取得し、ルールをパースできること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(200, ROBOTS_TXT_BASIC),
        ):
            result = await checker.is_allowed("https://example.com/private/page")

        assert result is False

    @pytest.mark.asyncio
    async def test_ac4_404_allows_all(self) -> None:
        """AC4: robots.txt が存在しない場合（HTTP 404）、全URLが許可されること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(404, ""),
        ):
            result = await checker.is_allowed("https://example.com/any/page")

        assert result is True

    @pytest.mark.asyncio
    async def test_ac5_timeout_allows_all(self) -> None:
        """AC5: robots.txt 取得がタイムアウトした場合、全URLが許可されること."""
        checker = RobotsTxtChecker()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=TimeoutError("timeout"))

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await checker.is_allowed("https://example.com/any/page")

        assert result is True

    @pytest.mark.asyncio
    async def test_ac5_network_error_allows_all(self) -> None:
        """AC5: ネットワークエラーの場合、全URLが許可されること（fail-open）."""
        checker = RobotsTxtChecker()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientError("connection failed")
        )

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await checker.is_allowed("https://example.com/any/page")

        assert result is True


class TestRobotsTxtCaching:
    """robots.txt キャッシュのテスト."""

    @pytest.mark.asyncio
    async def test_ac12_cache_prevents_refetch(self) -> None:
        """AC12: 同一ドメインへの複数リクエストで robots.txt が再取得されないこと."""
        checker = RobotsTxtChecker(cache_ttl=3600)

        mock_session = _make_mock_session(200, ROBOTS_TXT_BASIC)

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=mock_session,
        ) as mock_cls:
            # 1回目
            await checker.is_allowed("https://example.com/page1")
            # 2回目（キャッシュから）
            await checker.is_allowed("https://example.com/page2")

            # ClientSession は1回だけ作成される
            assert mock_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_ac13_cache_ttl_expiry(self) -> None:
        """AC13: キャッシュ TTL 経過後に robots.txt が再取得されること."""
        checker = RobotsTxtChecker(cache_ttl=1)

        mock_session = _make_mock_session(200, ROBOTS_TXT_BASIC)

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=mock_session,
        ) as mock_cls:
            # 1回目
            await checker.is_allowed("https://example.com/page1")
            assert mock_cls.call_count == 1

            # time.monotonic() をモックしてTTL超過をシミュレート
            with patch("src.services.robots_txt.time.monotonic", return_value=time.monotonic() + 10):
                await checker.is_allowed("https://example.com/page2")
                assert mock_cls.call_count == 2

    def test_clear_cache(self) -> None:
        """clear_cache() でキャッシュがクリアされること."""
        checker = RobotsTxtChecker()
        # キャッシュに直接データを入れる
        checker._cache["https://example.com"] = MagicMock()
        assert len(checker._cache) == 1
        checker.clear_cache()
        assert len(checker._cache) == 0


# ========================================
# Crawl-delay のテスト
# ========================================

class TestRobotsTxtCrawlDelay:
    """Crawl-delay のテスト."""

    @pytest.mark.asyncio
    async def test_ac14_crawl_delay_available(self) -> None:
        """AC14: robots.txt の Crawl-delay が取得できること."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(200, ROBOTS_TXT_WITH_CRAWL_DELAY),
        ):
            # is_allowed を呼んでキャッシュを構築
            await checker.is_allowed("https://example.com/page")

        delay = checker.get_crawl_delay("https://example.com/any")
        assert delay == 5.0

    def test_crawl_delay_none_when_not_cached(self) -> None:
        """キャッシュなしの場合、get_crawl_delay が None を返すこと."""
        checker = RobotsTxtChecker()
        assert checker.get_crawl_delay("https://example.com/page") is None

    @pytest.mark.asyncio
    async def test_crawl_delay_none_when_not_specified(self) -> None:
        """robots.txt に Crawl-delay がない場合、None を返すこと."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(200, ROBOTS_TXT_BASIC),
        ):
            await checker.is_allowed("https://example.com/page")

        assert checker.get_crawl_delay("https://example.com/any") is None


# ========================================
# is_allowed 統合テスト
# ========================================

class TestRobotsTxtIsAllowed:
    """is_allowed() の統合テスト."""

    @pytest.mark.asyncio
    async def test_allowed_path(self) -> None:
        """許可されたパスに対して True を返すこと."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(200, ROBOTS_TXT_BASIC),
        ):
            assert await checker.is_allowed("https://example.com/public/page") is True

    @pytest.mark.asyncio
    async def test_disallowed_path(self) -> None:
        """禁止されたパスに対して False を返すこと."""
        checker = RobotsTxtChecker()

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(200, ROBOTS_TXT_BASIC),
        ):
            assert await checker.is_allowed("https://example.com/private/page") is False

    @pytest.mark.asyncio
    async def test_query_string_in_path(self) -> None:
        """クエリ文字列を含むパスが正しく判定されること."""
        checker = RobotsTxtChecker()
        robots_txt = "User-agent: *\nDisallow: /search\n"

        with patch(
            "src.services.robots_txt.aiohttp.ClientSession",
            return_value=_make_mock_session(200, robots_txt),
        ):
            assert await checker.is_allowed("https://example.com/search?q=test") is False

    @pytest.mark.asyncio
    async def test_different_domains_separate_cache(self) -> None:
        """異なるドメインが別々にキャッシュされること."""
        checker = RobotsTxtChecker()

        call_count = 0

        async def tracking_fetch(origin: str) -> _RobotsTxtData:
            nonlocal call_count
            call_count += 1
            return _RobotsTxtData()

        with patch.object(checker, "_fetch_and_parse", side_effect=tracking_fetch):
            await checker.is_allowed("https://example.com/page")
            await checker.is_allowed("https://other.com/page")

        assert call_count == 2
