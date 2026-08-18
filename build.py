# -*- coding: utf-8 -*-
"""
index.json ビルダー（GitHub Actions から日次実行）。

処理:
  1. 解析処理の自己テスト（lib.textparse.self_test）
  2. stations.yaml を読む
  3. 各駅を adapter で取得。失敗したら fallback（manual / yahoo）を試す
  4. 駅ごとに contentHash を計算し、前回 public/index.json と比較
  5. 内容が変わった駅だけ updatedDate を今日に更新（変わらない駅は前回日付を維持）
  6. public/index.json を書き出し、GitHub Actions の Summary に本数表を出す

使い方:
  python build.py            # public/index.json を更新
  python build.py --check    # 生成して差分の有無だけ表示（終了コード0=差分あり/1=なし）
  python build.py --force-manual  # 全駅を manual から作る（ローカル検証・スクレイピング不可環境用）
"""
from __future__ import annotations
import argparse
import datetime
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402
from lib.model import (Line, Station, Trip, DIA_TYPES,  # noqa: E402
                       build_document, dump_json)
from lib.textparse import self_test  # noqa: E402
from adapters.base import FetchError  # noqa: E402
from adapters import manual as manual_adapter  # noqa: E402
from adapters import yahoo as yahoo_adapter  # noqa: E402

CONFIG = os.path.join(ROOT, "stations.yaml")
OUT = os.path.join(ROOT, "public", "index.json")
JST = datetime.timezone(datetime.timedelta(hours=9))

# adapter 名 -> モジュール
ADAPTERS = {
    "meitetsu": "adapters.meitetsu",
    "jrcentral": "adapters.jrcentral",
    "nagoya_subway": "adapters.nagoya_subway",
    "yahoo": "adapters.yahoo",
    "manual": "adapters.manual",
}


def load_prev(path: str):
    """前回JSONから stationId -> (contentHash, updatedDate) を読む。"""
    prev = {}
    if not os.path.exists(path):
        return prev
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for ln in doc.get("lines", []):
            for st in ln.get("stations", []):
                prev[st.get("stationId", "")] = (
                    st.get("contentHash", ""), st.get("updatedDate", ""))
    except Exception:
        pass
    return prev


def call_adapter(name: str, station: dict):
    """adapter を呼ぶ。manual/yahoo は root を渡す。"""
    mod = importlib.import_module(ADAPTERS[name])
    return mod.fetch(station, ROOT)


