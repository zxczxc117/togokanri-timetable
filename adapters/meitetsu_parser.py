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
from typing import Callable, Dict, List, Optional, Tuple
from html.parser import HTMLParser
from urllib.parse import urljoin
from html import unescape

try:
    from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip
except ModuleNotFoundError:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip

_HOUR_TOKEN = re.compile(r"^(\d{1,2})\s*(?:時|:|：)?$")
_MIN_TOKEN = re.compile(r"(\d{1,2})")


def _z2h(s: str) -> str:
    """HTMLエンティティを復元し、全角英数記号・全角スペースを半角へ。"""
    s = unescape(s or "")
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



# ---- 名鉄公式 TrainDiagram 専用解析 ---------------------------------------
# 一般 parser は変更せず、名鉄固有の DOM 情報を保持したまま解析する。
_MEITETSU_DEST_CODE_RE = re.compile(r"^\s*([^\s:：]{1,4})\s*[:：]\s*(.+?)\s*$")
_MEITETSU_MINUTE_RE = re.compile(r"(?<!\d)(\d{1,2})(?:\s*分\s*はつ)?")
_MEITETSU_KIND_NAMES = ("ミュースカイ", "快速特急", "快速急行", "特急", "急行", "準急", "普通")
# 名鉄 TrainDiagram の CSS クラスと列車種別の対応。
# 実際の公式HTMLで確認済み:
#   d_04 = 普通
#   d_18 = 準急
#   d_38 = 急行
_MEITETSU_KIND_BY_MM_CLASS: Dict[str, str] = {
    "d_04": "普通",
    "d_18": "準急",
    "d_38": "急行",
}

