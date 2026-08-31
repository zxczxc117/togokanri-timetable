```python
# -*- coding: utf-8 -*-
"""名鉄：駅・路線・方面固有のTrainDiagramを取得する。"""
from __future__ import annotations

from typing import Dict, List
from urllib.parse import parse_qs, urlencode, urlparse

from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip
from adapters.base import FetchError
from adapters.scrape_common import render_html, ensure_nonempty
from adapters.meitetsu_parser import parse_meitetsu_diagram


BASE = (
    "https://trainbus.meitetsu.co.jp/"
    "meitetsu-transfer/pc/diagram/TrainDiagram"
)


def resolve_diagram_url(station: dict) -> str:
    direction = str(
        station.get("direction_key", "")
    ).lower().strip()

    start = str(
        station.get("start_id", "")
    ).strip()

    link = str(
        station.get("link_id", "")
    ).strip()

    explicit = str(
        station.get("diagram_url", "")
    ).strip()

    if direction not in {"up", "down"}:
        raise FetchError(
            f"名鉄 {station.get('id', '')} は "
            "direction_key=up/down が必要です"
        )

    if explicit:
        q = parse_qs(urlparse(explicit).query)

        if q.get("direction", [""])[0].lower() != direction:
            raise FetchError("名鉄URLのdirection不一致")

        if start and q.get("startId", [""])[0] != start:
            raise FetchError("名鉄URLのstartId不一致")

        if link and q.get("linkId", [""])[0] != link:
            raise FetchError("名鉄URLのlinkId不一致")

        return explicit

    if not start or not link:
        raise FetchError(
            f"名鉄 {station.get('id', '')} は "
            "start_id/link_id が未設定です"
        )

    query = urlencode({
        "startId": start,
        "linkId": link,
        "direction": direction,
    })

    return f"{BASE}?{query}"


def _resolve_detail(url: str) -> tuple[str | None, str | None]:
    """詳細ページから種別・行先を取得する。

    現状は名鉄parserから必要になった場合だけ呼び出される。
    同一URLの重複取得はparser側のキャッシュで防止する。
    """
    html, _ = render_html(url)

    # 詳細ページの表示例:
    # 「路線時刻表 瀬戸線(普通) 尾張瀬戸(ST20)行」
    text = " ".join(html.replace("<", " <").split())

    kind = None
    destination = None

    # HTMLタグを除去してテキストとして解析。
    import re

    plain = re.sub(r"<[^>]+>", " ", html)
    plain = " ".join(plain.split())

    kind_match = re.search(
        r"路線時刻表\s+[^ ]*?\((ミュースカイ|快速特急|快速急行|特急|急行|準急|普通)\)",
        plain,
    )
    if kind_match:
        kind = kind_match.group(1)

    destination_match = re.search(
        r"\((?:ST\d+|[A-Z]{1,3}\d+)\)行|"
        r"([^\s()]+)\([^)]*\)行",
        plain,
    )

    if destination_match:
        candidate = destination_match.group(1)
        if candidate:
            destination = candidate

    return kind, destination


def fetch(
    station: dict,
    root: str = "",
) -> Dict[str, List[Trip]]:
    url = resolve_diagram_url(station)
    station["_resolved_url"] = url

    html, final_url = render_html(
        url,
        wait_selector="table",
    )

    trips = parse_meitetsu_diagram(
        html,
        base_url=final_url,
        detail_resolver=_resolve_detail,
    )

    if not trips:
        raise FetchError(
            f"名鉄時刻表を解析できませんでした: {url}"
        )

    # 現在の名鉄TrainDiagramは、
    # 平日・土休日を同一HTML内に左右並列で持つ。
    #
    # 名鉄parserは列車単位の解析を担当し、
    # 現状は取得結果を平日側へ格納する。
    #
    # ※土休日も正確に分離する必要がある場合は、
    # parserの戻り値を曜日別Dictへ拡張する。
    out: Dict[str, List[Trip]] = {
        WEEKDAY: trips,
        SATURDAY: [],
        HOLIDAY: [],
    }

    ensure_nonempty(out)

    return out
```
