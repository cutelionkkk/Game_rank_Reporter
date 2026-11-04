import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import config
import database as db
import cloud_job as cloud
import feishu_push as push
from notify import send_feishu, send_report_parts
import cloud_sync
from test_monitoring import BaseCase, ranks, T0, T1


def response(code=0, status=200, data=None):
    return Mock(status_code=status, json=lambda: dict(code=code, data=data or {}),
                headers={'content-type': 'application/json'})


RECIPIENTS = [{'type': 'email', 'id': 'a@example.com'}, {'type': 'email', 'id': 'b@example.com'}]


class DeliveryCase(BaseCase):
    def test_partial_failure_resumes_original_payload_only_for_failed_recipient(self):
        client = Mock(app_id='cli_test')
        client.send.side_effect = ['om_first', RuntimeError('temporary')]
        cfg = {'recipients': RECIPIENTS}
        first = push.send_daily_report(['<b>第一份</b>'], cfg, '2026-11-04', client)
        self.assertEqual((first['sent'], len(first['failures'])), (1, 1))
        original = client.send.call_args_list[1].args
        client.send.reset_mock()
        client.send.side_effect = ['om_second']
        second = push.send_daily_report(['改变的采集内容'], cfg, '2026-11-04', client)
        self.assertEqual((second['sent'], second['skipped'], second['failures']), (1, 1, []))
        self.assertEqual(client.send.call_args.args, original)
        third = push.send_daily_report(['再次重试'], cfg, '2026-11-04', client)
        self.assertEqual((third['sent'], third['skipped']), (0, 2))
        client.send.assert_called_once()

    def test_unicode_chunking_and_literal_markup(self):
        text = '中文🌍' * 5000
        chunks = push.split_utf8(text)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(c.encode()) <= 12000 for c in chunks))
        self.assertEqual(push.plain_report(['<b>A &amp; B</b>', '&lt;i&gt;literal&lt;/i&gt;']),
                         'A & B\n\n<i>literal</i>')

    def test_recipient_validation_and_dedup(self):
        values = push.recipients_from_config({'recipients': RECIPIENTS + [{'type': 'email', 'id': 'A@EXAMPLE.COM'}]})
        self.assertEqual(values, RECIPIENTS)
        for bad in ([], [{'type': 'chat_id', 'id': 'oc_no'}], [{'type': 'email', 'id': 'not-email'}]):
            with self.assertRaises(ValueError):
                push.recipients_from_config({'recipients': bad})

    def client(self):
        client = push.FeishuClient({'app_id': 'cli_test', 'app_secret': 'never-print-this'})
        client.token = 'never-print-token'
        return client

    @patch('feishu_push.requests.post')
    def test_http_200_is_not_api_success_and_no_secret_in_error(self, post):
        post.return_value = response(230013)
        with self.assertRaisesRegex(RuntimeError, 'code 230013') as caught:
            self.client().send(RECIPIENTS[0], 'private-report', 'uuid')
        self.assertNotIn('never-print', str(caught.exception))
        self.assertNotIn('a@example', str(caught.exception))
        post.return_value = response(0)
        with self.assertRaises(RuntimeError):
            self.client().send(RECIPIENTS[0], 'private-report', 'uuid')

    @patch('feishu_push.time.sleep')
    @patch('feishu_push.requests.post')
    def test_retry_uses_same_uuid(self, post, sleep):
        post.side_effect = [response(99991400, 429), response(data={'message_id': 'om_ok'})]
        result = self.client().send(RECIPIENTS[0], 'payload', 'stable-uuid')
        self.assertEqual(result, 'om_ok')
        self.assertEqual([c.kwargs['json']['uuid'] for c in post.call_args_list], ['stable-uuid'] * 2)

    @patch('notify.requests.post')
    def test_group_webhook_api_failure_is_reported(self, post):
        post.return_value = response(19024)
        ok, message = send_feishu('test', {'webhook_url': 'https://example.com/hook'})
        self.assertFalse(ok)
        self.assertIn('19024', message)

    def test_bot_dispatch_combines_all_sections(self):
        sender = Mock(return_value=(True, 'ok'))
        with patch.dict('notify.SENDERS', {'feishu_bot': sender}):
            result = send_report_parts(['one', 'two'], ['feishu_bot'])
        self.assertTrue(result['feishu_bot'][0])
        sender.assert_called_once_with(['one', 'two'], {})

    def test_daily_jitter_uses_yesterday_instead_of_two_days_ago(self):
        for time in (T0, '2026-11-02T12:20:00Z', '2026-11-03T11:50:00Z'):
            db.insert_rankings(time, 'ios', 'free', ranks(['a', 'b']), 'us')
        previous = db.get_previous_crawl_time('2026-11-03T12:10:00Z', 'ios', 'free', 'us', 24)
        self.assertEqual(previous, '2026-11-02T12:20:00Z')
        db.insert_rankings('2026-11-02T12:10:00Z', 'ios', 'free', ranks(['a', 'b']), 'jp')
        self.assertEqual(db.get_previous_crawl_time('2026-11-03T12:10:00Z', 'ios', 'free', 'us', 24), previous)


