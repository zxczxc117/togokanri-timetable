# -*- coding: utf-8 -*-
"""名鉄：駅・路線・方面固有のTrainDiagramを取得する。"""
from __future__ import annotations

from typing import Dict, List
from urllib.parse import parse_qs, urlencode, urlparse

from lib.model import Trip
from adapters.base import FetchError
from adapters.meitetsu_parser import parse_meitetsu_diagram

BASE = "https://trainbus.meitetsu.co.jp/meitetsu-transfer/pc/diagram/TrainDiagram"


def resolve_diagram_url(station: dict) -> str:
    direction = str(station.get("direction_key", "")).lower().strip()
    start = str(station.get("start_id", "")).strip()
    link = str(station.get("link_id", "")).strip()
    explicit = str(station.get("diagram_url", "")).strip()

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


def fetch(
    station: dict,
    root: str = "",
) -> Dict[str, List[Trip]]:
    url = resolve_diagram_url(station)
    station["_resolved_url"] = url

    return parse_meitetsu_diagram(
        url=url,
        station=station,
    )