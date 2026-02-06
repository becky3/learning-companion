"""天気予報MCPサーバーのテスト (Issue #83, AC1-AC3).

仕様: docs/specs/f5-mcp-integration.md
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_geocode_response(name: str = "東京", lat: float = 35.6762, lon: float = 139.6503) -> bytes:
    """Geocoding APIのモックレスポンスを生成する."""
    return json.dumps({
        "results": [{
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "country": "日本",
            "admin1": "東京都",
        }]
    }).encode("utf-8")


def _make_forecast_response(
    dates: list[str] | None = None,
    weather_codes: list[int] | None = None,
    temp_maxes: list[float] | None = None,
    temp_mins: list[float] | None = None,
) -> bytes:
    """Forecast APIのモックレスポンスを生成する."""
    if dates is None:
        dates = ["2026-02-06", "2026-02-07"]
    if weather_codes is None:
        weather_codes = [1, 61]
    if temp_maxes is None:
        temp_maxes = [15.0, 12.0]
    if temp_mins is None:
        temp_mins = [5.0, 4.0]
    return json.dumps({
        "daily": {
            "time": dates,
            "weather_code": weather_codes,
            "temperature_2m_max": temp_maxes,
            "temperature_2m_min": temp_mins,
        }
    }).encode("utf-8")


@pytest.mark.asyncio
async def test_ac1_weather_server_exposes_tool() -> None:
    """AC1: 天気予報MCPサーバーが起動し、get_weather ツールを公開すること."""
    # server.py を import してツール登録を確認
    from importlib import import_module

    mod = import_module("mcp-servers.weather.server")
    server = mod.mcp

    # FastMCP のツール一覧を確認
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "get_weather" in tool_names


@pytest.mark.asyncio
async def test_ac2_get_weather_returns_forecast() -> None:
    """AC2: get_weather ツールが地域名と日付を受け取り、天気予報テキストを返すこと."""
    from importlib import import_module

    mod = import_module("mcp-servers.weather.server")
    get_weather = mod.get_weather

    # Geocoding と Forecast の両方をモック
    mock_geocode_resp = MagicMock()
    mock_geocode_resp.read.return_value = _make_geocode_response()
    mock_geocode_resp.__enter__ = lambda s: s
    mock_geocode_resp.__exit__ = MagicMock(return_value=False)

    mock_forecast_resp = MagicMock()
    mock_forecast_resp.read.return_value = _make_forecast_response()
    mock_forecast_resp.__enter__ = lambda s: s
    mock_forecast_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        # 1回目: Geocoding, 2回目: Forecast
        mock_urlopen.side_effect = [mock_geocode_resp, mock_forecast_resp]

        result = await get_weather("東京", "today")

    assert "東京" in result
    assert "15.0°C" in result
    assert "5.0°C" in result
    assert "晴れ" in result


@pytest.mark.asyncio
async def test_ac2_get_weather_tomorrow() -> None:
    """AC2: 明日の天気予報を取得できること."""
    from importlib import import_module

    mod = import_module("mcp-servers.weather.server")
    get_weather = mod.get_weather

    mock_geocode_resp = MagicMock()
    mock_geocode_resp.read.return_value = _make_geocode_response()
    mock_geocode_resp.__enter__ = lambda s: s
    mock_geocode_resp.__exit__ = MagicMock(return_value=False)

    mock_forecast_resp = MagicMock()
    mock_forecast_resp.read.return_value = _make_forecast_response()
    mock_forecast_resp.__enter__ = lambda s: s
    mock_forecast_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [mock_geocode_resp, mock_forecast_resp]
        result = await get_weather("東京", "tomorrow")

    assert "明日" in result
    assert "12.0°C" in result
    assert "弱い雨" in result  # weather_code=61


@pytest.mark.asyncio
async def test_ac2_get_weather_week() -> None:
    """AC2: 週間天気予報を取得できること."""
    from importlib import import_module

    mod = import_module("mcp-servers.weather.server")
    get_weather = mod.get_weather

    dates = [f"2026-02-{6 + i:02d}" for i in range(7)]
    codes = [1, 2, 3, 61, 0, 71, 1]
    maxes = [15.0, 14.0, 13.0, 10.0, 16.0, 8.0, 15.0]
    mins = [5.0, 4.0, 3.0, 2.0, 6.0, 0.0, 5.0]

    mock_geocode_resp = MagicMock()
    mock_geocode_resp.read.return_value = _make_geocode_response()
    mock_geocode_resp.__enter__ = lambda s: s
    mock_geocode_resp.__exit__ = MagicMock(return_value=False)

    mock_forecast_resp = MagicMock()
    mock_forecast_resp.read.return_value = _make_forecast_response(dates, codes, maxes, mins)
    mock_forecast_resp.__enter__ = lambda s: s
    mock_forecast_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [mock_geocode_resp, mock_forecast_resp]
        result = await get_weather("東京", "week")

    assert "東京" in result
    # 7日分のデータが含まれる
    for d in dates:
        assert d in result


@pytest.mark.asyncio
async def test_ac3_weather_api_fetches_real_data() -> None:
    """AC3: 外部天気予報API（Open-Meteo）から実データを取得すること.

    Geocoding と Forecast の正しいAPIエンドポイントが呼ばれることを検証する。
    """
    from importlib import import_module

    mod = import_module("mcp-servers.weather.server")
    get_weather = mod.get_weather

    mock_geocode_resp = MagicMock()
    mock_geocode_resp.read.return_value = _make_geocode_response("大阪", 34.6937, 135.5023)
    mock_geocode_resp.__enter__ = lambda s: s
    mock_geocode_resp.__exit__ = MagicMock(return_value=False)

    mock_forecast_resp = MagicMock()
    mock_forecast_resp.read.return_value = _make_forecast_response()
    mock_forecast_resp.__enter__ = lambda s: s
    mock_forecast_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [mock_geocode_resp, mock_forecast_resp]
        await get_weather("大阪", "today")

    # 2回呼ばれる: Geocoding + Forecast
    assert mock_urlopen.call_count == 2

    # Geocoding API のURL確認
    geocode_call = mock_urlopen.call_args_list[0]
    geocode_url = geocode_call[0][0].full_url
    assert "geocoding-api.open-meteo.com" in geocode_url
    assert "name=%E5%A4%A7%E9%98%AA" in geocode_url  # URL-encoded "大阪"

    # Forecast API のURL確認
    forecast_call = mock_urlopen.call_args_list[1]
    forecast_url = forecast_call[0][0].full_url
    assert "api.open-meteo.com" in forecast_url
    assert "latitude=34.6937" in forecast_url
    assert "longitude=135.5023" in forecast_url


@pytest.mark.asyncio
async def test_ac3_geocode_not_found() -> None:
    """AC3: 存在しない地域名の場合、エラーメッセージを返すこと."""
    from importlib import import_module

    mod = import_module("mcp-servers.weather.server")
    get_weather = mod.get_weather

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"results": []}).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = await get_weather("存在しない場所XYZ", "today")

    assert "見つかりませんでした" in result
