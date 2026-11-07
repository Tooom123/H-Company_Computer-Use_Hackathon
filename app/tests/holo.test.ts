import { describe, expect, it } from 'vitest';
import { buildRequest, parseUsage, runHolo } from '../electron/holo.mjs';

const frame = {
  frameId: 'frozen-1', cropRect: { x: 300, y: 200, width: 800, height: 600 },
  detail: { dataUrl: 'data:image/png;base64,EXACT_CROP' },
  global: { dataUrl: 'data:image/png;base64,EXACT_GLOBAL' },
};

describe('Holo payload and measured usage', () => {
  it('sends exactly the encoded preview buffers in their labelled order', () => {
    const request = buildRequest(frame, 'Aide-moi.', 'test-model');
    const content = request.messages[1].content;
    if (!Array.isArray(content)) throw new Error('Expected image content');
    const images = content.filter(item => item.type === 'image_url');
    expect(images.map((item: { image_url: { url: string } }) => item.image_url.url)).toEqual([frame.global.dataUrl, frame.detail.dataUrl]);
    expect(JSON.stringify(request)).not.toContain('tools');
  });
  it('does not silently add a global image when disabled', () => {
    const request = buildRequest({ ...frame, global: null }, 'Aide-moi.', 'test-model');
    const content = request.messages[1].content;
    if (!Array.isArray(content)) throw new Error('Expected image content');
    expect(content.filter(item => item.type === 'image_url')).toHaveLength(1);
  });
  it('never sends the local observation reference image or window metadata', () => {
    const request = buildRequest({ ...frame, reference: { dataUrl: 'LOCAL_REFERENCE_ONLY' },
      selectedWindow: { id: 123, appName: 'LOCAL_APP_NAME', bounds: { x: 0, y: 0, width: 1000, height: 800 } },
    }, 'Aide-moi.', 'test-model');
    expect(JSON.stringify(request)).not.toContain('LOCAL_REFERENCE_ONLY');
    expect(JSON.stringify(request)).not.toContain('LOCAL_APP_NAME');
  });
  it('keeps missing usage unknown and accepts reported zero cache', () => {
    expect(parseUsage(undefined)).toEqual({ inputTokens: null, outputTokens: null, totalTokens: null, cachedInputTokens: null });
    expect(parseUsage({ prompt_tokens: 120, completion_tokens: -2, total_tokens: '123', prompt_tokens_details: { cached_tokens: 0 } })).toEqual({ inputTokens: 120, outputTokens: null, totalTokens: null, cachedInputTokens: 0 });
  });
  it('links a response to its frozen frame and preserves actual usage', async () => {
    let sentBody = '';
    const result = await runHolo({ frame, prompt: 'Que vois-tu ?', model: 'test-model', apiKey: 'test-only', signal: new AbortController().signal,
      fetchImpl: async (_url, options) => {
        sentBody = String(options?.body);
        return new Response(JSON.stringify({ id: 'req-7', choices: [{ message: { content: 'Une configuration.' } }], usage: { prompt_tokens: 200, completion_tokens: 20, total_tokens: 220 } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      },
    });
    expect(result).toMatchObject({ frameId: 'frozen-1', requestId: 'req-7', status: 'completed', usage: { inputTokens: 200, outputTokens: 20, totalTokens: 220, cachedInputTokens: null } });
    expect(result.latencyMs).toBeGreaterThanOrEqual(0);
    expect(sentBody).toContain(frame.detail.dataUrl);
    expect(sentBody).not.toContain('test-only');
  });
  it('retains failed calls with unknown cost instead of fabricating zero tokens', async () => {
    const result = await runHolo({ frame, prompt: 'Test', model: 'test', apiKey: 'test-only', signal: new AbortController().signal,
      fetchImpl: async () => new Response(JSON.stringify({ error: { message: 'Rate limit' } }), { status: 429 }),
    });
    expect(result.status).toBe('failed');
    expect(result.error).toContain('429');
    expect(result.usage.totalTokens).toBeNull();
  });
  it('marks cancellation and timeout distinctly without a successful result', async () => {
    for (const [reason, expected] of [[new DOMException('Stop', 'AbortError'), 'cancelled'], [new DOMException('Timeout', 'TimeoutError'), 'failed']] as const) {
      const controller = new AbortController(); controller.abort(reason);
      const result = await runHolo({ frame, prompt: 'Test', model: 'test', apiKey: 'test-only', signal: controller.signal, fetchImpl: async () => { throw reason; } });
      expect(result.status).toBe(expected);
      expect(result.usage.totalTokens).toBeNull();
    }
  });
});
