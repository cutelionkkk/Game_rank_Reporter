"""Publish only monitor preferences to the origin repository's Actions Secret."""
import json
from pathlib import Path
import re
import shutil
import subprocess

from config import SCRIPT_DIR, monitor_settings, validate_monitor_settings


def repository_name():
    try:
        result = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=SCRIPT_DIR,
                                capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?', result.stdout.strip())
    return match.group(1) if match else None


def sync_settings():
    repository = repository_name()
    if not repository:
        raise RuntimeError('当前项目没有 GitHub origin 仓库，无法同步')
    gh = shutil.which('gh')
    local = Path.home() / '.local/bin/gh'
    if not gh and local.is_file():
        gh = str(local)
    if not gh:
        raise RuntimeError('请先安装 GitHub CLI 并完成登录')
    payload = validate_monitor_settings(monitor_settings())
    try:
        result = subprocess.run([gh, 'secret', 'set', 'MONITOR_SETTINGS_JSON', '--repo', repository],
                                cwd=SCRIPT_DIR, input=json.dumps(payload, ensure_ascii=False),
                                text=True, capture_output=True, timeout=40)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError('同步未完成，请检查网络和 GitHub 登录状态；本地设置已保留') from None
    if result.returncode:
        raise RuntimeError('GitHub 拒绝同步，请检查当前账号的仓库管理权限；本地设置已保留')
    return repository


if __name__ == '__main__':
    print(f'已同步每天推送的监测范围：{sync_settings()}')
