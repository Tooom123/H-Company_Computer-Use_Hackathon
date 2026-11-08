import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

const code = await readFile(new URL('../billing.js', import.meta.url), 'utf8');
const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');

for (const origin of ['https://hcompanion.help', 'https://www.hcompanion.help', 'http://localhost:5173']) {
  test(`demo never contacts a payment or local API from ${origin}`, async () => {
    let requests = 0;
    const handlers = [];
    const message = { textContent: '', classList: { add() {}, remove() {} }, setAttribute() {} };
    const location = { href: `${origin}/?checkout=success&plan=pro`, search: '?checkout=success&plan=pro' };
    // Keep legacy buttons in the fixture: accidentally restoring the checkout handler must fail this test.
    const buttons = ['pro', 'fixpack'].map(plan => ({ dataset: { plan }, textContent: plan,
      addEventListener(_event, handler) { handlers.push(handler); } }));
    vm.runInNewContext(code, {
      URLSearchParams, location,
      document: { getElementById: () => message, querySelectorAll: () => buttons },
      fetch: async () => { requests++; throw new Error('offline'); },
      requestAnimationFrame: callback => callback(),
    });
    for (const click of handlers) await click();
    assert.equal(requests, 0, 'the public demo must never send a checkout request');
    assert.equal(location.href, `${origin}/?checkout=success&plan=pro`, 'query parameters cannot authorize a redirect');
    assert.match(message.textContent, /payments are not available/);
    assert.doesNotMatch(message.textContent, /payment received|welcome to|checkout cancelled/i);
  });
}

test('pricing links work without JavaScript and lead to the existing walkthrough', () => {
  const pricing = html.match(/<section class="section" id="pricing"[\s\S]*?<\/section>/)[0];
  const links = [...pricing.matchAll(/<a class="btn[^\"]*" href="([^"]+)"/g)];
  assert.equal(links.length, 3);
  assert.ok(links.every(link => link[1] === '#how'));
  assert.match(html, /id="how"/);
  assert.match(pricing, /Illustrative plans and prices/);
  assert.doesNotMatch(pricing, /data-plan|Subscribe with Stripe|Buy with Stripe|Verified results, every time|Unlimited/);
});

test('an old cancellation link is a demo notice, never a financial claim', () => {
  const message = { textContent: '', classList: { add() {} } };
  vm.runInNewContext(code, { URLSearchParams, location: { search: '?checkout=cancel' },
    document: { getElementById: () => message } });
  assert.match(message.textContent, /H Companion demo/);
  assert.doesNotMatch(message.textContent, /cancelled|no charge|received/i);
});
