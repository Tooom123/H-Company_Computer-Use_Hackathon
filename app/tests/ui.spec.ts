import { expect, test, type Page } from "@playwright/test";

// Browser-only fixtures. No camera permission, screen capture or H API is used.
async function installFixture(page: Page, keyConfigured = true) {
  await page.addInitScript(
    ({ keyConfigured }) => {
      type FixtureWindow = Window & {
        __labFixture: {
          complete: (outcome: "completed" | "failed") => void;
          moveCandidate: () => void;
          failCapture: () => void;
          requestFrame: string | null;
          requestModel: string | null;
          requests: Array<{ frameId: string; model: string; detailDataUrl?: string; globalDataUrl?: string }>;
          deferConfigurations: () => void;
          releaseConfiguration: () => void;
          failConfigurations: () => void;
          useFullSizeCapture: () => void;
          configurationCalls: Array<Record<string, unknown>>;
          captureSettings: Array<Record<string, unknown>>;
          observationOptions: Record<string, unknown> | null;
          finishObservation: () => void;
          selectedObservations: string[];
          annotationCalls: Array<{ frameId: string; label: string }>;
          trackerStartCalls: number;
          deferCalibration: () => void;
          setTrackerState: (state: "tracking" | "error") => void;
        };
      };
      const fixtureWindow = window as unknown as FixtureWindow;
      let state = {
        tracker: { state: "off" },
        candidate: { x: 100, y: 150, width: 400, height: 300 },
        sent: null,
        busy: null,
        settings: {
          selection: "gaze",
          roiWidth: 800,
          roiHeight: 600,
          includeGlobal: true,
          overlay: true,
        },
        observation: { status: "idle", sampleCount: 0, startedAt: null, durationSeconds: 30, intervalMs: 1000 },
      } as any;
      let latestFrame: any = null;
      let counter = 0;
      let rejectCapture = false;
      let configurationDeferred = false;
      let configurationRejected = false;
      let fullSizeCapture = false;
      let calibrationDeferred = false;
      const configurationResolvers: Array<() => void> = [];
      let resolveInference: ((value: any) => void) | null = null;
      let observationFrames: any[] = [];
      const listeners = new Set<(value: any) => void>();
      const emit = () =>
        listeners.forEach((listener) => listener(structuredClone(state)));
      const makeImage = (width: number, height: number) => {
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d")!;
        context.fillStyle = "#f0f3f7";
        context.fillRect(0, 0, width, height);
        context.fillStyle = "#223c43";
        context.fillRect(0, 0, width, 56);
        context.fillStyle = "#ffffff";
        context.font = "20px sans-serif";
        context.fillText(
          "Logiciel de démonstration · Données simulées",
          20,
          35,
        );
        context.fillStyle = "#ffffff";
        context.fillRect(20, 80, width - 40, Math.max(70, height - 105));
        context.fillStyle = "#334b50";
        context.font = "18px sans-serif";
        context.fillText("Opportunité : Acme Démo", 42, 120);
        context.fillStyle = "#14795f";
        context.fillRect(42, 150, Math.min(190, width - 80), 38);
        context.fillStyle = "#ffffff";
        context.font = "14px sans-serif";
        context.fillText("Planifier une activité", 55, 175);
        return {
          dataUrl: canvas.toDataURL("image/png"),
          width,
          height,
          sha256: "a".repeat(64),
        };
      };
      const complete = (status: "completed" | "failed" | "cancelled") => {
        if (!resolveInference) throw new Error("No fixture request is pending");
        state.busy = null;
        emit();
        resolveInference({
          frameId: fixtureWindow.__labFixture.requestFrame,
          requestId: "simulated-request",
          startedAt: "2026-11-07T10:00:00.000Z",
          latencyMs: status === "completed" ? 1245 : 100,
          usage: {
            inputTokens: status === "completed" ? 1024 : null,
            outputTokens: status === "completed" ? 40 : null,
            totalTokens: status === "completed" ? 1064 : null,
            cachedInputTokens: status === "completed" ? 128 : null,
          },
          text:
            status === "completed"
              ? "Réponse de fixture. Aucune requête Holo réelle."
              : "",
          model: fixtureWindow.__labFixture.requestModel ?? "holo4-27b",
          status,
          error:
            status === "failed" ? "Service de fixture indisponible" : undefined,
          simulated: true,
        });
        resolveInference = null;
      };
      fixtureWindow.__labFixture = {
        complete,
        moveCandidate: () => {
          state.candidate = { x: 250, y: 220, width: 400, height: 300 };
          emit();
        },
        failCapture: () => {
          rejectCapture = true;
          latestFrame = null;
        },
        requestFrame: null,
        requestModel: null,
        requests: [],
        deferConfigurations: () => { configurationDeferred = true; },
        releaseConfiguration: () => { configurationResolvers.shift()?.(); },
        failConfigurations: () => { configurationRejected = true; },
        useFullSizeCapture: () => { fullSizeCapture = true; },
        configurationCalls: [],
        captureSettings: [],
        observationOptions: null,
        selectedObservations: [],
        annotationCalls: [],
        trackerStartCalls: 0,
        deferCalibration: () => { calibrationDeferred = true; },
        setTrackerState: next => { state.tracker = { state: next }; emit(); },
        finishObservation: () => {
          observationFrames = [1, 2].map(index => ({
            frameId: `observed-fixture-${index}`,
            capturedAt: `2026-11-07T10:00:0${index}.000Z`,
            sourceWidth: 2880, sourceHeight: 1800,
            cropRect: { x: index * 100, y: 200, width: state.settings.roiWidth, height: state.settings.roiHeight },
            requestedRegion: { width: state.settings.roiWidth, height: state.settings.roiHeight },
            regionDisposition: "crop", screenBounds: { x: 0, y: 0, width: 1440, height: 900 },
            selection: state.settings.selection, fallbackReason: null,
            selectedWindow: { id: 7, appName: "Odoo · fixture", bounds: { x: 0, y: 0, width: 1200, height: 800 } },
            reference: makeImage(960, 600), detail: makeImage(state.settings.roiWidth, state.settings.roiHeight),
            global: state.settings.includeGlobal ? makeImage(480, 300) : null,
            preparationMs: 34, gazeAgeMs: 22, simulated: true, captureMethod: "explicit-browser-fixture", annotation: null,
          }));
          state.observation = { ...state.observation, status: "stopped", sampleCount: 2, stopReason: "duration" };
          emit();
        },
      };
      // Match main's frequent state broadcasts, including while an IPC write is pending.
      window.setInterval(emit, 100);
      window.companion = {
        getStatus: async () => ({
          platform: "fixture",
          model: "holo4-27b",
          models: ["holo4-27b", "holo4-35b-a3b", "holo3-1-35b-a3b"],
          apiKeyConfigured: keyConfigured,
          captureAvailable: true,
          observationShortcutAvailable: true,
          display: {
            id: 1,
            bounds: { x: 0, y: 0, width: 1440, height: 900 },
            scaleFactor: 2,
          },
        }),
        getState: async () => structuredClone(state),
        configure: async (settings) => {
          fixtureWindow.__labFixture.configurationCalls.push(structuredClone(settings));
          if (configurationDeferred) await new Promise<void>(resolve => configurationResolvers.push(resolve));
          if (configurationRejected) throw new Error("Réglage de fixture refusé");
          state.settings = settings;
          emit();
        },
        startTracker: async () => {
          fixtureWindow.__labFixture.trackerStartCalls += 1;
          state.tracker = { state: calibrationDeferred ? "calibrating" : "tracking" };
          emit();
        },
        stopTracker: async () => {
          state.tracker = { state: "off" };
          emit();
        },
        capture: async () => {
          fixtureWindow.__labFixture.captureSettings.push(structuredClone(state.settings));
          if (rejectCapture) throw new Error("Capture de fixture refusée");
          latestFrame = {
            frameId: `simulated-frame-${++counter}`,
            capturedAt: "2026-11-07T10:00:00.000Z",
            sourceWidth: 2880,
            sourceHeight: 1800,
            cropRect: { x: 200, y: 300, width: state.settings.roiWidth, height: state.settings.roiHeight },
            requestedRegion: { width: state.settings.roiWidth, height: state.settings.roiHeight },
            regionDisposition: "crop",
            screenBounds: { x: 0, y: 0, width: 1440, height: 900 },
            selection: state.settings.selection,
            fallbackReason: null,
            detail: makeImage(state.settings.roiWidth, state.settings.roiHeight),
            global: state.settings.includeGlobal ? makeImage(480, 300) : null,
            preparationMs: 34,
            gazeAgeMs: 22,
            simulated: true,
            captureMethod: "explicit-browser-fixture",
          };
          if (fullSizeCapture) Object.assign(latestFrame, {
            sourceWidth: 1470, sourceHeight: 956,
            requestedRegion: {width: 1600, height: 1200},
            regionDisposition: "full-size",
            cropRect: {x: 0, y: 0, width: 1470, height: 956},
            detail: makeImage(1470, 956), global: null,
          });
          return structuredClone(latestFrame);
        },
        analyze: async (input) => {
          fixtureWindow.__labFixture.requestFrame = input.frameId;
          fixtureWindow.__labFixture.requestModel = input.model ?? "holo4-27b";
          fixtureWindow.__labFixture.requests.push({
            frameId: input.frameId,
            model: input.model ?? "holo4-27b",
            detailDataUrl: latestFrame?.detail.dataUrl,
            globalDataUrl: latestFrame?.global?.dataUrl,
          });
          state.sent = {
            frameId: input.frameId,
            rect: { x: 100, y: 150, width: 400, height: 300 },
          };
          state.busy = "inference";
          emit();
          return new Promise((resolve) => {
            resolveInference = resolve;
          });
        },
        cancel: async () => {
          complete("cancelled");
        },
        onState: (callback) => {
          listeners.add(callback);
          return () => {
            listeners.delete(callback);
          };
        },
        reportGaze: () => {},
        reportTracker: () => {},
        finishCalibration: async () => {},
        requestCamera: async () => {},
        startObservation: async (options) => {
          fixtureWindow.__labFixture.observationOptions = { ...options, settings: structuredClone(state.settings) };
          observationFrames = [];
          latestFrame = null;
          state.observation = { ...state.observation, status: "running", sampleCount: 0, startedAt: "2026-11-07T10:00:00.000Z", durationSeconds: options.durationSeconds };
          emit();
        },
        stopObservation: async () => { fixtureWindow.__labFixture.finishObservation(); },
        listObservations: async () => structuredClone(observationFrames),
        selectObservation: async (frameId) => {
          const selected = observationFrames.find(frame => frame.frameId === frameId);
          if (!selected) throw new Error("Capture de fixture introuvable");
          latestFrame = selected;
          fixtureWindow.__labFixture.selectedObservations.push(frameId);
          return structuredClone(selected);
        },
        annotateObservation: async (input) => {
          fixtureWindow.__labFixture.annotationCalls.push(input);
          observationFrames = observationFrames.map(frame => frame.frameId === input.frameId ? {...frame, annotation: input.label} : frame);
        },
        clearObservations: async () => {
          observationFrames = [];
          latestFrame = null;
          state.observation = { ...state.observation, status: "idle", sampleCount: 0 };
          emit();
        },
      };
    },
    { keyConfigured },
  );
}