def fetch_station(station: dict, force_manual: bool):
    """
    1駅分の diagrams を取得する。
    戻り値: (diagrams, used_source, note)
    """
    adapter = station.get("adapter", "manual")
    fallback = station.get("fallback", "manual")

    if force_manual:
        return call_adapter("manual", station), "manual(forced)", ""

    # 1) 本命 adapter
    try:
        dia = call_adapter(adapter, station)
        return dia, adapter, ""
    except FetchError as e:
        primary_err = str(e)
    except Exception as e:  # noqa: BLE001
        primary_err = f"{type(e).__name__}: {e}"

    # 2) fallback
    if fallback and fallback != "none" and fallback != adapter:
        try:
            dia = call_adapter(fallback, station)
            return dia, f"{fallback}(fallback)", f"本命失敗: {primary_err}"
        except Exception as e2:  # noqa: BLE001
            return None, "", f"本命失敗: {primary_err} / fallback失敗: {e2}"

    return None, "", f"取得失敗: {primary_err}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force-manual", action="store_true")
    args = ap.parse_args()

    # 1) 自己テスト
    failures = self_test()
    if failures:
        print("解析処理の自己テスト: 失敗", failures)
        return 2
    print("解析処理の自己テスト: すべて成功")

    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    now = datetime.datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    prev = load_prev(OUT)

    # 路線単位でまとめる（順序維持）
    lines: dict[str, Line] = {}
    summary_rows = []
    changed = 0
    failed = 0

    for s in cfg.get("stations", []):
        if not s.get("enabled", True):
            continue
        sid = s["id"]
        diagrams, used, note = fetch_station(s, args.force_manual)

        st = Station(
            stationId=sid,
            stationName=s.get("name", ""),
            directionName=s.get("direction", ""),
            revision=s.get("revision", ""),
            sourceUrl=s.get("_resolved_url") or s.get("diagram_url") or s.get("url", ""),
            directionKey=s.get("direction_key", ""),
        )
        if diagrams is None:
            # 取得失敗。前回データがあれば維持（配信を止めない）
            failed += 1
            prev_hash, prev_date = prev.get(sid, ("", ""))
            st.source = "kept(previous)" if prev_hash else "failed"
            st.updatedDate = prev_date or today
            st.contentHash = prev_hash
            # 前回の時刻内容は index.json から復元
            _restore_prev_trips(st, OUT)
            summary_rows.append((s, st, note or "取得失敗"))
        else:
            st.diagrams = {d: diagrams.get(d, []) for d in DIA_TYPES}
            st.kinds = st.collect_kinds()
            st.source = used
            new_hash = st.compute_hash()
            st.contentHash = new_hash
            prev_hash, prev_date = prev.get(sid, ("", ""))
            if new_hash == prev_hash and prev_date:
                st.updatedDate = prev_date          # 変化なし → 日付据え置き
            else:
                st.updatedDate = today              # 変化あり → 今日
                if prev_hash != new_hash:
                    changed += 1
            summary_rows.append((s, st, note))

        ln = lines.get(s["line"])
        if ln is None:
            ln = Line(lineName=s["line"], operator=s.get("operator", ""))
            lines[s["line"]] = ln
        ln.stations.append(st)

    updated_date = today if changed else (
        max((d for _, _, _ in [] ), default=today))  # placeholder
    # ドキュメント全体の updatedDate は「変化があれば今日」、無ければ前回の最大
    doc_updated = today if changed else _max_prev_date(prev, today)

    doc = build_document(list(lines.values()), generated_at, doc_updated)

    if args.check:
        # 差分の有無だけ判定
        print(f"変更駅数: {changed} / 取得失敗: {failed}")
        return 0 if changed else 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    dump_json(doc, OUT)
    print(f"public/index.json を書き出し。変更駅数={changed} 取得失敗={failed}")

    _write_summary(summary_rows, changed, failed)
    return 0


def _restore_prev_trips(st: Station, out_path: str) -> None:
    if not os.path.exists(out_path):
        return
    try:
        with open(out_path, encoding="utf-8") as f:
            doc = json.load(f)
        for ln in doc.get("lines", []):
            for s in ln.get("stations", []):
                if s.get("stationId") == st.stationId:
                    for d in DIA_TYPES:
                        st.diagrams[d] = [
                            Trip(time=t.get("time", ""),
                                 kind=t.get("kind", "普通"),
                                 destination=t.get("destination", ""))
                            for t in s.get("diagrams", {}).get(d, [])
                        ]
                    st.kinds = st.collect_kinds()
                    return
    except Exception:
        pass


def _max_prev_date(prev: dict, today: str) -> str:
    dates = [d for _, d in prev.values() if d]
    return max(dates) if dates else today


def _write_summary(rows, changed, failed) -> None:
    """GitHub Actions の Step Summary に本数表を出す。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = []
    lines.append("## 時刻表ビルド結果\n")
    lines.append(f"- 変更のあった駅: **{changed}**")
    lines.append(f"- 取得失敗（前回データ維持）: **{failed}**\n")
    lines.append("| 駅 | 路線 | 方面 | 取得元 | 平日 | 土曜 | 休日 | 更新日 |")
    lines.append("|---|---|---|---|--:|--:|--:|---|")
    for s, st, note in rows:
        wc = len(st.diagrams.get("WEEKDAY", []))
        sc = len(st.diagrams.get("SATURDAY", []))
        hc = len(st.diagrams.get("HOLIDAY", []))
        lines.append(f"| {st.stationName} | {s['line']} | {st.directionName} | "
                     f"{st.source} | {wc} | {sc} | {hc} | {st.updatedDate} |")
        if note:
            lines.append(f"| ↳ | | | ⚠ {note} | | | | |")
    text = "\n".join(lines) + "\n"
    print(text)
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
