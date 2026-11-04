import json
import re
from unittest.mock import Mock, patch

import database as db
from feishu_card import build_cards, html_to_markdown, request_bytes, MAX_REQUEST_BYTES
from feishu_push import FeishuClient, send_daily_report, send_trial_report
from product_links import product_link, product_url
from report import generate_report_parts
from trial_review import generate_trial_review
from test_feishu_cloud import RECIPIENTS, response
from test_monitoring import BaseCase, scope, ranks, game, T0, T1


class CardCase(BaseCase):
    def test_store_identity_and_escaped_link_labels(self):
        name = 'A [Puzzle] & <b>Game</b> *!'
        link = product_link(dict(app_id='123456', app_name=name), 'ios', 'jp')
        markdown = html_to_markdown(link)
        self.assertIn('<link url="https://apps.apple.com/jp/app/id123456">', markdown)
        self.assertIn('[Puzzle]', markdown)
        self.assertNotIn(r'\!', markdown)
        self.assertIn('&lt;b&gt;Game&lt;/b&gt;', markdown)
        self.assertNotIn('**Game**', markdown)
        self.assertEqual(product_url('gp', 'com.example.game', 'us'),
                         'https://play.google.com/store/apps/details?id=com.example.game&gl=us')
        self.assertEqual(product_url('ios', 'javascript:alert(1)'), '')
        self.assertEqual(product_url('gp', 'com.example/game'), '')
        self.assertNotIn('https://evil.example', html_to_markdown('<a href="https://evil.example">name</a>'))

    def test_daily_and_trial_all_product_mentions_have_store_links(self):
        self.configure(chart_list=[scope(genre='all'),scope(genre='all',platform='gp')],companies=[self.company])
        for platform, ids in [('ios',['101','102','103','104']),('gp',['com.test.a','com.test.b','com.test.c','com.test.d'])]:
            db.insert_rankings(T0,platform,'free',ranks(ids[:3]),'us')
            db.insert_rankings(T1,platform,'free',ranks([ids[2],ids[3],ids[0]]),'us')
        self.catalog(T0,[game('201','2020-01-01')])
        self.catalog(T1,[game('201','2020-01-01'),game('202','2026-11-01'),game('203','2020-01-01')])
        for parts in [generate_report_parts(T1),generate_trial_review(T1)]:
            raw='\n'.join(parts)
            names=re.findall(r'Game [A-Za-z0-9.]+',raw)
            linked=re.findall(r'<a href="[^"]+">(Game [A-Za-z0-9.]+)</a>',raw)
            self.assertGreaterEqual(len(linked),6)
            self.assertEqual(sorted(names),sorted(linked))
            card=json.dumps(build_cards(parts,'2026-11-02'),ensure_ascii=False)
            self.assertIn('https://apps.apple.com/us/app/id202',card)
            self.assertIn('id=com.test.c&amp;gl=us',card)

    def test_snapshot_names_also_linked_without_history(self):
        self.configure(chart_list=[scope(genre='all')])
        db.insert_rankings(T1,'ios','free',ranks(['101','102']),'us')
        raw='\n'.join(generate_trial_review(T1))
        self.assertIn('<a href="https://apps.apple.com/us/app/id101">Game 101</a>',raw)

    def test_large_unicode_digest_splits_without_broken_or_lost_links(self):
        parts=[f'<b>📈 快速爬升</b>\n• {product_link(dict(app_id=str(1000+i),app_name="游戏🌍"*25),"ios")}\n#20 → #1（↑19）' for i in range(120)]
        cards=build_cards(parts,'2026-11-04',trial=True)
        self.assertGreater(len(cards),1)
        all_markdown='\n'.join(e.get('content','') for c in cards for e in c['body']['elements'])
        urls=re.findall(r'<link url="(https://apps.apple.com/[^"]+)">',all_markdown)
        self.assertEqual(len(urls),120)
        self.assertEqual(len(set(urls)),120)
        for card in cards:
            self.assertLessEqual(request_bytes(card),MAX_REQUEST_BYTES)
            self.assertEqual(card['schema'],'2.0')
            self.assertLess(len(card['body']['elements']),100)
        self.assertIn("<font color='green'>↑19</font>",all_markdown)

    @patch('feishu_push.requests.post')
    def test_transport_sends_interactive_card_and_persists_type(self,post):
        post.return_value=response(data={'message_id':'om_card'})
        client=FeishuClient(dict(app_id='cli_test',app_secret='not-a-real-secret'))
        client.token='not-a-real-token'
        result=send_trial_report(['<b>📈 爬升</b>\n'+product_link(game('123'),'ios')],
                                 'card-preview',dict(recipients=RECIPIENTS[:1]),'2026-11-04',client)
        self.assertEqual(result['sent'],1)
        payload=post.call_args.kwargs['json']
        self.assertEqual(payload['msg_type'],'interactive')
        self.assertEqual(json.loads(payload['content'])['schema'],'2.0')
        self.assertEqual(db.query('SELECT msg_type FROM feishu_trial_outbox')[0]['msg_type'],'interactive')

    def test_legacy_pending_post_is_migrated_and_retried_unchanged(self):
        with db.get_db() as conn:
            conn.execute('''CREATE TABLE feishu_outbox (
                delivery_date TEXT,app_id TEXT,recipient_type TEXT,recipient_id TEXT,
                part INTEGER,content TEXT,message_uuid TEXT,sent_at TEXT,message_id TEXT,error TEXT,
                PRIMARY KEY(delivery_date,app_id,recipient_type,recipient_id,part))''')
            conn.execute('INSERT INTO feishu_outbox VALUES (?,?,?,?,?,?,?,?,?,?)',
                         ('2026-11-04','cli_test','email',RECIPIENTS[0]['id'],0,'original-post','old-uuid',None,None,'retry'))
        client=Mock(app_id='cli_test',send=Mock(return_value='om_old'))
        cfg=dict(recipients=RECIPIENTS[:1])
        result=send_daily_report(['new card'],cfg,'2026-11-04',client)
        self.assertEqual(result['sent'],1)
        client.send.assert_called_once_with(RECIPIENTS[0],'original-post','old-uuid','post')
        self.assertEqual(send_daily_report(['changed'],cfg,'2026-11-04',client)['skipped'],1)
        self.assertEqual(db.query('SELECT content,msg_type FROM feishu_outbox')[0],dict(content='original-post',msg_type='post'))