async function finishFixture(page: Page, outcome: "completed" | "failed") {
  await page.evaluate(
    (outcome) => (window as any).__labFixture.complete(outcome),
    outcome,
  );
}

test("starts a local hidden-panel observation with applied dimensions and locks competing actions", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  await expect(page.getByRole("button", {name: "Activer le regard et calibrer"})).toBeEnabled();
  await expect(page.getByRole("button", {name: "Observer et masquer le panneau"})).toHaveCount(0);
  await page.getByRole("radio", {name: "Curseur", exact: true}).check();
  await page.getByRole("combobox", {name: "Cadre de la région"}).selectOption("window");
  await page.getByRole("spinbutton", {name: "Largeur de la région"}).fill("896");
  await page.getByRole("spinbutton", {name: "Hauteur de la région"}).fill("704");
  await page.getByRole("combobox", {name: "Durée de l’essai"}).selectOption("15");
  await page.getByRole("button", {name: "Observer et masquer le panneau"}).click();
  await expect(page.getByRole("button", {name: "Arrêter l’observation"})).toBeEnabled();
  await expect(page.getByRole("button", {name: "Capturer dans 3 s"})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Envoyer à Holo"})).toBeDisabled();
  await expect(page.getByRole("combobox", {name: "Cadre de la région"})).toBeDisabled();
  const start = await page.evaluate(() => (window as any).__labFixture.observationOptions);
  expect(start).toMatchObject({durationSeconds: 15, showOverlay: false, settings: {selection: "cursor", roiWidth: 896, roiHeight: 704, regionScope: "window"}});
  expect(await page.evaluate(() => (window as any).__labFixture.requests)).toHaveLength(0);
  expect(await page.evaluate(() => (window as any).__labFixture.trackerStartCalls)).toBe(0);
});

