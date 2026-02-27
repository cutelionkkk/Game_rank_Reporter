#!/usr/bin/env python3
"""
Game Rank Reporter — Main entry point

Usage:
  python run.py              # Crawl + analyze + report + notify
  python run.py --crawl      # Crawl only
  python run.py --report     # Generate report from latest data
  python run.py --notify     # Send latest report to configured channels
  python run.py --setup      # Interactive setup wizard
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import run_full_crawl
from report import generate_report
from notify import send_report
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

    # Default: do everything
    if not any([crawl_only, report_only, notify_only]):
        crawl_only = report_only = notify_only = True

    crawl_time = None
    report = None

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
        report = generate_report(crawl_time)

        # Print to stdout
        print("\n" + "=" * 50)
        print(report)
        print("=" * 50)

        # Save to file
        report_path = os.path.join(os.path.dirname(__file__), "latest_report.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n💾 Saved to {report_path}")

    # Step 3: Send notifications
    if notify_only and report:
        print("\n📡 Sending notifications...")
        results = send_report(report)
        if not results:
            print("  ℹ️ No channels configured. Run: python run.py --setup")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
