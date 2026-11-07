import { expect, test, type Page } from '@playwright/test';

async function mockPilot(page: Page, failFeedback = false) {
  await page.addInitScript(({ failFeedback }) => {
    const calls: { method: string; path: string; body?: unknown }[] = [];
    // This mock represents durable backend state, independent of a renderer reload.
    let snapshot: Record<string, unknown> | null = JSON.parse(localStorage.getItem('vp-test-backend') || 'null');
    const persist = () => localStorage.setItem('vp-test-backend', JSON.stringify(snapshot));
    const scenarios = [
      { id: '01', title: 'Lire le prix et le stock', prompt: 'Retrouve le gingembre et lis son prix et son stock.', procedure_id: 'odoo_inventory_read_product', requires_reference: false },
      { id: '02', title: 'Comparer les stocks', prompt: 'Quel produit a le moins de stock ?', procedure_id: 'odoo_inventory_compare_stock', requires_reference: false },
    ];
    Object.defineProperty(window, '__vpCalls', { value: calls });
    Object.defineProperty(window, 'voicePilot', { value: {
      request: async (method: string, path: string, body?: Record<string, unknown>) => {
        calls.push({ method, path, body });
        if (path === '/pilot/status') return { model: 'holo4-test', simulated: true, busy: false, transcription: { provider: 'test', ready: false } };
        if (path === '/pilot/scenarios') return scenarios;
        if (path === '/pilot/episodes' && method === 'POST') {
          snapshot = { session_id: 'test-episode', state: 'awaiting_approval', simulated: true, request: { goal: body?.goal }, report_ready: false,
            plan: { objective: 'Lire la fiche sans rien modifier', allowed_actions: ['Lire les valeurs'], forbidden_actions: ['Modifier le stock'] },
            pilot: { scenario_id: body?.scenario_id, export_status: 'simulated' } };
          persist(); return snapshot;
        }
        if (path.endsWith('/feedback') && method === 'POST') {
          if (failFeedback) throw new Error('Écriture du feedback indisponible');
          snapshot = { ...snapshot, pilot: { scenario_id: '01', feedback: body, export_status: 'simulated' } };
          persist(); return snapshot;
        }
        if (path === '/pilot/episodes/test-episode') return snapshot;
        throw new Error(`Unexpected request ${method} ${path}`);
      },
      approve: async (id: string) => {
        calls.push({ method: 'APPROVE', path: id });
        snapshot = { ...snapshot, state: 'resolved', report_ready: true,
          declared: { outcome: 'done', summary: 'Prix et stock lus.' }, verification: { satisfied: true, observed: 'Valeurs contrôlées.' },
          report: { timings: { approved_at: '2026-11-07T20:00:00Z', finished_at: '2026-11-07T20:00:26Z' } } };
        persist(); return snapshot;
      },
      stop: async () => { throw new Error('Unexpected stop'); },
      requestMicrophone: async () => { throw new Error('Test must not use the microphone'); },
      uploadAudio: async () => { throw new Error('Test must not upload audio'); },
    } });
  }, { failFeedback });
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