test("offers gaze calibration in the observation card and waits for an explicit observation start", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  const card = page.getByRole("region", {name: "Essai continu local"});
  await expect(card.getByLabel("Mode et suivi de l’essai")).toHaveText("Mode : Regard · Caméra arrêtée");
  await expect(card.getByText("La calibration est nécessaire après chaque lancement.", {exact: false})).toBeVisible();
  await page.evaluate(() => (window as any).__labFixture.deferCalibration());
  await card.getByRole("button", {name: "Activer le regard et calibrer"}).click();
  await expect(card.getByRole("button", {name: "Calibration en cours…"})).toBeDisabled();
  expect(await page.evaluate(() => (window as any).__labFixture.trackerStartCalls)).toBe(1);
  expect(await page.evaluate(() => (window as any).__labFixture.observationOptions)).toBeNull();
  await page.evaluate(() => (window as any).__labFixture.setTrackerState("tracking"));
  await expect(card.getByRole("button", {name: "Observer et masquer le panneau"})).toBeEnabled();
  expect(await page.evaluate(() => (window as any).__labFixture.observationOptions)).toBeNull();
  await card.getByRole("button", {name: "Observer et masquer le panneau"}).click();
  expect(await page.evaluate(() => (window as any).__labFixture.observationOptions)).toMatchObject({settings: {selection: "gaze"}});
});

