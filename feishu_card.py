"""Readable Feishu JSON 2.0 cards from the report's small HTML vocabulary."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

# Budget the actual nested JSON request (including ASCII escapes), not characters.
MAX_REQUEST_BYTES = 28000


def markdown_text(value):
    value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|~-])', r'\\\1', value)


class ReportMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ('b', 'i'):
            self.parts.append('**' if tag == 'b' else '*')
        elif tag == 'a':
            url = dict(attrs).get('href', '')
            parsed = urlsplit(url)
            valid = parsed.scheme == 'https' and parsed.hostname in ('apps.apple.com', 'play.google.com')
            self.links.append(url if valid else '')
            if valid:
                self.parts.append('[')

    def handle_endtag(self, tag):
        if tag in ('b', 'i'):
            self.parts.append('**' if tag == 'b' else '*')
        elif tag == 'a' and self.links:
            url = self.links.pop()
            if url:
                self.parts.append('](' + url.replace('(', '%28').replace(')', '%29') + ')')

    def handle_data(self, data):
        self.parts.append(markdown_text(data))


def html_to_markdown(value):
    parser = ReportMarkdown()
    parser.feed(value)
    parser.close()
    return ''.join(parser.parts)


def report_blocks(parts):
    blocks = []
    for part in parts:
        # Card headers replace the transport-specific repeated report titles.
        part = re.sub(r'^<b>(?:游戏雷达 · [^<]*|试推补充 · [^<]*)</b>\s*', '', part)
        blocks.extend(b.strip() for b in part.split('\n\n') if b.strip())
    return blocks


def block_elements(block):
    lines = block.split('\n')
    heading = re.fullmatch(r'<b>(.*?)</b>', lines[0])
    elements = []
    if heading:
        main = heading[1].startswith(('📈', '🆕', '🏢'))
        if main:
            elements.append(dict(tag='hr'))
        elements.append(dict(tag='markdown', content=html_to_markdown(lines.pop(0)),
                             text_size='heading' if main else 'normal', margin='8px 0px 0px 0px'))
    rendered = []
    for line in lines:
        content = html_to_markdown(line.strip())
        # Only the numeric increase is highlighted; the threshold remains explicit.
        content = re.sub(r'↑([0-9]+)', r"<font color='green'>↑\1</font>", content)
        muted = '<a ' not in line and not re.search(r'#[0-9]+.*→', line) and not line.startswith('• ')
        rendered.append("<font color='grey'>" + content + '</font>' if muted else content)
    if rendered:
        elements.append(dict(tag='markdown', content='\n'.join(rendered), text_size='normal', margin='4px 0px 8px 0px'))
    return elements


def card_payload(elements, title, trial):
    return {
        'schema': '2.0',
        'config': {'update_multi': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': title},
            'subtitle': {'tag': 'plain_text', 'content': '榜单爬升 · 竞品动态' + (' · 试推预览' if trial else '')},
            'template': 'blue',
            'padding': '12px 16px 12px 16px',
        },
        'body': {
            'direction': 'vertical', 'padding': '12px 16px 16px 16px',
            'elements': elements + [
                {'tag': 'hr'},
                {'tag': 'markdown', 'content': "<font color='grey'>点击游戏名称打开对应商店 · 时间为北京时间</font>",
                 'text_size': 'notation', 'margin': '4px 0px 0px 0px'},
            ],
        },
    }


def request_bytes(card):
    body = dict(receive_id='x'*256, msg_type='interactive', uuid='x'*40,
                content=json.dumps(card, ensure_ascii=False))
    return len(json.dumps(body).encode('utf-8'))


def build_cards(parts, day, trial=False):
    title = '游戏雷达 · ' + day
    pages, elements = [], []
    blocks = report_blocks(parts)
    if not blocks:
        raise ValueError('日报内容为空，未发送')
    for block in blocks:
        unit = block_elements(block)
        budget_title = title + '（999/999）'
        if request_bytes(card_payload(unit, budget_title, trial)) > MAX_REQUEST_BYTES:
            raise ValueError('单个报告段落过长，请减少本节展示数量；未截断产品链接')
        candidate = elements + unit
        if elements and (len(candidate) > 90 or request_bytes(card_payload(candidate, budget_title, trial)) > MAX_REQUEST_BYTES):
            pages.append(elements)
            elements = unit
        else:
            elements = candidate
    if elements:
        pages.append(elements)
    return [card_payload(page, title + (f'（{i+1}/{len(pages)}）' if len(pages)>1 else ''), trial)
            for i, page in enumerate(pages)]
