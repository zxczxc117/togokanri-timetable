# -*- coding: utf-8 -*-
"""名鉄（名古屋鉄道）駅時刻表アダプタ。JS描画後の表を取得する。"""
from __future__ import annotations
from typing import Dict, List
from lib.model import Trip
from adapters.scrape_common import scrape_station_tables


def fetch(station: dict, root: str = "") -> Dict[str, List[Trip]]:
    # 名鉄の駅時刻表は方面・ダイヤがタブ切替。汎用表抽出で拾い、失敗時は fallback。
    return scrape_station_tables(station, wait_selector="table")
