from pathlib import Path
from adapters.meitetsu import resolve_diagram_url
from adapters.nagoya_subway import parse_timetable_html
from adapters.jrcentral import _result_links

FIX=Path(__file__).parent/'fixtures'

def test_meitetsu_rejects_missing_direction_ids():
    try:
        resolve_diagram_url({'id':'x','direction_key':'down'})
    except Exception:
        return
    raise AssertionError('未設定の名鉄方向を受け入れた')

def test_meitetsu_direction_is_not_replaced():
    u=resolve_diagram_url({'direction_key':'up','start_id':'00003449','link_id':'00000871'})
    assert 'startId=00003449' in u and 'linkId=00000871' in u and 'direction=up' in u

def test_subway_saved_detail_is_split():
    html=(FIX/'subway_detail.html').read_text(encoding='utf-8')
    d=parse_timetable_html(html,{'destination':'金山方面'})
    assert len(d['WEEKDAY'])>10 and len(d['SATURDAY'])>10 and len(d['HOLIDAY'])==len(d['SATURDAY'])
    assert any(x.destination=='名古屋港' for x in d['WEEKDAY'])

def test_jr_saved_result_has_direction_links():
    html=(FIX/'jr_result.html').read_text(encoding='utf-8')
    links=_result_links(html,'https://railway.jr-central.co.jp/time-schedule/search/result.html','中央線','up')
    assert links and any('pdf' in u for _,u,_ in links)
