"""天気予報MCPサーバー
仕様: docs/specs/f5-mcp-integration.md

Open-Meteo API を使用して天気予報データを提供する。
分離制約: src/ 配下のモジュールは一切importしない。
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("weather")

# WMO Weather Codes → 日本語の天気説明
WMO_WEATHER_CODES: dict[int, str] = {
    0: "快晴",
    1: "晴れ",
    2: "一部曇り",
    3: "曇り",
    45: "霧",
    48: "着氷性の霧",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    56: "弱い着氷性の霧雨",
    57: "強い着氷性の霧雨",
    61: "弱い雨",
    63: "雨",
    65: "強い雨",
    66: "弱い着氷性の雨",
    67: "強い着氷性の雨",
    71: "弱い雪",
    73: "雪",
    75: "強い雪",
    77: "霧雪",
    80: "弱いにわか雨",
    81: "にわか雨",
    82: "激しいにわか雨",
    85: "弱いにわか雪",
    86: "激しいにわか雪",
    95: "雷雨",
    96: "雹を伴う雷雨",
    99: "激しい雹を伴う雷雨",
}


def _weather_code_to_text(code: int) -> str:
    """WMO天気コードを日本語テキストに変換する."""
    return WMO_WEATHER_CODES.get(code, f"不明(コード: {code})")


def _needs_umbrella(code: int) -> bool:
    """天気コードから傘が必要かどうかを判定する."""
    return code >= 51  # 霧雨以上の降水


async def _geocode(location: str) -> tuple[float, float, str]:
    """地名から緯度・経度を取得する.

    Returns:
        (latitude, longitude, resolved_name) のタプル

    Raises:
        ValueError: 地名が見つからない場合
    """
    params = urllib.parse.urlencode({
        "name": location,
        "count": 1,
        "language": "ja",
        "format": "json",
    })
    url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = data.get("results", [])
    if not results:
        raise ValueError(f"地域 '{location}' が見つかりませんでした。")

    result = results[0]
    name = result.get("name", location)
    country = result.get("country", "")
    admin1 = result.get("admin1", "")
    display = f"{name}"
    if admin1 and admin1 != name:
        display = f"{name} ({admin1}, {country})"
    elif country:
        display = f"{name} ({country})"

    return float(result["latitude"]), float(result["longitude"]), display


async def _fetch_forecast(
    latitude: float, longitude: float, forecast_days: int = 7
) -> dict:  # type: ignore[type-arg]
    """Open-Meteo API から天気予報データを取得する.

    Returns:
        APIレスポンスの辞書
    """
    params = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "Asia/Tokyo",
        "forecast_days": forecast_days,
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data: dict = json.loads(resp.read().decode("utf-8"))  # type: ignore[type-arg]

    return data


@mcp.tool()
async def get_weather(location: str, date: str = "today") -> str:
    """指定された場所の天気予報を取得する.

    Args:
        location: 地域名（例: "東京", "大阪", "札幌", "New York"）
        date: 日付指定（"today" = 今日, "tomorrow" = 明日, "week" = 週間予報）

    Returns:
        天気予報のテキスト
    """
    try:
        lat, lon, display_name = await _geocode(location)
    except ValueError as e:
        return str(e)
    except Exception:
        logger.exception("Geocoding failed for %s", location)
        return f"地域 '{location}' の検索中にエラーが発生しました。"

    try:
        forecast_days = 7 if date == "week" else 2
        data = await _fetch_forecast(lat, lon, forecast_days)
    except Exception:
        logger.exception("Forecast fetch failed for %s", location)
        return f"'{display_name}' の天気予報の取得中にエラーが発生しました。"

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    weather_codes = daily.get("weather_code", [])
    temp_maxes = daily.get("temperature_2m_max", [])
    temp_mins = daily.get("temperature_2m_min", [])

    if not dates:
        return f"'{display_name}' の天気予報データが取得できませんでした。"

    lines = [f"{display_name} の天気予報:"]

    if date == "today":
        idx = 0
        weather = _weather_code_to_text(weather_codes[idx])
        umbrella = "必要" if _needs_umbrella(weather_codes[idx]) else "不要"
        lines.append(
            f"今日 ({dates[idx]}): {weather}、"
            f"最高 {temp_maxes[idx]}°C / 最低 {temp_mins[idx]}°C、"
            f"傘: {umbrella}"
        )
    elif date == "tomorrow":
        if len(dates) < 2:
            return f"'{display_name}' の明日の天気予報データがありません。"
        idx = 1
        weather = _weather_code_to_text(weather_codes[idx])
        umbrella = "必要" if _needs_umbrella(weather_codes[idx]) else "不要"
        lines.append(
            f"明日 ({dates[idx]}): {weather}、"
            f"最高 {temp_maxes[idx]}°C / 最低 {temp_mins[idx]}°C、"
            f"傘: {umbrella}"
        )
    elif date == "week":
        for i, d in enumerate(dates):
            weather = _weather_code_to_text(weather_codes[i])
            lines.append(
                f"  {d}: {weather}、"
                f"最高 {temp_maxes[i]}°C / 最低 {temp_mins[i]}°C"
            )
    else:
        return f"日付指定 '{date}' は無効です。'today', 'tomorrow', 'week' のいずれかを指定してください。"

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
