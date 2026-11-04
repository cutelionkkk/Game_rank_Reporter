import copy
import json
from unittest.mock import patch
import config
import database as db
from cloud_job import trial_settings,trial_report
from history_import import import_history
from publishers import store_catalog
from trial_review import review_analysis
from test_monitoring import BaseCase,ranks,scope,game,T0,T1

class HistoryReviewCase(BaseCase):
    def test_short_history_uses_oldest_available_in_window_with_actual_interval(self):
        self.configure(chart_list=[scope(genre='all')],rank_surge_threshold=15)
        early='2026-11-02T10:00:00Z';later='2026-11-02T11:00:00Z'
        db.insert_rankings(early,'ios','free',ranks(['a','b','c']),'us')
        db.insert_rankings(later,'ios','free',ranks(['a','c','b']),'us')
        db.insert_rankings(T1,'ios','free',ranks(['c','a','b','expanded']),'us')
        chart=review_analysis(T1)['charts']['ios_us_free']
        self.assertEqual(chart['previous_time'],early)
        self.assertEqual(chart['elapsed_hours'],2)
        self.assertTrue(chart['short_history'])
        self.assertEqual(chart['changes']['surges'],[])
        self.assertEqual(chart['changes']['top_movers_up'][0]['rank_change'],2)
        self.assertEqual(chart['changes']['new_entries'],[])
        report='\n'.join(trial_report(T1))
        self.assertIn('短时变化',report);self.assertIn('120 分钟',report)
        self.assertIn('#3 → #1（↑2）',report);self.assertIn('暂无达到 ↑15',report)

    def test_existing_full_window_keeps_original_baseline(self):
        self.configure(chart_list=[scope(genre='all')])
        for time in [T0,'2026-11-02T10:00:00Z',T1]:
            db.insert_rankings(time,'ios','free',ranks(['a','b','c']),'us')
        chart=review_analysis(T1)['charts']['ios_us_free']
        self.assertEqual(chart['previous_time'],T0)
        self.assertFalse(chart['short_history'])

    def test_company_baseline_lists_recent_releases_without_new_events(self):
        company=dict(self.company,group='关注公司')
        self.configure(chart_list=[],companies=[company])
        apps=[game('recent','2026-11-01'),game('old','2020-01-01'),game('unknown'),game('future','2027-01-01')]
        store_catalog(T1,company,'us',dict(apps=apps),30)
        report='\n'.join(trial_report(T1))
        self.assertIn('Game recent',report)
        self.assertNotIn('Game old',report);self.assertNotIn('Game future',report)
        self.assertIn('不等同于今天新发布',report)
        self.assertEqual(db.query('SELECT * FROM publisher_events'),[])

    def test_history_import_idempotent_and_conflicts_do_not_partially_write(self):
        original=dict(crawl_time=T0,platform='ios',country='us',chart_type='free',items=ranks(['a','b']))
        self.assertEqual(import_history(json.dumps([original])),1)
        self.assertEqual(import_history(json.dumps([original])),0)
        good=dict(original,platform='gp')
        bad=dict(original,items=ranks(['b','a']))
        with self.assertRaisesRegex(ValueError,'冲突'):import_history(json.dumps([good,bad]))
        self.assertEqual(db.get_rankings_at(T0,'gp','free','us'),[])
        self.assertEqual([r['app_id'] for r in db.get_rankings_at(T0,'ios','free','us')],['a','b'])
