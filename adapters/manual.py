# -*- coding: utf-8 -*-
"""
手貼りテキストアダプタ。
manual/<駅id>/WEEKDAY.txt SATURDAY.txt HOLIDAY.txt を読んで解析する。
最も確実な最後の手段であり、他アダプタの fallback 先にもなる。
"""
from __future__ import annotations
import os
from typing import Dict, List

from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip
from lib.textparse import parse_hour_block_text
from adapters.base import FetchError, empty_diagrams

_FILES = {WEEKDAY: "WEEKDAY.txt", SATURDAY: "SATURDAY.txt", HOLIDAY: "HOLIDAY.txt"}


def manual_dir(root: str, station_id: str) -> str:
    return os.path.join(root, "manual", station_id)


def has_manual(root: str, station_id: str) -> bool:
    d = manual_dir(root, station_id)
    return any(os.path.exists(os.path.join(d, fn)) for fn in _FILES.values())


def fetch(station: dict, root: str) -> Dict[str, List[Trip]]:
    d = manual_dir(root, station["id"])
    if not os.path.isdir(d):
        raise FetchError(f"manual フォルダが無い: {d}")
    dest = station.get("destination", "") or ""
    out = empty_diagrams()
    found = False
    for dia, fn in _FILES.items():
        path = os.path.join(d, fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        trips = parse_hour_block_text(text, destination=dest)
        if trips:
            out[dia] = trips
            found = True
    if not found:
        raise FetchError(f"manual テキストから時刻を読めない: {d}")
    return out
