import base64
import json
import os
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import config
import cloud_job as cloud
import feishu_push as push
from test_feishu_cloud import RECIPIENTS
from test_monitoring import BaseCase, T1

DAY = '2026-11-05'


class DailyRecoveryCase(BaseCase):
    def setUp(self):
        super().setUp()
        # Delivery-state tests use mocked quality gates; source rejection has separate integration tests.
        for target, value in [('feishu_push.validate_report', {}), ('feishu_push.validate_saved_payload', None)]:
            guard = patch(target,return_value=value)
            guard.start();self.addCleanup(guard.stop)
        self.client = Mock(app_id='cli_test', send=Mock(return_value='om_sent'))
        self.env = dict(MONITOR_SETTINGS_JSON=json.dumps(config.monitor_settings()),
                        MONITOR_STATE_KEY=base64.b64encode(os.urandom(32)).decode(),
                        FEISHU_RECIPIENTS=json.dumps(RECIPIENTS),GITHUB_RUN_ID='456')

    def runner(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ,self.env))
        stack.enter_context(patch('cloud_job.restore_latest'))
        stack.enter_context(patch('cloud_job.validate_report'))
        stack.enter_context(patch('cloud_job.FeishuClient',return_value=self.client))
        now = stack.enter_context(patch('cloud_job.datetime'))
        now.now.return_value = datetime(2026,11,5,1,25,tzinfo=timezone.utc)
        collect = stack.enter_context(patch('monitoring.run_monitoring',return_value=dict(
            crawl_time=T1,ranking_entries=2,company_catalogs=0,errors=[])))
        render = stack.enter_context(patch('report.generate_report_parts',return_value=['new report']))
        pack = stack.enter_context(patch('cloud_job.pack_state'))
        return collect, render, pack

    def test_already_delivered_check_does_not_collect_send_or_replace_artifact(self):
        push.send_daily_report(['original'],dict(recipients=RECIPIENTS),DAY,self.client)
        self.client.send.reset_mock()
        collect,render,pack = self.runner()
        self.assertEqual(cloud.run(),0)
        collect.assert_not_called();render.assert_not_called();pack.assert_not_called()
        self.client.send.assert_not_called()

    def test_partial_failure_resumes_original_card_without_source_dependency(self):
        self.client.send.side_effect = ['om_first',RuntimeError('temporary')]
        push.send_daily_report(['original'],dict(recipients=RECIPIENTS),DAY,self.client)
        failed_args = self.client.send.call_args.args
        self.client.send.reset_mock();self.client.send.side_effect=['om_second']
        collect,render,pack = self.runner()
        self.assertEqual(cloud.run(),0)
        collect.assert_not_called();render.assert_not_called();pack.assert_called_once()
        self.client.send.assert_called_once_with(*failed_args)
        self.assertTrue(push.daily_delivery_state(day=DAY,client=self.client)['complete'])

    def test_missing_new_recipient_uses_normal_collection_and_skips_existing_success(self):
        push.send_daily_report(['original'],dict(recipients=RECIPIENTS[:1]),DAY,self.client)
        self.client.send.reset_mock()
        collect,render,pack = self.runner()
        state=push.daily_delivery_state(day=DAY,client=self.client)
        self.assertFalse(state['complete']);self.assertFalse(state['resumable'])
        self.assertEqual(cloud.run(),0)
        collect.assert_called_once();render.assert_called_once();pack.assert_called_once()
        self.client.send.assert_called_once()
        self.assertEqual(self.client.send.call_args.args[0],RECIPIENTS[1])

    def test_completion_is_scoped_to_day_app_and_active_recipient_list(self):
        push.send_daily_report(['original'],dict(recipients=RECIPIENTS),DAY,self.client)
        self.runner()
        self.assertFalse(push.daily_delivery_state(day='2026-11-06',client=self.client)['complete'])
        self.assertFalse(push.daily_delivery_state(day=DAY,client=Mock(app_id='cli_other'))['complete'])
        # A removed recipient's old failed rows must not hold up today's active users.
        changed=[RECIPIENTS[0],dict(type='email',id='new@example.com')]
        state=push.daily_delivery_state(dict(recipients=changed),DAY,self.client)
        self.assertEqual((state['missing_recipients'],state['sent']),(1,1))

    def test_collect_only_and_explicit_trial_do_not_use_daily_completion_guard(self):
        push.send_daily_report(['original'],dict(recipients=RECIPIENTS),DAY,self.client)
        collect,render,pack = self.runner()
        self.assertEqual(cloud.run(collect_only=True),0)
        self.assertEqual(collect.call_count,1)
        with patch('cloud_job.trial_report',return_value=['trial']):
            self.assertEqual(cloud.run(trial_us_free=True),0)
        self.assertEqual(collect.call_count,2)
        self.assertEqual(pack.call_count,2)
