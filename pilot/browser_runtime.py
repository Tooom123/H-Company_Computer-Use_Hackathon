"""Own one headless Odoo browser; authenticate before exposing it to H.

Playwright stays alive on a private event-loop thread to service HTTP Basic
challenges. No HAR, video, trace or credential-bearing exception is exported.
This isolates browser state, not the operating system: use a dedicated container
for a stronger filesystem/network sandbox. The runtime deliberately permits one
tab and one application origin, and fails closed after an unexpected navigation.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

ODOO_DEMO_ORIGIN = 'https://holo-demo.62.83.79.254.sslip.io'


class BrowserRuntimeError(RuntimeError):
    """Public error text must never contain credentials, URLs or driver details."""


@dataclass(frozen=True)
class BrowserCredentials:
    odoo_username: str = field(repr=False)
    odoo_password: str = field(repr=False)
    basic_username: str = field(repr=False)
    basic_password: str = field(repr=False)

    def __post_init__(self):
        if not all(isinstance(x, str) and x for x in (
            self.odoo_username, self.odoo_password, self.basic_username, self.basic_password
        )):
            raise BrowserRuntimeError('Four non-empty browser credentials are required.')


@dataclass(frozen=True)
class BrowserConfig:
    origin: str = ODOO_DEMO_ORIGIN
    start_path: str = '/odoo/crm'
    width: int = 1280
    height: int = 832
    startup_timeout_s: float = 60
    operation_timeout_s: float = 15
    channel: str = 'chrome'
    read_only: bool = True

    def __post_init__(self):
        if self.origin != ODOO_DEMO_ORIGIN:
            raise BrowserRuntimeError('Only the configured public Odoo demo origin is allowed.')
        if not isinstance(self.start_path, str) or not self.start_path.startswith('/'):
            raise BrowserRuntimeError('The browser start path must be an application path.')
        if not allowed_page_url(self.origin + self.start_path, self.origin):
            raise BrowserRuntimeError('The browser start path is outside the application.')
        if not (640 <= self.width <= 2560 and 480 <= self.height <= 1600):
            raise BrowserRuntimeError('Browser viewport dimensions are outside the supported range.')
        if not (1 <= self.operation_timeout_s <= 60 and 5 <= self.startup_timeout_s <= 120):
            raise BrowserRuntimeError('Browser timeouts are outside the supported range.')
        if self.channel not in {'chrome', 'chromium'}:
            raise BrowserRuntimeError('Only Chrome or Playwright Chromium is supported.')
        if not isinstance(self.read_only, bool):
            raise BrowserRuntimeError('The browser read-only setting must be a boolean.')

    @property
    def start_url(self) -> str:
        return self.origin + self.start_path


def allowed_network_url(url: str, origin: str = ODOO_DEMO_ORIGIN) -> bool:
    """Exact HTTPS origin only; reject credentials, malformed/encoded authorities."""
    try:
        if not isinstance(url, str) or any(ord(c) < 32 for c in url) or '\\' in url:
            return False
        parsed, expected = urlsplit(url), urlsplit(origin)
        return (parsed.scheme == 'https' and parsed.hostname == expected.hostname
                and parsed.port in (None, 443) and parsed.username is None
                and parsed.password is None and '%' not in parsed.netloc)
    except (ValueError, TypeError):
        return False


def allowed_page_url(url: str, origin: str = ODOO_DEMO_ORIGIN) -> bool:
    """Only Odoo application pages; never expose authentication/database screens."""
    if not allowed_network_url(url, origin):
        return False
    parsed = urlsplit(url)
    path = unquote(unquote(parsed.path)).rstrip('/')
    if any(part in {'.', '..'} for part in path.split('/')) or '\\' in path:
        return False
    if path != '/web' and not (path == '/odoo' or path.startswith('/odoo/')):
        return False
    # A credential accidentally placed in a URL must not reach metadata/traces.
    from urllib.parse import parse_qsl
    sensitive = {'password', 'passwd', 'token', 'api_key', 'apikey', 'login', 'secret', 'access_token'}
    return not any(k.lower() in sensitive for k, _ in parse_qsl(parsed.query) + parse_qsl(parsed.fragment))


def _unused_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


# These are conventional read/view RPCs, not a substitute for database ACLs.
# Unknown RPCs fail closed; diagnostics contain names only, never their arguments.
READ_RPC_METHODS = frozenset({
    'read', 'web_read', 'search', 'search_read', 'web_search_read', 'search_count',
    'name_search', 'name_get', 'fields_get', 'fields_view_get', 'get_views', 'get_view',
    'load_views', 'get_metadata', 'read_group', 'web_read_group',
    'search_panel_select_range', 'search_panel_select_multi_range',
    'has_group', 'has_access', 'check_access_rights', 'check_access_rule', 'check_access',
})
READ_POST_PATHS = frozenset({'/web/action/load', '/web/session/get_session_info', '/web/webclient/version_info'})
READ_MAIL_THREAD_MODELS = frozenset({'crm.lead', 'res.partner', 'sale.order', 'purchase.order', 'account.move',
    'stock.picking', 'mrp.production', 'mrp.bom', 'project.project', 'project.task', 'product.template', 'product.product'})
READ_MAIL_THREAD_FIELDS = frozenset({'activities', 'attachments', 'followers', 'contact_fields', 'defaultSubject',
    'display_name', 'pinned_messages', 'has_pinned_messages', 'scheduledMessages', 'suggestedRecipients',
    'showSubjectInSmallComposer', 'suggestedSubject'})


def read_mail_store_allowed(payload) -> bool:
    """Odoo 20 store handlers, checked against addons/mail/controllers/webclient.py.

    Business records stay read-only. One explicit navigation side effect is
    permitted: /mail/thread/messages marks the fictitious account's message
    notifications read (Odoo's set_message_done). Its models, record IDs and
    fetch limits are bounded below. This is not an absolute database read-only
    policy. In particular `failures` can delete notifications and stays blocked.
    Reject the WHOLE unknown batch; never silently remove response fields.
    """
    params = payload.get('params') if isinstance(payload, dict) else None
    batch = params.get('fetch_params') if isinstance(params, dict) else None
    if not isinstance(batch, list) or not 0 < len(batch) <= 50:
        return False
    message_threads = set()
    detail_threads = set()
    for item in batch:
        if not isinstance(item, list) or len(item) not in (2, 3):
            return False  # these handlers require explicit parameters
        name, args = item[:2]
        if not isinstance(name, str) or not isinstance(args, dict):
            return False
        if len(item) == 3 and (not isinstance(item[2], (str, int)) or isinstance(item[2], bool)):
            return False
        if name == 'mail.activity':
            ids = args.get('ids')
            if (set(args) != {'ids'} or not isinstance(ids, list) or len(ids) > 1000
                    or any(type(i) is not int or i <= 0 for i in ids)):
                return False
        elif name in {'mail.thread', '/mail/thread/messages'}:
            model, record_id = args.get('thread_model'), args.get('thread_id')
            if (not isinstance(model, str) or model not in READ_MAIL_THREAD_MODELS
                    or type(record_id) is not int or record_id <= 0
                    or args.get('access_params') not in (None, {})):
                return False
            if name == '/mail/thread/messages':
                if set(args) - {'thread_model', 'thread_id', 'fetch_params', 'access_params'}:
                    return False
                fetch = args.get('fetch_params')
                if (not isinstance(fetch, dict) or set(fetch) != {'limit'}
                        or type(fetch['limit']) is not int or not 1 <= fetch['limit'] <= 100):
                    return False
                message_threads.add((model, record_id))
                continue
            if set(args) - {'thread_model', 'thread_id', 'request_list', 'access_params'}:
                return False
            requests = args.get('request_list')
            if (not isinstance(requests, list)
                    or any(not isinstance(field, str) or field not in READ_MAIL_THREAD_FIELDS for field in requests)):
                return False
            detail_threads.add((model, record_id))
        else:
            return False
    # A mixed initial form load must reference the same business record(s).
    return not message_threads or not detail_threads or message_threads <= detail_threads


def read_only_request_allowed(method: str, url: str, payload) -> tuple[bool, str]:
    """Return decision plus a safe bounded diagnostic category (never arguments)."""
    if method in {'GET', 'HEAD', 'OPTIONS'}:
        return True, ''
    if method != 'POST':
        return False, 'http_method'
    path = urlsplit(url).path.rstrip('/')
    if path in READ_POST_PATHS:
        return True, ''
    if path == '/mail/store':
        return (True, '') if read_mail_store_allowed(payload) else (False, 'mail_store_scope')
    if path == '/web/dataset/call_kw' or path.startswith('/web/dataset/call_kw/'):
        params = payload.get('params') if isinstance(payload, dict) else None
        rpc_method = params.get('method') if isinstance(params, dict) else None
        if isinstance(rpc_method, str) and rpc_method in READ_RPC_METHODS:
            return True, ''
        # Report only known method identifiers, not attacker-controlled text.
        write_names = {'create', 'write', 'unlink', 'web_save', 'action_confirm', 'action_post',
                       'button_validate', 'action_cancel', 'onchange'}
        return False, rpc_method if isinstance(rpc_method, str) and rpc_method in write_names else 'unlisted_rpc'
    return False, 'unlisted_post_route'


class OwnedBrowserRuntime:
    """Synchronous facade around one private Playwright event loop.

    `start` does not call H. `screenshot` returns only the authenticated viewport.
    Closing this object never closes another browser or a user's Chrome profile.
    A fresh runtime is required after a blocked navigation or failed bootstrap.
    """

    def __init__(self, config: BrowserConfig, credentials: BrowserCredentials):
        self.config = config
        self._credentials = credentials
        self._lock = threading.RLock()
        self._loop = None
        self._thread = None
        self._context = None
        self._playwright = None
        self._page = None
        self._profile = None
        self._target_id = None
        self._browser_endpoint = None
        self._ready = False
        self._closed = False
        self._violation = threading.Event()
        self._blocked_requests: list[str] = []
        self.debugging_port: int | None = None

    def _submit(self, coroutine, timeout: float | None = None):
        if self._loop is None or not self._loop.is_running():
            coroutine.close()
            raise BrowserRuntimeError('The isolated browser is not running.')
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout or self.config.operation_timeout_s + 5)
        except Exception:
            future.cancel()
            raise BrowserRuntimeError('The isolated browser operation failed or timed out.') from None

    def start(self) -> None:
        with self._lock:
            if self._closed or self._violation.is_set():
                raise BrowserRuntimeError('The isolated browser must be recreated.')
            if self._ready:
                self.assert_safe()
                return
            if self._thread is not None:
                raise BrowserRuntimeError('The isolated browser initialization is incomplete.')
            self._loop = asyncio.new_event_loop()
            started = threading.Event()

            def serve():
                asyncio.set_event_loop(self._loop)
                self._loop.call_soon(started.set)
                self._loop.run_forever()
                self._loop.close()

            self._thread = threading.Thread(target=serve, name='hcompanion-owned-browser', daemon=True)
            self._thread.start()
            if not started.wait(5):
                raise BrowserRuntimeError('The isolated browser worker did not start.')
            try:
                self._submit(self._open(), self.config.startup_timeout_s + 10)
            except Exception:
                with contextlib.suppress(Exception):
                    self.close()
                raise BrowserRuntimeError('Browser bootstrap failed; no H session was started.') from None

    async def _open(self):
        # Import lazily: unit tests and server startup do not require a browser install.
        from playwright.async_api import async_playwright

        self._profile = tempfile.TemporaryDirectory(prefix='hcompanion-browser-')
        os.chmod(self._profile.name, 0o700)
        self.debugging_port = _unused_loopback_port()
        self._playwright = await async_playwright().start()
        c = self._credentials
        # Remove debugging/tracing env settings and all unrelated application secrets.
        browser_env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL') if k in os.environ}
        self._context = await self._playwright.chromium.launch_persistent_context(
            self._profile.name, headless=True, channel=self.config.channel, chromium_sandbox=True,
            viewport={'width': self.config.width, 'height': self.config.height},
            device_scale_factor=1, accept_downloads=False, service_workers='block',
            http_credentials={'username': c.basic_username, 'password': c.basic_password,
                              'origin': self.config.origin},
            args=[f'--remote-debugging-port={self.debugging_port}', '--remote-debugging-address=127.0.0.1'],
            env=browser_env, timeout=self.config.startup_timeout_s * 1000,
        )
        self._context.set_default_timeout(self.config.operation_timeout_s * 1000)
        self._context.set_default_navigation_timeout(self.config.operation_timeout_s * 1000)
        await self._context.route('**/*', self._route)
        # Odoo's live bus is not needed by these tests. Block all websockets, also
        # preventing connections that are outside Playwright HTTP routing.
        if not hasattr(self._context, 'route_web_socket'):
            raise BrowserRuntimeError('Playwright with websocket routing support is required.')
        await self._context.route_web_socket('**/*', lambda ws: ws.close())
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        for other in pages[1:]:
            await other.close()
        self._context.on('page', self._unexpected_page)
        self._page.on('download', lambda download: download.cancel())
        await self._page.goto(self.config.origin + '/web/login', wait_until='domcontentloaded')
        await self._page.locator('input[name="login"]').fill(c.odoo_username)
        await self._page.locator('input[name="password"]').fill(c.odoo_password)
        await self._page.locator('button[type="submit"]').click()
        await self._page.wait_for_url(lambda url: allowed_page_url(str(url), self.config.origin))
        await self._page.goto(self.config.start_url, wait_until='domcontentloaded')
        await self._settle_app()
        session = await self._context.new_cdp_session(self._page)
        try:
            target = await session.send('Target.getTargetInfo')
            self._target_id = target['targetInfo']['targetId']
        finally:
            await session.detach()
        # Remember the exact CDP browser websocket identity. A later port reuse
        # must never attach H to a different browser process.
        import httpx
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            response = await client.get(f'http://127.0.0.1:{self.debugging_port}/json/version')
            response.raise_for_status()
            self._browser_endpoint = response.json()['webSocketDebuggerUrl']
        self._page.on('framenavigated', self._navigated)
        self._ready = True
        await self._assert_safe()

    async def _route(self, route):
        request = route.request
        if allowed_network_url(request.url, self.config.origin):
            if self._ready and self.config.read_only:
                try:
                    payload = request.post_data_json if request.method == 'POST' else None
                except Exception:
                    payload = None
                allowed, diagnostic = read_only_request_allowed(request.method, request.url, payload)
                if not allowed:
                    if len(self._blocked_requests) < 50:
                        self._blocked_requests.append(diagnostic)
                    await route.abort('blockedbyclient')
                    return
            await route.continue_()
        else:
            if request.is_navigation_request():
                self._violation.set()
            await route.abort('blockedbyclient')

    async def _unexpected_page(self, page):
        self._violation.set()
        with contextlib.suppress(Exception):
            await page.close()

    def _navigated(self, frame):
        if frame == self._page.main_frame and not allowed_page_url(frame.url, self.config.origin):
            self._violation.set()

    async def _assert_safe(self):
        if (not self._ready or self._closed or self._violation.is_set()
                or self._context is None or self._page is None or self._page.is_closed()
                or self._context.pages != [self._page]
                or not allowed_page_url(self._page.url, self.config.origin)):
            raise BrowserRuntimeError('Browser observation or action blocked by the application boundary.')
        if await self._page.locator('input[type="password"]:visible').count():
            self._violation.set()
            raise BrowserRuntimeError('Browser observation blocked on an authentication screen.')

    async def _settle_app(self):
        # o_web_client exists while the screen is still white. Require the
        # navigation, content container and an actual view before handing to H.
        await self._page.locator('.o_main_navbar').wait_for(state='visible')
        await self._page.locator('.o_action_manager .o_content').first.wait_for(state='visible')
        await self._page.locator('.o_kanban_view, .o_list_view, .o_form_view').first.wait_for(state='visible')
        await self._page.locator('.o_loading_indicator').wait_for(state='hidden')
        await self._page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')

    def assert_safe(self) -> None:
        self._submit(self._assert_safe())

    def assert_owned_endpoint(self) -> None:
        """No fallback launch and no attachment to a substituted CDP listener."""
        self.assert_safe()
        import httpx
        try:
            with httpx.Client(trust_env=False, timeout=3) as client:
                response = client.get(f'http://127.0.0.1:{self.debugging_port}/json/version')
                response.raise_for_status()
                actual = response.json().get('webSocketDebuggerUrl')
            if not self._browser_endpoint or actual != self._browser_endpoint:
                raise ValueError('different browser')
        except Exception:
            raise BrowserRuntimeError('The owned browser debugging endpoint is unavailable.') from None

    @property
    def target_id(self) -> str:
        if not self._target_id:
            raise BrowserRuntimeError('The owned browser page has not been initialized.')
        return self._target_id

    async def _screenshot(self) -> bytes:
        await self._assert_safe()
        data = await self._page.screenshot(type='png', full_page=False, animations='disabled')
        await self._assert_safe()
        return data

    def screenshot(self) -> bytes:
        return self._submit(self._screenshot())

    async def _reset_page(self):
        await self._assert_safe()
        await self._page.goto(self.config.start_url, wait_until='domcontentloaded')
        await self._settle_app()
        await self._assert_safe()

    def reset_page(self) -> None:
        """Prepare a consistent start page; preserves auth, never resets between H turns."""
        self.start()
        self._submit(self._reset_page())

    def diagnostics(self) -> dict:
        return {'transport': 'browser', 'start_url': self.config.start_url,
                'viewport': {'width': self.config.width, 'height': self.config.height},
                'business_read_only_network_guard': self.config.read_only,
                'read_only_network_guard_revision': 'odoo20-business-read-v3',
                'permitted_navigation_side_effects': ['message_notifications_marked_read'] if self.config.read_only else [],
                'blocked_request_categories': list(self._blocked_requests)}

    async def _close(self):
        self._ready = False
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._violation.set()
            error = False
            try:
                if self._loop is not None and self._loop.is_running():
                    self._submit(self._close(), 15)
            except Exception:
                error = True
            finally:
                if self._loop is not None and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread is not None:
                    self._thread.join(timeout=5)
                if self._profile is not None and self._context is None:
                    self._profile.cleanup()
                    self._profile = None
            if error:
                raise BrowserRuntimeError('The owned browser did not confirm shutdown.') from None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.close()
