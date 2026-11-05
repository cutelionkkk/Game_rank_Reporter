"""GitHub Actions runner. Only authenticated ciphertext leaves the runner."""
import argparse
import base64
import contextlib
import gzip
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

import config
import database as db
from feishu_push import FeishuClient, recipients_from_config, send_daily_report, send_trial_report, daily_delivery_state
from report_guard import ReportBlocked, validate_report

HEADER = b'GAME-RADAR-STATE-v1\0'
ARTIFACT = 'game-radar-state'
MAX_STATE_BYTES = 512 * 1024 * 1024


def state_key():
    try:
        key = base64.b64decode(os.environ.get('MONITOR_STATE_KEY', ''), validate=True)
    except ValueError:
        raise ValueError('MONITOR_STATE_KEY 应为 32 字节密钥的 Base64 编码') from None
    if len(key) != 32:
        raise ValueError('MONITOR_STATE_KEY 应为 32 字节密钥的 Base64 编码')
    return key


def pack_state(destination, key):
    """SQLite backup includes committed WAL pages; never upload the live DB."""
    with tempfile.TemporaryDirectory() as temp:
        snapshot = Path(temp) / 'snapshot.db'
        source = db.get_db()
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        raw = snapshot.read_bytes()
        if len(raw) > MAX_STATE_BYTES:
            raise RuntimeError('历史数据库超出保存上限，请先调整保留周期')
        nonce = os.urandom(12)
        encrypted = HEADER + nonce + AESGCM(key).encrypt(nonce, gzip.compress(raw), HEADER)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending = destination.with_suffix('.tmp')
        pending.write_bytes(encrypted)
        pending.chmod(0o600)
        pending.replace(destination)


def unpack_state(encrypted, key):
    if not encrypted.startswith(HEADER):
        raise RuntimeError('历史文件格式不正确，已停止以避免覆盖历史')
    offset = len(HEADER)
    try:
        compressed = AESGCM(key).decrypt(encrypted[offset:offset+12], encrypted[offset+12:], HEADER)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle:
            raw = handle.read(MAX_STATE_BYTES + 1)
    except (InvalidTag, ValueError, OSError, EOFError):
        raise RuntimeError('历史解密或完整性校验失败，已停止以避免覆盖历史') from None
    if len(raw) > MAX_STATE_BYTES or not raw.startswith(b'SQLite format 3\0'):
        raise RuntimeError('历史数据库无效或过大')
    destination = Path(db.DB_PATH)
    # Restore only into a fresh checkout: never replace a live local database.
    if destination.exists():
        raise RuntimeError('目标数据库已存在，拒绝覆盖；请在干净目录恢复历史')
    pending = destination.with_suffix('.restore.tmp')
    try:
        pending.write_bytes(raw)
        pending.chmod(0o600)
        connection = sqlite3.connect(pending)
        try:
            if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('历史数据库完整性校验失败')
        finally:
            connection.close()
        pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)


def restore_latest(key, bootstrap=False, session=None):
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    token = os.environ.get('GITHUB_TOKEN', '')
    if not repository or not token:
        raise ValueError('缺少 GitHub 仓库或运行凭据')
    session = session or requests.Session()
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    base = f'https://api.github.com/repos/{repository}/actions/artifacts'
    response = session.get(base, params={'name': ARTIFACT, 'per_page': 100}, headers=headers, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f'无法查询历史文件（HTTP {response.status_code}）')
    artifacts = response.json().get('artifacts', [])
    # Do not fall back to an older artifact: that could resend already delivered reports.
    artifacts.sort(key=lambda a: a['id'], reverse=True)
    if not artifacts:
        if not bootstrap:
            raise RuntimeError('没有可恢复的历史。首次运行须手动选择 initialize_history；其他情况请恢复备份')
        print('首次运行：将建立安静基线。')
        return False
    latest = artifacts[0]
    if latest.get('expired'):
        raise RuntimeError('最近的历史文件已过期，请恢复备份，不能自动重建基线')
    response = session.get(f"{base}/{latest['id']}/zip", headers=headers, timeout=90)
    if response.status_code != 200:
        raise RuntimeError(f'无法下载最近历史（HTTP {response.status_code}）')
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            if names != ['state.bin'] or archive.getinfo('state.bin').file_size > MAX_STATE_BYTES:
                raise ValueError('Unexpected artifact contents')
            encrypted = archive.read('state.bin')
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise RuntimeError('历史压缩包格式错误') from None
    unpack_state(encrypted, key)
    print('已恢复加密历史与投递记录。')
    return True


