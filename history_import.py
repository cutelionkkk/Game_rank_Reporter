"""Import a bounded, original local snapshot without overwriting cloud history."""
import json
from database import get_rankings_at, insert_rankings, parse_time, utcnow


def import_history(raw):
    if not raw:
        return 0
    records = json.loads(raw)
    if not isinstance(records,list) or not 1<=len(records)<=10:
        raise ValueError('历史补录格式无效')
    prepared,seen = [],set()
    for record in records:
        if not isinstance(record,dict) or set(record)!={'crawl_time','platform','country','chart_type','items'}:
            raise ValueError('历史补录字段无效')
        if record['platform'] not in ('ios','gp') or record['country']!='us' or record['chart_type']!='free':
            raise ValueError('本次历史补录仅支持美国全部游戏免费榜')
        at = parse_time(record['crawl_time'])
        if at>=parse_time(utcnow()):
            raise ValueError('历史时间不能为未来')
        items = record['items']
        if not isinstance(items,list) or not 1<=len(items)<=200:
            raise ValueError('历史榜单数量无效')
        if any(not isinstance(a,dict) or not isinstance(a.get('app_id'),str) or not a['app_id'] or
               not isinstance(a.get('app_name'),str) or not a['app_name'] for a in items):
            raise ValueError('历史产品信息无效')
        if [a.get('rank') for a in items]!=list(range(1,len(items)+1)) or len({a['app_id'] for a in items})!=len(items):
            raise ValueError('历史名次不连续或重复')
        key=(record['crawl_time'],record['platform'])
        if key in seen:
            raise ValueError('历史快照重复')
        seen.add(key)
        old=get_rankings_at(record['crawl_time'],record['platform'],'free','us')
        if old:
            if [(a['rank'],a['app_id']) for a in old]!=[(a['rank'],a['app_id']) for a in items]:
                raise ValueError('历史快照冲突，拒绝覆盖已有数据')
        else:
            prepared.append(record)
    for record in prepared:
        insert_rankings(record['crawl_time'],record['platform'],'free',record['items'],'us')
    return len(prepared)
