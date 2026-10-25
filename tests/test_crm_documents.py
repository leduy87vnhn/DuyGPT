"""CRM regression tests. Database tests use a disposable schema, never live tables.
Run: DUYGPT_RUN_DB_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
"""
import base64
import json
import os
import re
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import app
import crm
import db
from psycopg import sql
from psycopg_pool import ConnectionPool

CFG = {'provider': 'ollama', 'model': 'test'}
EMPTY_TARGETS = {'file':'', 'screen':'', 'module':'', 'evidence':''}

def source_from_messages(messages):
    lines = re.sub(r'^\[L\d+\] ', '', messages[-1]['content'], flags=re.M).splitlines()
    prefix = re.search(r'Dòng 1 đến (\d+) chỉ', messages[0]['content'])
    return '\n'.join(lines[int(prefix[1]) if prefix else 0:])


def ai_response(cfg, model, messages, tools):
    text = source_from_messages(messages)
    return {'content': json.dumps({'requirements': [
        {'requirement': line, 'source_quote': line} for line in text.splitlines() if line.strip()
    ]})}


class ExtractionTests(unittest.TestCase):
    def test_rejects_unsubstantiated_or_invalid_output(self):
        for result in ['oops', '{}', '{"requirements":[{"requirement":"invented","source_quote":"absent"}]}']:
            with self.subTest(result=result), patch('llm_tools.chat_with_tools', return_value={'content': result}):
                with self.assertRaises(ValueError):
                    crm.extract_requirements(CFG, 'Actual source')

    def test_malformed_json_retries_without_losing_requirements(self):
        good = {'content': json.dumps({'requirements':[{'requirement':'Export', 'source_quote':'Export'}]})}
        with patch('llm_tools.chat_with_tools', side_effect=[{'content':'{"requirements":[{"requirement":"bad"'}, good]) as model:
            self.assertEqual(crm.extract_requirements(CFG, 'Export'), [('Export', 'Export', None, EMPTY_TARGETS)])
            self.assertEqual(model.call_count, 2)

    def test_unverifiable_citation_is_retried_with_feedback(self):
        responses = [{'content':json.dumps({'requirements':[{'requirement':'Export', 'source_quote':quote}]})}
                     for quote in ('Invented quote', 'Export')]
        with patch('llm_tools.chat_with_tools', side_effect=responses) as model:
            self.assertEqual(crm.extract_requirements(CFG, 'Export'), [('Export', 'Export', None, EMPTY_TARGETS)])
            self.assertIn('Lượt trước không hợp lệ', model.call_args.args[2][0]['content'])

    def test_truncated_valid_json_is_not_saved_as_complete(self):
        with patch('llm_tools.chat_with_tools', return_value={'content':'{"requirements":[]}', 'finish_reason':'length'}):
            with self.assertRaisesRegex(ValueError, 'Chưa lưu danh sách thiếu'):
                crm.extract_requirements(CFG, 'Export')

    def test_failed_long_chunk_is_split_and_all_source_is_processed(self):
        source = 'Start ' + 'requirement ' * 100 + ' End'
        seen = []
        def model(cfg, name, messages, tools):
            chunk = source_from_messages(messages)
            seen.append(chunk)
            if len(chunk) > 800:
                return {'content':'{"requirements":['}
            return {'content':json.dumps({'requirements':[{'requirement':chunk, 'source_quote':chunk}]})}
        with patch('llm_tools.chat_with_tools', side_effect=model):
            result = crm.extract_requirements(CFG, source)
        self.assertTrue(any(r[1].startswith('Start') for r in result))
        self.assertTrue(any(r[1].endswith('End') for r in result))
        self.assertGreater(len(seen), 2)

    def test_source_line_references_preserve_exact_original_spelling(self):
        item = dict(requirement='Corrected description', source_lines=[2], completed=True, status_quote='Done')
        with patch('llm_tools.chat_with_tools', return_value={'content':json.dumps({'requirements':[item]})}):
            self.assertEqual(crm.extract_requirements(CFG, 'Header\nOrignal tyop | Done'),
                             [('Corrected description', 'Orignal tyop | Done', True, EMPTY_TARGETS)])
        for indices in ([0], [3], [True], [1,3], []):
            with self.subTest(indices=indices), patch('llm_tools.chat_with_tools', return_value={
                'content':json.dumps({'requirements':[{**item, 'source_lines':indices}]})
            }):
                with self.assertRaises(ValueError):
                    crm.extract_requirements(CFG, 'Header\nOrignal tyop | Done')

    def test_context_distinguishes_identical_requirements(self):
        source = 'Module Kho\nMàn hình Nhập kho\nThêm nút Lưu\nMàn hình Xuất kho\nThêm nút Lưu'
        items = [dict(requirement='Thêm nút Lưu', source_lines=[line], completed=None, status_quote='',
                      context=dict(file='', screen=screen, module='Kho', source_lines=[1, heading]))
                 for line, heading, screen in [(3,2,'Nhập kho'), (5,4,'Xuất kho')]]
        with patch('llm_tools.chat_with_tools', return_value={'content':json.dumps({'requirements':items})}):
            result = crm.extract_requirements(CFG, source)
        self.assertEqual(len(result), 2)
        self.assertEqual({r[3]['screen'] for r in result}, {'Nhập kho','Xuất kho'})
        self.assertTrue(all(r[3]['module'] == 'Kho' for r in result))
        bad = {**items[0], 'context':dict(file='invented.py', screen='', module='', source_lines=[1])}
        with patch('llm_tools.chat_with_tools', return_value={'content':json.dumps({'requirements':[bad]})}):
            with self.assertRaises(ValueError):
                crm.extract_requirements(CFG, source)

    def test_inherited_module_evidence_is_recovered_from_earlier_heading(self):
        source = 'Module: Kho\nMàn hình: Nhập\nLưu\nMàn hình: Xuất\nLưu'
        item = dict(requirement='Lưu', source_lines=[5], completed=None, status_quote='',
                    context=dict(file='', screen='Xuất', module='Kho', source_lines=[4,5]))
        with patch('llm_tools.chat_with_tools', return_value={'content':json.dumps({'requirements':[item]})}):
            targets = crm.extract_requirements(CFG, source)[0][3]
        self.assertIn('Module: Kho', targets['evidence'])
        self.assertEqual(targets['screen'], 'Xuất')

    def test_context_heading_survives_chunk_boundary(self):
        source = 'Màn hình TabInfo\n' + ('Ghi chú chung.\n' * 500) + 'Thêm nút Lưu'
        def model(cfg, name, messages, tools):
            if 'Thêm nút Lưu' not in source_from_messages(messages):
                return {'content':'{"requirements":[]}'}
            lines = messages[-1]['content'].splitlines()
            heading = next(int(re.match(r'\[L(\d+)\]', line)[1]) for line in lines if 'Màn hình TabInfo' in line)
            target = next(int(re.match(r'\[L(\d+)\]', line)[1]) for line in lines if 'Thêm nút Lưu' in line)
            return {'content':json.dumps({'requirements':[dict(requirement='Thêm nút Lưu', source_lines=[target],
                completed=None, status_quote='', context=dict(file='', screen='TabInfo', module='', source_lines=[heading]))]})}
        with patch('llm_tools.chat_with_tools', side_effect=model):
            result = crm.extract_requirements(CFG, source)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][3]['screen'], 'TabInfo')

    def test_empty_source_is_not_success(self):
        with self.assertRaises(ValueError):
            crm.extract_requirements(CFG, '   ')

    def test_processes_entire_document_and_deduplicates(self):
        text = 'First requirement\n' * 600 + 'Last requirement'
        with patch('llm_tools.chat_with_tools', side_effect=ai_response) as model:
            result = crm.extract_requirements(CFG, text)
        self.assertGreater(model.call_count, 1)
        self.assertIn(('Last requirement', 'Last requirement', None, EMPTY_TARGETS), result)
        self.assertEqual(sum(r[0] == 'First requirement' for r in result), 1)

    def test_explicit_status_requires_boolean_and_source_evidence(self):
        for status, evidence in [('true', 'Done'), (1, 'Done'), (True, ''), (True, 'invented')]:
            item = dict(requirement='Export', source_quote='Export | Done', completed=status, status_quote=evidence)
            with self.subTest(status=status, evidence=evidence), patch(
                'llm_tools.chat_with_tools', return_value={'content': json.dumps({'requirements': [item]})}
            ):
                with self.assertRaises(ValueError):
                    crm.extract_requirements(CFG, 'Export | Done')

    def test_separate_table_cell_quotes_must_belong_to_same_source_row(self):
        item = dict(requirement='Export', source_quote='Export', completed=True, status_quote='Done')
        with patch('llm_tools.chat_with_tools', return_value={'content': json.dumps({'requirements': [item]})}):
            self.assertEqual(crm.extract_requirements(CFG, '| Export | Done |'), [('Export', '| Export | Done |', True, EMPTY_TARGETS)])
            with self.assertRaises(ValueError):
                crm.extract_requirements(CFG, '| Export | Pending |\n| Import | Done |')

    def test_status_from_overlapping_chunk_is_retained(self):
        items = [dict(requirement='Export', source_quote='Export'),
                 dict(requirement='Export', source_quote='Export | Done', completed=True, status_quote='Done')]
        with patch('llm_tools.chat_with_tools', return_value={'content': json.dumps({'requirements': items})}):
            self.assertEqual(crm.extract_requirements(CFG, 'Export | Done'), [('Export', 'Export | Done', True, EMPTY_TARGETS)])

    def test_conflicting_explicit_status_is_not_silently_accepted(self):
        items = [dict(requirement='Export', source_quote='Export | Done', completed=True, status_quote='Done'),
                 dict(requirement='Export', source_quote='Export | Not done', completed=False, status_quote='Not done')]
        with patch('llm_tools.chat_with_tools', return_value={'content': json.dumps({'requirements': items})}):
            with self.assertRaises(ValueError):
                crm.extract_requirements(CFG, 'Export | Done\nExport | Not done')


