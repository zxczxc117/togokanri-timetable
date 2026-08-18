# -*- coding: utf-8 -*-
"""JR東海：駅コード検索→検索結果→路線/方面PDF→時刻解析。"""
from __future__ import annotations
from typing import Dict,List,Tuple
from urllib.parse import quote,urljoin
import re
from lib.model import WEEKDAY,SATURDAY,HOLIDAY,Trip
from lib.textparse import parse_hour_block_text
from adapters.base import FetchError,empty_diagrams,ensure_nonempty,http_get,fetch_html
BASE='https://railway.jr-central.co.jp'
STATION_API=BASE+'/common/_api/time-schedule/list_station.json'

def _norm(s): return re.sub(r'[\s　駅]+','',str(s or '')).lower()

def resolve_station_code(name: str) -> str:
    r=http_get(STATION_API+'?timetable=1');
    try: data=r.json()
    except Exception as e: raise FetchError(f'JR駅コードJSON解析失敗: {e}')
    rows=data.get('station',[]) if isinstance(data,dict) else []
    exact=[x for x in rows if _norm(x.get('name'))==_norm(name)]
    if not exact: exact=[x for x in rows if _norm(name) in _norm(x.get('name'))]
    if not exact: raise FetchError(f'JR東海の駅コードが見つかりません: {name}')
    code=exact[0].get('code')
    if not code: raise FetchError(f'JR東海の駅コードが空です: {name}')
    return str(code)

def _result_links(html, result_url, line_keyword, direction_key):
    try:
        from bs4 import BeautifulSoup
    except Exception as e: raise FetchError(str(e))
    soup=BeautifulSoup(html,'lxml'); out=[]
    direction_text='上り' if direction_key=='up' else '下り' if direction_key=='down' else ''
    for a in soup.select('ul.result a[href]')+soup.find_all('a',href=True):
        href=urljoin(result_url,a.get('href','')); text=a.get_text(' ',strip=True)
        if not href.lower().endswith('.pdf'): continue
        if line_keyword and line_keyword not in text: continue
        if direction_text and direction_text not in text: continue
        dia=WEEKDAY if '平日' in text else HOLIDAY if ('休日' in text or '土曜' in text) else ''
        if dia: out.append((dia,href,text))
    seen=set(); unique=[]
    for item in out:
        key=(item[0],item[1])
        if key not in seen: seen.add(key); unique.append(item)
    return unique

def _collapse_repeated_token(text: str) -> str:
    import re
    t=text.strip()
    for n in range(2,24):
        unit=str(n)
        if len(t)>=len(unit)*3 and t == unit*(len(t)//len(unit)):
            return unit
    # PDFの同一文字重複（1111122222）の場合
    runs=[]
    for ch in t:
        if not runs or runs[-1]!=ch: runs.append(ch)
    return ''.join(runs)

def _pdf_kind(text: str) -> str:
    t=_collapse_repeated_token(text)
    if '区間快速' in t: return '区間快速'
    if '快速' in t: return '快速'
    if '特急' in t: return '特急'
    if '急行' in t: return '急行'
    if '準急' in t: return '準急'
    if '普通' in t: return '普通'
    if 'ホームライナー' in t: return 'ホームライナー'
    return '普通'

def _pdf_hour(text: str):
    t=text.strip()
    # 11/22時はPDF抽出時に「1111111111」「2222222222」となるため、
    # 1桁候補より先に2桁候補を判定する。
    for h in range(10,24):
        q=str(h)
        if len(t)>=len(q)*3 and t == q*(len(t)//len(q)):
            return h
    for h in range(10):
        q=str(h)
        if len(t)>=len(q)*3 and t == q*(len(t)//len(q)):
            return h
    q=_collapse_repeated_token(t)
    return int(q) if q.isdigit() and 0<=int(q)<=23 else None

def _parse_jr_pdf(raw: bytes, destination: str) -> List[Trip]:
    """JR PDFの座標配置（時刻/行先/種別の3段組）を列単位で読む。"""
    try:
        import io, pdfplumber
    except Exception as e:
        raise FetchError(f'pdfplumber が使えません: {e}')
    out=[]
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            words=page.extract_words(x_tolerance=1,y_tolerance=2,keep_blank_chars=False)
            hour_words=[]
            for w in words:
                if w['x0']>72 or w['top']<175 or w['top']>790: continue
                h=_pdf_hour(w['text'])
                if h is not None: hour_words.append((w,h))
            for hw,hour in hour_words:
                y=hw['top']
                # 時刻欄の横並びの分を取得。隣の「停車駅案内」はx>450なので除外。
                mins=[]
                for w in words:
                    if not (74<=w['x0']<=450 and abs(w['top']-y)<=5): continue
                    tok=_collapse_repeated_token(w['text'])
                    if not tok.isdigit(): continue
                    val=int(tok)
                    if 0<=val<=59:
                        mins.append((w['x0'],val,w))
                for x,minute,mw in mins:
                    kind='普通'
                    # 同じ列の下段に種別が配置される。最も近いxの文字を使う。
                    candidates=[w for w in words if abs(w['x0']-x)<3 and y+8<=w['top']<=y+28]
                    if candidates: kind=_pdf_kind(' '.join(w['text'] for w in candidates))
                    out.append(Trip(time=f'{hour:02d}:{minute:02d}',kind=kind,destination=destination))
    # 重複した座標語を除去
    unique={(x.time,x.kind,x.destination):x for x in out}
    return sorted(unique.values(),key=lambda x:(int(x.time[:2]),int(x.time[3:]),x.kind))

def fetch(station: dict, root: str='')->Dict[str,List[Trip]]:
    name=station.get('name','').strip(); code=resolve_station_code(name)
    schedule=str(station.get('schedule','0'))
    result_url=f'{BASE}/time-schedule/search/result.html?code={quote(code)}&name={quote(name)}&schedule={schedule}'
    html,final=fetch_html(result_url)
    links=_result_links(html,final,station.get('line_keyword',''),str(station.get('direction_key','')))
    if not links:
        raise FetchError(f'JR東海の対象PDFが見つかりません: {name}/{station.get("line_keyword","")}/{station.get("direction_key","")}')
    out=empty_diagrams(); pdf_urls=[]
    for dia,pdf_url,_ in links:
        raw=http_get(pdf_url).content
        trips=_parse_jr_pdf(raw,station.get('destination',''))
        if not trips: raise FetchError(f'JR PDFから時刻を解析できません: {pdf_url}')
        out[dia].extend(trips); pdf_urls.append(pdf_url)
    if out[HOLIDAY] and not out[SATURDAY]: out[SATURDAY]=list(out[HOLIDAY])
    for k in out: out[k]=sorted({(x.time,x.kind,x.destination):x for x in out[k]}.values(),key=lambda t:(int(t.time[:2]),int(t.time[3:]),t.kind))
    ensure_nonempty(out)
    station['_resolved_url']=';'.join(pdf_urls)
    return out
