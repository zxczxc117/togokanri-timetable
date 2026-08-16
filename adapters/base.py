# -*- coding: utf-8 -*-
"""
アダプタ共通処理。

各アダプタは fetch(station: dict) -> Dict[str, List[Trip]] を実装する。
戻り値は {"WEEKDAY":[Trip...], "SATURDAY":[...], "HOLIDAY":[...]} の形。
取得に失敗した場合は例外を送出する（build 側が fallback を試みる）。

Playwright はローカル/Actions にしか無い場合があるため、
スクレイピング系アダプタは import を関数内で行い、
未導入環境では明確な例外を出してフォールバックへ回す。
"""
from __future__ import annotations
from typing import Dict, List

from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip


class FetchError(RuntimeError):
    """取得失敗。build 側はこれを捕まえて fallback へ回す。"""


def empty_diagrams() -> Dict[str, List[Trip]]:
    return {WEEKDAY: [], SATURDAY: [], HOLIDAY: []}


def ensure_nonempty(diagrams: Dict[str, List[Trip]], min_total: int = 10) -> None:
    """取得結果が薄すぎる（表の一部しか読めていない）場合は失敗扱い。"""
    total = sum(len(v) for v in diagrams.values())
    if total < min_total:
        raise FetchError(f"本数が少なすぎます（{total}本）。取得失敗とみなします。")


def render_html(url: str, wait_selector: str = "", timeout_ms: int = 30000) -> str:
    """Playwright で JS 描画後の HTML を取得する。未導入なら FetchError。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"Playwright が使えません: {e}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=timeout_ms)
                except Exception:  # noqa: BLE001
                    pass
            html = page.content()
            browser.close()
            return html
    except FetchError:
        raise
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"ページ描画に失敗: {e}")
