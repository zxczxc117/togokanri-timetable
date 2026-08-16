# -*- coding: utf-8 -*-
"""
Yahoo!路線情報アダプタ（公式が取れない時の保険）。

Yahoo!路線情報の駅時刻表は平日/土曜/日祝が URL の kind で分かれる:
  ...&kind=1 平日  &kind=2 土曜  &kind=3 日曜祝日
表は「時 → その時台の分（種別記号つき）」の構造で、
requests + BeautifulSoup で静的に取得できることが多い。
取得できない場合は FetchError を送出する。
"""
from __future__ import annotations
import re
from typing import Dict, List

from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip
from adapters.base import FetchError, empty_diagrams, ensure_nonempty

_KIND_PARAM = {WEEKDAY: "1", SATURDAY: "2", HOLIDAY: "3"}
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; togokanri-timetable/1.0)"}


def _with_kind(url: str, kind: str) -> str:
    if "kind=" in url:
        return re.sub(r"kind=\d", f"kind={kind}", url)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}kind={kind}"


def _parse_yahoo_html(html: str, destination: str) -> List[Trip]:
    try:
        from bs4 import BeautifulSoup
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"BeautifulSoup が使えません: {e}")
    soup = BeautifulSoup(html, "lxml")
    trips: List[Trip] = []
    # Yahoo は各時台が <tr> で、先頭セルが時、以降が便（分＋種別）
    for tr in soup.select("table tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        head = cells[0].get_text(strip=True)
        m = re.match(r"^(\d{1,2})", head)
        if not m:
            continue
        hour = int(m.group(1))
        if hour < 0 or hour > 27:
            continue
        for c in cells[1:]:
            for tok in re.findall(r"\d{1,2}", c.get_text(" ", strip=True)):
                mi = int(tok)
                if 0 <= mi <= 59:
                    trips.append(Trip(time=f"{hour:02d}:{mi:02d}",
                                      kind="普通", destination=destination))
    return trips


def fetch(station: dict, root: str = "") -> Dict[str, List[Trip]]:
    try:
        import requests
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"requests が使えません: {e}")
    url = station.get("url", "")
    if "transit.yahoo" not in url:
        raise FetchError("yahoo アダプタには Yahoo!路線情報のURLが必要です")
    dest = station.get("destination", "") or ""
    out = empty_diagrams()
    for dia, kind in _KIND_PARAM.items():
        u = _with_kind(url, kind)
        try:
            r = requests.get(u, headers=_HEADERS, timeout=20)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            raise FetchError(f"Yahoo取得失敗({dia}): {e}")
        out[dia] = _parse_yahoo_html(r.text, dest)
    ensure_nonempty(out)
    return out
