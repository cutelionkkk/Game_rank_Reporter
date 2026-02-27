"""Export structured analysis data for AI agents"""

import json
import os
from datetime import datetime, timezone

from analyzer import generate_full_analysis
from database import (
    get_rankings_at, get_latest_crawl_time, get_previous_crawl_time,
    get_db, init_db
)
from config import load_settings

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_PATH = os.path.join(SCRIPT_DIR, "analysis_data.json")


def export_analysis_data(crawl_time=None):
    """Export full analysis data as structured JSON for AI consumption"""
    init_db()
    settings = load_settings()

    if not crawl_time:
        crawl_time = get_latest_crawl_time()
    if not crawl_time:
        return None

    analysis = generate_full_analysis(crawl_time)
    if not analysis:
        return None

    # Build the export structure
    export = {
        "metadata": {
            "crawl_time": crawl_time,
            "previous_crawl_time": None,
            "country": settings.get("country", "us"),
            "top_n": settings.get("top_n", 100),
            "export_time": datetime.now(timezone.utc).isoformat(),
        },
        "charts": {},
        "category_trends": analysis.get("category_trends", {}),
        "consecutive_risers": analysis.get("consecutive_risers", {}),
    }

    for platform in ['ios', 'gp']:
        for chart_type in ['free', 'paid', 'grossing']:
            key = f"{platform}_{chart_type}"

            # Get current rankings
            current = get_rankings_at(crawl_time, platform, chart_type)
            prev_time = get_previous_crawl_time(crawl_time, platform)

            if prev_time and not export["metadata"]["previous_crawl_time"]:
                export["metadata"]["previous_crawl_time"] = prev_time

            # Clean up data for export
            current_clean = []
            for app in current:
                entry = {
                    "rank": app["rank"],
                    "app_id": app["app_id"],
                    "app_name": app["app_name"],
                    "developer": app.get("developer") or "",
                    "category": app.get("category") or "",
                    "rating": app.get("rating"),
                    "rating_count": app.get("rating_count"),
                    "price": app.get("price"),
                }
                # Parse extra_json
                try:
                    extra = json.loads(app.get("extra_json", "{}") or "{}")
                    entry["extra"] = extra
                except:
                    entry["extra"] = {}
                current_clean.append(entry)

            # Get changes from analysis
            chart_data = analysis["charts"].get(key, {})
            changes = chart_data.get("changes", {})

            # Simplify changes for export
            changes_clean = {}
            for change_type in ['surges', 'new_entries', 'drops', 'exits',
                                'top_movers_up', 'top_movers_down']:
                items = changes.get(change_type, [])
                changes_clean[change_type] = [
                    {
                        "rank": item.get("rank"),
                        "app_id": item.get("app_id"),
                        "app_name": item.get("app_name"),
                        "category": item.get("category", ""),
                        "prev_rank": item.get("prev_rank"),
                        "rank_change": item.get("rank_change"),
                        "is_new_game": item.get("is_new_game", False),
                    }
                    for item in items
                ]

            export["charts"][key] = {
                "current": current_clean,
                "changes": changes_clean,
                "previous_crawl_time": prev_time,
            }

    # Save to file
    with open(EXPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    return export


if __name__ == "__main__":
    data = export_analysis_data()
    if data:
        charts_summary = []
        for key, chart in data["charts"].items():
            n = len(chart["current"])
            changes = chart["changes"]
            surges = len(changes.get("surges", []))
            new = len(changes.get("new_entries", []))
            charts_summary.append(f"  {key}: {n} apps, {surges} surges, {new} new")

        print(f"✅ Exported to {EXPORT_PATH}")
        print(f"  Crawl time: {data['metadata']['crawl_time']}")
        print(f"  Charts:")
        for s in charts_summary:
            print(s)
    else:
        print("❌ No data to export. Run crawler first.")
