import base64
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch

import cloud_job as cloud
import config
import database as db
import feishu_push as push
from report import generate_report_parts
from report_guard import ReportBlocked, validate_report
from test_feishu_cloud import RECIPIENTS
from test_monitoring import BaseCase, T0, T1, ranks, scope, game

DAY = '2026-11-02'
NOW = datetime(2026,11,2,12,5,tzinfo=timezone.utc)


class QualityCase(BaseCase):
    def setUp(self):
        super().setUp()
        self.configure(chart_list=[scope(genre='all')],companies=[])
        clock = patch('report_guard.datetime')
        clock.start().now.return_value = NOW
        self.addCleanup(clock.stop)
        for at, ids in [(T0,['101','102','103','104']), (T1,['103','101','102','104'])]:
            db.insert_rankings(at,'ios','free',ranks(ids),'us')
            db.log_crawl(at,'ios','free',4,'ok',country='us')
            with db.get_db() as conn:
                conn.execute('INSERT INTO monitor_runs(crawl_time,status,finished_at,settings_json) VALUES (?,?,?,?)',(at,'ok',at,json.dumps(config.monitor_settings())))
        self.client = Mock(app_id='cli_test',send=Mock(return_value='om_ok'))
        self.cfg = dict(recipients=RECIPIENTS)

    def send(self):
        return push.send_daily_report(generate_report_parts(T1),self.cfg,DAY,self.client)

    def assert_blocked(self, text):
        with self.assertRaisesRegex(ReportBlocked,text):
            self.send()
        self.client.send.assert_not_called()
        self.assertEqual(db.query('SELECT COUNT(*) n FROM feishu_outbox')[0]['n'],0)

    def test_valid_report_is_checked_and_delivered_once(self):
        self.assertEqual(self.send()['sent'],2)
        rows = db.query('SELECT * FROM feishu_outbox')
        self.assertTrue(all(json.loads(r['approval_json'])['crawl_time']==T1 for r in rows))
        self.assertEqual(self.send()['skipped'],2)
        self.assertEqual(self.client.send.call_count,2)

    def test_explicit_trial_with_real_linked_snapshot_can_pass_without_history(self):
        from trial_review import generate_trial_review
        with db.get_db() as conn:
            conn.execute('DELETE FROM rankings WHERE crawl_time=?',(T0,))
        result=push.send_trial_report(generate_trial_review(T1),'test',self.cfg,DAY,self.client)
        self.assertEqual(result['sent'],2)

    def test_company_only_report_with_verified_new_game_can_pass(self):
        self.configure(ranking_enabled=False,companies=[self.company])
        self.catalog(T0,[game('201','2020-01-01')])
        self.catalog(T1,[game('201','2020-01-01'),game('202','2026-11-02')])
        self.assertEqual(self.send()['sent'],2)

    def test_rendered_card_losing_products_is_blocked(self):
        with patch('feishu_card.build_cards',return_value=[{'body':{'elements':[]}}]):
            self.assert_blocked('卡片渲染丢失')

    def test_empty_report_and_lack_of_comparison_history_never_send(self):
        with db.get_db() as conn:
            conn.execute('DELETE FROM rankings WHERE crawl_time=?',(T0,))
        self.assert_blocked('缺少有效对比历史')

    def test_good_collection_with_no_signal_is_silent(self):
        db.insert_rankings(T1,'ios','free',ranks(['101','102','103','104']),'us')
        self.assert_blocked('无符合条件')

    def test_source_errors_and_missing_selected_scope_block_other_good_sections(self):
        self.configure(chart_list=[scope(genre='all'),scope(country='jp',genre='all')])
        self.assert_blocked('榜单为空、缺失或采集异常')
        self.configure(chart_list=[scope(genre='all')])
        with db.get_db() as conn:
            conn.execute("UPDATE monitor_runs SET status='partial',error='network' WHERE crawl_time=?",(T1,))
        self.assert_blocked('采集未完整成功')

    def test_unavailable_and_partial_company_catalogs_block_report(self):
        self.configure(companies=[self.company])
        self.catalog(T1,[game('201')],partial=True)
        self.assert_blocked('公司账号目录未完整取得')
        with db.get_db() as conn:
            conn.execute("UPDATE publisher_snapshots SET status='unavailable'")
        self.assert_blocked('公司账号目录未完整取得')

    def test_stale_wrong_date_and_future_data_block(self):
        parts=generate_report_parts(T1)
        for at,day in [(datetime(2026,11,2,16,tzinfo=timezone.utc),DAY),
                       (NOW,'2026-11-03'),(datetime(2026,11,2,11,tzinfo=timezone.utc),DAY)]:
            with self.assertRaisesRegex(ReportBlocked,'数据过期'):
                validate_report(parts,day,now=at)

    def test_changed_content_or_wrong_product_link_blocks_before_outbox(self):
        parts=generate_report_parts(T1)
        for content in [[],['暂无数据'],[p.replace('id103','id999') for p in parts]]:
            with self.assertRaises(ReportBlocked):
                push.send_daily_report(content,self.cfg,DAY,self.client)
        self.client.send.assert_not_called()
        self.assertEqual(db.query('SELECT COUNT(*) n FROM feishu_outbox')[0]['n'],0)

    def test_missing_product_id_and_abrupt_depth_drop_block(self):
        with db.get_db() as conn:
            conn.execute("UPDATE rankings SET app_id='invalid' WHERE crawl_time=? AND rank=1",(T1,))
        self.assert_blocked('产品信息')
        with db.get_db() as conn:
            conn.execute("UPDATE rankings SET app_id='103' WHERE crawl_time=? AND rank=1",(T1,))
            conn.execute('DELETE FROM rankings WHERE crawl_time=? AND rank>2',(T1,))
            conn.execute('UPDATE crawl_log SET count=2 WHERE crawl_time=?',(T1,))
        self.assert_blocked('采集深度异常')

    def test_partial_retry_rechecks_original_and_keeps_uuid(self):
        self.client.send.side_effect=['om_first',RuntimeError('offline')]
        self.assertEqual(len(self.send()['failures']),1)
        original=self.client.send.call_args.args
        self.client.send.reset_mock();self.client.send.side_effect=['om_second']
        result=push.send_daily_report(None,self.cfg,DAY,self.client)
        self.assertEqual((result['sent'],result['skipped']),(1,1))
        self.client.send.assert_called_once_with(*original)

    def test_tampered_pending_card_blocks_all_recipients(self):
        self.client.send.side_effect=RuntimeError('offline')
        self.send();self.client.send.reset_mock()
        with db.get_db() as conn:
            conn.execute("UPDATE feishu_outbox SET content='tampered' WHERE recipient_id=?",(RECIPIENTS[1]['id'],))
        with self.assertRaisesRegex(ReportBlocked,'审核记录'):
            push.send_daily_report(None,self.cfg,DAY,self.client)
        self.client.send.assert_not_called()

    def test_stale_retry_and_changed_scope_are_blocked(self):
        self.client.send.side_effect=RuntimeError('offline')
        self.send();self.client.send.reset_mock()
        with patch('report_guard.datetime') as clock:
            clock.now.return_value=datetime(2026,11,2,16,tzinfo=timezone.utc)
            with self.assertRaisesRegex(ReportBlocked,'数据过期'):
                push.send_daily_report(None,self.cfg,DAY,self.client)
        self.configure(rank_surge_threshold=3)
        with self.assertRaisesRegex(ReportBlocked,'配置已改变'):
            push.send_daily_report(None,self.cfg,DAY,self.client)
        self.client.send.assert_not_called()

    def test_cloud_block_saves_history_without_sending_or_outbox(self):
        with db.get_db() as conn:
            conn.execute('DELETE FROM rankings WHERE crawl_time=?',(T0,))
        env=dict(MONITOR_SETTINGS_JSON=json.dumps(config.monitor_settings()),
                 MONITOR_STATE_KEY=base64.b64encode(os.urandom(32)).decode(),
                 FEISHU_RECIPIENTS=json.dumps(RECIPIENTS),GITHUB_RUN_ID='123')
        result=dict(crawl_time=T1,ranking_entries=4,company_catalogs=0,errors=[])
        with patch.dict(os.environ,env),patch('cloud_job.restore_latest'), \
             patch('cloud_job.FeishuClient',return_value=self.client),patch('cloud_job.datetime') as clock, \
             patch('monitoring.run_monitoring',return_value=result),patch('cloud_job.pack_state') as pack:
            clock.now.return_value=NOW.astimezone(ZoneInfo('Asia/Shanghai'))
            self.assertEqual(cloud.run(),1)
            self.assertEqual(cloud.run(trial_us_free=True),1) # missing selected Google Play scope
            self.assertEqual(pack.call_count,2)
        self.client.send.assert_not_called()
        self.assertEqual(db.query('SELECT COUNT(*) n FROM feishu_outbox')[0]['n'],0)
