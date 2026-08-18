# -*- coding: utf-8 -*-
"""時刻表取得アダプタ共通処理。"""
from __future__ import annotations
from typing import Dict, List, Callable, Optional, Tuple
from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip

class FetchError(RuntimeError):
    """公式ページから対象の時刻表を特定できない場合の例外。"""

def empty_diagrams() -> Dict[str, List[Trip]]:
    return {WEEKDAY: [], SATURDAY: [], HOLIDAY: []}

def ensure_nonempty(diagrams: Dict[str, List[Trip]], min_total: int = 10) -> None:
    total = sum(len(v) for v in diagrams.values())
    if total < min_total:
        raise FetchError(f"本数が少なすぎます（{total}本）。取得失敗とみなします。")

def _response_text(response) -> str:
    enc = getattr(response, 'encoding', None)
    if not enc or str(enc).lower() in {'iso-8859-1', 'ascii'}:
        head = response.content[:512]
        enc = 'cp932' if b'charset=Shift_JIS' in head or b'charset=shift_jis' in head else 'utf-8'
    try:
        return response.content.decode(enc, errors='replace')
    except Exception:
        return response.text

def http_get(url: str, timeout: int = 30, session=None):
    try:
        import requests
    except Exception as e:
        raise FetchError(f"requests が使えません: {e}")
    client = session or requests.Session()
    try:
        r = client.get(url, timeout=timeout, headers={
            'User-Agent': 'TogoKanri timetable updater/1.13.0',
            'Accept-Language': 'ja,en;q=0.8',
        })
    except Exception as e:
        raise FetchError(f"HTTP取得失敗: {url}: {e}")
    if r.status_code >= 400:
        raise FetchError(f"HTTP {r.status_code}: {url}")
    return r

def fetch_html(url: str, timeout: int = 30, session=None) -> Tuple[str, str]:
    r = http_get(url, timeout=timeout, session=session)
    return _response_text(r), r.url

def render_page(url: str, wait_selector: str = '', timeout_ms: int = 30000,
                setup: Optional[Callable] = None) -> Tuple[str, str]:
    """PlaywrightでJS遷移が必要なページを操作して最終HTMLを返す。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise FetchError(f"Playwright が使えません: {e}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--no-sandbox'])
            page = browser.new_page(locale='ja-JP')
            page.goto(url, timeout=timeout_ms, wait_until='domcontentloaded')
            if setup:
                setup(page)
            try:
                page.wait_for_load_state('networkidle', timeout=timeout_ms)
            except Exception:
                pass
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            html, final_url = page.content(), page.url
            browser.close()
            return html, final_url
    except FetchError:
        raise
    except Exception as e:
        raise FetchError(f"ページ遷移/描画失敗: {url}: {e}")

def render_html(url: str, wait_selector: str = '', timeout_ms: int = 30000) -> str:
    return render_page(url, wait_selector, timeout_ms)[0]
