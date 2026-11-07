import { expect, test, type Page } from '@playwright/test';

async function mockPilot(page: Page, failFeedback = false, options: { longPlan?: boolean; deferReport?: boolean } = {}) {
  await page.addInitScript(({ failFeedback, options }) => {
    const calls: { method: string; path: string; body?: unknown }[] = [];
    // This mock represents durable backend state, independent of a renderer reload.
    let snapshot: Record<string, unknown> | null = JSON.parse(localStorage.getItem('vp-test-backend') || 'null');
    const persist = () => localStorage.setItem('vp-test-backend', JSON.stringify(snapshot));
    const scenarios = [
      { id: '01', title: 'Lire le prix et le stock', prompt: 'Retrouve le gingembre et lis son prix et son stock.', procedure_id: 'odoo_inventory_read_product', requires_reference: false },
      { id: '02', title: 'Comparer les stocks', prompt: 'Quel produit a le moins de stock ?', procedure_id: 'odoo_inventory_compare_stock', requires_reference: false },
    ];
    Object.defineProperty(window, '__vpCalls', { value: calls });
    Object.defineProperty(window, '__vpReportReady', { value: () => { snapshot = { ...snapshot, report_ready: true }; persist(); } });
    Object.defineProperty(window, '__vpSetState', { value: (state: string, reportReady: boolean) => { snapshot = { ...snapshot, state, report_ready: reportReady }; persist(); } });
    Object.defineProperty(window, 'voicePilot', { value: {
      request: async (method: string, path: string, body?: Record<string, unknown>) => {
        calls.push({ method, path, body });
        if (path === '/pilot/status') return { model: 'holo4-test', simulated: true, busy: false, transcription: { provider: 'test', ready: false } };
        if (path === '/pilot/scenarios') return scenarios;
        if (path === '/pilot/episodes' && method === 'POST') {
          snapshot = { session_id: snapshot ? crypto.randomUUID() : 'test-episode', state: 'awaiting_approval', simulated: true, request: { goal: body?.goal }, report_ready: false,
            plan: { objective: 'Lire la fiche sans rien modifier', allowed_actions: options.longPlan ? Array.from({ length: 30 }, (_, index) => `Étape ${index + 1} : lire les informations de cette fiche sans modifier les données.`) : ['Lire les valeurs'], forbidden_actions: ['Modifier le stock'] },
            pilot: { scenario_id: body?.scenario_id, export_status: 'simulated' } };
          persist(); return snapshot;
        }
        if (path.endsWith('/feedback') && method === 'POST') {
          if (failFeedback) throw new Error('Écriture du feedback indisponible');
          snapshot = { ...snapshot, pilot: { scenario_id: '01', feedback: body, export_status: 'simulated' } };
          persist(); return snapshot;
        }
        if (path === `/pilot/episodes/${snapshot?.session_id}`) return snapshot;
        throw new Error(`Unexpected request ${method} ${path}`);
      },
      approve: async (id: string) => {
        calls.push({ method: 'APPROVE', path: id });
        snapshot = { ...snapshot, state: 'resolved', report_ready: !options.deferReport,
          declared: { outcome: 'done', summary: 'Prix et stock lus.' }, verification: { satisfied: true, observed: 'Valeurs contrôlées.' },
          report: { timings: { approved_at: '2026-11-07T20:00:00Z', finished_at: '2026-11-07T20:00:26Z' } } };
        persist(); return snapshot;
      },
      stop: async () => { throw new Error('Unexpected stop'); },
      requestMicrophone: async () => { throw new Error('Test must not use the microphone'); },
      uploadAudio: async () => { throw new Error('Test must not upload audio'); },
    } });
  }, { failFeedback, options });
}

