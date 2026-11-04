"""Application-bot daily DMs with a durable per-recipient delivery ledger."""
import hashlib
import json
import os
import re
import time
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

import requests
from database import get_db, init_db, utcnow, query
from monitoring import monitor_lock

API = 'https://open.feishu.cn/open-apis'


def recipients_from_config(config=None):
    config = config or {}
    raw = config.get('recipients')
    if raw is None:
        try:
            raw = json.loads(os.environ.get('FEISHU_RECIPIENTS', '[]'))
        except ValueError as exc:
            raise ValueError('FEISHU_RECIPIENTS 必须是 JSON 数组') from exc
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        raise ValueError('请配置 1–20 个飞书接收人')
    recipients, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('接收人配置格式错误')
        kind, value = item.get('type', 'open_id'), item.get('id', '')
        if not isinstance(value, str):
            raise ValueError('接收人标识必须是字符串')
        value = value.strip()
        valid = (kind == 'open_id' and re.fullmatch(r'ou_[a-zA-Z0-9]+', value)) or (
            kind == 'email' and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value))
        if not valid:
            raise ValueError('接收人请使用已核对的 open_id 或企业邮箱')
        if kind == 'email':
            value = value.lower()
        key = (kind,value)
        if key not in seen:
            recipients.append(dict(type=kind,id=value));seen.add(key)
    return recipients


def plain_report(parts):
    # Decode source text only after removing our own formatting tags.
    return '\n\n'.join(unescape(re.sub(r'</?(?:b|i)>', '', part)) for part in parts)


def split_utf8(text, limit=12000):
    chunks, current, size = [], [], 0
    for char in text:
        width = len(char.encode('utf-8'))
        if size + width > limit:
            chunks.append(''.join(current));current=[];size=0
        current.append(char);size += width
    if current:
        chunks.append(''.join(current))
    return chunks


class FeishuClient:
    def __init__(self, config=None):
        config = config or {}
        self.app_id = config.get('app_id') or os.environ.get('FEISHU_APP_ID', '')
        self.app_secret = config.get('app_secret') or os.environ.get('FEISHU_APP_SECRET', '')
        if not re.fullmatch(r'cli_[a-zA-Z0-9]+',self.app_id) or not self.app_secret:
            raise ValueError('请配置飞书应用 FEISHU_APP_ID 和 FEISHU_APP_SECRET')
        self.token = None

    def authenticate(self):
        try:
            r = requests.post(API+'/auth/v3/tenant_access_token/internal',
                              json={'app_id':self.app_id,'app_secret':self.app_secret},timeout=20)
            d = r.json()
        except (requests.RequestException,ValueError) as exc:
            raise RuntimeError('飞书应用认证请求未完成，请检查网络') from exc
        if r.status_code != 200 or d.get('code') != 0 or not d.get('tenant_access_token'):
            raise RuntimeError(f"飞书应用认证失败（HTTP {r.status_code}，code {d.get('code')}），请核对应用凭证")
        self.token = d['tenant_access_token']

    def send(self, recipient, content, message_uuid):
        for attempt in range(3):
            if not self.token:
                self.authenticate()
            try:
                r = requests.post(API+'/im/v1/messages',params={'receive_id_type':recipient['type']},
                    headers={'Authorization':'Bearer '+self.token},
                    json={'receive_id':recipient['id'],'msg_type':'post','content':content,'uuid':message_uuid},timeout=25)
                d = r.json()
            except (requests.RequestException,ValueError):
                if attempt < 2:
                    time.sleep(2**attempt);continue
                raise RuntimeError('飞书投递请求超时或响应无效，待下次重试') from None
            message_id = d.get('data',{}).get('message_id')
            if r.status_code == 200 and d.get('code') == 0 and message_id:
                return message_id
            if d.get('code') in (99991663,99991664,99991668) and attempt < 2:
                self.token = None;continue
            if (r.status_code == 429 or r.status_code >= 500) and attempt < 2:
                time.sleep(2**attempt);continue
            # Keep recipients, tokens and the message body out of public workflow logs.
            raise RuntimeError(f"飞书投递失败（HTTP {r.status_code}，code {d.get('code')}）；检查机器人权限与接收人的应用可用范围")
        raise RuntimeError('飞书投递失败')


def _init_outbox():
    init_db()
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS feishu_outbox (
            delivery_date TEXT NOT NULL, app_id TEXT NOT NULL,
            recipient_type TEXT NOT NULL, recipient_id TEXT NOT NULL,
            part INTEGER NOT NULL, content TEXT NOT NULL, message_uuid TEXT NOT NULL,
            sent_at TEXT, message_id TEXT, error TEXT,
            PRIMARY KEY(delivery_date,app_id,recipient_type,recipient_id,part))''')
    conn.close()


def send_daily_report(parts, config=None, day=None, client=None):
    """One immutable daily report per recipient; retries resume failed deliveries."""
    recipients = recipients_from_config(config)
    client = client or FeishuClient(config)
    day = day or datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
        raise ValueError('日报日期格式错误')
    chunks = split_utf8(plain_report(parts))
    if not chunks:
        raise ValueError('日报内容为空，未发送')
    with monitor_lock():
        _init_outbox()
        with get_db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for recipient in recipients:
                # A retry must use the original payload even if collection results changed.
                existing = conn.execute('''SELECT 1 FROM feishu_outbox WHERE delivery_date=?
                    AND app_id=? AND recipient_type=? AND recipient_id=? LIMIT 1''',
                    (day,client.app_id,recipient['type'],recipient['id'])).fetchone()
                if existing:
                    continue
                for index,chunk in enumerate(chunks):
                    title = f'游戏监测日报 · {day}' + (f'（{index+1}/{len(chunks)}）' if len(chunks)>1 else '')
                    content = json.dumps({'zh_cn':{'title':title,'content':[[{'tag':'text','text':chunk}]]}},ensure_ascii=False)
                    seed = json.dumps([day,client.app_id,recipient['type'],recipient['id'],index],ensure_ascii=False)
                    message_uuid = hashlib.sha256(seed.encode()).hexdigest()[:40]
                    conn.execute('''INSERT INTO feishu_outbox
                        (delivery_date,app_id,recipient_type,recipient_id,part,content,message_uuid)
                        VALUES (?,?,?,?,?,?,?)''',(day,client.app_id,recipient['type'],recipient['id'],index,content,message_uuid))
        conn.close()
        sent, skipped, failures = 0, 0, []
        for number,recipient in enumerate(recipients,1):
            rows = query('''SELECT * FROM feishu_outbox WHERE delivery_date=? AND app_id=?
                AND recipient_type=? AND recipient_id=? ORDER BY part''',
                (day,client.app_id,recipient['type'],recipient['id']))
            for row in rows:
                if row['sent_at']:
                    skipped += 1;continue
                try:
                    message_id = client.send(recipient,row['content'],row['message_uuid'])
                    with get_db() as conn:
                        conn.execute('UPDATE feishu_outbox SET sent_at=?,message_id=?,error=NULL WHERE message_uuid=?',
                                     (utcnow(),message_id,row['message_uuid']))
                    conn.close();sent += 1
                except (RuntimeError,ValueError) as exc:
                    with get_db() as conn:
                        conn.execute('UPDATE feishu_outbox SET error=? WHERE message_uuid=?',(str(exc),row['message_uuid']))
                    conn.close();failures.append(f'接收人 {number}，第 {row["part"]+1} 部分：{exc}')
        return dict(sent=sent,skipped=skipped,failures=failures,recipients=len(recipients))
