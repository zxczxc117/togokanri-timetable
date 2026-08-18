# -*- coding: utf-8 -*-
"""名古屋市交通局：駅名→路線別→方面詳細ページを辿って取得する。"""
from __future__ import annotations
from typing import Dict,List
from urllib.parse import quote,urljoin,urlparse,parse_qs
import re
from lib.model import WEEKDAY,SATURDAY,HOLIDAY,Trip
from adapters.base import FetchError,empty_diagrams,ensure_nonempty,fetch_html
from adapters.scrape_common import extract_table_records
BASE='https://www.kotsu.city.nagoya.jp/rp/subway/'

def resolve_detail_url(station: dict, html: str='') -> str:
    name=station.get('name','').strip(); key=str(station.get('direction_key','')).strip()
    if not name: raise FetchError('地下鉄駅名が空です')
    list_url=BASE+'timetable_list.html?name='+quote(name)
    if not html:
        html,_=fetch_html(list_url)
    try:
        from bs4 import BeautifulSoup
    except Exception as e: raise FetchError(str(e))
    soup=BeautifulSoup(html,'lxml')
    links=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(list_url,a['href'])
        if 'timetable_dtl.html' not in href: continue
        text=a.get_text(' ',strip=True)
        if station.get('direction_keyword') and station['direction_keyword'] not in text and station['direction_keyword'] not in href:
            continue
        links.append((href,text))
    if key in {'0','1'}:
        links=[x for x in links if parse_qs(urlparse(x[0]).query).get('direction',[''])[0]==key] or links
    if not links: raise FetchError(f"地下鉄 {name} の方面リンクが見つかりません（{station.get('direction_keyword','')}）")
    url=links[0][0]
    q=parse_qs(urlparse(url).query)
    if 'code' not in q or 'direction' not in q: raise FetchError('地下鉄詳細URLのcode/directionがありません')
    return url

def _parse_cell(cell, default_dest, dest_map):
    out=[]
    pending=default_dest
    for token in re.split(r'[\s\u3000,]+',cell or ''):
        if not token: continue
        m=re.match(r'^(\d{1,2})(.*)$',token)
        if not m:
            if token in dest_map: pending=dest_map[token]
            continue
        minute=int(m.group(1)); suffix=m.group(2).strip()
        if minute>59: continue
        dest=dest_map.get(suffix,pending)
        out.append((minute,dest))
        pending=default_dest
    return out

def _parse_rows(rows, destination, dest_map):
    result=[]
    for row in rows:
        if not row: continue
        m=re.match(r'^\s*(\d{1,2})\s*$',row[0])
        if not m: continue
        hour=int(m.group(1))
        for cell in row[1:]:
            for minute,dest in _parse_cell(cell,destination,dest_map):
                result.append(Trip(time=f'{hour:02d}:{minute:02d}',kind='普通',destination=dest))
    return result

def parse_timetable_html(html: str, station: dict) -> Dict[str,List[Trip]]:
    records=extract_table_records(html)
    tables=[rows for rows,ctx in records if rows and any(r and r[0].strip()=='時' for r in rows[:2])]
    if not tables: raise FetchError('地下鉄詳細ページに時刻表表がありません')
    dest=station.get('destination','') or ''
    dest_map={'港':'名古屋港','名':'名古屋','栄':'栄','金':'金山','新':'新瑞橋','藤':'藤が丘','高':'高畑'}
    out=empty_diagrams(); combined=None
    for rows in tables:
        header=rows[0]
        if len(header)>=3 and any('平日' in c for c in header) and any('土曜' in c or '休日' in c for c in header):
            wi=next((i for i,c in enumerate(header) if '平日' in c),1)
            hi=next((i for i,c in enumerate(header) if '土曜' in c or '休日' in c),2)
            combined=(
                [[r[0],r[wi]] for r in rows[1:] if len(r)>wi],
                [[r[0],r[hi]] for r in rows[1:] if len(r)>hi],
            )
            break
    if combined:
        out[WEEKDAY]=_parse_rows(combined[0],dest,dest_map)
        out[SATURDAY]=_parse_rows(combined[1],dest,dest_map)
        out[HOLIDAY]=list(out[SATURDAY])
    else:
        for rows in tables:
            h=' '.join(rows[0])
            if '平日' in h: out[WEEKDAY]=_parse_rows(rows[1:],dest,dest_map)
            elif '土曜' in h or '休日' in h: out[SATURDAY]=_parse_rows(rows[1:],dest,dest_map); out[HOLIDAY]=list(out[SATURDAY])
    for k in out: out[k]=sorted(out[k],key=lambda t:(int(t.time[:2]),int(t.time[3:])))
    ensure_nonempty(out)
    return out

def fetch(station: dict, root: str='')->Dict[str,List[Trip]]:
    list_url=BASE+'timetable_list.html?name='+quote(station.get('name','').strip())
    detail=resolve_detail_url(station)
    html,final=fetch_html(detail)
    station['_resolved_url']=final
    return parse_timetable_html(html,station)
