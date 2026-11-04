"""Stable store links from collected product IDs, never from name searches."""
import re
from html import escape
from urllib.parse import urlencode


def product_url(platform, app_id, country='us'):
    app_id = str(app_id or '')
    country = str(country or 'us').lower()
    country = country if re.fullmatch(r'[a-z]{2}', country) else 'us'
    if platform == 'ios' and re.fullmatch(r'[0-9]+', app_id):
        return f'https://apps.apple.com/{country}/app/id{app_id}'
    if platform == 'gp' and re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+', app_id):
        return 'https://play.google.com/store/apps/details?' + urlencode(dict(id=app_id, gl=country))
    return ''


def product_link(app, platform, country='us', limit=120):
    name = escape(str(app.get('app_name') or '')[:limit])
    url = product_url(platform, app.get('app_id'), country)
    return f'<a href="{escape(url, quote=True)}">{name}</a>' if url else name
