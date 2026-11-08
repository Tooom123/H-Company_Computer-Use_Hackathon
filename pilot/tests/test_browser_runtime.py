"""Private auth bootstrap, URL boundaries and capture tests without a browser."""
import asyncio
from types import SimpleNamespace

import pytest

import pilot.browser_runtime as module

ORIGIN = module.ODOO_DEMO_ORIGIN


@pytest.mark.parametrize('url', [ORIGIN + '/odoo', ORIGIN + '/odoo/crm', ORIGIN + '/web#action=3',
                               ORIGIN + '/web?debug=1', ORIGIN + ':443/odoo'])
def test_application_urls_allowed(url):
    assert module.allowed_page_url(url)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'about:blank', 'javascript:alert(1)',
    'http://holo-demo.62.83.79.254.sslip.io/odoo', ORIGIN + '.evil/odoo',
    'https://user:password@holo-demo.62.83.79.254.sslip.io/odoo', ORIGIN + ':444/odoo',
    ORIGIN + '/web/login', ORIGIN + '/web/database/manager', ORIGIN + '/odoo/../web/login',
    ORIGIN + '/odoo/%252e%252e/web/login', ORIGIN + '/odoo?password=private',
    ORIGIN + '/odoo#access_token=private', ORIGIN + '\\@evil/odoo', '\n' + ORIGIN + '/odoo', None])
def test_untrusted_or_auth_urls_denied(url):
    assert not module.allowed_page_url(url)


def test_config_refuses_other_origins_and_credential_repr_is_redacted():
    creds = module.BrowserCredentials('USER-PRIVATE', 'PASSWORD-PRIVATE', 'BASIC-PRIVATE', 'SECRET-PRIVATE')
    assert 'PRIVATE' not in repr(creds)
    with pytest.raises(module.BrowserRuntimeError):
        module.BrowserConfig(origin='https://example.com')
    with pytest.raises(module.BrowserRuntimeError):
        module.BrowserConfig(start_path='/web/login')


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector
    async def fill(self, value):
        self.page.calls.append(('fill', self.selector, value))
    async def click(self):
        self.page.calls.append(('submit',))
        self.page.url = ORIGIN + '/odoo'
    async def wait_for(self, **kwargs):
        self.page.calls.append(('wait_for', self.selector))
    async def count(self):
        return int(self.page.password_visible)
    @property
    def first(self):
        return self


class FakePage:
    def __init__(self):
        self.url = 'about:blank'
        self.calls = []
        self.password_visible = False
        self.main_frame = SimpleNamespace(url=self.url)
        self.after_capture = lambda: None
    def on(self, *args):
        pass
    def locator(self, selector):
        return FakeLocator(self, selector)
    async def goto(self, url, **kwargs):
        self.calls.append(('goto', url))
        self.url = url
    async def wait_for_url(self, predicate):
        assert predicate(self.url)
    def is_closed(self):
        return False
    async def evaluate(self, script):
        self.calls.append(('settle_paint',))
    async def screenshot(self, **kwargs):
        self.calls.append(('screenshot', kwargs))
        self.after_capture()
        return b'viewport-png'


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]
        self.options = {}
    def set_default_timeout(self, _):
        pass
    def set_default_navigation_timeout(self, _):
        pass
    async def route(self, pattern, callback):
        self.route_handler = callback
    async def route_web_socket(self, pattern, callback):
        self.websocket_handler = callback
    def on(self, *args):
        pass
    async def new_cdp_session(self, page):
        async def send(*args):
            return {'targetInfo': {'targetId': 'owned-target'}}
        async def detach():
            pass
        return SimpleNamespace(send=send, detach=detach)
    async def close(self):
        self.closed = True


@pytest.fixture
def bootstrap(monkeypatch):
    import playwright.async_api
    context = FakeContext()
    async def launch(path, **kwargs):
        context.options = kwargs
        context.profile = path
        return context
    async def start():
        return SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch), stop=stop)
    async def stop():
        pass
    monkeypatch.setattr(playwright.async_api, 'async_playwright', lambda: SimpleNamespace(start=start))
    monkeypatch.setattr(module, '_unused_loopback_port', lambda: 37901)
    import httpx
    client = httpx.AsyncClient
    def request(req):
        assert str(req.url) == 'http://127.0.0.1:37901/json/version'
        return httpx.Response(200, json={'webSocketDebuggerUrl': 'ws://127.0.0.1:37901/devtools/browser/owned'})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client(transport=httpx.MockTransport(request), **kwargs))
    runtime = module.OwnedBrowserRuntime(module.BrowserConfig(), module.BrowserCredentials('app-user', 'app-secret', 'basic-user', 'basic-secret'))
    yield runtime, context
    asyncio.run(runtime._close())
    if runtime._profile:
        runtime._profile.cleanup()


