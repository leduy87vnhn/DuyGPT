import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

from pathlib import Path

root = str(Path(__file__).resolve().parents[1] / 'web')
class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=root))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
docs = [dict(id=i, title='Memo', filename='memo.txt', doc_type='memo', version=i,
             is_current=i == 2, created_at='2026-10-20T00:00:00Z', analysis_status='ready',
             analysis_error='', has_original=True, raw_text=f'Raw version {i}') for i in [2, 1]]
requirements = {i: [dict(id=i, document_id=i, document_title='Memo', version=i,
                        requirement=f'Requirement v{i}', source_quote=f'Raw version {i}', completed=False, status='todo', target_module='Kho', target_screen='TabInfo', target_file='report.xlsx', target_evidence='Module Kho / TabInfo / report.xlsx', source_context=f'Business context\nRaw version {i}\nExpected outcome', context_start_line=1, context_end_line=3)] for i in [1,2]}
errors = []
access = {"is_owner": True, "shared_user_ids": []}

def route_api(route):
    path = urlsplit(route.request.url).path
    data = {}
    if path == '/api/auth/me': data = dict(authenticated=True, user_type='admin_user', crm_access=True)
    elif path == '/api/crm/customers': data = {'customers':[{'id':1, 'name':'Test customer', 'is_owner': access['is_owner']}]}
    elif path == '/api/crm/customers/1/shares':
        if route.request.method == 'PUT':
            access['shared_user_ids'] = route.request.post_data_json['user_ids']
            data = {'shared_user_ids': access['shared_user_ids']}
        else:
            data = {'users': [{'id':2, 'username':'shared-reader', 'shared':2 in access['shared_user_ids']}]}
    elif path == '/api/crm/products': data = {'products':[{'id':1, 'name':'Test product'}]}
    elif path == '/api/crm/requirements': data = {'requirements':requirements[2]}
    elif path == '/api/crm/documents': data = {'documents':docs if 'all=1' in route.request.url else docs[:1]}
    elif path.endswith('/requirements') and path.startswith('/api/crm/documents/'):
        doc_id = int(path.split('/')[4]); count = len(requirements[doc_id]); requirements[doc_id] = []
        data = {'deleted_count':count, 'document_id':doc_id}
    elif path.startswith('/api/crm/documents/'):
        doc_id = int(path.rsplit('/',1)[1]); data = {**next(d for d in docs if d['id'] == doc_id), 'requirements':requirements[doc_id]}
    elif path.startswith('/api/crm/document-requirements/'):
        rid = int(path.rsplit('/',1)[1])
        if route.request.method == 'DELETE':
            requirements[rid] = []; data = {'deleted_count':1, 'document_id':rid}
        else:
            requirements[rid][0]['status'] = route.request.post_data_json['status']
            requirements[rid][0]['completed'] = requirements[rid][0]['status'] == 'done'
            data = requirements[rid][0]
    route.fulfill(json=data)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/**', route_api)
        page.add_init_script("localStorage.setItem('crm_selected_customer_id', '1'); localStorage.setItem('crm_selected_product_id', '1');")
        page.goto(base+'/crm.html?tab=tailieu')
        page.get_by_role('button', name='Xem nội dung raw').click()
        page.locator('#documentViewer > .document-raw').filter(has_text='Raw version 2').wait_for()
        page.get_by_role('button', name='Requirement', exact=True).click()
        page.locator('#documentViewer select').select_option('done')
        page.wait_for_function('!document.querySelector("#documentViewer select").disabled')
        assert requirements[2][0]['completed']
        page.get_by_role('button', name='Đóng', exact=True).click()
        page.get_by_label('Hiện tất cả phiên bản').check()
        page.get_by_role('button', name='Danh sách requirement').nth(1).click()
        assert page.locator('#documentViewer select').input_value() == 'todo'
        page.get_by_role('button', name='Nội dung raw', exact=True).click()
        page.locator('#documentViewer > .document-raw').filter(has_text='Raw version 1').wait_for()
        page.goto(base+'/crm.html?tab=hientrang')
        page.locator('#requirementList').get_by_text('Yêu cầu: Requirement v2').wait_for()
        assert page.locator('#requirementList select').input_value() == 'done'
        page.goto(base+'/crm.html?tab=khachhang')
        page.get_by_role('button', name='Share', exact=True).click()
        page.get_by_role('dialog').get_by_label('shared-reader').check()
        page.get_by_role('button', name='Lưu chia sẻ').click()
        page.get_by_role('dialog').wait_for(state='detached')
        assert access['shared_user_ids'] == [2]
        page.get_by_role('button', name='Share', exact=True).click()
        assert page.get_by_role('dialog').get_by_label('shared-reader').is_checked()
        page.get_by_role('dialog').get_by_label('shared-reader').uncheck()
        page.get_by_role('button', name='Lưu chia sẻ').click()
        page.get_by_role('dialog').wait_for(state='detached')
        assert access['shared_user_ids'] == []
        access['is_owner'] = False
        page.reload()
        page.get_by_text('Được chia sẻ · Chỉ xem').wait_for()
        assert page.get_by_role('button', name='Share', exact=True).count() == 0
        page.goto(base+'/crm.html?tab=tailieu')
        page.get_by_role('button', name='Danh sách requirement').click()
        page.locator('#documentViewer select').wait_for()
        assert page.locator('#documentViewer select').is_disabled()
        assert not page.locator('#documentForm').is_visible()
        assert page.locator('#documentViewer .requirement-context').is_visible()
        assert 'Màn hình: TabInfo' in page.locator('#documentViewer .requirement-targets').inner_text()
        assert 'File: report.xlsx' in page.locator('#documentViewer .requirement-targets').inner_text()
        assert 'Module: Kho' in page.locator('#documentViewer .requirement-targets').inner_text()
        assert 'Business context' in page.locator('#documentViewer .requirement-context').inner_text()
        assert page.locator('#documentViewer').get_by_role('button', name='Xóa', exact=True).count() == 0
        access['is_owner'] = True
        page.reload()
        page.get_by_role('button', name='Danh sách requirement').click()
        select = page.locator('#documentViewer select')
        for value in ('progress', 'rejected', 'done', 'todo'):
            select.select_option(value)
            page.wait_for_function('!document.querySelector("#documentViewer select").disabled')
            assert requirements[2][0]['status'] == value
        page.locator('#documentViewer').get_by_text('Xem toàn bộ nội dung file').click()
        page.locator('#documentViewer details pre').filter(has_text='Raw version 2').wait_for()
        page.once('dialog', lambda dialog: dialog.dismiss())
        page.locator('#documentViewer').get_by_role('button', name='Xóa', exact=True).click()
        assert len(requirements[2]) == 1
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#documentViewer').get_by_role('button', name='Xóa', exact=True).click()
        page.wait_for_function('document.querySelector("#documentViewer")?.textContent.includes("Chưa có mục ghi nhận nào")')
        assert requirements[2] == []
        assert len(requirements[1]) == 1
        page.get_by_label('Hiện tất cả phiên bản').check()
        page.get_by_role('button', name='Danh sách requirement').nth(1).click()
        page.locator('#documentViewer select').wait_for()
        page.once('dialog', lambda dialog: dialog.accept())
        page.locator('#documentViewer').get_by_role('button', name='Xóa tất cả requirement: Memo, phiên bản 1', exact=True).click()
        page.wait_for_function('document.querySelector("#documentViewer")?.textContent.includes("Chưa có mục ghi nhận nào")')
        assert requirements[1] == []
        assert len(docs) == 2
        assert not errors, errors
        browser.close()
    print('Browser checks passed: raw versions, four statuses, context/full source, single/all deletion, version isolation, Share selection/revocation, read-only recipient UI; no JS errors.')
finally:
    server.shutdown(); server.server_close()
