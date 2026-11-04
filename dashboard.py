"""Loopback-only dashboard. Configuration API never returns notification secrets."""
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from config import (SCRIPT_DIR, monitor_settings, save_monitor_settings,
                    country_code)
from database import init_db
from genres import GENRES, CHART_TYPES, PLATFORMS

COUNTRIES = {'us':'美国','cn':'中国大陆','jp':'日本','kr':'韩国','gb':'英国','de':'德国',
             'fr':'法国','ca':'加拿大','au':'澳大利亚','tw':'中国台湾','hk':'中国香港',
             'sg':'新加坡','in':'印度','br':'巴西','mx':'墨西哥','id':'印度尼西亚',
             'th':'泰国','vn':'越南','my':'马来西亚','ph':'菲律宾','tr':'土耳其',
             'sa':'沙特阿拉伯','ae':'阿联酋','es':'西班牙','it':'意大利','ru':'俄罗斯'}


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.job_lock = threading.Lock()
        self.job = dict(running=False, result=None, error=None)
        self.search_lock = threading.Lock()

    def run_job(self):
        try:
            from monitoring import run_monitoring
            result = run_monitoring()
            from export import export_analysis_data
            export_analysis_data(result['crawl_time'])
            self.job = dict(running=False,result=result,error=None)
        except Exception as exc:
            self.job = dict(running=False,result=None,error=str(exc)[:600])
        finally:
            self.job_lock.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Avoid logging search terms or configuration content.
        pass

    def respond(self, value, status=200, content_type='application/json; charset=utf-8'):
        data = json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def local_request(self):
        port = self.server.server_port
        allowed = (f'127.0.0.1:{port}', f'localhost:{port}')
        origin = self.headers.get('Origin')
        valid = (self.headers.get('Host') in allowed and
                 (not origin or origin in ['http://' + h for h in allowed]) and
                 self.headers.get('Sec-Fetch-Site') != 'cross-site')
        if not valid:
            self.respond({'error':'仅允许本机网页访问'},403)
        return valid

    def do_GET(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        try:
            if path == '/api/bootstrap':
                self.respond(dict(settings=monitor_settings(), token=self.server.token,
                                  options=dict(countries=COUNTRIES,genres=GENRES,charts=CHART_TYPES,platforms=PLATFORMS)))
            elif path in ('/api/state','/api/export'):
                from analyzer import generate_full_analysis
                analysis = generate_full_analysis()
                if path == '/api/export':
                    from export import build_export
                    self.respond(build_export(analysis['crawl_time']) if analysis else {'metadata':{'schema_version':2},'charts':{},'companies':[]})
                else:
                    self.respond(dict(job=self.server.job, analysis=analysis))
            elif path in ('/','/app.js','/style.css'):
                file = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
                mime = {'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8',
                        '/style.css':'text/css; charset=utf-8'}[path]
                with open(os.path.join(SCRIPT_DIR,'web',file),'rb') as f:
                    self.respond(f.read(),content_type=mime)
            else:
                self.respond({'error':'页面不存在'},404)
        except (ValueError, OSError) as exc:
            self.respond({'error':str(exc)[:600]},400)

    def do_POST(self):
        if not self.local_request():
            return
        if not secrets.compare_digest(self.headers.get('X-Monitor-Token',''), self.server.token):
            self.respond({'error':'页面已过期，请刷新后重试'},403)
            return
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 256000:
                raise ValueError('请求体为空或过大')
            body = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == '/api/settings':
                if not self.server.job_lock.acquire(blocking=False):
                    self.respond({'error':'监测运行中，完成后再保存设置'},409)
                    return
                try:
                    from monitoring import monitor_lock
                    with monitor_lock():
                        self.respond(dict(settings=save_monitor_settings(body)))
                finally:
                    self.server.job_lock.release()
            elif path == '/api/search':
                if not self.server.search_lock.acquire(blocking=False):
                    self.respond({'error':'搜索正在进行，请稍后再试'},409)
                    return
                try:
                    if not isinstance(body,dict):
                        raise ValueError('搜索参数无效')
                    from store_api import search_companies
                    matches = search_companies(body.get('platform'),country_code(body.get('country')),body.get('term'))
                    self.respond(dict(results=matches))
                finally:
                    self.server.search_lock.release()
            elif path == '/api/run':
                if not self.server.job_lock.acquire(blocking=False):
                    self.respond({'error':'监测已经在运行'},409)
                    return
                self.server.job = dict(running=True,result=None,error=None)
                threading.Thread(target=self.server.run_job,daemon=True).start()
                self.respond(dict(started=True),202)
            else:
                self.respond({'error':'接口不存在'},404)
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            self.respond({'error':str(exc)[:600]},400)
        except Exception as exc:
            self.respond({'error':'请求未完成：' + str(exc)[:400]},502)


def serve(port=8765, open_browser=False):
    if not 1 <= port <= 65535:
        raise ValueError('端口必须在 1–65535 之间')
    init_db()
    server = DashboardServer(('127.0.0.1',port))
    print(f'本地游戏监测网页：http://127.0.0.1:{port}',flush=True)
    print('网页运行监测不会发送通知；按 Ctrl+C 停止服务。',flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
