import copy
from unittest.mock import Mock,patch
import config
import database as db
from test_monitoring import BaseCase,ranks,T1
from test_feishu_cloud import RECIPIENTS
from feishu_push import send_daily_report,send_trial_report
from cloud_job import trial_settings,trial_report

class TrialCase(BaseCase):
    def test_trial_isolated_from_daily_and_retry_keeps_original_payload(self):
        client=Mock(app_id='cli_test',send=Mock(return_value='om_daily'))
        cfg=dict(recipients=RECIPIENTS)
        day='2026-11-04'
        send_daily_report(['daily'],cfg,day,client)
        original_daily=db.query('SELECT * FROM feishu_outbox')
        client.send.side_effect=['om_trial',RuntimeError('temporary')]
        trial=send_trial_report(['trial'], 'github-123',cfg,day,client)
        self.assertEqual((trial['sent'],len(trial['failures'])),(1,1))
        failed=client.send.call_args.args
        self.assertIn('试推',failed[1])
        client.send.side_effect=['om_retry']
        retry=send_trial_report(['changed'], 'github-123',cfg,day,client)
        self.assertEqual(client.send.call_args.args,failed)
        self.assertEqual((retry['sent'],retry['skipped']),(1,1))
        self.assertEqual(db.query('SELECT * FROM feishu_outbox'),original_daily)
        self.assertEqual(send_daily_report(['changed'],cfg,day,client)['skipped'],2)
        uuids=db.query('SELECT message_uuid FROM feishu_outbox UNION SELECT message_uuid FROM feishu_trial_outbox')
        self.assertEqual(len(uuids),4)

    def test_trial_scope_does_not_mutate_daily_settings(self):
        daily=config.monitor_settings();daily['companies']=[self.company]
        before=copy.deepcopy(daily)
        trial=trial_settings(daily)
        self.assertEqual(daily,before)
        self.assertFalse(trial['company_enabled'])
        self.assertEqual(trial['top_n'],100)
        self.assertEqual({(x['platform'],x['country'],x['chart_type'],x['genre']) for x in trial['chart_list']},
                         {('ios','us','free','all'),('gp','us','free','all')})
        trial['companies'][0]['name']='edit'
        self.assertEqual(daily,before)

    def test_trial_snapshot_has_real_top10_and_no_other_scopes(self):
        settings=trial_settings(config.monitor_settings());config.save_monitor_settings(settings)
        for p in ('ios','gp'):
            db.insert_rankings(T1,p,'free',ranks([p+str(i) for i in range(1,13)]),'us')
        db.insert_rankings(T1,'ios','paid',ranks(['paid-only']),'us')
        db.insert_rankings(T1,'ios','free',ranks(['jp-only']),'jp')
        text='\n'.join(trial_report(T1))
        for p in ('ios','gp'):
            self.assertIn('Game '+p+'10',text)
            self.assertNotIn('Game '+p+'11',text)
        self.assertNotIn('paid-only',text);self.assertNotIn('jp-only',text)
        self.assertNotIn('关注公司新游',text)
        self.assertIn('当前排名快照',text)
