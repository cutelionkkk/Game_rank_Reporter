import copy
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import config
import database as db
from analyzer import analyze_chart_changes, generate_full_analysis, find_consecutive_risers
from publishers import store_catalog, crawl_companies, company_analysis, release_age_days
from crawler import _parse_ios_old, _ios_old_rss_url, run_full_crawl
from monitoring import run_monitoring, monitor_lock
from report import generate_report_parts
from export import export_analysis_data
from store_api import fetch_publisher, search_companies
from dashboard import DashboardServer

T0 = '2026-11-01T12:00:00Z'
T1 = '2026-11-02T12:00:00Z'
T2 = '2026-11-03T12:00:00Z'


def scope(country='us',genre='puzzle',platform='ios',chart='free'):
    return dict(platform=platform,country=country,chart_type=chart,genre=genre,enabled=True)


def ranks(ids):
    return [dict(rank=i,app_id=a,app_name='Game '+a,developer='Studio',category='Puzzle',extra_json='{}')
            for i,a in enumerate(ids,1)]


def game(id,release=None,is_game=True):
    return dict(app_id=id,app_name='Game '+id,release_date=release,is_game=is_game,url='https://apps.apple.com/us/app/id1')


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_path = os.path.join(self.temp.name,'settings.json')
        for target,value in [('config.CONFIG_FILE',self.settings_path),('database.DB_PATH',os.path.join(self.temp.name,'rankings.db')),
                             ('export.EXPORT_PATH',os.path.join(self.temp.name,'analysis.json')),('monitoring.SCRIPT_DIR',self.temp.name)]:
            p = patch(target,value); p.start(); self.addCleanup(p.stop)
        self.settings = copy.deepcopy(config.DEFAULTS)
        self.settings.update(chart_list=[scope()],comparison_hours=24,rank_surge_threshold=2)
        config.save_settings(self.settings)
        db.init_db()
        self.company = dict(id='studio1',name='Studio',platform='ios',developer_id='123',countries=['us'],enabled=True)

    def configure(self,**values):
        self.settings.update(values)
        config.save_settings(self.settings)

    def catalog(self,time,apps,country='us',partial=False):
        return store_catalog(time,self.company,country,dict(apps=apps,partial=partial,message='capped' if partial else ''),30)


