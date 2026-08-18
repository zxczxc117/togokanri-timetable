# -*- coding: utf-8 -*-
"""
index.json のスキーマ定義とデータ構造。

Android 側の StationEntry / Departure にそのまま対応する。
  time         "HH:MM"（24時超は "25:03" のように表記可）
  kind         種別（普通/準急/急行/快速/特急 など）
  destination  行先
  dia          WEEKDAY / SATURDAY / HOLIDAY

このファイルは外部ライブラリに依存しない（標準ライブラリのみ）。
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List

SCHEMA_VERSION = 2

# ダイヤ種別（Android 側 DiaType と一致させること）
WEEKDAY = "WEEKDAY"
SATURDAY = "SATURDAY"
HOLIDAY = "HOLIDAY"
DIA_TYPES = (WEEKDAY, SATURDAY, HOLIDAY)


@dataclass
class Trip:
    time: str            # "HH:MM"
    kind: str = "普通"
    destination: str = ""

    def normalized_key(self) -> str:
        return f"{self.time}|{self.kind}|{self.destination}"


@dataclass
class Station:
    stationId: str
    stationName: str
    directionName: str = ""
    revision: str = ""
    kinds: List[str] = field(default_factory=list)
    diagrams: Dict[str, List[Trip]] = field(default_factory=dict)
    updatedDate: str = ""
    contentHash: str = ""
    source: str = ""          # 実際に採用した取得方法（adapter/yahoo/manual）
    sourceUrl: str = ""       # 駅・方面固有の実取得URL
    directionKey: str = ""    # 名鉄のup/down等、取得対象を識別するキー

    def compute_hash(self) -> str:
        """時刻内容だけからハッシュを作る。更新判定に使う。"""
        h = hashlib.sha1()
        for dia in DIA_TYPES:
            trips = self.diagrams.get(dia, [])
            h.update(dia.encode("utf-8"))
            for t in sorted(trips, key=lambda x: x.normalized_key()):
                h.update(t.normalized_key().encode("utf-8"))
        return h.hexdigest()[:16]

    def total_trips(self) -> int:
        return sum(len(self.diagrams.get(d, [])) for d in DIA_TYPES)

    def collect_kinds(self) -> List[str]:
        seen: List[str] = []
        for dia in DIA_TYPES:
            for t in self.diagrams.get(dia, []):
                if t.kind and t.kind not in seen:
                    seen.append(t.kind)
        return seen

    def to_json(self) -> dict:
        return {
            "stationId": self.stationId,
            "stationName": self.stationName,
            "directionName": self.directionName,
            "revision": self.revision,
            "updatedDate": self.updatedDate,
            "contentHash": self.contentHash,
            "source": self.source,
            "sourceUrl": self.sourceUrl,
            "directionKey": self.directionKey,
            "kinds": self.kinds or self.collect_kinds(),
            "diagrams": {
                dia: [
                    {"time": t.time, "kind": t.kind, "destination": t.destination}
                    for t in sorted(self.diagrams.get(dia, []),
                                    key=lambda x: _time_sort_key(x.time))
                ]
                for dia in DIA_TYPES
            },
        }


@dataclass
class Line:
    lineName: str
    operator: str = ""
    stations: List[Station] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "lineName": self.lineName,
            "operator": self.operator,
            "stations": [s.to_json() for s in self.stations],
        }


def _time_sort_key(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def build_document(lines: List[Line], generated_at: str, updated_date: str) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "updatedDate": updated_date,
        "publisher": "togokanri-timetable",
        "lines": [ln.to_json() for ln in lines],
    }


def dump_json(doc: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
