"""Shared CLI/web collection job; a file lock prevents overlapping cron and UI runs."""
import json
import os
from contextlib import contextmanager
from config import SCRIPT_DIR, load_settings, monitor_settings, validate_monitor_settings
from database import init_db, get_db, utcnow
from crawler import run_full_crawl
from publishers import crawl_companies


@contextmanager
def monitor_lock():
    path = os.path.join(SCRIPT_DIR, '.monitor.lock')
    handle = open(path, 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('已有监测正在运行，请等待完成') from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('已有监测正在运行，请等待完成') from exc
        yield
    finally:
        handle.close()


def run_monitoring():
    with monitor_lock():
        init_db()
        settings = load_settings()
        public = validate_monitor_settings(monitor_settings(settings))
        settings.update(public)
        crawl_time = utcnow()
        with get_db() as conn:
            # A lock was acquired, so previous unfinished local jobs were interrupted.
            conn.execute("UPDATE monitor_runs SET status='interrupted',error='上次进程中断' WHERE status='running'")
            conn.execute('INSERT INTO monitor_runs(crawl_time,status,settings_json) VALUES (?,\'running\',?)',
                         (crawl_time,json.dumps(public,ensure_ascii=False)))
        conn.close()
        try:
            _, total, errors = run_full_crawl(crawl_time, settings)
            companies, company_errors = crawl_companies(crawl_time, settings)
            errors.extend(company_errors)
            result = dict(crawl_time=crawl_time, ranking_entries=total,
                          company_catalogs=companies, errors=errors,
                          status='partial' if errors and (total or companies) else 'error' if errors else 'ok')
        except Exception as exc:
            with get_db() as conn:
                conn.execute("UPDATE monitor_runs SET status='error',finished_at=?,error=? WHERE crawl_time=?",
                             (utcnow(),str(exc)[:600],crawl_time))
            conn.close()
            raise
        with get_db() as conn:
            conn.execute('UPDATE monitor_runs SET status=?,finished_at=?,error=? WHERE crawl_time=?',
                         (result['status'],utcnow(),'\n'.join(errors),crawl_time))
        conn.close()
        return result
