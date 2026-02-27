#!/usr/bin/env python3
"""Main entry point: crawl + analyze + report"""

import sys
import os

# Ensure we can import from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import run_full_crawl
from report import generate_report
from database import init_db


def main():
    init_db()

    print("🎮 Game Tracker — Starting full run")
    print()

    # Step 1: Crawl
    crawl_time, total, errors = run_full_crawl()

    if total == 0:
        print("\n❌ No data collected. Cannot generate report.")
        sys.exit(1)

    # Step 2: Generate report
    print("\n📝 Generating report...")
    report = generate_report(crawl_time)

    print("\n" + "=" * 50)
    print("REPORT OUTPUT:")
    print("=" * 50)
    print(report)

    # Step 3: Save report to file
    report_path = os.path.join(os.path.dirname(__file__), "latest_report.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n💾 Report saved to {report_path}")

    if errors:
        print(f"\n⚠️ {len(errors)} errors during crawl")
        sys.exit(2)  # partial success


if __name__ == "__main__":
    main()
