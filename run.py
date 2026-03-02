#!/usr/bin/env python3
"""
Game Rank Reporter — Main entry point

Usage:
  python run.py                   # Crawl + analyze + report + notify
  python run.py --crawl           # Crawl only
  python run.py --report          # Generate report from latest data
  python run.py --notify          # Send latest report to configured channels
  python run.py --export-analysis # Export structured data for AI analysis
  python run.py --setup           # Interactive setup wizard
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import run_full_crawl
from report import generate_report, generate_report_parts
from notify import send_report, send_report_parts
from export import export_analysis_data, EXPORT_PATH
from database import init_db


def main():
    args = set(sys.argv[1:])
    init_db()

    if '--setup' in args:
        from setup_wizard import interactive_setup
        interactive_setup()
        return

    if '--help' in args or '-h' in args:
        print(__doc__)
        return

    crawl_only = '--crawl' in args
    report_only = '--report' in args
    notify_only = '--notify' in args
    export_only = '--export-analysis' in args

    # Default: do everything
    if not any([crawl_only, report_only, notify_only, export_only]):
        crawl_only = report_only = notify_only = export_only = True

    crawl_time = None
    report = None
    parts = []

    # Step 1: Crawl
    if crawl_only:
        print("🎮 Game Rank Reporter — Starting crawl")
        print()
        crawl_time, total, errors = run_full_crawl()
        if total == 0:
            print("\n❌ No data collected.")
            if not report_only and not notify_only:
                sys.exit(1)

    # Step 2: Generate report
    if report_only or notify_only:
        print("\n📝 Generating report...")
        parts = generate_report_parts(crawl_time)
        report = '\n\n' + '─' * 40 + '\n\n'.join(parts)

        # Print to stdout (stripped of HTML tags for readability)
        import re
        clean = re.sub(r'<[^>]+>', '', report)
        print("\n" + "=" * 50)
        print(clean[:3000] + ('\n...(truncated)' if len(clean) > 3000 else ''))
        print("=" * 50)

        # Save full report to file
        report_path = os.path.join(os.path.dirname(__file__), "latest_report.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(clean)
        print(f"\n💾 Saved to {report_path} ({len(parts)} sections)")

    # Step 3: Export analysis data for AI
    if export_only:
        print("\n📦 Exporting analysis data for AI...")
        data = export_analysis_data(crawl_time)
        if data:
            total_apps = sum(len(c.get('current', [])) for c in data['charts'].values())
            print(f"  ✅ Exported {total_apps} app entries across 6 charts")
            print(f"  📁 {EXPORT_PATH}")
        else:
            print("  ❌ No data to export")

    # Step 4: Send notifications (one message per chart)
    if notify_only and parts:
        print("\n📡 Sending notifications...")
        results = send_report_parts(parts)
        if not results:
            print("  ℹ️ No channels configured. Run: python run.py --setup")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
