import { expect, test } from '@playwright/test';

// End-to-end React flow with synthetic landmarks, not a camera/accuracy benchmark.
// No webcam permission, screen capture or Holo request is used by this fixture.
test('calibrates and validates head-only tracking without eye labels, then rejects stale landmarks', async ({ page }) => {
  test.setTimeout(90_000);
  await page.addInitScript(() => {
    const fixture = {
      target: { x: 0.5, y: 0.5 },
      faceVisible: true,
      cameraRequests: 0,
      finishCalls: 0,
      eyeLabels: [] as Array<{ x: number; y: number }>,
      statuses: [] as any[],
      headSamples: [] as any[],
      gazeSamples: [] as any[],
      setTarget(target: { x: number; y: number }) { this.target = target; },
      loseFace() { this.faceVisible = false; },
      restoreFace() { this.faceVisible = true; },
    };
    let positions: number[][] | null = null;
    let callback: ((sample: null, elapsed: number) => void) | undefined;
    let timer: ReturnType<typeof setInterval> | undefined;
    const makeMesh = () => {
      // Known synthetic head rotation is chosen by the test, never by reading
      // the rendered target or borrowing the production orientation function.
      const yaw = (fixture.target.x - 0.5) * 40 * Math.PI / 180;
      const pitch = (fixture.target.y - 0.5) * 30 * Math.PI / 180;
      const horizontal = [Math.cos(yaw), 0, -Math.sin(yaw)];
      const vertical = [-Math.sin(pitch) * Math.sin(yaw), Math.cos(pitch), -Math.sin(pitch) * Math.cos(yaw)];
      const points = Array.from({ length: 468 }, () => [320, 240, 0]);
      for (const [index, x, y] of [[33, -50, -25], [263, 50, -25], [10, 0, -80], [152, 0, 100]]) {
        points[index] = [320 + x * horizontal[0] + y * vertical[0], 240 + x * horizontal[1] + y * vertical[1], x * horizontal[2] + y * vertical[2]];
      }
      return points;
    };
    const api = {
      params: { faceMeshSolutionPath: '' },
      async begin() {
        timer = setInterval(() => {
          // Reproduce WebGazer's stale-array behavior when no face is found.
          if (fixture.faceVisible) positions = makeMesh();
          callback?.(null, performance.now());
        }, 100);
        return api;
      },
      pause() { if (timer) clearInterval(timer); return api; },
      async clearData() { fixture.eyeLabels = []; },
      clearGazeListener() { callback = undefined; return api; },
      setGazeListener(listener: typeof callback) { callback = listener; return api; },
      setRegression() { return api; },
      removeMouseEventListeners() { return api; },
      recordScreenPosition(x: number, y: number) { fixture.eyeLabels.push({ x, y }); return api; },
      getRegression() { return [{ getData: () => fixture.eyeLabels }]; },
      getTracker() { return { getPositions: () => positions }; },
      saveDataAcrossSessions() { return api; },
      showPredictionPoints() { return api; },
      showVideoPreview() { return api; },
    };
    Object.assign(window, {
      __headTrackerFixture: fixture,
      webgazer: api,
      companion: {
        async getState() { return { tracker: { state: 'off' }, settings: { selection: 'head' } }; },
        async requestCamera() { fixture.cameraRequests += 1; },
        async finishCalibration() { fixture.finishCalls += 1; },
        async stopTracker() { api.pause(); },
        reportGaze(sample: unknown) { fixture.gazeSamples.push(sample); },
        reportHead(sample: unknown) { fixture.headSamples.push(sample); },
        reportTracker(status: unknown) { fixture.statuses.push(status); },
      },
    });
  });
  await page.goto('/tracker.html#tracker');
  await expect(page.getByRole('heading', { name: 'Calibrons la tête.' })).toBeVisible();
  await page.getByRole('button', { name: /Activer la caméra et calibrer/ }).click();
  await page.getByRole('button', { name: /Calibrer la tête · 5 cibles/ }).click();
  await expect(page.getByText('TÊTE · APPRENTISSAGE', { exact: true })).toBeVisible();

  const trainingTargets = [{ x: 0.5, y: 0.5 }, { x: 0.18, y: 0.22 }, { x: 0.82, y: 0.22 }, { x: 0.82, y: 0.78 }, { x: 0.18, y: 0.78 }];
  for (let index = 0; index < trainingTargets.length; index += 1) {
    await page.evaluate(target => (window as any).__headTrackerFixture.setTarget(target), trainingTargets[index]);
    await page.getByRole('button', { name: `Cible ${index + 1}`, exact: true }).click();
    if (index < trainingTargets.length - 1) await expect(page.getByRole('button', { name: `Cible ${index + 2}`, exact: true })).toBeEnabled({ timeout: 8_000 });
  }
  await expect(page.getByText('TÊTE · VALIDATION INDÉPENDANTE', { exact: true })).toBeVisible({ timeout: 8_000 });
  const validationTargets = [{ x: 0.3, y: 0.32 }, { x: 0.7, y: 0.68 }, { x: 0.7, y: 0.32 }, { x: 0.3, y: 0.68 }];
  for (let index = 0; index < validationTargets.length; index += 1) {
    await page.evaluate(target => (window as any).__headTrackerFixture.setTarget(target), validationTargets[index]);
    await page.getByRole('button', { name: `Cible ${index + 1}`, exact: true }).click();
    if (index < validationTargets.length - 1) await expect(page.getByRole('button', { name: `Cible ${index + 2}`, exact: true })).toBeEnabled({ timeout: 8_000 });
  }
  await expect(page.getByRole('heading', { name: 'Votre zone est prête.' })).toBeVisible({ timeout: 8_000 });
  const summary = await page.evaluate(() => {
    const fixture = (window as any).__headTrackerFixture;
    return { status: fixture.statuses.at(-1), eyeLabels: fixture.eyeLabels.length, cameraRequests: fixture.cameraRequests, finishCalls: fixture.finishCalls };
  });
  expect(summary).toMatchObject({ status: { state: 'calibrating', headCalibrated: true, gazeCalibrated: false }, eyeLabels: 0, cameraRequests: 1, finishCalls: 0 });
  expect(Number.isFinite(summary.status.headCalibrationErrorPx)).toBe(true);
  expect(summary.status.calibrationErrorPx).toBeUndefined();

  await page.getByRole('button', { name: /Commencer le suivi/ }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__headTrackerFixture.headSamples.at(-1)?.point != null)).toBe(true);
  const tracking = await page.evaluate(() => {
    const fixture = (window as any).__headTrackerFixture;
    return { status: fixture.statuses.at(-1), eyeLabels: fixture.eyeLabels.length, finishCalls: fixture.finishCalls, gaze: fixture.gazeSamples };
  });
  expect(tracking).toMatchObject({ status: { state: 'tracking', headCalibrated: true, gazeCalibrated: false }, eyeLabels: 0, finishCalls: 1 });
  expect(tracking.gaze.length).toBeGreaterThan(0);
  expect(tracking.gaze.every((sample: unknown) => sample === null)).toBe(true);
  await expect(page.locator('.tracker-screen')).toHaveCount(0);

  await page.evaluate(() => (window as any).__headTrackerFixture.loseFace());
  await expect.poll(() => page.evaluate(() => (window as any).__headTrackerFixture.headSamples.at(-1))).toBeNull();
  expect(await page.evaluate(() => (window as any).__headTrackerFixture.statuses.at(-1).state)).toBe('lost');
  await page.evaluate(() => (window as any).__headTrackerFixture.restoreFace());
  await expect.poll(() => page.evaluate(() => (window as any).__headTrackerFixture.headSamples.at(-1)?.point != null)).toBe(true);
  expect(await page.evaluate(() => (window as any).__headTrackerFixture.statuses.at(-1).state)).toBe('tracking');
});
