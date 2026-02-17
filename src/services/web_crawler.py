"""Webページクローラー

仕様: docs/specs/f9-rag.md
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes

logger = logging.getLogger(__name__)


class RobotsTxtChecker:
    """robots.txt の取得・解析・キャッシュを管理する.

    仕様: docs/specs/f9-rag.md (#160)

    ドメインごとに robots.txt をキャッシュし、Disallow / Crawl-delay を判定する。
    robots.txt の取得に失敗した場合はクロールを許可する（fail-open）。
    """

    def __init__(self, timeout: float = 10.0, user_agent: str = "*") -> None:
        """RobotsTxtCheckerを初期化する.

        Args:
            timeout: robots.txt 取得のタイムアウト秒数
            user_agent: robots.txt の判定に使用する User-Agent
        """
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._user_agent = user_agent
        self._cache: dict[str, RobotFileParser] = {}
        self._lock = asyncio.Lock()

    def _get_robots_url(self, url: str) -> str:
        """URLからrobots.txtのURLを生成する.

        Args:
            url: 対象URL

        Returns:
            robots.txt の URL
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _get_cache_key(self, url: str) -> str:
        """URLからキャッシュキー（scheme + netloc）を生成する.

        Args:
            url: 対象URL

        Returns:
            キャッシュキー
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def _fetch_robots_txt(self, robots_url: str) -> str | None:
        """robots.txt を取得する. 失敗時は None.

        Args:
            robots_url: robots.txt の URL

        Returns:
            robots.txt の内容、または取得失敗時は None
        """
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(robots_url, allow_redirects=True) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "robots.txt not found or error: %s (status=%d)",
                            robots_url,
                            resp.status,
                        )
                        return None
                    return await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            logger.debug("Failed to fetch robots.txt: %s - %s", robots_url, e)
            return None
        except Exception:
            logger.debug("Unexpected error fetching robots.txt: %s", robots_url, exc_info=True)
            return None

    async def _get_parser(self, url: str) -> RobotFileParser:
        """指定URLのドメインに対する RobotFileParser を取得する（キャッシュ付き）.

        Args:
            url: 対象URL

        Returns:
            RobotFileParser インスタンス
        """
        cache_key = self._get_cache_key(url)

        async with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        robots_url = self._get_robots_url(url)
        content = await self._fetch_robots_txt(robots_url)

        parser = RobotFileParser()
        parser.set_url(robots_url)
        if content is not None:
            parser.parse(content.splitlines())
        else:
            # 取得失敗時は全て許可（fail-open）
            # 空の robots.txt として解析するとデフォルトで全許可になる
            parser.parse([])

        async with self._lock:
            self._cache[cache_key] = parser

        return parser

    async def is_allowed(self, url: str) -> bool:
        """指定URLへのクロールが許可されているかを判定する.

        Args:
            url: 判定するURL

        Returns:
            True: クロール許可、False: クロール禁止
        """
        parser = await self._get_parser(url)
        result: bool = parser.can_fetch(self._user_agent, url)
        return result

    async def get_crawl_delay(self, url: str) -> float | None:
        """指定URLのドメインの Crawl-delay を取得する.

        Args:
            url: 対象URL

        Returns:
            Crawl-delay の値（秒）、未指定の場合は None
        """
        parser = await self._get_parser(url)
        delay = parser.crawl_delay(self._user_agent)
        if delay is not None:
            return float(delay)
        return None


@dataclass
class CrawledPage:
    """クロール結果."""

    url: str
    title: str
    text: str  # 抽出済みプレーンテキスト
    crawled_at: str  # ISO 8601 タイムスタンプ


class WebCrawler:
    """Webページクローラー.

    仕様: docs/specs/f9-rag.md
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_pages: int = 50,
        crawl_delay: float = 1.0,
        max_concurrent: int = 5,
        respect_robots_txt: bool = True,
    ) -> None:
        """WebCrawlerを初期化する.

        Args:
            timeout: HTTPリクエストのタイムアウト秒数
            max_pages: 1回のクロールで取得する最大ページ数
            crawl_delay: 同一ドメインへの連続リクエスト間の待機秒数
            max_concurrent: 同時接続数の上限
            respect_robots_txt: robots.txt を遵守するか（デフォルト: True）
        """
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_pages = max_pages
        self._crawl_delay = crawl_delay
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._respect_robots_txt = respect_robots_txt
        self._robots_checker: RobotsTxtChecker | None = (
            RobotsTxtChecker(timeout=min(timeout, 10.0)) if respect_robots_txt else None
        )

    def validate_url(self, url: str) -> str:
        """URL検証・正規化. 問題なければ正規化済みURLを返す.

        検証・正規化内容:
        - URLフラグメント（#以降）を除去
        - スキームが http または https であること
        - ホスト名がプライベートIP/localhost/リンクローカルでないこと（SSRF対策）
        - 検証失敗時は ValueError を送出

        Args:
            url: 検証するURL

        Returns:
            正規化済みURL（フラグメント除去済み）

        Raises:
            ValueError: URL検証に失敗した場合
        """
        # フラグメント除去（#以降を除去して正規化）
        defragmented_url, _ = urldefrag(url)
        parsed = urlparse(defragmented_url)

        # スキーム検証
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"許可されていないスキームです: {parsed.scheme}. http または https のみ許可されます。"
            )

        # ホスト名検証
        hostname = parsed.hostname or ""
        if not hostname:
            raise ValueError("URLにホスト名が含まれていません。")

        # SSRF対策: プライベートIP/localhost/リンクローカルをブロック
        self._validate_hostname_not_private(hostname)

        return defragmented_url

    async def _decode_response(self, resp: aiohttp.ClientResponse) -> str:
        """レスポンスボディをエンコーディング自動検出でデコードする.

        charset_normalizerを使用してエンコーディングを自動検出し、
        日本語サイトのShift_JIS/EUC-JP等にも対応する。

        Args:
            resp: aiohttpのレスポンスオブジェクト

        Returns:
            デコードされたHTML文字列
        """
        raw_bytes = await resp.read()
        detected = from_bytes(raw_bytes).best()
        if detected:
            return str(detected)
        return raw_bytes.decode("utf-8", errors="replace")

    def _validate_hostname_not_private(self, hostname: str) -> None:
        """ホスト名がプライベートIP/localhost/リンクローカルでないことを検証する.

        SSRF対策として、以下のアドレスへのアクセスをブロック:
        - localhost / 127.0.0.0/8 (ループバック)
        - 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (RFC1918 プライベート)
        - 169.254.0.0/16 (リンクローカル)
        - ::1 (IPv6 ループバック)
        - fc00::/7 (IPv6 ユニークローカル)
        - fe80::/10 (IPv6 リンクローカル)

        Args:
            hostname: 検証するホスト名

        Raises:
            ValueError: プライベートアドレスへのアクセスが検出された場合
        """
        # localhost の文字列チェック
        if hostname.lower() in ("localhost", "localhost.localdomain"):
            raise ValueError("localhost へのアクセスは許可されていません。")

        # DNS解決してIPアドレスを取得
        try:
            # getaddrinfo で IPv4/IPv6 両方を取得
            addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            # DNS解決に失敗した場合は通す（接続時にエラーになる）
            return

        # 全ての解決済みIPアドレスをチェック
        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            # プライベート/予約済みIPをブロック
            # 注: 順序が重要。is_private は is_loopback/is_link_local を含むため、
            # より具体的なチェックを先に行う
            if ip.is_loopback:
                raise ValueError(
                    f"ループバックアドレス ({ip_str}) へのアクセスは許可されていません。"
                )
            if ip.is_link_local:
                raise ValueError(
                    f"リンクローカルアドレス ({ip_str}) へのアクセスは許可されていません。"
                )
            # IPv4の場合、169.254.0.0/16 (リンクローカル) も追加チェック
            if isinstance(ip, ipaddress.IPv4Address):
                if ip in ipaddress.ip_network("169.254.0.0/16"):
                    raise ValueError(
                        f"リンクローカルアドレス ({ip_str}) へのアクセスは許可されていません。"
                    )
            if ip.is_private:
                raise ValueError(
                    f"プライベートIPアドレス ({ip_str}) へのアクセスは許可されていません。"
                )
            if ip.is_reserved:
                raise ValueError(
                    f"予約済みアドレス ({ip_str}) へのアクセスは許可されていません。"
                )

    def _extract_text(self, html: str) -> tuple[str, str]:
        """HTMLから本文テキストを抽出する.

        抽出ロジック:
        1. <script>, <style>, <nav>, <header>, <footer> タグを除去
        2. <article> → <main> → <body> の優先順で本文領域を特定
        3. テキストを抽出してクリーンアップ

        Args:
            html: HTML文字列

        Returns:
            (title, text) のタプル
        """
        soup = BeautifulSoup(html, "html.parser")

        # タイトル抽出
        title = ""
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

        # 不要なタグを除去
        for tag_name in ("script", "style", "nav", "header", "footer", "aside", "noscript"):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # 本文領域を特定（優先順: article → main → body）
        content_element = soup.find("article")
        if content_element is None:
            content_element = soup.find("main")
        if content_element is None:
            content_element = soup.find("body")
        if content_element is None:
            content_element = soup

        # テキスト抽出とクリーンアップ
        text = content_element.get_text(separator="\n", strip=True)
        # 連続する空白行を1つにまとめる
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 連続するスペースを1つにまとめる
        text = re.sub(r"[ \t]+", " ", text)

        return title, text.strip()

    async def crawl_index_page(
        self,
        index_url: str,
        url_pattern: str = "",
    ) -> list[str]:
        """リンク集ページ内の <a> タグからURLリストを抽出する（深度1のみ、再帰クロールは行わない）.

        - index_url および抽出したリンクURLを validate_url() で検証
        - 抽出URL数が max_pages を超える場合は先頭 max_pages 件に制限

        Args:
            index_url: リンク集ページのURL
            url_pattern: 正規表現パターンでリンクをフィルタリング（任意）

        Returns:
            抽出されたURLのリスト

        Raises:
            ValueError: URL検証に失敗した場合
        """
        # インデックスページのURL検証
        validated_url = self.validate_url(index_url)

        # パターンのコンパイル
        pattern = re.compile(url_pattern) if url_pattern else None

        # ページ取得（SSRF対策: リダイレクト追従を無効化）
        async with aiohttp.ClientSession(
            timeout=self._timeout,
        ) as session:
            async with session.get(validated_url, allow_redirects=False) as resp:
                # リダイレクト応答の場合はログを出して空リストを返す
                if resp.status in (301, 302, 303, 307, 308):
                    logger.warning(
                        "Redirect detected (SSRF protection): %s -> %s",
                        index_url,
                        resp.headers.get("Location", "unknown"),
                    )
                    return []
                if resp.status != 200:
                    logger.warning("Failed to fetch index page: %s (status=%d)", index_url, resp.status)
                    return []
                html = await self._decode_response(resp)

        # リンク抽出
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()

        # インデックスページのホスト名を取得（同一ドメインチェック用）
        index_hostname = urlparse(validated_url).hostname or ""

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href")
            if not isinstance(href, str):
                continue
            # 相対URLを絶対URLに変換
            absolute_url = urljoin(index_url, href)

            # フラグメント除去（DNS解決を含むvalidate_url()より先に実行）
            normalized_url, _ = urldefrag(absolute_url)

            # 同一ドメインチェック: インデックスページと異なるドメインのリンクはスキップ
            link_hostname = urlparse(normalized_url).hostname or ""
            if link_hostname != index_hostname:
                logger.debug(
                    "Skipping external domain link: %s (index: %s)",
                    link_hostname,
                    index_hostname,
                )
                continue

            # 正規化済みURLで重複スキップ
            if normalized_url in seen:
                continue

            # パターンフィルタリング（正規化済みURLに対して適用）
            if pattern and not pattern.search(normalized_url):
                continue

            # スキーム検証・SSRF対策（DNS解決を含むので最後に実行）
            # 重複・パターンで弾かれたURLには問い合わせしない
            try:
                self.validate_url(normalized_url)
            except ValueError:
                continue

            seen.add(normalized_url)
            urls.append(normalized_url)

            # max_pages に達したら終了
            if len(urls) >= self._max_pages:
                break

        # robots.txt によるフィルタリング
        if self._robots_checker is not None and urls:
            allowed_urls: list[str] = []
            for link_url in urls:
                if await self._robots_checker.is_allowed(link_url):
                    allowed_urls.append(link_url)
                else:
                    logger.info("Blocked by robots.txt (index): %s", link_url)
            return allowed_urls

        return urls

    async def crawl_page(self, url: str) -> CrawledPage | None:
        """単一ページの本文テキストを取得する. 失敗時は None.

        - validate_url() でURL検証後にHTTPアクセスを行う
        - robots.txt 遵守が有効な場合、Disallow 対象パスはスキップする

        Args:
            url: クロールするURL

        Returns:
            CrawledPage オブジェクト、または失敗時は None
        """
        try:
            validated_url = self.validate_url(url)
        except ValueError as e:
            logger.warning("URL validation failed: %s - %s", url, e)
            return None

        # robots.txt チェック
        if self._robots_checker is not None:
            if not await self._robots_checker.is_allowed(validated_url):
                logger.info("Blocked by robots.txt: %s", validated_url)
                return None

        try:
            async with self._semaphore:
                async with aiohttp.ClientSession(
                    timeout=self._timeout,
                ) as session:
                    # SSRF対策: リダイレクト追従を無効化
                    async with session.get(validated_url, allow_redirects=False) as resp:
                        # リダイレクト応答の場合はログを出して None を返す
                        if resp.status in (301, 302, 303, 307, 308):
                            logger.warning(
                                "Redirect detected (SSRF protection): %s -> %s",
                                url,
                                resp.headers.get("Location", "unknown"),
                            )
                            return None
                        if resp.status != 200:
                            logger.warning("Failed to fetch page: %s (status=%d)", url, resp.status)
                            return None
                        html = await self._decode_response(resp)

            title, text = self._extract_text(html)
            crawled_at = datetime.now(tz=timezone.utc).isoformat()

            return CrawledPage(
                url=validated_url,
                title=title,
                text=text,
                crawled_at=crawled_at,
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout while fetching page: %s", url)
            return None
        except aiohttp.ClientError as e:
            logger.warning("HTTP error while fetching page: %s - %s", url, e)
            return None
        except Exception:
            logger.exception("Unexpected error while fetching page: %s", url)
            return None

    async def crawl_pages(self, urls: list[str]) -> list[CrawledPage]:
        """複数ページを並行クロールする.

        - Semaphore により同時接続数を max_concurrent に制限
        - 同一ドメインへの連続リクエスト間に crawl_delay 秒の待機を挿入（負荷軽減）
        - ページ単位でエラーを隔離し、他のページの処理は継続

        Args:
            urls: クロールするURLのリスト

        Returns:
            クロールに成功したページのリスト
        """
        if not urls:
            return []

        # ホストごとの最終リクエスト時刻を管理するロック付き辞書
        last_request_time: dict[str, float] = {}
        time_lock = asyncio.Lock()

        # robots.txt の Crawl-delay を考慮した実効遅延を取得
        robots_delays: dict[str, float] = {}
        if self._robots_checker is not None:
            checked_hosts: set[str] = set()
            for url in urls:
                hostname = urlparse(url).hostname or ""
                if hostname and hostname not in checked_hosts:
                    checked_hosts.add(hostname)
                    delay = await self._robots_checker.get_crawl_delay(url)
                    if delay is not None:
                        robots_delays[hostname] = delay

        async def crawl_with_delay(url: str) -> CrawledPage | None:
            """同一ドメインへの遅延を挿入してクロールする."""
            hostname = urlparse(url).hostname

            # robots.txt の Crawl-delay と設定値の大きい方を使用
            effective_delay = self._crawl_delay
            if hostname and hostname in robots_delays:
                effective_delay = max(self._crawl_delay, robots_delays[hostname])

            if hostname and effective_delay > 0:
                async with time_lock:
                    previous = last_request_time.get(hostname)
                    if previous is not None:
                        now = asyncio.get_event_loop().time()
                        elapsed = now - previous
                        if elapsed < effective_delay:
                            await asyncio.sleep(effective_delay - elapsed)
                    # リクエスト前に時刻を更新（他のタスクが同じホストに同時アクセスしないようにする）
                    last_request_time[hostname] = asyncio.get_event_loop().time()

            page = await self.crawl_page(url)

            # リクエスト後に実際の完了時刻を更新
            if hostname:
                async with time_lock:
                    last_request_time[hostname] = asyncio.get_event_loop().time()

            return page

        # 並行実行（Semaphore は crawl_page 内で適用される）
        tasks = [crawl_with_delay(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 成功したページのみを収集（例外はログ済みなのでスキップ）
        pages: list[CrawledPage] = []
        for result in results:
            if isinstance(result, CrawledPage):
                pages.append(result)

        return pages
