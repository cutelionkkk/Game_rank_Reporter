#!/usr/bin/env python3
"""Game Rank Reporter: local dashboard and scheduled monitoring."""
import argparse
import os
import re
from html import unescape


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true', help='打开本地配置与结果网页')
    parser.add_argument('--port', type=int, default=8765, help='本地网页端口（默认 8765）')
    parser.add_argument('--open-browser', action='store_true', help='启动网页服务后打开浏览器')
    parser.add_argument('--setup', action='store_true', help='旧版通知/榜单配置向导')
    parser.add_argument('--crawl', action='store_true', help='仅采集已启用的榜单和公司')
    parser.add_argument('--report', action='store_true', help='生成最近一轮报告')
    parser.add_argument('--notify', action='store_true', help='向已配置渠道发送报告')
    parser.add_argument('--export-analysis', action='store_true', help='导出结构化结果')
    parser.add_argument('--dry-run', action='store_true', help='采集、报告和导出；不发送通知')
    args = parser.parse_args()
    if args.serve:
        from dashboard import serve
        serve(args.port, args.open_browser)
        return 0
    if args.setup:
        from setup_wizard import interactive_setup
        interactive_setup()
        return 0
    from database import init_db
    init_db()
    default = not any((args.crawl,args.report,args.notify,args.export_analysis))
    crawl = args.crawl or default or args.dry_run
    report = args.report or args.notify or default or args.dry_run
    export = args.export_analysis or default or args.dry_run
    notify = (args.notify or default) and not args.dry_run
    crawl_time, result = None, None
    if crawl:
        from monitoring import run_monitoring
        result = run_monitoring()
        crawl_time = result['crawl_time']
    parts = []
    if report:
        from report import generate_report_parts
        parts = generate_report_parts(crawl_time)
        content = ('\n\n' + '─'*40 + '\n\n').join(parts)
        clean = unescape(re.sub(r'<[^>]+>', '', content))
        print(clean)
        with open(os.path.join(os.path.dirname(__file__), 'latest_report.txt'), 'w', encoding='utf-8') as f:
            f.write(clean)
    if export:
        from export import export_analysis_data, EXPORT_PATH
        data = export_analysis_data(crawl_time)
        if data:
            print(f"已导出 {len(data['charts'])} 个版块、{len(data['companies'])} 个公司账号：{EXPORT_PATH}")
    if notify and parts:
        from notify import send_report_parts
        send_report_parts(parts)
    return 1 if result and result['errors'] else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'错误：{exc}')
        raise SystemExit(1)