test("offers a calibration retry in the observation card after a tracker error", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  await page.evaluate(() => (window as any).__labFixture.setTrackerState("error"));
  const card = page.getByRole("region", {name: "Essai continu local"});
  await expect(card.getByRole("button", {name: "Activer le regard et calibrer"})).toBeEnabled();
  await card.getByRole("button", {name: "Activer le regard et calibrer"}).click();
  await expect(card.getByRole("button", {name: "Observer et masquer le panneau"})).toBeEnabled();
  expect(await page.evaluate(() => (window as any).__labFixture.observationOptions)).toBeNull();
});

test("reviews and annotates stopped observations without mixing them with Holo success or sending the reference", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  await page.getByRole("button", {name: "Activer la caméra et calibrer"}).click();
  await page.getByRole("button", {name: "Observer et masquer le panneau"}).click();
  await page.getByRole("button", {name: "Arrêter l’observation"}).click();
  const review = page.getByRole("region", {name: "Essai continu local"});
  await expect(review.getByRole("img", {name: "Bureau de référence de l’essai"})).toBeVisible();
  await page.getByRole("button", {name: "Arrêter la caméra"}).click();
  await expect(review.locator(".review-count")).toHaveText("Capture 1 / 2");
  await expect(review.locator(".review-summary")).toContainText("0 / 0 captures jugées");
  await review.getByRole("button", {name: "Impossible à juger"}).click();
  await expect(review.locator(".review-summary")).toContainText("0 / 0 captures jugées · 1 incertaine(s) · 1 non annotée(s)");
  await review.getByRole("button", {name: "Capture suivante"}).click();
  await expect(review.locator(".review-count")).toHaveText("Capture 2 / 2");
  await review.getByRole("button", {name: "Cible présente", exact: true}).click();
  await expect(review.locator(".review-summary")).toContainText("1 / 1 captures jugées (100 %) · 1 incertaine(s)");
  expect(await page.evaluate(() => (window as any).__labFixture.annotationCalls)).toEqual([
    {frameId: "observed-fixture-1", label: "uncertain"}, {frameId: "observed-fixture-2", label: "present"},
  ]);
  expect(await page.evaluate(() => (window as any).__labFixture.requests)).toHaveLength(0);
  await page.getByRole("button", {name: "Envoyer à Holo"}).click();
  expect(await page.evaluate(() => (window as any).__labFixture.requestFrame)).toBe("observed-fixture-2");
  const request = await page.evaluate(() => (window as any).__labFixture.requests[0]);
  expect(Object.keys(request).sort()).toEqual(["detailDataUrl", "frameId", "globalDataUrl", "model"]);
  await finishFixture(page, "completed");
  await review.getByRole("button", {name: "Effacer cet essai local"}).click();
  await expect(review.getByRole("img")).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Envoyer à Holo"})).toBeDisabled();
});

