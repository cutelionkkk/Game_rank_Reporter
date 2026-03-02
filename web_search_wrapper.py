"""
Thin wrapper to call OpenClaw's web_search MCP tool from within the project.
Falls back gracefully if the tool is unavailable (e.g., no Brave API key).
"""

import subprocess
import json
import os


def web_search(query: str, count: int = 3) -> list[dict]:
    """
    Search the web using the available search backend.
    Returns a list of result dicts: [{title, url, snippet}, ...]
    Falls back to empty list if search is unavailable.
    """
    # Try using the OpenClaw MCP bridge if available
    try:
        result = _search_via_requests(query, count)
        if result:
            return result
    except Exception:
        pass

    return []


def _search_via_requests(query: str, count: int) -> list[dict]:
    """Try Brave Search API if BRAVE_API_KEY is set in environment"""
    api_key = os.environ.get('BRAVE_API_KEY', '')
    if not api_key:
        return []

    import requests
    resp = requests.get(
        'https://api.search.brave.com/res/v1/web/search',
        params={'q': query, 'count': count},
        headers={
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'X-Subscription-Token': api_key,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return []

    data = resp.json()
    results = []
    for item in data.get('web', {}).get('results', [])[:count]:
        results.append({
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'snippet': item.get('description', ''),
        })
    return results
