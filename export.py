"""Export every selected scope and publisher event, using the same analysis as the UI."""
import json
import os
from analyzer import generate_full_analysis
from config import SCRIPT_DIR, load_settings
from database import utcnow

EXPORT_PATH = os.path.join(SCRIPT_DIR, 'analysis_data.json')


def build_export(crawl_time=None):
    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return None
    settings = load_settings()
    export = dict(analysis)
    export['metadata'] = dict(schema_version=2, crawl_time=analysis['crawl_time'], export_time=utcnow(),
                              top_n=settings['top_n'], rank_surge_threshold=settings['rank_surge_threshold'],
                              comparison_hours=settings['comparison_hours'])
    for chart in export['charts'].values():
        chart['previous_crawl_time'] = chart['previous_time']
        for app in chart['current']:
            try:
                app['extra'] = json.loads(app.get('extra_json') or '{}')
            except ValueError:
                app['extra'] = {}
    return export


def export_analysis_data(crawl_time=None):
    export = build_export(crawl_time)
    if export is not None:
        with open(EXPORT_PATH, 'w', encoding='utf-8') as f:
            json.dump(export,f,ensure_ascii=False,indent=2)
    return export


if __name__ == '__main__':
    data = export_analysis_data()
    print(EXPORT_PATH if data else '暂无数据')