test("captures the latest two dimensions after deferred setting writes and stale broadcasts", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByRole("img")).toHaveCount(2);
  await page.evaluate(() => (window as any).__labFixture.deferConfigurations());
  const width = page.getByRole("spinbutton", { name: "Largeur de la région" });
  const height = page.getByRole("spinbutton", { name: "Hauteur de la région" });
  await width.fill("896");
  await height.fill("704");
  await height.press("Tab");
  // This one click must queue the capture behind both pending writes, not be dropped.
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByRole("img")).toHaveCount(0);
  await expect(page.locator(".applied-region")).toContainText("800 × 600 px");
  await page.waitForTimeout(250);
  await expect(width).toHaveValue("896");
  await expect(height).toHaveValue("704");
  expect(await page.evaluate(() => (window as any).__labFixture.captureSettings.length)).toBe(1);

  // The first capture used one configure; now width, height and the capture flush are serial.
  for (const callCount of [2, 3, 4]) {
    await expect.poll(() => page.evaluate(() => (window as any).__labFixture.configurationCalls.length)).toBe(callCount);
    await page.evaluate(() => (window as any).__labFixture.releaseConfiguration());
  }
  await expect(page.getByRole("img")).toHaveCount(2);
  await expect(page.locator(".applied-region")).toContainText("896 × 704 px");
  await expect(page.locator(".requested-region")).toContainText("896 × 704 px");
  const captured = await page.evaluate(() => (window as any).__labFixture.captureSettings);
  expect(captured).toHaveLength(2);
  expect(captured[1]).toMatchObject({roiWidth: 896, roiHeight: 704});
});

test("discards the old observation and prevents capture when settings cannot be persisted", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  await expect(page.locator(".applied-region")).toContainText("800 × 600 px");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByRole("img")).toHaveCount(2);
  await page.evaluate(() => (window as any).__labFixture.failConfigurations());
  await page.getByRole("spinbutton", { name: "Largeur de la région" }).fill("960");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByRole("alert")).toContainText("Réglage de fixture refusé");
  await expect(page.getByRole("img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__labFixture.captureSettings.length)).toBe(1);
});

test("distinguishes an oversized region from a tracking fallback", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  await page.evaluate(() => (window as any).__labFixture.useFullSizeCapture());
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByText("La région demandée couvre tout l’écran", {exact: true})).toBeVisible();
  await expect(page.getByText("Repli plein écran", {exact: true})).toHaveCount(0);
  await expect(page.locator(".requested-region")).toContainText("1 600 × 1 200 px");
  await expect(page.locator(".requested-region")).toContainText("surface conservée : 100 %");
  await expect(page.getByRole("img")).toHaveCount(1);
});