class StorageCase(BaseCase):
    def test_empty_selection_does_not_fall_back(self):
        self.configure(chart_list=[])
        self.assertEqual(config.chart_scopes(),[])
        self.configure(chart_list=[scope()],ranking_enabled=False)
        self.assertEqual(config.chart_scopes(),[])

    def test_secrets_preserved_but_not_exposed(self):
        self.configure(channel_config={'telegram':{'bot_token':'test-secret'}})
        public = config.monitor_settings()
        self.assertNotIn('test-secret',json.dumps(public))
        public['rank_surge_threshold'] = 7
        config.save_monitor_settings(public)
        self.assertEqual(config.load_settings()['channel_config']['telegram']['bot_token'],'test-secret')
        self.assertEqual(config.load_settings()['rank_surge_threshold'],7)

    def test_invalid_settings_fail_without_overwrite(self):
        before = Path(self.settings_path).read_text()
        public = config.monitor_settings(); public['chart_list'].append(scope())
        with self.assertRaises(ValueError): config.save_monitor_settings(public)
        self.assertEqual(Path(self.settings_path).read_text(),before)
        public['chart_list'] = [scope()]; public['comparison_hours'] = -1
        with self.assertRaises(ValueError): config.save_monitor_settings(public)
        public['comparison_hours'] = 24; public['ranking_enabled'] = 'false'
        with self.assertRaises(ValueError): config.save_monitor_settings(public)

    def test_legacy_settings_gain_default_country(self):
        self.configure(country='jp',chart_list=[dict(platform='ios',chart_type='paid',genre='all')])
        self.assertEqual(config.monitor_settings()['chart_list'][0]['country'],'jp')
        config.validate_monitor_settings(config.monitor_settings())

    def test_company_validation(self):
        public = config.monitor_settings(); public['companies'] = [self.company]
        config.validate_monitor_settings(public)
        public['companies'][0]['developer_id'] = 'name-not-numeric'
        with self.assertRaises(ValueError): config.validate_monitor_settings(public)

    def test_country_isolation_and_unique_constraint(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b','c']),'us')
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['c','b','a']),'jp')
        db.insert_rankings(T1,'ios','free:puzzle',ranks(['c','a','b']),'us')
        result = analyze_chart_changes('ios','free:puzzle',T1,T0,'us')
        self.assertEqual([(a['app_id'],a['rank_change']) for a in result['surges']],[('c',2)])
        self.assertEqual(db.get_rankings_at(T0,'ios','free:puzzle','jp')[0]['app_id'],'c')

    def test_first_snapshot_is_quiet(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b']),'us')
        changes = analyze_chart_changes('ios','free:puzzle',T0,None,'us')
        self.assertTrue(all(not values for values in changes.values()))

    def test_missing_snapshot_not_exit(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b']),'us')
        changes = analyze_chart_changes('ios','free:puzzle',T1,T0,'us')
        self.assertEqual(changes['exits'],[])

    def test_window_and_stale_history(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b','c']),'us')
        db.insert_rankings('2026-11-02T11:00:00Z','ios','free:puzzle',ranks(['b','c','a']),'us')
        db.insert_rankings(T1,'ios','free:puzzle',ranks(['c','a','b']),'us')
        a = generate_full_analysis(T1)['charts']['ios_us_free:puzzle']
        self.assertEqual(a['previous_time'],T0)
        self.assertEqual(a['elapsed_hours'],24)
        db.insert_rankings('2026-11-10T12:00:00Z','ios','free:puzzle',ranks(['a','b','c']),'us')
        self.assertIsNone(generate_full_analysis('2026-11-10T12:00:00Z')['charts']['ios_us_free:puzzle']['previous_time'])

    def test_report_export_share_threshold_and_genres(self):
        self.configure(rank_surge_threshold=2,chart_list=[scope(),scope('jp')])
        for country in ('us','jp'):
            db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b','c'] ),country)
            db.insert_rankings(T1,'ios','free:puzzle',ranks(['c','a','b'] ),country)
        report = '\n'.join(generate_report_parts(T1))
        self.assertIn('上升 ≥2 名',report)
        self.assertIn('Game c',report)
        self.assertIn('US',report);self.assertIn('JP',report)
        data = export_analysis_data(T1)
        self.assertEqual(set(data['charts']),{'ios_us_free:puzzle','ios_jp_free:puzzle'})
        self.assertEqual(data['charts']['ios_jp_free:puzzle']['changes']['surges'][0]['rank_change'],2)

    def test_report_escapes_source_html(self):
        before = ranks(['a','b','c'])
        after = ranks(['c','a','b']);after[0]['app_name'] = '<script>bad</script>'
        db.insert_rankings(T0,'ios','free:puzzle',before,'us')
        db.insert_rankings(T1,'ios','free:puzzle',after,'us')
        report = '\n'.join(generate_report_parts(T1))
        self.assertNotIn('<script>',report)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;',report)

    def test_dry_run_never_notifies(self):
        from run import main
        from contextlib import redirect_stdout
        from io import StringIO
        with patch('sys.argv',['run.py','--dry-run']), patch('monitoring.run_monitoring',return_value={'crawl_time':T0,'errors':[]}), patch('report.generate_report_parts',return_value=['test']), patch('export.export_analysis_data',return_value=None), patch('notify.send_report_parts') as notify, patch('run.os.path.dirname',return_value=self.temp.name), redirect_stdout(StringIO()):
            self.assertEqual(main(),0)
        notify.assert_not_called()

    def test_depth_change_does_not_manufacture_exits(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b','c']),'us')
        db.insert_rankings(T1,'ios','free:puzzle',ranks(['a','b']),'us')
        self.assertEqual(analyze_chart_changes('ios','free:puzzle',T1,T0,'us')['exits'],[])

    def test_streak_must_end_now(self):
        times = ['2026-11-01T00:00:00Z','2026-11-01T06:00:00Z','2026-11-01T12:00:00Z','2026-11-01T18:00:00Z']
        for time,ids in zip(times,[['a','b','c'],['a','c','b'],['c','a','b'],['a','c','b']]):
            db.insert_rankings(time,'ios','free:puzzle',ranks(ids),'us')
        self.assertFalse(find_consecutive_risers('ios','free:puzzle',min_rises=2,country='us',current_time=times[-1]))
        self.assertEqual(find_consecutive_risers('ios','free:puzzle',min_rises=2,country='us',current_time=times[-2])[0]['app_id'],'c')

    def test_company_baseline_release_discovery_and_dedup(self):
        self.configure(chart_list=[],companies=[self.company])
        self.assertEqual(self.catalog(T0,[game('old','2020-01-01')]),0)
        apps = [game('old','2020-01-01'),game('new','2026-11-02'),game('unknown'),game('old2','2019-01-01'),game('future','2027-01-01'),game('utility','2026-11-02',False)]
        self.assertEqual(self.catalog(T1,apps),4)
        events = company_analysis(T1,self.settings)[0]['events']
        self.assertEqual({e['app_id']:e['kind'] for e in events},
                         dict(new='new_release',unknown='newly_discovered',old2='newly_discovered',future='newly_discovered'))
        self.assertEqual(self.catalog(T2,apps),0)
        self.assertEqual(len(db.query('SELECT * FROM publisher_events')),4)
        self.assertIn('近期发布','\n'.join(generate_report_parts(T1)))
        self.assertEqual(export_analysis_data(T1)['companies'][0]['events'][0]['app_id'],'new')

    def test_new_country_has_own_quiet_baseline(self):
        self.catalog(T0,[game('a')],'us')
        self.catalog(T1,[game('a'),game('b','2026-11-02')],'jp')
        self.assertEqual(db.query('SELECT * FROM publisher_events'),[])
        self.catalog(T2,[game('a'),game('b','2026-11-02')],'us')
        self.assertEqual(db.query('SELECT * FROM publisher_events'),[])

    def test_failed_company_fetch_does_not_baseline_or_emit(self):
        self.configure(companies=[self.company])
        with patch('publishers.fetch_publisher',side_effect=RuntimeError('network down')):
            total,errors = crawl_companies(T0,self.settings)
        self.assertEqual(total,0); self.assertEqual(len(errors),1)
        self.assertEqual(db.query('SELECT * FROM publisher_apps'),[])
        self.catalog(T1,[game('a','2026-11-01')])
        self.assertEqual(db.query('SELECT * FROM publisher_events'),[])
        self.assertEqual(db.query('SELECT baseline FROM publisher_snapshots WHERE crawl_time=?',(T1,))[0]['baseline'],1)

    def test_partial_catalog_is_marked(self):
        self.catalog(T0,[game('a')],partial=True)
        snapshot = db.query('SELECT * FROM publisher_snapshots')[0]
        self.assertEqual(snapshot['status'],'partial')
        self.assertEqual(snapshot['message'],'capped')

    def test_bad_catalog_rolls_back(self):
        self.catalog(T0,[game('a')])
        with self.assertRaises(KeyError): self.catalog(T1,[game('b'),{'app_id':'bad','is_game':True}])
        self.assertEqual([r['app_id'] for r in db.query('SELECT app_id FROM publisher_apps')],['a'])
        self.assertEqual(db.query('SELECT * FROM publisher_events'),[])

    def test_crawler_captures_failure_without_fake_snapshot(self):
        with patch('crawler.crawl_ios_chart',side_effect=RuntimeError('HTTP 404')):
            _,total,errors = run_full_crawl(T0,self.settings)
        self.assertEqual(total,0);self.assertEqual(len(errors),1)
        analysis = generate_full_analysis(T0)
        self.assertEqual(analysis['charts']['ios_us_free:puzzle']['status'],'error')
        self.assertEqual(analysis['charts']['ios_us_free:puzzle']['current'],[])
        self.assertIn('HTTP 404','\n'.join(generate_report_parts(T0)))

    def test_disabled_monitors_never_call_network(self):
        self.configure(ranking_enabled=False,company_enabled=False,companies=[self.company])
        with patch('crawler.crawl_ios_chart') as charts, patch('publishers.fetch_publisher') as pubs:
            result = run_monitoring()
        charts.assert_not_called();pubs.assert_not_called()
        self.assertEqual(result['status'],'ok')

    def test_shared_lock_prevents_overlapping_jobs(self):
        with monitor_lock():
            with self.assertRaises(RuntimeError):
                with monitor_lock(): pass

    def test_failed_current_run_does_not_reuse_old_results(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks(['a']),'us')
        with patch('crawler.crawl_ios_chart',side_effect=RuntimeError('offline')):
            result = run_monitoring()
        self.assertEqual(result['status'],'error')
        analysis = generate_full_analysis()
        self.assertEqual(analysis['crawl_time'],result['crawl_time'])
        self.assertFalse(analysis['charts']['ios_us_free:puzzle']['current'])


class MigrationCase(BaseCase):
    def test_migrate_legacy_country_backup_and_repeat(self):
        for suffix in ('','-wal','-shm'):
            if os.path.exists(db.DB_PATH+suffix): os.unlink(db.DB_PATH+suffix)
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute('''CREATE TABLE rankings(id INTEGER PRIMARY KEY,crawl_time TEXT,platform TEXT,
          chart_type TEXT,rank INTEGER,app_id TEXT,app_name TEXT,developer TEXT,category TEXT,
          rating REAL,rating_count INTEGER,price REAL,icon_url TEXT,extra_json TEXT,
          UNIQUE(crawl_time,platform,chart_type,rank))''')
        conn.execute("INSERT INTO rankings(crawl_time,platform,chart_type,rank,app_id,app_name) VALUES (?,'ios','free',1,'a','A')",(T0,))
        conn.execute('CREATE TABLE crawl_log(id INTEGER PRIMARY KEY,crawl_time TEXT,platform TEXT,chart_type TEXT,count INTEGER,status TEXT,message TEXT,duration_sec REAL)')
        conn.commit();conn.close()
        self.configure(country='jp')
        db.init_db(); db.init_db()
        self.assertTrue(os.path.exists(db.DB_PATH+'.pre-country.bak'))
        self.assertEqual(db.get_rankings_at(T0,'ios','free','jp')[0]['app_id'],'a')
        db.insert_rankings(T0,'ios','free',ranks(['b']),'us')
        self.assertEqual(len(db.query('SELECT * FROM rankings')),2)


class SourceCase(unittest.TestCase):
    def test_ios_game_feed_never_uses_all_apps_v2(self):
        self.assertIn('genre=6014',_ios_old_rss_url('free','all','jp',100))
        self.assertIn('/jp/',_ios_old_rss_url('free','all','jp',100))

    def test_single_ios_entry(self):
        data = {'feed':{'entry':{'id':{'attributes':{'im:id':'1'}},'im:name':{'label':'Test'}}}}
        self.assertEqual(_parse_ios_old(data)[0]['app_id'],'1')

    def test_ios_lookup_filters_other_accounts_and_marks_non_games(self):
        records = [dict(wrapperType='software',artistId=123,trackId=1,trackName='Game',genreIds=['6014']),
                   dict(wrapperType='software',artistId=456,trackId=2,trackName='Wrong',genreIds=['6014']),
                   dict(wrapperType='software',artistId=123,trackId=3,trackName='Utility',genreIds=['6002'])]
        with patch('store_api.fetch_json',return_value={'results':records}):
            data = fetch_publisher(dict(platform='ios',developer_id='123'),'us')
        self.assertEqual([a['app_id'] for a in data['apps']],['1','3'])
        self.assertTrue(data['apps'][0]['is_game']);self.assertFalse(data['apps'][1]['is_game'])

    def test_empty_lookup_is_error(self):
        with patch('store_api.fetch_json',return_value={'results':[]}):
            with self.assertRaises(ValueError): fetch_publisher(dict(platform='ios',developer_id='123'),'us')

    def test_release_dates_and_unknown(self):
        self.assertEqual(release_age_days('Nov 1, 2026',T1),1.5)
        self.assertIsNone(release_age_days('unknown',T1))
        self.assertLess(release_age_days('2027-01-01',T1),0)


class WebCase(BaseCase):
    def setUp(self):
        super().setUp()
        self.server = DashboardServer(('127.0.0.1',0))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def request(self,path,body=None,headers=None):
        extra = dict(headers or {})
        if body is not None: extra.setdefault('Content-Type','application/json')
        req = Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=extra)
        with urlopen(req,timeout=5) as response:
            return response.status,json.loads(response.read())

    def test_web_roundtrip_and_secret_hiding(self):
        self.configure(channel_config={'slack':{'webhook_url':'private-test-token'}})
        _,body = self.request('/api/bootstrap')
        self.assertNotIn('private-test-token',json.dumps(body))
        body['settings']['chart_list'] = []
        status,data = self.request('/api/settings',body['settings'],{'X-Monitor-Token':body['token']})
        self.assertEqual(status,200);self.assertEqual(config.chart_scopes(),[])
        self.assertEqual(config.load_settings()['channel_config']['slack']['webhook_url'],'private-test-token')

    def test_web_rejects_cross_origin_and_missing_token(self):
        with self.assertRaises(HTTPError) as err: self.request('/api/settings',config.monitor_settings())
        self.assertEqual(err.exception.code,403)
        with self.assertRaises(HTTPError) as err: self.request('/api/bootstrap',headers={'Origin':'https://attacker.example'})
        self.assertEqual(err.exception.code,403)
        with self.assertRaises(HTTPError) as err: self.request('/api/bootstrap',headers={'Host':'attacker.example'})
        self.assertEqual(err.exception.code,403)

    def test_web_no_arbitrary_file_read(self):
        with self.assertRaises(HTTPError) as err: self.request('/settings.json')
        self.assertEqual(err.exception.code,404)

    def test_web_run_and_save_conflict(self):
        self.server.job_lock.acquire()
        self.addCleanup(self.server.job_lock.release)
        with self.assertRaises(HTTPError) as err:
            self.request('/api/run',{}, {'X-Monitor-Token':self.server.token})
        self.assertEqual(err.exception.code,409)


if __name__ == '__main__': unittest.main()
