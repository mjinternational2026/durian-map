#!/usr/bin/env python3
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = [
    ROOT / "dashboards" / "泰国到中国陆运天气互动地图.html",
    ROOT / "land-route-weather.html",
]
SNAPSHOT_PATH = ROOT / "data" / "processed" / "land_route_weather_forecast.json"

TIMEZONE = "Asia/Bangkok"
FORECAST_DAYS = 7

POINTS = [
    {
        "id": "langsuan",
        "name": "Lang Suan 春蓬",
        "lat": 9.95,
        "lng": 99.08,
        "routes": ["yunnan", "guangxi"],
        "sensitive": "果源出发/泰南主干道入口",
        "base": 0,
    },
    {
        "id": "bangkok",
        "name": "曼谷",
        "lat": 13.75,
        "lng": 100.50,
        "routes": ["yunnan", "guangxi"],
        "sensitive": "泰国中部绕城/北上分流",
        "base": 0,
    },
    {
        "id": "korat",
        "name": "呵叻",
        "lat": 14.97,
        "lng": 102.10,
        "routes": ["yunnan", "guangxi"],
        "sensitive": "泰国东北干线",
        "base": 0,
    },
    {
        "id": "nongkhai",
        "name": "廊开口岸",
        "lat": 17.88,
        "lng": 102.74,
        "routes": ["yunnan"],
        "sensitive": "口岸/桥梁通行",
        "base": 1,
    },
    {
        "id": "vientiane",
        "name": "万象",
        "lat": 17.97,
        "lng": 102.60,
        "routes": ["yunnan"],
        "sensitive": "老挝入境/城市段",
        "base": 1,
    },
    {
        "id": "luangprabang",
        "name": "琅勃拉邦",
        "lat": 19.89,
        "lng": 102.14,
        "routes": ["yunnan"],
        "sensitive": "老挝北部山路",
        "base": 2,
    },
    {
        "id": "mengla",
        "name": "磨憨/勐腊",
        "lat": 21.48,
        "lng": 101.56,
        "routes": ["yunnan"],
        "sensitive": "口岸+山地道路",
        "base": 2,
    },
    {
        "id": "kunming",
        "name": "昆明",
        "lat": 25.04,
        "lng": 102.72,
        "routes": ["yunnan"],
        "sensitive": "云南集散/高原路段",
        "base": 1,
    },
    {
        "id": "savannakhet",
        "name": "沙湾拿吉",
        "lat": 16.55,
        "lng": 104.75,
        "routes": ["guangxi"],
        "sensitive": "中老/越方向通道",
        "base": 1,
    },
    {
        "id": "hanoi",
        "name": "河内",
        "lat": 21.03,
        "lng": 105.85,
        "routes": ["guangxi"],
        "sensitive": "越南北部城市段",
        "base": 1,
    },
    {
        "id": "pingxiang",
        "name": "友谊关/凭祥",
        "lat": 22.10,
        "lng": 106.75,
        "routes": ["guangxi"],
        "sensitive": "中越口岸",
        "base": 1,
    },
    {
        "id": "nanning",
        "name": "南宁",
        "lat": 22.82,
        "lng": 108.32,
        "routes": ["guangxi"],
        "sensitive": "广西集散/城市配送",
        "base": 1,
    },
]


def fetch_point(point):
    params = {
        "latitude": point["lat"],
        "longitude": point["lng"],
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
            ]
        ),
        "timezone": TIMEZONE,
        "forecast_days": FORECAST_DAYS,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    daily = payload["daily"]
    return {
        **point,
        "weatherCode": daily["weather_code"],
        "rain": [round(float(value), 1) for value in daily["precipitation_sum"]],
        "pop": [int(value) for value in daily["precipitation_probability_max"]],
        "tempMax": [round(float(value), 1) for value in daily["temperature_2m_max"]],
        "tempMin": [round(float(value), 1) for value in daily["temperature_2m_min"]],
        "windMax": [round(float(value), 1) for value in daily["wind_speed_10m_max"]],
    }, daily["time"]


def js_value(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def js_node(node):
    parts = [
        f'id:{js_value(node["id"])}',
        f'name:{js_value(node["name"])}',
        f'lat:{node["lat"]:.2f}',
        f'lng:{node["lng"]:.2f}',
        f'routes:{js_value(node["routes"])}',
        f'sensitive:{js_value(node["sensitive"])}',
        f'rain:{js_value(node["rain"])}',
        f'pop:{js_value(node["pop"])}',
        f'tempMax:{js_value(node["tempMax"])}',
        f'tempMin:{js_value(node["tempMin"])}',
        f'weatherCode:{js_value(node["weatherCode"])}',
        f'windMax:{js_value(node["windMax"])}',
        f'base:{node["base"]}',
    ]
    return "      { " + ", ".join(parts) + " }"


def main():
    nodes = []
    dates = None
    for point in POINTS:
        node, point_dates = fetch_point(point)
        if dates is None:
            dates = point_dates
        elif dates != point_dates:
            raise RuntimeError(f"date mismatch for {point['id']}: {point_dates} != {dates}")
        nodes.append(node)

    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat(timespec="seconds")
    block = "\n".join(
        [
            "    // WEATHER_DATA_START",
            f"    const forecastUpdatedAt = {js_value(now)};",
            f"    const dates = {js_value(dates)};",
            "    const nodes = [",
            ",\n".join(js_node(node) for node in nodes),
            "    ];",
            "    // WEATHER_DATA_END",
        ]
    )

    for html_path in HTML_PATHS:
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")
        html = re.sub(
            r"    // WEATHER_DATA_START[\s\S]*?    // WEATHER_DATA_END",
            block,
            html,
            count=1,
        )
        html_path.write_text(html, encoding="utf-8")

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(
            {
                "updated_at": now,
                "timezone": TIMEZONE,
                "dates": dates,
                "nodes": nodes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"updated {len(nodes)} route weather points through {dates[-1]}")


if __name__ == "__main__":
    main()