def test_bootstrap_authenticates_privately_before_ready(bootstrap):
    runtime, context = bootstrap
    assert not runtime._ready
    asyncio.run(runtime._open())
    options = context.options
    assert options['headless'] is True and options['channel'] == 'chrome'
    assert options['chromium_sandbox'] is True
    assert options['http_credentials']['origin'] == ORIGIN
    assert options['service_workers'] == 'block' and options['accept_downloads'] is False
    assert 'record_har_path' not in options and 'record_video_dir' not in options
    assert '--remote-debugging-port=37901' in options['args']
    assert runtime._ready and runtime.target_id == 'owned-target'
    assert ('fill', 'input[name="password"]', 'app-secret') in context.pages[0].calls
    assert all('secret' not in call[1] for call in context.pages[0].calls if call[0] == 'goto')
    assert ('wait_for', '.o_main_navbar') in context.pages[0].calls
    assert ('wait_for', '.o_kanban_view, .o_list_view, .o_form_view') in context.pages[0].calls
    assert context.pages[0].calls[-1] == ('settle_paint',)


def test_capture_is_viewport_and_auth_pages_are_never_captured(bootstrap):
    runtime, context = bootstrap
    async def run():
        await runtime._open()
        assert await runtime._screenshot() == b'viewport-png'
        page = context.pages[0]
        assert page.calls[-1] == ('screenshot', {'type': 'png', 'full_page': False, 'animations': 'disabled'})
        count = len(page.calls)
        page.password_visible = True
        with pytest.raises(module.BrowserRuntimeError):
            await runtime._screenshot()
        assert len(page.calls) == count
    asyncio.run(run())


def test_navigation_during_capture_discards_result(bootstrap):
    runtime, context = bootstrap
    async def run():
        await runtime._open()
        context.pages[0].after_capture = lambda: setattr(context.pages[0], 'url', 'file:///private/secret')
        with pytest.raises(module.BrowserRuntimeError):
            await runtime._screenshot()
    asyncio.run(run())


def test_network_filter_blocks_external_navigation_and_latches(bootstrap):
    runtime, _ = bootstrap
    calls = []
    async def abort(reason):
        calls.append(('abort', reason))
    async def continued():
        calls.append(('continue',))
    route = SimpleNamespace(request=SimpleNamespace(url='https://example.com', is_navigation_request=lambda: True),
                            abort=abort, continue_=continued)
    asyncio.run(runtime._route(route))
    assert calls == [('abort', 'blockedbyclient')]
    assert runtime._violation.is_set()


def test_popup_is_closed_and_blocks_runtime(bootstrap):
    runtime, _ = bootstrap
    calls = []
    async def close():
        calls.append('closed')
    asyncio.run(runtime._unexpected_page(SimpleNamespace(close=close)))
    assert calls == ['closed'] and runtime._violation.is_set()


@pytest.mark.parametrize('method', ['read', 'web_read', 'web_search_read', 'name_search', 'get_views', 'has_access'])
def test_read_rpc_allowed(method):
    assert module.read_only_request_allowed('POST', ORIGIN + '/web/dataset/call_kw/product.template/' + method,
                                          {'params': {'method': method}}) == (True, '')


@pytest.mark.parametrize('method', ['create', 'write', 'unlink', 'web_save', 'action_confirm',
                                  'action_post', 'button_validate', 'custom_mutation', None, 'PRIVATE=sentinel'])
def test_write_and_unknown_rpc_blocked_with_safe_diagnostics(method):
    allowed, reason = module.read_only_request_allowed('POST', ORIGIN + '/web/dataset/call_kw',
                                                     {'params': {'method': method, 'args': ['PRIVATE=sentinel']}})
    assert allowed is False
    assert 'PRIVATE' not in reason


def test_malformed_rpc_method_fails_closed():
    assert module.read_only_request_allowed('POST', ORIGIN + '/web/dataset/call_kw',
                                           {'params': {'method': ['write']}}) == (False, 'unlisted_rpc')


def test_read_guard_blocks_write_before_network(bootstrap):
    runtime, _ = bootstrap
    runtime._ready = True
    calls = []
    async def abort(reason):
        calls.append('blocked')
    async def continued():
        pytest.fail('Write reached Odoo')
    route = SimpleNamespace(request=SimpleNamespace(url=ORIGIN + '/web/dataset/call_kw', method='POST',
        post_data_json={'params': {'method': 'write', 'args': ['PRIVATE=sentinel']}}, is_navigation_request=lambda: False),
        abort=abort, continue_=continued)
    asyncio.run(runtime._route(route))
    assert calls == ['blocked']
    assert runtime.diagnostics()['blocked_request_categories'] == ['write']
    assert 'PRIVATE' not in str(runtime.diagnostics())