@unittest.skipUnless(os.getenv('DUYGPT_RUN_DB_TESTS') == '1', 'opt in to disposable PostgreSQL schema tests')
class DocumentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'crm_test_' + uuid.uuid4().hex
        cls.live_pool = db.get_pool()
        with cls.live_pool.connection() as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        cls.pool = ConnectionPool(cls.live_pool.conninfo, min_size=1, max_size=8,
                                  kwargs={'options': f'-c search_path={cls.schema},public'})
        with cls.pool.connection() as conn:
            conn.execute(Path('schema.sql').read_text())
            # Migration is repeatable.
            conn.execute(Path('schema.sql').read_text())
            cls.user_id = conn.execute("INSERT INTO users(username,password_hash) VALUES('test','unused') RETURNING id").fetchone()[0]
        cls.embed = patch('rag.embed', return_value=[1.0] + [0.0] * 767)
        cls.ai = patch('llm_tools.chat_with_tools', side_effect=ai_response)
        cls.embed.start(); cls.ai.start()

    @classmethod
    def tearDownClass(cls):
        cls.ai.stop(); cls.embed.stop(); cls.pool.close()
        with cls.live_pool.connection() as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        cls.live_pool.close()
        db._pool = None

    def setUp(self):
        name = uuid.uuid4().hex
        self.customer = crm.create_customer(self.pool, self.user_id, name)['id']
        self.product = crm.create_product(self.pool, self.user_id, name)['id']

    def upload(self, text, title='Memo', filename='memo.txt'):
        return crm.ingest_document(self.pool, self.customer, self.product, 'memo', title,
                                   filename, 'text/plain', text.encode(), self.user_id)

    def requirements(self, doc):
        return crm.list_document_requirements(self.pool, self.customer, self.product, doc['id'])

    def test_versions_snapshots_completion_and_deletion(self):
        v1 = self.upload('Keep\nRemove')
        self.assertEqual(crm.analyze_document(self.pool, v1['id'], CFG)['analysis_status'], 'ready')
        first = self.requirements(v1)
        crm.set_document_requirement_completed(self.pool, first[0]['id'], True)
        v2 = self.upload('Keep\nAdd', title='A different display title')
        self.assertEqual(v2['version'], 2)
        crm.analyze_document(self.pool, v2['id'], CFG)
        current = crm.list_requirements(self.pool, self.customer, self.product)
        self.assertEqual([r['requirement'] for r in current], ['Keep', 'Add'])
        self.assertEqual([r['completed'] for r in current], [True, False])
        self.assertEqual([r['requirement'] for r in self.requirements(v1)], ['Keep', 'Remove'])
        crm.set_document_requirement_completed(self.pool, current[0]['id'], False)
        self.assertTrue(self.requirements(v1)[0]['completed'])
        crm.analyze_document(self.pool, v2['id'], CFG)  # idempotent retry
        self.assertEqual(len(self.requirements(v2)), 2)
        self.assertEqual(bytes(crm.get_document_file(self.pool, v1['id'])[1]), b'Keep\nRemove')
        self.assertEqual(crm.get_document(self.pool, v2['id'])['raw_text'], 'Keep\nAdd')
        crm.delete_document(self.pool, v2['id'])
        self.assertEqual(crm.list_documents(self.pool, self.customer, self.product)[0]['id'], v1['id'])

    def test_uploaded_status_overrides_history_and_missing_status_inherits(self):
        def status_response(cfg, model, messages, tools):
            items = []
            for line in source_from_messages(messages).splitlines():
                title, _, status = line.partition(' | ')
                done = True if status in ('Done', 'Đã xong', 'Hoàn thành', '[x]') else False if status else None
                items.append(dict(requirement=title, source_quote=line, completed=done, status_quote=status))
            return {'content': json.dumps({'requirements': items})}
        with patch('llm_tools.chat_with_tools', side_effect=status_response):
            v1 = self.upload('Export | Done\nImport | Đã xong\nReport | Hoàn thành\nSearch | [x]\nOther | Chưa xong')
            crm.analyze_document(self.pool, v1['id'], CFG)
            self.assertEqual([r['completed'] for r in self.requirements(v1)], [True, True, True, True, False])
            v2 = self.upload('Export | Not done\nImport\nReport | Chưa hoàn thành\nSearch | [ ]\nOther | Done')
            crm.analyze_document(self.pool, v2['id'], CFG)
            self.assertEqual([r['completed'] for r in self.requirements(v2)], [False, True, False, False, True])
            self.assertEqual([r['completed'] for r in self.requirements(v1)], [True, True, True, True, False])

    def test_failure_retry_legacy_and_scope_isolation(self):
        doc = self.upload('Requirement')
        with patch('llm_tools.chat_with_tools', side_effect=RuntimeError('offline')):
            result = crm.analyze_document(self.pool, doc['id'], CFG)
        self.assertEqual(result['analysis_status'], 'failed')
        self.assertTrue(crm.get_document(self.pool, doc['id'])['has_original'])
        self.assertEqual(self.requirements(doc), [])
        crm.analyze_document(self.pool, doc['id'], CFG)
        self.assertEqual(len(self.requirements(doc)), 1)
        self.assertEqual(crm.list_document_requirements(self.pool, self.customer + 1000, self.product, doc['id']), [])
        legacy = self.upload('Legacy', filename='old.txt', title='Old')
        with self.pool.connection() as conn:
            conn.execute('UPDATE crm_documents SET raw_content = NULL, extracted_text = NULL WHERE id = %s', (legacy['id'],))
        self.assertEqual(crm.get_document(self.pool, legacy['id'])['raw_text'], 'Legacy')
        self.assertFalse(crm.get_document(self.pool, legacy['id'])['has_original'])
        self.assertEqual(crm.analyze_document(self.pool, legacy['id'], CFG)['analysis_status'], 'ready')

    def test_invalid_later_chunk_does_not_save_partial_snapshot(self):
        doc = self.upload('Start ' + 'sample ' * 600)
        count = 0
        def response(cfg, model, messages, tools):
            nonlocal count
            count += 1
            if count == 1:
                return {'content':json.dumps({'requirements':[{'requirement':'Start', 'source_quote':'Start'}]})}
            return {'content':'{"requirements":['}
        with patch('llm_tools.chat_with_tools', side_effect=response):
            result = crm.analyze_document(self.pool, doc['id'], CFG)
        self.assertEqual(result['analysis_status'], 'failed')
        self.assertEqual(self.requirements(doc), [])

    def test_concurrent_uploads_get_distinct_versions(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            docs = list(executor.map(self.upload, ['One', 'Two']))
        self.assertEqual(sorted(d['version'] for d in docs), [1, 2])
        self.assertEqual(len(crm.list_documents(self.pool, self.customer, self.product)), 1)

    def test_four_statuses_context_and_scoped_deletion(self):
        doc = self.upload('Section: Warehouse\nReason: slow exports\nExport CSV\nExpected: daily report\nOwner: operations')
        with patch('crm.extract_requirements', return_value=[('Export CSV', 'Export CSV', None, EMPTY_TARGETS), ('Daily report', 'Expected: daily report', None, EMPTY_TARGETS)]):
            crm.analyze_document(self.pool, doc['id'], CFG)
        req = self.requirements(doc)[0]
        self.assertIn('Reason: slow exports', req['source_context'])
        self.assertIn('Expected: daily report', req['source_context'])
        self.assertEqual(req['context_start_line'], 1)
        for status in ('todo', 'progress', 'done', 'rejected'):
            crm.set_document_requirement_status(self.pool, req['id'], status)
            saved = self.requirements(doc)[0]
            self.assertEqual(saved['status'], status)
            self.assertEqual(saved['completed'], status == 'done')
        self.assertIn('error', crm.set_document_requirement_status(self.pool, req['id'], 'unknown'))
        # Reapplying migration must preserve the new status.
        with self.pool.connection() as conn:
            conn.execute(Path('schema.sql').read_text())
        self.assertEqual(self.requirements(doc)[0]['status'], 'rejected')
        newer = self.upload('Export CSV')
        with patch('crm.extract_requirements', return_value=[('Export CSV', 'Export CSV', None, EMPTY_TARGETS)]):
            crm.analyze_document(self.pool, newer['id'], CFG)
        self.assertEqual(self.requirements(newer)[0]['status'], 'rejected')
        self.assertEqual(crm.delete_document_requirements(self.pool, doc['id'], req['id'])['deleted_count'], 1)
        self.assertEqual(len(self.requirements(doc)), 1)
        self.assertEqual(len(self.requirements(newer)), 1)
        self.assertEqual(crm.delete_document_requirements(self.pool, doc['id'])['deleted_count'], 1)
        self.assertEqual(self.requirements(doc), [])
        self.assertTrue(crm.get_document(self.pool, doc['id'])['has_original'])
        self.assertEqual(len(self.requirements(newer)), 1)
        self.assertEqual(crm.delete_document_requirements(self.pool, doc['id'])['deleted_count'], 0)

    def test_target_context_persists_and_status_does_not_cross_screens(self):
        first = self.upload('Màn hình A\nLưu')
        context_a = dict(file='', screen='A', module='', evidence='Màn hình A')
        context_b = dict(file='', screen='B', module='', evidence='Màn hình B')
        with patch('crm.extract_requirements', return_value=[('Lưu','Lưu',None,context_a)]):
            crm.analyze_document(self.pool, first['id'], CFG)
        req = self.requirements(first)[0]
        self.assertEqual(req['target_screen'], 'A')
        self.assertEqual(req['target_evidence'], 'Màn hình A')
        crm.set_document_requirement_status(self.pool, req['id'], 'done')
        second = self.upload('Màn hình A\nLưu\nMàn hình B\nLưu')
        with patch('crm.extract_requirements', return_value=[('Lưu','Lưu',None,context_a), ('Lưu','Lưu',None,context_b)]):
            crm.analyze_document(self.pool, second['id'], CFG)
        self.assertEqual({r['target_screen']:r['status'] for r in self.requirements(second)}, {'A':'done','B':'todo'})
        with self.pool.connection() as conn:
            conn.execute(Path('schema.sql').read_text())
        self.assertEqual(self.requirements(first)[0]['target_screen'], 'A')

    def test_customer_sharing_http_isolation_and_revocation(self):
        import auth
        with self.pool.connection() as conn:
            conn.execute('UPDATE users SET crm_access = TRUE WHERE id = %s', (self.user_id,))
            reader = conn.execute("INSERT INTO users(username,password_hash,crm_access) VALUES(%s,'unused',TRUE) RETURNING id",
                                  ('reader_' + uuid.uuid4().hex,)).fetchone()[0]
            outsider = conn.execute("INSERT INTO users(username,password_hash,user_type) VALUES(%s,'unused','admin_user') RETURNING id",
                                    ('admin_' + uuid.uuid4().hex,)).fetchone()[0]
        tokens = {uid: auth.create_session(self.pool, uid)[0] for uid in (self.user_id, reader, outsider)}
        private = crm.create_customer(self.pool, outsider, 'Other private customer')['id']
        doc = self.upload('Secret requirement')
        crm.analyze_document(self.pool, doc['id'], CFG)
        rid = self.requirements(doc)[0]['id']
        manual = crm.add_requirement(self.pool, self.customer, self.product, '', 'Secret manual', self.user_id)['id']
        proposal = crm.create_proposal(self.pool, self.customer, self.product, 'Secret proposal', 'Secret content', self.user_id)['id']
        other_proposal = crm.create_proposal(self.pool, private, self.product, 'Other secret', 'Other content', outsider)['id']
        with self.pool.connection() as conn:
            attachment = conn.execute("INSERT INTO crm_proposal_attachments(proposal_id,filename,content_type) VALUES(%s,'secret.pdf','application/pdf') RETURNING id", (proposal,)).fetchone()[0]
        class Handler(app.DuyGPTHandler):
            def log_message(self, *args): pass
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(uid, path, method='GET', payload=None):
            req = urllib.request.Request(base + path, method=method,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={'Content-Type': 'application/json', 'Cookie': f'duygpt_session={tokens[uid]}'})
            try:
                with urllib.request.urlopen(req) as response:
                    raw = response.read()
                    return response.status, json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, json.load(error)
        scope = f'?customer_id={self.customer}&product_id={self.product}'
        reads = [('/api/crm/requirements' + scope), ('/api/crm/documents' + scope),
                 ('/api/crm/proposals' + scope), f"/api/crm/documents/{doc['id']}",
                 f"/api/crm/documents/{doc['id']}/download", f'/api/crm/proposals/{proposal}/attachments']
        writes = [(f'/api/crm/document-requirements/{rid}', 'DELETE', None),
                  (f"/api/crm/documents/{doc['id']}/requirements", 'DELETE', None),
                  (f'/api/crm/customers/{self.customer}', 'PUT', {'name':'hacked'}),
                  (f'/api/crm/customers/{self.customer}', 'DELETE', None),
                  (f'/api/crm/requirements/{manual}', 'PUT', {'requirement':'hacked'}),
                  (f'/api/crm/requirements/{manual}', 'DELETE', None),
                  (f"/api/crm/documents/{doc['id']}", 'DELETE', None),
                  (f"/api/crm/documents/{doc['id']}/analyze", 'POST', None),
                  (f'/api/crm/document-requirements/{rid}', 'PUT', {'completed':True}),
                  (f'/api/crm/proposals/{proposal}', 'PUT', {'content':'hacked'}),
                  (f'/api/crm/proposals/{proposal}', 'DELETE', None),
                  (f'/api/crm/proposals/{proposal}/active', 'PUT', {'active':False}),
                  (f'/api/crm/proposals/{proposal}/finalize', 'PUT', None),
                  (f'/api/crm/proposals/{proposal}/attachments', 'POST', {'filename':'x.pdf'}),
                  (f'/api/crm/proposals/{proposal}/attachments/{attachment}', 'DELETE', None)]
        for endpoint in ('requirements', 'documents', 'proposals'):
            writes.append((f'/api/crm/{endpoint}', 'POST', {'customer_id':self.customer, 'product_id':self.product}))
        chat = {'customer_id':self.customer, 'product_id':self.product, 'message':'Summarize requirements'}
        try:
            with patch('db.get_pool', return_value=self.pool), patch('app.get_feature_flags', return_value={'crm':True}), \
                 patch('app.module_config', return_value=CFG), patch('crm.run_agent', return_value=('Secret analysis', [])) as agent:
                for uid in (reader, outsider):
                    self.assertNotIn(self.customer, [c['id'] for c in request(uid, '/api/crm/customers')[1]['customers']])
                    for path in reads:
                        self.assertEqual(request(uid, path)[0], 404, (uid, path))
                    self.assertEqual(request(uid, '/api/crm/chat', 'POST', chat)[0], 404)
                agent.assert_not_called()
                share_path = f'/api/crm/customers/{self.customer}/shares'
                self.assertEqual(request(reader, share_path)[0], 404)
                self.assertEqual(request(outsider, share_path, 'PUT', {'user_ids':[outsider]})[0], 404)
                status, choices = request(self.user_id, share_path)
                self.assertEqual(status, 200)
                self.assertTrue(all(set(u) == {'id','username','shared'} for u in choices['users']))
                self.assertEqual(request(self.user_id, share_path, 'PUT', {'user_ids':[reader]})[0], 200)
                customer = next(c for c in request(reader, '/api/crm/customers')[1]['customers'] if c['id'] == self.customer)
                self.assertFalse(customer['is_owner'])
                for path in reads:
                    self.assertEqual(request(reader, path)[0], 200, path)
                for path, method, payload in writes:
                    self.assertEqual(request(reader, path, method, payload)[0], 404, (method, path))
                    self.assertEqual(request(outsider, path, method, payload)[0], 404, (method, path))
                # The path's parent proposal must match the attachment being deleted.
                self.assertEqual(request(self.user_id, f'/api/crm/proposals/{other_proposal}/attachments/{attachment}', 'DELETE')[0], 404)
                status, answer = request(reader, '/api/crm/chat', 'POST', chat)
                self.assertEqual(status, 200)
                conversation = answer['conversation_id']
                self.assertEqual(request(reader, f'/api/conversations/{conversation}/messages')[0], 200)
                self.assertEqual(request(outsider, f'/api/conversations/{conversation}/messages')[0], 404)
                self.assertEqual(request(reader, share_path, 'PUT', {'user_ids':[outsider]})[0], 404)
                self.assertEqual(request(self.user_id, share_path, 'PUT', {'user_ids':[]})[0], 200)
                agent.reset_mock()
                for path in reads:
                    self.assertEqual(request(reader, path)[0], 404, path)
                self.assertEqual(request(reader, '/api/crm/chat', 'POST', {**chat, 'conversation_id':conversation})[0], 404)
                self.assertEqual(request(reader, f'/api/conversations/{conversation}/messages')[0], 404)
                self.assertEqual(request(reader, '/api/conversations?kind=crm')[1]['conversations'], [])
                agent.assert_not_called()
                # Shared catalog deletion must not cascade customer data.
                self.assertEqual(request(self.user_id, f'/api/crm/products/{self.product}', 'DELETE')[0], 400)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_agent_history_and_schedule_customer_boundaries(self):
        import work_schedule
        with self.pool.connection() as conn:
            reader = conn.execute("INSERT INTO users(username,password_hash,crm_access) VALUES(%s,'unused',TRUE) RETURNING id",
                                  ('r_' + uuid.uuid4().hex,)).fetchone()[0]
        self.upload('Visible customer requirement')
        hidden_customer = crm.create_customer(self.pool, reader, 'Hidden customer')['id']
        crm.ingest_document(self.pool, hidden_customer, self.product, 'memo', 'Hidden file', 'hidden.txt',
                            'text/plain', b'Other customer secret', reader)
        owner = {'id':self.user_id}
        customer = crm.get_customer(self.pool, self.customer, self.user_id)
        product = crm.get_product(self.pool, self.product)
        with patch('llm_tools.run_tool_loop') as model:
            with self.assertRaises(PermissionError):
                crm.run_agent(CFG, self.pool, customer, product, reader, [])
            model.assert_not_called()
        crm.set_customer_shares(self.pool, self.user_id, self.customer, [reader])
        def tool_loop(cfg, model, messages, tools, handlers, iterations):
            self.assertNotIn('save_draft_proposal', [t['function']['name'] for t in tools])
            found = handlers['search_documents']({'query':'requirement'})
            self.assertIn('Visible customer requirement', json.dumps(found))
            self.assertNotIn('Other customer secret', json.dumps(found))
            self.assertNotIn('Hidden file', json.dumps(handlers['list_documents']({})))
            with self.assertRaises(PermissionError):
                handlers['save_draft_proposal']({'title':'Injected', 'content':'Should not be saved'})
            crm.set_customer_shares(self.pool, self.user_id, self.customer, [])
            with self.assertRaises(PermissionError):
                handlers['list_requirements']({})
            return 'Should not return after revocation', []
        with patch('llm_tools.run_tool_loop', side_effect=tool_loop):
            with self.assertRaises(PermissionError):
                crm.run_agent(CFG, self.pool, customer, product, reader, [])
        other = crm.create_customer(self.pool, self.user_id, 'Another customer')['id']
        handler = object.__new__(app.DuyGPTHandler)
        with patch('db.get_pool', return_value=self.pool):
            first = handler.ensure_conversation(owner, None, 'first', kind='crm', crm_scope=(self.customer,self.product))
            second = handler.ensure_conversation(owner, first, 'second', kind='crm', crm_scope=(other,self.product))
            self.assertNotEqual(first, second)
            self.assertEqual(second, handler.ensure_conversation(owner, second, 'again', kind='crm', crm_scope=(other,self.product)))
            self.assertNotEqual(first, handler.ensure_conversation(owner, first, 'chat', kind='chat'))
        denied = work_schedule.create_entry(self.pool, reader, self.customer, 'Meeting', '', '2026-10-20T09:00:00Z', '2026-10-20T10:00:00Z')
        self.assertIn('error', denied)
        crm.set_customer_shares(self.pool, self.user_id, self.customer, [reader])
        meeting = work_schedule.create_entry(self.pool, reader, self.customer, 'Meeting', '', '2026-10-20T09:00:00Z', '2026-10-20T10:00:00Z')
        self.assertEqual(meeting['customer_name'], customer['name'])
        crm.set_customer_shares(self.pool, self.user_id, self.customer, [])
        self.assertIsNone(work_schedule.list_entries(self.pool, reader)[0]['customer_name'])

    def test_http_upload_view_download_completion_and_access(self):
        user_id = self.user_id
        class Handler(app.DuyGPTHandler):
            allowed = True
            def require_crm_access(self):
                if self.allowed:
                    return {'id': user_id}
                self.write_json({'error': 'forbidden'}, 403)
            def log_message(self, *args):
                pass
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, payload=None, method=None):
            req = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                                         headers={'Content-Type': 'application/json'}, method=method)
            return urllib.request.urlopen(req)
        try:
            with patch('db.get_pool', return_value=self.pool), patch('app.module_config', return_value=CFG):
                payload = dict(customer_id=self.customer, product_id=self.product, filename='memo.txt',
                               content_base64=base64.b64encode(b'Test requirement').decode())
                doc = json.load(request('/api/crm/documents', payload))
                self.assertEqual(doc['analysis_status'], 'ready')
                detail = json.load(request(f"/api/crm/documents/{doc['id']}"))
                self.assertEqual(detail['raw_text'], 'Test requirement')
                response = request(f"/api/crm/documents/{doc['id']}/download")
                self.assertEqual(response.read(), b'Test requirement')
                self.assertIn('attachment;', response.headers['Content-Disposition'])
                rid = detail['requirements'][0]['id']
                result = json.load(request(f'/api/crm/document-requirements/{rid}', {'completed': True}, 'PUT'))
                self.assertTrue(result['completed'])
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request(f'/api/crm/document-requirements/{rid}', {'completed': 'false'}, 'PUT')
                self.assertEqual(error.exception.code, 400)
                for status in ('todo', 'progress', 'done', 'rejected'):
                    result = json.load(request(f'/api/crm/document-requirements/{rid}', {'status':status}, 'PUT'))
                    self.assertEqual(result['status'], status)
                result = json.load(request(f'/api/crm/document-requirements/{rid}', method='DELETE'))
                self.assertEqual(result['deleted_count'], 1)
                result = json.load(request(f"/api/crm/documents/{doc['id']}/requirements", method='DELETE'))
                self.assertEqual(result['deleted_count'], 0)
                Handler.allowed = False
                for path, method in [(f"/api/crm/documents/{doc['id']}", 'GET'),
                                     (f"/api/crm/documents/{doc['id']}/download", 'GET'),
                                     (f"/api/crm/documents/{doc['id']}/analyze", 'POST'),
                                     (f'/api/crm/document-requirements/{rid}', 'PUT')]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request(path, method=method)
                    self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
