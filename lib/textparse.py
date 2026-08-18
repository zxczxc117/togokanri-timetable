# -*- coding: utf-8 -*-
"""
時刻表テキスト/表の解析ユーティリティ。

公式サイト・Yahoo!・手貼りテキストのいずれも、最終的に
「時（毎時）ごとに分のリスト」へ落とし込めれば Trip 化できる。
ここでは代表的な貼り付け形式を吸収する:

  形式1（列コピー: 時のあとに分が縦に並ぶ）
      5
      30
      47◆
      6
      6◆
      24◆

  形式2（"6時 05 20 38" のような行）
      6時 05 20 38
      7時 02 15 30 48

  形式3（"5<TAB>38 52" のようにタブ/空白区切り）
      5	38 52
      6	05 20 38 51

いずれも次を正しく扱う:
  - ◆ ▲ ＊ * などの種別記号（除去し、必要なら kind ヒントに使う）
  - 24時を超える "25:05" 表記（そのまま保持）
  - 全角数字・全角スペース
"""
from __future__ import annotations
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

try:
    from lib.model import Trip
except ModuleNotFoundError:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from lib.model import Trip

_HOUR_TOKEN = re.compile(r"^(\d{1,2})\s*(?:時|:|：)?$")
_MIN_TOKEN = re.compile(r"(\d{1,2})")


def _z2h(s: str) -> str:
    """全角英数記号・全角スペースを半角へ。"""
    return unicodedata.normalize("NFKC", s)


def _clean_symbols(tok: str) -> Tuple[str, str]:
    """トークンから分の数字だけ取り出し、付随記号を返す。"""
    m = _MIN_TOKEN.search(tok)
    if not m:
        return "", ""
    mins = m.group(1)
    symbols = tok.replace(mins, "", 1)
    symbols = re.sub(r"\s+", "", symbols)
    return mins, symbols


def parse_hour_block_text(
    text: str,
    default_kind: str = "普通",
    destination: str = "",
    symbol_kind: Optional[Dict[str, str]] = None,
) -> List[Trip]:
    """時刻表テキスト（形式1/2/3のいずれか混在可）を Trip リストへ変換する。"""
    symbol_kind = symbol_kind or {}
    text = _z2h(text)
    trips: List[Trip] = []
    cur_hour: Optional[int] = None

    def add(hour: int, tok: str):
        mins, sym = _clean_symbols(tok)
        if mins == "":
            return
        mi = int(mins)
        if mi > 59:
            return
        kind = symbol_kind.get(sym, default_kind) if sym else default_kind
        trips.append(Trip(time=f"{hour:02d}:{mi:02d}",
                          kind=kind, destination=destination))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = re.split(r"[\s\u3000,]+", line)
        parts = [p for p in parts if p]
        head = parts[0]
        hm = _HOUR_TOKEN.match(head)

        # 形式2/3: 先頭が時トークンで後続に分が並ぶ（"6時 05 20" / "5\t38 52"）
        if hm and len(parts) >= 2:
            hour = int(hm.group(1))
            if 0 <= hour <= 27:
                cur_hour = hour
                for tok in parts[1:]:
                    add(hour, tok)
                continue

        # 単独トークン行（形式1: 縦並び）
        if len(parts) == 1:
            num_m = _MIN_TOKEN.search(head)
            val = int(num_m.group(1)) if num_m else None
            # 明示的に「時」記号付き → 常に時
            explicit_hour = bool(re.search(r"[時:：]", head))
            is_new_hour = False
            if val is not None:
                if explicit_hour and 0 <= val <= 27:
                    is_new_hour = True
                elif cur_hour is None and 0 <= val <= 27:
                    is_new_hour = True   # 先頭は必ず時
                elif cur_hour is not None and val == cur_hour + 1 and val <= 27 \
                        and "◆" not in head and "▲" not in head and "*" not in head:
                    is_new_hour = True   # 直前の時の +1 は次の時とみなす
            if is_new_hour:
                cur_hour = val
                continue
            if cur_hour is not None:
                add(cur_hour, head)
            continue

        # 先頭が時でない複数トークン → 現在の時に全て分として足す
        if cur_hour is not None:
            for tok in parts:
                add(cur_hour, tok)

    return trips


