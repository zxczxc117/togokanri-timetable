# -*- coding: utf-8 -*-
"""HTML表を共通モデルへ変換する処理。"""
from __future__ import annotations
import re
from typing import Dict, List, Tuple
from lib.model import WEEKDAY, SATURDAY, HOLIDAY, Trip
from lib.textparse import parse_table_rows
from adapters.base import FetchError, empty_diagrams, ensure_nonempty, render_html

_DAY_WORDS = (
    (HOLIDAY, ('土・休日','土休日','土曜・日曜・休日','休日','日曜','祝日')),
    (SATURDAY, ('土曜','土曜日')),
    (WEEKDAY, ('平日','月〜金','月-金','Weekdays')),
)

def _kind_from_element(el) -> str:
    raw=' '.join([el.get_text(' ',strip=True),' '.join(el.get('class',[])),
                  str(el.get('aria-label','')),str(el.get('title',''))])
    for kind in ('ミュースカイ','快速特急','快速急行','特急','急行','準急','区間急行','新快速','快速','普通'):
        if kind in raw: return kind
    low=raw.lower()
    for key,kind in (('limited','特急'),('express','急行'),('rapid','快速'),('semi','準急'),('local','普通')):
        if key in low: return kind
    return ''

def _cell_text(cell) -> str:
    text=cell.get_text(' ',strip=True)
    marks=[]
    for child in cell.find_all(['small','sub','sup']):
        v=child.get_text(' ',strip=True)
        if v: marks.append('[行先:%s]' % v)
    for child in [cell]+list(cell.find_all(True)):
        k=_kind_from_element(child)
        if k:
            marks.append('[種別:%s]'%k); break
        d=child.get('data-destination') or child.get('data-dest')
        if d: marks.append('[行先:%s]'%d)
    return (text+' '+' '.join(dict.fromkeys(marks))).strip()

def extract_table_records(html: str) -> List[Tuple[List[List[str]], str]]:
    try:
        from bs4 import BeautifulSoup
    except Exception as e: raise FetchError(f'BeautifulSoup が使えません: {e}')
    soup=BeautifulSoup(html,'lxml'); out=[]
    for tbl in soup.find_all('table'):
        rows=[]
        for tr in tbl.find_all('tr'):
            cells=[]
            for c in tr.find_all(['th','td'],recursive=False):
                v=_cell_text(c)
                if v: cells.append(v)
            if cells: rows.append(cells)
        if rows:
            attrs=' '.join([str(tbl.get('id','')),' '.join(tbl.get('class',[])),
                            ' '.join(str(v) for v in tbl.attrs.values())])
            out.append((rows,attrs+' '+tbl.get_text(' ',strip=True)))
    return out

def extract_tables(html: str) -> List[List[List[str]]]:
    return [x[0] for x in extract_table_records(html)]

def looks_like_timetable(rows) -> bool:
    return sum(bool(r and re.match(r'^\s*\d{1,2}\s*(?:時|:|：)?\s*$',r[0])) for r in rows)>=4

def parse_dia_from_context(text: str) -> str:
    t=text.replace(' ','')
    for dia,words in _DAY_WORDS:
        if any(w in t for w in words): return dia
    return ''

def split_side_by_side(rows):
    header=-1; wk=hol=-1
    for i,row in enumerate(rows[:5]):
        for j,c in enumerate(row):
            c=c.replace(' ','')
            if '平日' in c: wk=j; header=i
            if any(x in c for x in ('土・休日','土休日','土曜・日曜・休日')): hol=j; header=i
    if wk<0 or hol<0 or wk==hol: return None
    def take(col):
        result=[]
        for row in rows[header+1:]:
            if row and re.match(r'^\s*\d{1,2}',row[0]) and len(row)>col:
                result.append([row[0],row[col]])
        return result
    return take(wk),take(hol)

def scrape_station_tables(station: dict, wait_selector: str='table', context_keyword: str='') -> Dict[str,List[Trip]]:
    html=render_html(station['url'],wait_selector=wait_selector)
    records=[x for x in extract_table_records(html) if looks_like_timetable(x[0])]
    if context_keyword:
        kw=context_keyword.replace('方面','').strip()
        matched=[x for x in records if kw and kw in x[1]]
        if matched: records=matched
    if not records: raise FetchError('時刻表らしい表が見つかりません')
    out=empty_diagrams(); dest=station.get('destination','') or ''
    for rows,ctx in records:
        sides=split_side_by_side(rows)
        if sides:
            out[WEEKDAY]+=parse_table_rows(sides[0],destination=dest)
            out[SATURDAY]+=parse_table_rows(sides[1],destination=dest)
            out[HOLIDAY]+=parse_table_rows(sides[1],destination=dest)
            continue
        dia=parse_dia_from_context(ctx)
        if dia: out[dia]+=parse_table_rows(rows,destination=dest)
    if sum(map(len,out.values()))==0 and len(records)==1:
        out[WEEKDAY]=parse_table_rows(records[0][0],destination=dest)
    for k in out:
        unique={(t.time,t.kind,t.destination):t for t in out[k]}
        out[k]=sorted(unique.values(),key=lambda t:(int(t.time.split(':')[0]),int(t.time.split(':')[1]),t.kind,t.destination))
    ensure_nonempty(out)
    return out