def prune_history():
    """Retain 90 days of snapshots; keep company first-seen baselines permanently."""
    with db.get_db() as connection:
        for table, column in [('rankings', 'crawl_time'), ('crawl_log', 'crawl_time'),
                              ('monitor_runs', 'crawl_time')]:
            connection.execute(f"DELETE FROM {table} WHERE julianday({column}) < julianday('now','-90 days')")
        for table, column in [('feishu_outbox', 'delivery_date'), ('feishu_trial_outbox', 'delivery_key')]:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                connection.execute(f"DELETE FROM {table} WHERE julianday(substr({column},1,10)) < julianday('now','-90 days')")
    connection.close()


def trial_settings(settings):
    """A manual trial overrides only the ephemeral runner configuration."""
    import copy
    result = copy.deepcopy(settings)
    result.update(ranking_enabled=True, top_n=100)
    result['chart_list'] = [dict(platform=p,country='us',chart_type='free',genre='all',enabled=True)
                            for p in ('ios','gp')]
    return result


def trial_report(crawl_time):
    from trial_review import generate_trial_review
    return generate_trial_review(crawl_time)


def run(bootstrap=False, collect_only=False, trial_us_free=False):
    from monitoring import run_monitoring
    from report import generate_report_parts
    key = state_key()
    day = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    try:
        settings = config.validate_monitor_settings(json.loads(os.environ.get('MONITOR_SETTINGS_JSON', '')))
    except (ValueError, TypeError):
        raise ValueError('MONITOR_SETTINGS_JSON 缺失或监测配置无效') from None
    client = None
    if not collect_only:
        recipients_from_config()
        client = FeishuClient()  # Validate credentials before any collection.
    trial_id = None
    if trial_us_free:
        run_id = os.environ.get('GITHUB_RUN_ID', '')
        if not run_id.isdigit():
            raise ValueError('试推需要有效的 GitHub 运行编号')
        trial_id = 'github-' + run_id
        settings = trial_settings(settings)
    config.save_settings(settings)
    restore_latest(key, bootstrap)
    state = None
    if not collect_only and not trial_us_free:
        state = daily_delivery_state(day=day,client=client)
        if state['complete']:
            print('今日所有接收人均已送达，本次复查结束，不重复采集或发送。')
            return 0  # No writes: keep the existing encrypted artifact unchanged.
    # Only save after a successful restore/explicit first-run initialization.
    # A failed restore must never publish a blank replacement artifact.
    try:
        if state and state['resumable']:
            delivery = send_daily_report(None,day=day,client=client)
            print(f"补发原始日报：{delivery['sent']} 条成功，{delivery['skipped']} 条已送达跳过，{len(delivery['failures'])} 项失败。")
            for error in delivery['failures']:
                print(error)
            return 1 if delivery['failures'] else 0
        if trial_us_free and os.environ.get('MONITOR_HISTORY_BACKFILL_JSON'):
            from history_import import import_history
            count = import_history(os.environ['MONITOR_HISTORY_BACKFILL_JSON'])
            print(f'补入 {count} 份原始历史快照。')
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_monitoring()
            parts = trial_report(result['crawl_time']) if trial_us_free else generate_report_parts(result['crawl_time'])
        print(f"采集完成：{result['ranking_entries']} 条排名，{result['company_catalogs']} 个公司目录，{len(result['errors'])} 项失败。")
        validate_report(parts,day,trial=trial_us_free,crawl_time=result['crawl_time'])
        print('发送检查通过：数据、历史比较、有效游戏内容及商店链接已核对。')
        if collect_only:
            print('仅采集，本次没有发送消息。')
            return 1 if result['errors'] else 0
        delivery = send_trial_report(parts, trial_id,day=day,client=client) if trial_us_free else send_daily_report(parts,day=day,client=client)
        print(f"私聊投递：{delivery['sent']} 条成功，{delivery['skipped']} 条已送达跳过，{len(delivery['failures'])} 项失败。")
        for error in delivery['failures']:
            print(error)
        prune_history()
        return 1 if result['errors'] or delivery['failures'] else 0
    except ReportBlocked as exc:
        print(f'{exc}；本次未发送，采集历史保留供后续复查。')
        return 1
    finally:
        if Path(db.DB_PATH).exists():
            pack_state('.cloud/state.bin', key)
            print('已保存加密历史，包括已完成的投递。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize-history', action='store_true')
    parser.add_argument('--collect-only', action='store_true')
    parser.add_argument('--trial-us-free', action='store_true', help='单次试推美国全部游戏免费榜，不修改每日配置')
    options = parser.parse_args()
    try:
        raise SystemExit(run(options.initialize_history, options.collect_only, options.trial_us_free))
    except Exception as exc:
        # Public Actions logs must not include response bodies or request headers.
        if isinstance(exc, (ValueError, RuntimeError)):
            print(f'运行失败：{exc}')
        else:
            print(f'运行失败：{type(exc).__name__}；详细采集状态保存在加密历史中。')
        raise SystemExit(1)
