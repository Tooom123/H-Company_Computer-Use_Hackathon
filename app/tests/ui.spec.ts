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
      } as any;
      let latestFrame: any = null;
      let counter = 0;
      let rejectCapture = false;
      let resolveInference: ((value: any) => void) | null = null;
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
          model: "holo-fixture",
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
      };
      window.companion = {
        getStatus: async () => ({
          platform: "fixture",
          model: "holo-fixture",
          apiKeyConfigured: keyConfigured,
          captureAvailable: true,
          display: {
            id: 1,
            bounds: { x: 0, y: 0, width: 1440, height: 900 },
            scaleFactor: 2,
          },
        }),
        getState: async () => structuredClone(state),
        configure: async (settings) => {
          state.settings = settings;
          emit();
        },
        startTracker: async () => {
          state.tracker = { state: "tracking" };
          emit();
        },
        stopTracker: async () => {
          state.tracker = { state: "off" };
          emit();
        },
        capture: async () => {
          if (rejectCapture) throw new Error("Capture de fixture refusée");
          latestFrame = {
            frameId: `simulated-frame-${++counter}`,
            capturedAt: "2026-11-07T10:00:00.000Z",
            sourceWidth: 2880,
            sourceHeight: 1800,
            cropRect: { x: 200, y: 300, width: 800, height: 600 },
            screenBounds: { x: 0, y: 0, width: 1440, height: 900 },
            selection: state.settings.selection,
            fallbackReason: null,
            detail: makeImage(800, 600),
            global: state.settings.includeGlobal ? makeImage(480, 300) : null,
            preparationMs: 34,
            gazeAgeMs: 22,
            simulated: true,
            captureMethod: "explicit-browser-fixture",
          };
          return structuredClone(latestFrame);
        },
        analyze: async (input) => {
          fixtureWindow.__labFixture.requestFrame = input.frameId;
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
