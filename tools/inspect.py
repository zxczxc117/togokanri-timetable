# -*- coding: utf-8 -*-
"""
取得できなくなったときの調査ツール。
指定URLを Playwright で描画し、ページ内の表を一覧表示する。

  python -m playwright install chromium   # 初回のみ
  python tools/inspect.py "https://..." --tables
  python tools/inspect.py "https://..." --text   # 本文テキストを表示
"""
from __future__ import annotations
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from adapters.base import render_html, FetchError  # noqa: E402
from adapters.scrape_common import extract_tables, looks_like_timetable  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--tables", action="store_true", help="表を一覧表示")
    ap.add_argument("--text", action="store_true", help="本文テキストを表示")
    ap.add_argument("--selector", default="table", help="待機するセレクタ")
    args = ap.parse_args()

    try:
        html = render_html(args.url, wait_selector=args.selector)
    except FetchError as e:
        print("描画失敗:", e)
        return 1

    if args.text:
        try:
            from bs4 import BeautifulSoup
            print(BeautifulSoup(html, "lxml").get_text("\n", strip=True)[:4000])
        except Exception as e:  # noqa: BLE001
            print("テキスト抽出失敗:", e)
        return 0

    tables = extract_tables(html)
    print(f"検出した表: {len(tables)} 個")
    for i, rows in enumerate(tables):
        mark = "★時刻表らしい" if looks_like_timetable(rows) else ""
        print(f"\n--- 表{i} 行数{len(rows)} {mark} ---")
        for r in rows[:6]:
            print("  ", " | ".join(r[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