_KNOWN_KINDS = ("ミュースカイ", "快速特急", "快速急行", "特急", "急行", "準急", "普通")

def _cell_meta(cell: str, default_kind: str, default_destination: str):
    """色や小文字をテキスト化したセルから種別・行先を失わず取り出す。"""
    text = _z2h(cell or "").replace("\n", " ").strip()
    kind = default_kind
    km = re.search(r"\[種別:([^\]]+)\]", text)
    if km:
        kind = km.group(1).strip() or default_kind
    for candidate in _KNOWN_KINDS:
        if candidate in text:
            kind = candidate
            break
    dest = default_destination
    dm0 = re.search(r"\[行先:([^\]]+)\]", text)
    if dm0:
        dest = dm0.group(1).strip() or default_destination
    # 公式表の「栄町行」「栄町行き」「行先:栄町」を拾う。
    dm = re.search(r"(?:行先\s*[:：]?\s*|→\s*)([^\s,、]+?)(?:行き|行|$)", text)
    if dm:
        dest = dm.group(1).strip()
    return kind, dest

def parse_table_rows(
    rows: List[List[str]],
    default_kind: str = "普通",
    destination: str = "",
) -> List[Trip]:
    """表から時刻・種別・小文字の行先を抽出する。"""
    trips: List[Trip] = []
    for row in rows:
        cells = [_z2h(c).strip() for c in row if c is not None]
        cells = [c for c in cells if c != ""]
        if not cells:
            continue
        hm = _HOUR_TOKEN.match(cells[0])
        if not hm:
            continue
        hour = int(hm.group(1))
        for cell in cells[1:]:
            cell_kind, cell_dest = _cell_meta(cell, default_kind, destination)
            clean_cell = re.sub(r"\[(?:種別|行先):[^\]]+\]", " ", cell)
            for tok in re.split(r"[\s\u3000,]+", clean_cell):
                mins, _sym = _clean_symbols(tok)
                if mins == "" or int(mins) > 59:
                    continue
                trips.append(Trip(time=f"{hour:02d}:{int(mins):02d}",
                                  kind=cell_kind, destination=cell_dest))
    return trips


# ---- 自己テスト（build 実行時と単体実行で使う） ----
def self_test() -> List[str]:
    """解析処理の自己テスト。失敗した項目名のリストを返す（空なら全成功）。"""
    failures: List[str] = []

    # 形式1（列コピー・記号・全角）
    t1 = parse_hour_block_text("5\n30\n47◆\n6\n6◆\n24◆")
    got = [x.time for x in t1]
    if got != ["05:30", "05:47", "06:06", "06:24"]:
        failures.append(f"form1:{got}")

    # 形式2（"6時 05 20 38"）
    t2 = parse_hour_block_text("6時 05 20 38\n7時 02 15 30 48")
    got = [x.time for x in t2]
    if got != ["06:05", "06:20", "06:38", "07:02", "07:15", "07:30", "07:48"]:
        failures.append(f"form2:{got}")

    # 形式3（タブ区切り）
    t3 = parse_hour_block_text("5\t38 52\n6\t05 20 38 51")
    got = [x.time for x in t3]
    if got != ["05:38", "05:52", "06:05", "06:20", "06:38", "06:51"]:
        failures.append(f"form3:{got}")

    # 24時超（25:05）
    t4 = parse_hour_block_text("25\t05\n24\t10 40")
    got = [x.time for x in t4]
    if got != ["25:05", "24:10", "24:40"]:
        failures.append(f"over24:{got}")

    # 全角数字
    t5 = parse_hour_block_text("６時　０５　２０")
    got = [x.time for x in t5]
    if got != ["06:05", "06:20"]:
        failures.append(f"zenkaku:{got}")

    # 表形式
    t6 = parse_table_rows([["5", "38 52"], ["6", "05", "20", "38"]])
    got = [x.time for x in t6]
    if got != ["05:38", "05:52", "06:05", "06:20", "06:38"]:
        failures.append(f"table:{got}")

    return failures


if __name__ == "__main__":
    f = self_test()
    if f:
        print("FAIL:", f)
        raise SystemExit(1)
    print("解析処理の自己テスト: すべて成功")