test('requires approval and saves unknown human labels separately before unlocking the next scenario', async ({ page }) => {
  await mockPilot(page);
  await page.goto('/#voice');
  await page.getByLabel('Votre demande · transcription à relire').fill('Montre le prix et le stock du gingembre.');
  await page.getByRole('button', { name: 'Préparer le plan', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approuver et observer Odoo' })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __vpCalls: { method: string }[] }).__vpCalls.filter(call => call.method === 'APPROVE').length)).toBe(0);
  await expect(page.getByRole('button', { name: '02 Comparer les stocks' })).toBeDisabled();
  await page.getByRole('button', { name: 'Approuver et observer Odoo' }).click();
  await expect(page.getByText('Valeurs contrôlées.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Valeurs contrôlées.')).toBeVisible();
  await expect(page.getByRole('button', { name: '02 Comparer les stocks' })).toBeDisabled();
  await expect(page.getByText('Le recadrage du Vision Lab n’est pas activé pour ces essais.', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Selon vous, la tâche est…')).toHaveValue('unknown');
  await expect(page.getByLabel('L’aide était-elle utile ?')).toHaveValue('unknown');
  await page.getByLabel('Votre retour · transcription à relire').fill('Je n’ai pas pu voir, utilité non évaluée.');
  await page.getByRole('button', { name: 'Enregistrer mon retour' }).click();
  await expect(page.getByText('Retour enregistré avec cet essai.', { exact: true })).toBeVisible();
  const feedback = await page.evaluate(() => (window as unknown as { __vpCalls: { path: string; body?: unknown }[] }).__vpCalls.find(call => call.path.endsWith('/feedback'))?.body);
  expect(feedback).toMatchObject({ task_success_user: 'unknown', useful: 'unknown', allow_training: false, comment: 'Je n’ai pas pu voir, utilité non évaluée.' });
  await page.getByRole('button', { name: 'Préparer le scénario 02' }).click();
  await expect(page.getByRole('heading', { name: 'Comparer les stocks', exact: true })).toBeVisible();
  await expect(page.getByLabel('Votre demande · transcription à relire')).toHaveValue('');
});

test('a failed feedback write does not claim saved or unlock another scenario', async ({ page }) => {
  await mockPilot(page, true);
  await page.goto('/#voice');
  await page.getByLabel('Votre demande · transcription à relire').fill('Lis le prix.');
  await page.getByRole('button', { name: 'Préparer le plan', exact: true }).click();
  await page.getByRole('button', { name: 'Approuver et observer Odoo' }).click();
  await page.getByRole('button', { name: 'Enregistrer mon retour' }).click();
  await expect(page.getByRole('alert')).toContainText('Écriture du feedback indisponible');
  await expect(page.getByText('Retour enregistré avec cet essai.', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '02 Comparer les stocks' })).toBeDisabled();
});

test('brings a ready answer into view once, preserves feedback scrolling and restores the question', async ({ page }) => {
  await page.setViewportSize({ width: 840, height: 650 });
  await mockPilot(page, false, { longPlan: true, deferReport: true });
  await page.goto('/#voice');
  await page.getByLabel('Votre demande · transcription à relire').fill('Lis le prix et le stock.');
  await page.getByRole('button', { name: 'Préparer le plan', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Actions interdites' })).toBeVisible();
  await page.getByRole('button', { name: 'Approuver et observer Odoo' }).click();
  await expect(page.getByText('Préparation du compte rendu… La réponse apparaîtra ici.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Réponse de H-Companion' })).toHaveCount(0);
  await page.evaluate(() => (window as unknown as { __vpReportReady: () => void }).__vpReportReady());
  const answer = page.getByRole('heading', { name: 'Réponse de H-Companion' });
  await expect(answer).toBeInViewport();
  await expect.poll(async () => (await answer.boundingBox())?.y ?? Infinity).toBeLessThan(100);
  await expect(page.getByText('Prix et stock lus.', { exact: true })).toBeInViewport();
  await expect(page.getByText('Vous dictez votre demande ; la réponse s’affiche par écrit, sans lecture audio.')).toBeVisible();

  const pollCount = () => page.evaluate(() => (window as unknown as { __vpCalls: { method: string; path: string }[] }).__vpCalls.filter(call => call.method === 'GET' && call.path === '/pilot/episodes/test-episode').length);
  const feedback = page.getByLabel('Votre retour · transcription à relire');
  await feedback.fill('Je lis puis je donne mon retour.');
  const feedbackScroll = await page.evaluate(() => window.scrollY);
  const beforeWriting = await pollCount();
  await expect.poll(pollCount).toBeGreaterThanOrEqual(beforeWriting + 2);
  await expect(feedback).toBeFocused();
  await expect(feedback).toHaveValue('Je lis puis je donne mon retour.');
  expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(feedbackScroll, 0);

  await feedback.blur();
  await page.evaluate(() => window.scrollTo(0, 0));
  const beforeBrowsing = await pollCount();
  await expect.poll(pollCount).toBeGreaterThan(beforeBrowsing);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);

  await page.reload();
  await expect(answer).toBeInViewport();
  await expect.poll(async () => (await answer.boundingBox())?.y ?? Infinity).toBeLessThan(100);
  await page.getByRole('button', { name: 'Enregistrer mon retour' }).click();
  await expect(page.getByText('Retour enregistré avec cet essai.', { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.reload();
  await expect(page.getByText('Retour enregistré avec cet essai.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.history.scrollRestoration)).toBe('manual');
  await expect(answer).toBeInViewport({ ratio: 1 });
  const afterSavedReload = await pollCount();
  await expect.poll(pollCount).toBeGreaterThan(afterSavedReload);
  await expect(answer).toBeInViewport({ ratio: 1 });
  await page.getByRole('button', { name: 'Préparer le scénario 02' }).click();
  await expect(page.getByRole('heading', { name: 'Posez votre question' })).toBeInViewport();
});

test('retries a stopped restored episode without labels or automatic approval, but never skips an active episode', async ({ page }) => {
  await mockPilot(page);
  await page.goto('/#voice');
  await page.getByLabel('Votre demande · transcription à relire').fill('Vérifie le prix.');
  await page.getByRole('button', { name: 'Préparer le plan', exact: true }).click();
  const retry = page.getByRole('button', { name: 'Retenter sans ajouter de feedback' });
  await expect(retry).toHaveCount(0);
  const setState = (state: string, reportReady: boolean) => page.evaluate(({ state, reportReady }) => {
    (window as unknown as { __vpSetState: (state: string, ready: boolean) => void }).__vpSetState(state, reportReady);
  }, { state, reportReady });
  await setState('running', false);
  await expect(page.getByRole('heading', { name: 'H-Companion agit', exact: true })).toBeVisible();
  await expect(retry).toHaveCount(0);
  await setState('stopping', false);
  await expect(page.getByRole('heading', { name: 'Arrêt demandé', exact: true })).toBeVisible();
  await expect(retry).toHaveCount(0);

  await setState('stopped', false);
  await page.reload();
  await expect(retry).toBeEnabled();
  await expect(page.getByText('Cet essai reste conservé sans feedback ni nouveau consentement d’entraînement.', { exact: false })).toBeVisible();
  await retry.click();
  await expect(page.getByLabel('Votre demande · transcription à relire')).toHaveValue('');
  const calls = () => page.evaluate(() => (window as unknown as { __vpCalls: { method: string; path: string }[] }).__vpCalls);
  expect((await calls()).filter(call => call.method === 'APPROVE' || (call.method === 'POST' && call.path.endsWith('/feedback')))).toEqual([]);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('vp-test-backend') || '{}').state)).toBe('stopped');

  await page.getByLabel('Votre demande · transcription à relire').fill('Retrouve la bonne fiche et vérifie son prix.');
  await expect(page.getByRole('button', { name: 'Approuver et observer Odoo' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Préparer le plan', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approuver et observer Odoo' })).toBeVisible();
  expect((await calls()).filter(call => call.method === 'APPROVE')).toEqual([]);
  await page.getByRole('button', { name: 'Approuver et observer Odoo' }).click();
  expect((await calls()).filter(call => call.method === 'APPROVE')).toHaveLength(1);
  expect((await calls()).filter(call => call.method === 'POST' && call.path.endsWith('/feedback'))).toEqual([]);
});
