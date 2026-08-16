# -*- coding: utf-8 -*-
"""JR東海 駅時刻表アダプタ。JS描画後の表を取得する。"""
from __future__ import annotations
from typing import Dict, List
from lib.model import Trip
from adapters.scrape_common import scrape_station_tables


def fetch(station: dict, root: str = "") -> Dict[str, List[Trip]]:
    return scrape_station_tables(station, wait_selector="table")