def test_reset_page_uses_same_context_and_keeps_read_guard(bootstrap):
    runtime, context = bootstrap
    async def run():
        await runtime._open()
        original_page = runtime._page
        runtime._page.url = ORIGIN + '/odoo/purchase'
        await runtime._reset_page()
        assert runtime._page is original_page
        assert runtime._page.url == runtime.config.start_url
        assert runtime._ready and runtime.config.read_only
    asyncio.run(run())


def mail_payload(*items):
    return {'params': {'fetch_params': list(items)}}


def test_mail_store_allows_only_confirmed_read_handlers():
    payload = mail_payload(
        ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 7,
                         'request_list': ['activities', 'followers', 'attachments', 'suggestedRecipients']}],
        ['mail.activity', {'ids': [3, 4]}, 'request-1'])
    assert module.read_only_request_allowed('POST', ORIGIN + '/mail/store', payload) == (True, '')


@pytest.mark.parametrize('bad', [
    ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 7, 'request_list': ['activities', 'failures']}],
    ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 7}],
    ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 7, 'request_list': ['activities'], 'access_params': {'token': 'PRIVATE'}}],
    ['mail.thread', {'thread_model': 'ir.config_parameter', 'thread_id': 7, 'request_list': ['activities']}],
    ['mail.activity', {'ids': [1], 'mark_done': True}],
    ['mail.activity', {'ids': ['PRIVATE']}],
    ['mail.activity', {'ids': [True]}],
    ['mail.thread', {'thread_model': ['crm.lead'], 'thread_id': 7, 'request_list': ['activities']}],
    ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 7, 'request_list': [None]}],
    ['mail.message', {'ids': [1]}], 'init_messaging', [], None,
])
def test_mail_store_rejects_entire_batch_with_unknown_or_writing_handler(bad):
    payload = mail_payload(['mail.activity', {'ids': [1]}], bad)
    allowed, reason = module.read_only_request_allowed('POST', ORIGIN + '/mail/store', payload)
    assert allowed is False and reason == 'mail_store_scope'
    assert 'PRIVATE' not in reason


def test_direct_mail_thread_messages_route_stays_blocked():
    # Only the validated /mail/store batch has the notification-read exception.
    assert module.read_only_request_allowed('POST', ORIGIN + '/mail/thread/messages',
                                           {'params': {'thread_id': 7}})[0] is False


def message_request(**overrides):
    args = {'thread_model': 'crm.lead', 'thread_id': 7, 'fetch_params': {'limit': 30}}
    args.update(overrides)
    return ['/mail/thread/messages', args, 1]


def test_business_read_guard_allows_bounded_real_chatter_batch():
    detail = ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 7, 'access_params': {},
        'request_list': ['activities', 'attachments', 'contact_fields', 'defaultSubject', 'followers',
                         'has_pinned_messages', 'scheduledMessages', 'showSubjectInSmallComposer',
                         'suggestedRecipients', 'suggestedSubject']}]
    assert module.read_only_request_allowed('POST', ORIGIN + '/mail/store',
                                           mail_payload(message_request(), detail)) == (True, '')


@pytest.mark.parametrize('overrides', [
    {'thread_model': 'res.users'}, {'thread_model': ['crm.lead']},
    {'thread_id': True}, {'thread_id': 0}, {'thread_id': -1}, {'thread_id': '7'},
    {'fetch_params': None}, {'fetch_params': {}}, {'fetch_params': {'limit': True}},
    {'fetch_params': {'limit': 0}}, {'fetch_params': {'limit': 101}},
    {'fetch_params': {'limit': 30, 'before': 50}},
    {'fetch_params': {'limit': 30, 'domain': []}},
    {'access_params': {'token': 'PRIVATE'}}, {'arbitrary': True},
])
def test_message_notification_exception_is_tightly_bounded(overrides):
    assert module.read_only_request_allowed('POST', ORIGIN + '/mail/store',
                                           mail_payload(message_request(**overrides))) == (False, 'mail_store_scope')


def test_message_and_detail_batches_must_match_the_business_record():
    detail = ['mail.thread', {'thread_model': 'crm.lead', 'thread_id': 8, 'request_list': ['activities']}]
    assert not module.read_mail_store_allowed(mail_payload(message_request(), detail))
    assert not module.read_mail_store_allowed(mail_payload(message_request(), ['failures', {}]))
    assert not module.read_mail_store_allowed(mail_payload([['PRIVATE'], {}]))


def test_diagnostics_disclose_business_read_scope_and_navigation_side_effect(bootstrap):
    runtime, _ = bootstrap
    diagnostics = runtime.diagnostics()
    assert diagnostics['business_read_only_network_guard'] is True
    assert diagnostics['read_only_network_guard_revision'] == 'odoo20-business-read-v4'
    assert diagnostics['permitted_navigation_side_effects'] == ['message_notifications_marked_read']
    assert 'read_only_network_guard' not in diagnostics


