import copy
from unittest.mock import patch
import config
import database as db
from analyzer import analyze_chart_changes
from report import generate_report_parts
from test_monitoring import BaseCase, scope, ranks, T0, T1, game

class DigestCase(BaseCase):
    def test_same_game_combines_scopes_and_removes_noise(self):
        self.configure(chart_list=[scope(),scope('jp')])
        for country in ('us','jp'):
            db.insert_rankings(T0,'ios','free:puzzle',ranks(['a','b','c']),country)
            db.insert_rankings(T1,'ios','free:puzzle',ranks(['c','a','b']),country)
        report='\n'.join(generate_report_parts(T1))
        self.assertEqual(report.count('Game c'),1)
        self.assertIn('US',report);self.assertIn('JP',report)
        self.assertIn('#3 → #1（↑2）',report)
        for removed in ('在榜产品数','玩法分布',T0,T1):self.assertNotIn(removed,report)

    def test_expansion_from_50_to_100_is_not_new_entries(self):
        db.insert_rankings(T0,'ios','free:puzzle',ranks([str(i) for i in range(50)]),'us')
        db.insert_rankings(T1,'ios','free:puzzle',ranks([str(i) for i in range(100)]),'us')
        self.assertEqual(analyze_chart_changes('ios','free:puzzle',T1,T0,'us')['new_entries'],[])

    def test_company_group_is_compact_and_incomplete_not_no_new_games(self):
        first=dict(self.company,group='母公司')
        second=dict(first,id='studio2',developer_id='456',name='第二账号')
        self.configure(chart_list=[],companies=[first,second])
        self.catalog(T0,[game('a')])
        self.catalog(T1,[game('a'),game('b','2026-11-02')])
        report='\n'.join(generate_report_parts(T1))
        self.assertEqual(report.count('<b>母公司</b>'),1)
        self.assertIn('Game b',report)
        self.assertIn('数据不完整',report)
        self.assertNotIn('暂无新增游戏',report)
        report='\n'.join(generate_report_parts(T0))
        self.assertIn('暂不能确认',report)
        self.assertNotIn('暂无新增游戏',report)

    def test_watchlist_accepts_60_accounts_and_validates_groups(self):
        public=config.monitor_settings()
        public['companies']=[dict(self.company,id=str(i),developer_id=str(i),group='母公司') for i in range(60)]
        config.save_monitor_settings(public)
        self.assertEqual(len(config.monitor_settings()['companies']),60)
        public['companies'][0]['group']=['bad']
        with self.assertRaises(ValueError):config.validate_monitor_settings(public)

    def test_unavailable_store_account_stays_watched_without_false_baseline(self):
        from publishers import crawl_companies
        from store_api import PublisherUnavailable
        self.configure(chart_list=[],companies=[self.company])
        with patch('publishers.fetch_publisher',side_effect=PublisherUnavailable('账号暂不可用')):
            total,errors=crawl_companies(T0,self.settings)
        self.assertEqual((total,errors),(0,[]))
        self.assertEqual(db.query('SELECT status,baseline FROM publisher_snapshots')[0],dict(status='unavailable',baseline=0))
        self.assertIn('暂不能确认','\n'.join(generate_report_parts(T0)))
        self.assertEqual(db.query('SELECT * FROM publisher_apps'),[])
        self.catalog(T1,[game('a')])
        self.assertEqual(db.query('SELECT * FROM publisher_events'),[])

    def test_verified_artist_without_products_is_distinct_from_invalid_lookup(self):
        from store_api import fetch_publisher, PublisherUnavailable
        with patch('store_api.fetch_json',return_value={'results':[dict(wrapperType='artist',artistId=123)]}):
            with self.assertRaises(PublisherUnavailable):fetch_publisher(self.company,'us')
        with patch('store_api.fetch_json',return_value={'results':[]}):
            with self.assertRaises(ValueError):fetch_publisher(self.company,'us')