def _meitetsu_kind_from_attrs(
    attrs: Dict[str, str],
    kind_class_map: Optional[Dict[str, str]] = None,
    kind_style_map: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """名鉄HTML属性から列車種別を取得する。

    優先順位:
      1. TrainDiagram の mm d_xx クラス
      2. 呼び出し側から指定された class map
      3. style map
      4. HTML属性内に種別名そのものがある場合
    """

    class_map = kind_class_map or {}
    style_map = kind_style_map or {}

    # ------------------------------------------------------------
    # 1. 名鉄公式 TrainDiagram の mm クラス
    # ------------------------------------------------------------
    mm_class = attrs.get("_meitetsu_mm_class", "")

    if mm_class:
        kind = _MEITETSU_KIND_BY_MM_CLASS.get(mm_class)

        if kind is not None:
            return kind

    # ------------------------------------------------------------
    # 2. 呼び出し側指定の class map
    # ------------------------------------------------------------
    class_tokens = attrs.get("class", "").split()

    for token in class_tokens:
        if token in class_map:
            return class_map[token]

    # ------------------------------------------------------------
    # 3. style map
    # ------------------------------------------------------------
    style = attrs.get("style", "").strip()

    if style and style in style_map:
        return style_map[style]

    # ------------------------------------------------------------
    # 4. 属性値に種別名そのものが含まれる場合
    # ------------------------------------------------------------
    candidates: List[str] = []

    for key, value in attrs.items():
        key_l = key.lower()

        if key in {"class", "style", "_meitetsu_mm_class"}:
            continue

        if key_l.startswith("data-") or key_l in {
            "title",
            "aria-label",
            "alt",
            "id",
            "name",
            "type",
            "kind",
        }:
            candidates.append(value)

    candidates.extend(class_tokens)
    candidates.append(style)

    for value in candidates:
        value = _z2h(value or "").strip()

        for kind in _MEITETSU_KIND_NAMES:
            if kind in value:
                return kind

    return None


class _MeitetsuCell:
    """1つの td/th 内の文字列と a 要素を DOM 順に保持する。"""

    def __init__(
        self,
        tag: str = "",
        attrs: Optional[Dict[str, str]] = None,
    ) -> None:
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.parts: List[Tuple[str, str, Dict[str, str]]] = []
        self._open_link: Optional[Dict[str, str]] = None
        self._link_text: List[str] = []

    def start_link(self, attrs: Dict[str, str]) -> None:
        self._open_link = dict(attrs)
        self._link_text = []

    def add_text(self, text: str) -> None:
        if self._open_link is not None:
            self._link_text.append(text)
        else:
            self.parts.append(("text", text, {}))

    def end_link(self) -> None:
        if self._open_link is None:
            return

        self.parts.append(
            ("a", "".join(self._link_text), self._open_link)
        )

        self._open_link = None
        self._link_text = []


class _MeitetsuDiagramHTMLParser(HTMLParser):
    """TrainDiagram の table/td/a 構造を保持する。

    名鉄の時刻リンクは、

        <div class="mm d_04">
            <a href="...">30</a>
        </div>

    のように、列車種別を親の mm クラスで表現している。

    そのため、a 要素だけでなく親の d_04 / d_18 / d_38
    をリンク属性へ引き継ぐ。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)

        self.rows: List[List[_MeitetsuCell]] = []

        self._row: Optional[List[_MeitetsuCell]] = None
        self._cell: Optional[_MeitetsuCell] = None

        self.page_text: List[str] = []

        # 現在の div の class をスタックで保持する。
        # div の入れ子があっても、現在有効な mm クラスを取得できる。
        self._div_stack: List[str] = []

    def _current_mm_class(self) -> Optional[str]:
        """現在のDOM位置で有効な mm d_xx クラスを返す。"""
        for class_value in reversed(self._div_stack):
            tokens = class_value.split()

            if "mm" not in tokens:
                continue

            for token in tokens:
                if token in _MEITETSU_KIND_BY_MM_CLASS:
                    return token

        return None

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        tag_l = tag.lower()
        attr_dict = {k: (v or "") for k, v in attrs}

        if tag_l == "tr":
            self._row = []


        elif tag_l in {"td", "th"} and self._row is not None:
            self._cell = _MeitetsuCell(
                tag=tag_l,
                attrs=attr_dict,
            )
            self._row.append(self._cell)

        elif tag_l == "div":
            class_value = attr_dict.get("class", "")
            self._div_stack.append(class_value)

        elif tag_l == "a" and self._cell is not None:
            link_attrs = dict(attr_dict)

            # 親の <div class="mm d_xx"> をリンクへ引き継ぐ。
            mm_class = self._current_mm_class()

            if mm_class is not None:
                link_attrs["_meitetsu_mm_class"] = mm_class

            self._cell.start_link(link_attrs)

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()

        if tag_l == "a" and self._cell is not None:
            self._cell.end_link()

        elif tag_l in {"td", "th"}:
            self._cell = None

        elif tag_l == "tr":
            if self._row:
                self.rows.append(self._row)

            self._row = None

        elif tag_l == "div":
            if self._div_stack:
                self._div_stack.pop()

    def handle_data(self, data: str) -> None:
        self.page_text.append(data)

        if self._cell is not None:
            self._cell.add_text(data)


def _meitetsu_extract_destination_map(html: str) -> Dict[str, str]:
    """ページ下部の「行先表示」からコード→正式名称を取得する。"""
    text = _z2h(re.sub(r"<[^>]+>", " ", html))
    result: Dict[str, str] = {}
    in_destination = False

    for raw_line in re.split(r"[\r\n]+", text):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if "行先表示" in line:
            in_destination = True
            continue
        if in_destination and ("免責事項" in line or "ページの先頭" in line):
            break
        if not in_destination:
            continue

        # 同一行に複数の「コード : 名称」がある場合にも対応。
        for code, name in re.findall(
            r"([^\s:：]{1,4})\s*[:：]\s*([^\s]+)", line
        ):
            result[code] = name

    # HTML を改行なしで取得した場合のフォールバック。
    if not result:
        m = re.search(
            r"行先表示(.*?)(?:免責事項|ページの先頭|$)", text, flags=re.S
        )
        if m:
            for code, name in re.findall(
                r"([^\s:：]{1,4})\s*[:：]\s*([^\s]+)", m.group(1)
            ):
                result[code] = name

    return result


def _meitetsu_extract_destination_from_parts(
    parts: List[Tuple[str, str, Dict[str, str]]],
    destination_map: Dict[str, str],
    anchor_index: int,
) -> Optional[str]:
    """アンカーの直後に表示される行先コードを DOM 順から取得する。"""
    for kind, text, _attrs in parts[anchor_index + 1:]:
        if kind == "a":
            break
        normalized = _z2h(text).strip()
        if not normalized:
            continue
        for code in destination_map:
            if re.search(rf"(?<!\S){re.escape(code)}(?!\S)", normalized):
                return destination_map[code]
    return None


def _meitetsu_parse_anchor_url(
    href: str,
    base_url: str,
) -> str:
    return urljoin(base_url, href) if href else ""


def parse_meitetsu_diagram(
    html: str,
    *,
    base_url: str = "",
    kind_class_map: Optional[Dict[str, str]] = None,
    kind_style_map: Optional[Dict[str, str]] = None,
    detail_resolver: Optional[
        Callable[[str], Tuple[Optional[str], Optional[str]]]
    ] = None,
    destination_fallback: str = "",
) -> Dict[str, List[Trip]]:
    """名鉄公式 TrainDiagram HTML を列車単位で Trip 化する。

    重要:
      * HTML を先に List[List[str]] 化しない。
      * 行先は時刻リンク直後のコードを列車単位で取得する。
      * 種別は HTML 属性/class/style から取得し、失敗を「普通」に隠さない。
      * detail_resolver は、メイン HTML から種別を確定できない場合だけ使う。
        同一 URL は内部キャッシュにより一度しか解決しない。

    detail_resolver(url) は (kind, destination) を返す想定。
    """
    if not html or not html.strip():
        raise ValueError("名鉄 TrainDiagram の HTML が空です")

    parser = _MeitetsuDiagramHTMLParser()
    parser.feed(html)
    parser.close()

    destination_map = _meitetsu_extract_destination_map(html)
    if not destination_map:
        raise ValueError("名鉄ページから「行先表示」の対応表を取得できません")

    trips_by_day: Dict[str, List[Trip]] = {
        WEEKDAY: [],
        SATURDAY: [],
        HOLIDAY: [],
    }

    for row in parser.rows:
        if not row:
            continue

        # ------------------------------------------------------------
        # 行頭の <th class="hour"> から「時」を取得
        # ------------------------------------------------------------
        hour: Optional[int] = None

        for cell in row:
            if cell.tag != "th":
                continue

            cell_text = _z2h(
                " ".join(
                    text
                    for _kind, text, _attrs in cell.parts
                )
            ).strip()

            hm = _HOUR_TOKEN.match(cell_text)

            if hm:
                hour = int(hm.group(1))
                break

        if hour is None or not 0 <= hour <= 27:
            continue

        # ------------------------------------------------------------
        # 曜日セルごとに解析
        #
        # 名鉄公式HTML:
        #   td.wkd = 平日
        #   td.snd = 土休日
        # ------------------------------------------------------------
        for cell in row:
            if cell.tag != "td":
                continue

            cell_classes = set(
                cell.attrs.get("class", "").split()
            )

            if "wkd" in cell_classes:
                day_keys = [WEEKDAY]

            elif "snd" in cell_classes:
                day_keys = [SATURDAY, HOLIDAY]

            else:
                continue

            # --------------------------------------------------------
            # セル内の列車を解析
            # --------------------------------------------------------
            for index, (part_kind, text, attrs) in enumerate(cell.parts):
                if part_kind != "a":
                    continue

                minute_match = _MEITETSU_MINUTE_RE.search(
                    _z2h(text)
                )

                if not minute_match:
                    continue

                minute = int(minute_match.group(1))

                if minute > 59:
                    continue

                # ----------------------------------------------------
                # 列車種別
                # ----------------------------------------------------
                kind = _meitetsu_kind_from_attrs(
                    attrs,
                    kind_class_map,
                    kind_style_map,
                )

                # ----------------------------------------------------
                # 行先コード
                # ----------------------------------------------------
                destination = _meitetsu_extract_destination_from_parts(
                    cell.parts,
                    destination_map,
                    index,
                )

                # ----------------------------------------------------
                # 行先コードを取得できない場合は駅デフォルト行先
                #
                # 例:
                # 守山自衛隊前
                #   無印 : 栄町
                #
                # → destination_fallback = "栄町"
                # ----------------------------------------------------
                if destination is None:
                    destination = destination_fallback.strip()

                # ----------------------------------------------------
                # 種別が取れない場合は「普通」にしない
                # ----------------------------------------------------
                if kind is None:
                    raise ValueError(
                        f"列車種別を取得できません: "
                        f"{hour:02d}:{minute:02d}"
                    )

                # ----------------------------------------------------
                # 行先が最終的にも取得できない場合だけエラー
                # ----------------------------------------------------
                if not destination:
                    raise ValueError(
                        f"行先を取得できません: "
                        f"{hour:02d}:{minute:02d}"
                    )

                href = _meitetsu_parse_anchor_url(
                    attrs.get("href", ""),
                    base_url,
                )

                trip = Trip(
                    time=f"{hour:02d}:{minute:02d}",
                    kind=kind,
                    destination=destination,
                )

                # snd は土曜・休日共通ダイヤなので、
                # SATURDAY と HOLIDAY の両方へ登録
                for day_key in day_keys:
                    trips_by_day[day_key].append(trip)

    return trips_by_day

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

    # 名鉄専用 parser:
    # 実際の TrainDiagram と同じ
    # <div class="mm d_04"><a>04</a></div>
    # 構造をテストする。
    meitetsu_html = """
    <table class="diagram-table parallel">
      <tbody>
        <tr class="l2">
          <th class="hour">15</th>

          <td class="wkd">

            <div class="diagram-item">
              <div class="mm d_04">
                <a href="/detail/1500">
                  <span aria-hidden="true">00</span>
                  <span class="speech-only">0分はつ 行き</span>
                </a>
              </div>
              <div class="mark">
                <div class="top">瀬</div>
              </div>
            </div>

            <div class="diagram-item">
              <div class="mm d_18">
                <a href="/detail/1540">
                  <span aria-hidden="true">40</span>
                  <span class="speech-only">40分はつ 行き</span>
                </a>
              </div>
              <div class="mark">
                <div class="top">瀬</div>
              </div>
            </div>

            <div class="diagram-item">
              <div class="mm d_38">
                <a href="/detail/1555">
                  <span aria-hidden="true">55</span>
                  <span class="speech-only">55分はつ 行き</span>
                </a>
              </div>
              <div class="mark">
                <div class="top">瀬</div>
              </div>
            </div>

          </td>
        </tr>
      </tbody>
    </table>

    <div>行先表示</div>
    <div>瀬 : 尾張瀬戸　旭 : 尾張旭　喜 : 喜多山</div>
    """

    mt = parse_meitetsu_diagram(meitetsu_html)

    got = [
        (x.time, x.kind, x.destination)
        for x in mt
    ]

    expected = [
        ("15:00", "普通", "尾張瀬戸"),
        ("15:40", "準急", "尾張瀬戸"),
        ("15:55", "急行", "尾張瀬戸"),
    ]

    if got != expected:
        failures.append(
            f"meitetsu_real_structure:{got}"
        )

    # 行先コードは列車単位で分離する。
    if [x.destination for x in mt] != ["尾張瀬戸", "尾張旭", "尾張旭"]:
        failures.append(f"meitetsu_destination:{[x.destination for x in mt]}")

    # 種別未取得を「普通」に隠さない。
    try:
        parse_meitetsu_diagram(
            meitetsu_html,
            kind_class_map={"kind-futsu": "普通"},
        )
    except ValueError:
        pass
    else:
        failures.append("meitetsu_missing_kind_not_rejected")

    return failures


if __name__ == "__main__":
    f = self_test()
    if f:
        print("FAIL:", f)
        raise SystemExit(1)
    print("解析処理の自己テスト: すべて成功")