def navigation_payload(model='purchase.order', method='action_view_picking', **changes):
    params = {'model': model, 'method': method, 'args': [[7]],
              'kwargs': {'context': {'lang': 'fr_FR', 'tz': 'Europe/Paris', 'uid': 2,
                                     'allowed_company_ids': [3], 'quotation_only': True}}}
    params.update(changes)
    return {'params': params}


@pytest.mark.parametrize('model,method', sorted(module.READ_NAVIGATION_ACTIONS))
@pytest.mark.parametrize('qualified', [False, True])
def test_reviewed_navigation_buttons_allowed_with_matching_route(model, method, qualified):
    path = '/web/dataset/call_button' + (f'/{model}/{method}' if qualified else '')
    assert module.read_only_request_allowed('POST', ORIGIN + path,
                                           navigation_payload(model, method)) == (True, '')


@pytest.mark.parametrize('model,method', [
    ('purchase.order', 'action_view_invoice'), ('sale.order', 'action_view_picking'),
    ('purchase.order', 'button_confirm'), ('sale.order', 'action_confirm'),
    ('account.move', 'action_post'), ('stock.picking', 'button_validate'),
    ('purchase.order', 'write'), ('sale.order', '_create_invoices'),
    ('purchase.order', 'action_create_invoice'), ('PRIVATE', 'PRIVATE'),
    (['purchase.order'], 'action_view_picking'), ('purchase.order', ['action_view_picking']),
])
def test_other_buttons_and_write_actions_stay_blocked(model, method):
    result = module.read_only_request_allowed('POST', ORIGIN + '/web/dataset/call_button',
                                            navigation_payload(model, method))
    assert result == (False, 'navigation_action_scope')


@pytest.mark.parametrize('path', [
    '/web/dataset/call_button/sale.order/action_view_invoice',
    '/web/dataset/call_button/purchase.order/write',
    '/web/dataset/call_button/purchase.order/action_view_picking/extra',
    '/web/dataset/call_button/purchase.order/%61ction_view_picking',
])
def test_navigation_button_route_must_match_payload(path):
    assert module.read_only_request_allowed('POST', ORIGIN + path,
                                           navigation_payload()) == (False, 'navigation_action_scope')


@pytest.mark.parametrize('changes', [
    {'args': []}, {'args': [[7], False]}, {'args': [[7, 8]]}, {'args': [[]]},
    {'args': [[True]]}, {'args': [[0]]}, {'args': [[-1]]}, {'args': [['7']]},
    {'args': [7]}, {'kwargs': None}, {'kwargs': {'invoices': [8]}},
    {'kwargs': {'context': {'active_model': 'account.move'}}},
    {'kwargs': {'context': {'active_id': 8}}}, {'kwargs': {'context': {'active_id': True}}},
    {'kwargs': {'context': {'active_ids': [8]}}},
    {'kwargs': {'context': {'allowed_company_ids': [True]}}},
    {'kwargs': {'context': {'allowed_company_ids': []}}},
    {'kwargs': {'context': {'quotation_only': 'True'}}},
    {'kwargs': {'context': {'default_move_type': 'PRIVATE'}}},
    {'kwargs': {'context': {'sudo': True}}}, {'kwargs': {'context': []}},
    {'kwargs': {'context': {'uid': True}}}, {'kwargs': {'context': {'lang': ['fr_FR']}}},
    {'kwargs': {'context': {'tz': 'x' * 101}}}, {'unknown': 'PRIVATE'},
])
def test_navigation_payload_is_bounded_and_rejects_alternate_arguments(changes):
    assert module.read_only_request_allowed('POST', ORIGIN + '/web/dataset/call_button',
        navigation_payload(**changes)) == (False, 'navigation_action_scope')


def test_navigation_exception_does_not_open_call_kw_or_write_before_network(bootstrap):
    payload = navigation_payload()
    assert module.read_only_request_allowed('POST', ORIGIN + '/web/dataset/call_kw', payload) == (False, 'unlisted_rpc')
    runtime, _ = bootstrap
    runtime._ready = True
    calls = []
    async def abort(reason):
        calls.append('blocked')
    async def continued():
        pytest.fail('Mutating button reached Odoo')
    route = SimpleNamespace(request=SimpleNamespace(url=ORIGIN + '/web/dataset/call_button/sale.order/action_confirm',
        method='POST', post_data_json=navigation_payload('sale.order', 'action_confirm'),
        is_navigation_request=lambda: False), abort=abort, continue_=continued)
    asyncio.run(runtime._route(route))
    assert calls == ['blocked']
    assert runtime.diagnostics()['blocked_request_categories'] == ['navigation_action_scope']