test("blocks sending without an API key and shows no fabricated usage", async ({
  page,
}) => {
  await installFixture(page, false);
  await page.goto("/");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(
    page.getByRole("img", { name: "Région détaillée", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Envoyer à Holo" }),
  ).toBeDisabled();
  await expect(
    page.getByText("Préparée · locale", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric-card strong")).toHaveText([
    "—",
    "—",
    "—",
    "—",
  ]);
  await expect(page.getByText("SIMULÉ", { exact: true })).toBeVisible();
});

test("keeps the payload fixed as the candidate moves and displays measured usage after response", async ({
  page,
}, testInfo) => {
  await installFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  const crop = page.getByRole("img", { name: "Région détaillée", exact: true });
  const exactPayload = await crop.getAttribute("src");
  await page.getByRole("button", { name: "Envoyer à Holo" }).click();
  await expect(page.getByText("Envoyée à Holo", { exact: true })).toBeVisible();
  await expect(page.locator(".metric-card strong")).toHaveText([
    "—",
    "—",
    "—",
    "—",
  ]);
  await page.evaluate(() => (window as any).__labFixture.moveCandidate());
  await expect(crop).toHaveAttribute("src", exactPayload!);
  await expect(
    page.getByRole("button", { name: "Capturer dans 3 s" }),
  ).toBeDisabled();
  await finishFixture(page, "completed");
  await expect(page.locator(".metric-card strong")).toHaveText([
    "1 024",
    "40",
    "1 064",
    "1 245 ms",
  ]);
  await expect(
    page.getByText("Réponse de fixture. Aucune requête Holo réelle."),
  ).toBeVisible();
  expect(
    await page.evaluate(() => (window as any).__labFixture.requestFrame),
  ).toBe("simulated-frame-1");
  await page.screenshot({
    path: testInfo.outputPath("dashboard-fixture.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(
    page.getByText("Préparée · locale", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric-card strong")).toHaveText([
    "—",
    "—",
    "—",
    "—",
  ]);
  await expect(
    page.getByText("Réponse de fixture. Aucune requête Holo réelle."),
  ).toHaveCount(0);
});

test("retains unknown usage for failed and cancelled requests", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await page.getByRole("button", { name: "Envoyer à Holo" }).click();
  await finishFixture(page, "failed");
  await expect(page.getByRole("alert")).toContainText(
    "Service de fixture indisponible",
  );
  await expect(page.locator(".metric-card strong")).toHaveText([
    "—",
    "—",
    "—",
    "100 ms",
  ]);
  await expect(page.getByText(/Usage inconnu/)).toBeVisible();
  await page.getByRole("button", { name: "Envoyer à Holo" }).click();
  await page.getByRole("button", { name: "Annuler", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Requête annulée" }),
  ).toBeVisible();
  await expect(page.locator(".metric-card strong")).toHaveText([
    "—",
    "—",
    "—",
    "100 ms",
  ]);
});

test("replays the same image with the selected model and labels prior measurements", async ({ page }) => {
  await installFixture(page);
  await page.goto("/");
  const model = page.getByRole("combobox", { name: "Modèle Holo" });
  await expect(model).toHaveValue("holo4-27b");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  const crop = page.getByRole("img", { name: "Région détaillée", exact: true });
  const original = await crop.getAttribute("src");
  await page.getByRole("button", { name: "Envoyer à Holo" }).click();
  await expect(model).toBeDisabled();
  await finishFixture(page, "completed");
  await expect(page.locator(".measured-model")).toContainText("Modèle mesuré : holo4-27b");

  await model.selectOption("holo3-1-35b-a3b");
  await expect(crop).toHaveAttribute("src", original!);
  await expect(page.locator(".measured-model")).toContainText("holo4-27b");
  await expect(page.locator(".measured-model")).toContainText("Ces mesures précèdent le changement de modèle.");
  await expect(page.locator(".response-model")).toContainText("holo4-27b");
  await page.getByRole("button", { name: "Envoyer à Holo" }).click();
  const requests = await page.evaluate(() => (window as any).__labFixture.requests);
  expect(requests.map((request: { model: string }) => request.model)).toEqual(["holo4-27b", "holo3-1-35b-a3b"]);
  expect(requests[1].frameId).toBe(requests[0].frameId);
  expect(requests[1].detailDataUrl).toBe(requests[0].detailDataUrl);
  expect(requests[1].globalDataUrl).toBe(requests[0].globalDataUrl);
  await finishFixture(page, "completed");
  await expect(page.locator(".measured-model")).toContainText("Modèle mesuré : holo3-1-35b-a3b");
  await expect(page.locator(".response-model")).toContainText("holo3-1-35b-a3b");
  await expect(page.getByText("Ces mesures précèdent le changement de modèle.")).toHaveCount(0);
});

test("invalidates the previous image when a subsequent capture fails", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByRole("img")).toHaveCount(2);
  await page.evaluate(() => (window as any).__labFixture.failCapture());
  await page.getByRole("button", { name: "Capturer dans 3 s" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Capture de fixture refusée",
  );
  await expect(page.getByRole("img")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Envoyer à Holo" }),
  ).toBeDisabled();
});

test("shows the desktop requirement without an injected bridge", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ouvrez H-Companion dans Electron." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Envoyer à Holo" }),
  ).toHaveCount(0);
});

test("overlay preserves the sent rectangle when the candidate moves", async ({
  page,
}) => {
  await installFixture(page);
  await page.goto("/#overlay");
  const candidate = page.locator(".screen-zone-candidate");
  const sent = page.locator(".screen-zone-sent");
  await expect(candidate).toHaveCSS("left", "100px");
  await page.evaluate(() => {
    void window.companion.analyze({
      frameId: "simulated-overlay-frame",
      prompt: "Fixture",
    });
  });
  await expect(sent).toHaveCSS("left", "100px");
  await page.evaluate(() => (window as any).__labFixture.moveCandidate());
  await expect(candidate).toHaveCSS("left", "250px");
  await expect(sent).toHaveCSS("left", "100px");
  await expect(sent).toContainText("simulated-overlay-frame");
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgba(0, 0, 0, 0)",
  );
  await expect(page.locator(".screen-overlay")).toHaveCSS(
    "pointer-events",
    "none",
  );
});