class CloudStateCase(BaseCase):
    def setUp(self):
        super().setUp()
        self.key = os.urandom(32)
        self.state = Path(self.temp.name) / 'encrypted.bin'

    def make_state(self):
        db.insert_rankings(T0, 'ios', 'free', ranks(['private-game']), 'us')
        push._init_outbox()
        cloud.pack_state(self.state, self.key)
        return self.state.read_bytes()

    def test_encryption_roundtrip_includes_wal_and_hides_private_data(self):
        connection = db.get_db()
        connection.execute('CREATE TABLE privacy_test(value TEXT)')
        connection.execute('INSERT INTO privacy_test VALUES (?)', ('private-recipient@example.com',))
        connection.commit()
        encrypted = self.make_state()
        self.assertNotIn(b'private-game', encrypted)
        self.assertNotIn(b'private-recipient', encrypted)
        restore = str(Path(self.temp.name) / 'restored.db')
        with patch('database.DB_PATH', restore):
            cloud.unpack_state(encrypted, self.key)
            self.assertEqual(db.query('SELECT value FROM privacy_test')[0]['value'], 'private-recipient@example.com')
            self.assertEqual(db.query('SELECT app_id FROM rankings')[0]['app_id'], 'private-game')
        connection.close()

    def test_tampering_wrong_key_and_existing_db_fail_closed(self):
        encrypted = self.make_state()
        with self.assertRaisesRegex(RuntimeError, '已存在'):
            cloud.unpack_state(encrypted, self.key)
        with patch('database.DB_PATH', str(Path(self.temp.name) / 'new.db')):
            for data, key in [(encrypted[:-1] + bytes([encrypted[-1] ^ 1]), self.key),
                              (encrypted, os.urandom(32)), (b'invalid', self.key)]:
                with self.assertRaises(RuntimeError):
                    cloud.unpack_state(data, key)
            self.assertFalse(Path(db.DB_PATH).exists())

    @patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_TOKEN': 'private'})
    def test_missing_history_requires_explicit_first_run(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=lambda: {'artifacts': []})
        with self.assertRaisesRegex(RuntimeError, '首次运行'):
            cloud.restore_latest(self.key, session=session)
        self.assertFalse(cloud.restore_latest(self.key, bootstrap=True, session=session))

    @patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_TOKEN': 'private'})
    def test_no_fallback_from_expired_latest_or_malicious_zip(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=lambda: {'artifacts': [
            {'id': 1, 'expired': False}, {'id': 2, 'expired': True}]})
        with self.assertRaisesRegex(RuntimeError, '已过期'):
            cloud.restore_latest(self.key, bootstrap=True, session=session)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('../settings.json', 'bad')
        session.get.side_effect = [Mock(status_code=200, json=lambda: {'artifacts': [{'id': 2}]}),
                                   Mock(status_code=200, content=buffer.getvalue())]
        with self.assertRaisesRegex(RuntimeError, '格式错误'):
            cloud.restore_latest(self.key, session=session)

    def test_failed_delivery_still_saves_state_but_restore_failure_does_not(self):
        result = dict(crawl_time=T1, ranking_entries=2, company_catalogs=0, errors=[])
        env = dict(MONITOR_SETTINGS_JSON=json.dumps(config.monitor_settings()),
                   MONITOR_STATE_KEY=base64.b64encode(self.key).decode(),
                   FEISHU_APP_ID='cli_test', FEISHU_APP_SECRET='secret',
                   FEISHU_RECIPIENTS=json.dumps(RECIPIENTS))
        push._init_outbox()
        with patch.dict(os.environ, env), patch('cloud_job.restore_latest') as restore, \
             patch('monitoring.run_monitoring', return_value=result), \
             patch('report.generate_report_parts', return_value=['report']), \
             patch('cloud_job.send_daily_report', return_value=dict(sent=1, skipped=0, failures=['failed'])), \
             patch('cloud_job.pack_state') as pack:
            self.assertEqual(cloud.run(), 1)
            pack.assert_called_once()
            pack.reset_mock()
            restore.side_effect = RuntimeError('restore failed')
            with self.assertRaises(RuntimeError):
                cloud.run()
            pack.assert_not_called()


class CloudSyncCase(BaseCase):
    @patch('cloud_sync.repository_name', return_value='owner/repo')
    @patch('cloud_sync.shutil.which', return_value='/usr/bin/gh')
    @patch('cloud_sync.subprocess.run')
    def test_sync_uses_stdin_and_never_exports_channel_credentials(self, command, which, repository):
        self.configure(channel_config={'slack': {'webhook_url': 'private-token'}})
        command.return_value = Mock(returncode=0)
        self.assertEqual(cloud_sync.sync_settings(), 'owner/repo')
        args, kwargs = command.call_args
        self.assertEqual(args[0][-2:], ['--repo', 'owner/repo'])
        self.assertNotIn('private-token', kwargs['input'])
        self.assertEqual(json.loads(kwargs['input']), config.monitor_settings())
        command.return_value = Mock(returncode=1, stderr='private response')
        with self.assertRaisesRegex(RuntimeError, '本地设置已保留') as caught:
            cloud_sync.sync_settings()
        self.assertNotIn('private response', str(caught.exception))

    @patch('cloud_sync.subprocess.run')
    def test_only_recognized_github_origin_is_used(self, command):
        for url in ('https://github.com/owner/repo.git', 'git@github.com:owner/repo.git'):
            command.return_value = Mock(stdout=url)
            self.assertEqual(cloud_sync.repository_name(), 'owner/repo')
        for url in ('https://github.com.attacker.test/owner/repo.git', 'https://other.test/owner/repo'):
            command.return_value = Mock(stdout=url)
            self.assertIsNone(cloud_sync.repository_name())


if __name__ == '__main__':
    unittest.main()
