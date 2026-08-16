# -*- coding: utf-8 -*-
"""スクレイピング系アダプタの共通処理（表抽出）。"""
from __future__ import annotations
import re
from typing import Dict, List

from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip
from lib.textparse import parse_table_rows
from adapters.base import FetchError, empty_diagrams, ensure_nonempty, render_html


def extract_tables(html: str) -> List[List[List[str]]]:
    """HTML から全テーブルを rows(=list of cells) の集合として取り出す。"""
    try:
        from bs4 import BeautifulSoup
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"BeautifulSoup が使えません: {e}")
    soup = BeautifulSoup(html, "lxml")
    tables: List[List[List[str]]] = []
    for tbl in soup.find_all("table"):
        rows: List[List[str]] = []
        for tr in tbl.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def looks_like_timetable(rows: List[List[str]]) -> bool:
    """1列目が時（0-27）の行が複数あれば時刻表とみなす。"""
    hour_rows = 0
    for r in rows:
        if r and re.match(r"^\s*\d{1,2}\s*(時|:|：)?\s*$", r[0]):
            v = int(re.match(r"^\s*(\d{1,2})", r[0]).group(1))
            if 0 <= v <= 27:
                hour_rows += 1
    return hour_rows >= 4


def parse_dia_from_context(text: str) -> str:
    """見出し等の文言からダイヤ種別を推定する。"""
    if any(k in text for k in ("日曜", "休日", "祝日", "土曜・休日", "土休")):
        if "土曜" in text and "休日" not in text and "日曜" not in text:
            return SATURDAY
        return HOLIDAY
    if "土曜" in text:
        return SATURDAY
    return WEEKDAY


def scrape_station_tables(station: dict, wait_selector: str = "table") -> Dict[str, List[Trip]]:
    """
    汎用スクレイパ。ページを描画して全テーブルを取り、
    時刻表らしいテーブルを平日/土曜/休日に振り分ける。
    ダイヤの振り分けが不確実なため、種別が特定できない表は WEEKDAY 扱い。
    公式サイトはダイヤ切替が JS タブのことが多く、確実性は低い（fallback 前提）。
    """
    url = station["url"]
    dest = station.get("destination", "") or ""
    html = render_html(url, wait_selector=wait_selector)
    tables = extract_tables(html)
    tt = [t for t in tables if looks_like_timetable(t)]
    if not tt:
        raise FetchError("時刻表らしい表が見つかりません")
    out = empty_diagrams()
    # 先頭から WEEKDAY/SATURDAY/HOLIDAY の順に割り当てる素朴な方式
    order = [WEEKDAY, SATURDAY, HOLIDAY]
    for i, rows in enumerate(tt[:3]):
        dia = order[i] if i < len(order) else WEEKDAY
        out[dia] = parse_table_rows(rows, destination=dest)
    ensure_nonempty(out)
    return out
