import { performance } from 'node:perf_hooks';

export function buildRequest(frame, prompt, model) {
  /** @type {Array<{type: 'text', text: string} | {type: 'image_url', image_url: {url: string}}>} */
  const content = [{ type: 'text', text: '<observation>\n' }];
  if (frame.global) {
    content.push({ type: 'text', text: 'Image 1 : aperçu global pour le contexte uniquement.' });
    content.push({ type: 'image_url', image_url: { url: frame.global.dataUrl } });
  }
  content.push({ type: 'text', text: `Image ${frame.global ? 2 : 1} : région détaillée, source x=${frame.cropRect.x}, y=${frame.cropRect.y}, largeur=${frame.cropRect.width}, hauteur=${frame.cropRect.height}.` });
  content.push({ type: 'image_url', image_url: { url: frame.detail.dataUrl } });
  content.push({ type: 'text', text: `\n</observation>\n${prompt}` });
  return {
    model, temperature: 0, max_tokens: 1024, reasoning_effort: 'none', stream: false,
    messages: [
      { role: 'system', content: 'Tu aides à comprendre un logiciel à partir des images fournies. Réponds en français. Décris ce qui est visible et les limites du contexte. Aucune action ne sera exécutée. Si tu proposes des coordonnées, nomme explicitement l’image et utilise son repère normalisé de 0 à 1000. N’affirme pas avoir cliqué ni vérifié un changement.' },
      { role: 'user', content },
    ],
  };
}

export function parseUsage(usage) {
  const token = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
  return {
    inputTokens: token(usage?.prompt_tokens), outputTokens: token(usage?.completion_tokens),
    totalTokens: token(usage?.total_tokens), cachedInputTokens: token(usage?.prompt_tokens_details?.cached_tokens),
  };
}

// The immutable encoded image displayed by the panel is used without recapture,
// resizing, recompression or additional screenshots in this request.
export async function runHolo({ frame, prompt, model, apiKey, signal, fetchImpl = fetch }) {
  const body = JSON.stringify(buildRequest(frame, prompt, model));
  const startedAt = new Date().toISOString();
  const start = performance.now();
  let requestId = null;
  let usage = parseUsage(null);
  try {
    const response = await fetchImpl('https://api.hcompany.ai/v1/chat/completions', {
      method: 'POST', headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' }, body, signal,
    });
    requestId = response.headers.get('x-request-id');
    const data = await response.json();
    usage = parseUsage(data?.usage);
    if (!response.ok) throw new Error(`Holo HTTP ${response.status}${typeof data?.error?.message === 'string' ? ` : ${data.error.message.slice(0, 350)}` : ''}`);
    requestId ??= typeof data.id === 'string' ? data.id : null;
    const message = data?.choices?.[0]?.message;
    if (!message) throw new Error('Réponse Holo sans message exploitable.');
    const text = typeof message.content === 'string' ? message.content : 'Réponse reçue sans texte ; aucune action exécutée.';
    return { frameId: frame.frameId, requestId, startedAt, latencyMs: performance.now() - start, usage, text, model, status: 'completed', simulated: false };
  } catch (error) {
    const cancelled = signal?.aborted && signal.reason?.name !== 'TimeoutError';
    return {
      frameId: frame.frameId, requestId, startedAt, latencyMs: performance.now() - start,
      usage, text: '', model, status: cancelled ? 'cancelled' : 'failed', simulated: false,
      error: signal?.aborted ? (cancelled ? 'Requête interrompue localement ; facturation serveur éventuellement engagée.' : 'Délai de réponse dépassé (60 s). Usage inconnu si non retourné.') : String(error?.message ?? error),
    };
  }
}
