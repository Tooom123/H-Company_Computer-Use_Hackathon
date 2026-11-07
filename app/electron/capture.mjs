import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { nativeImage } from 'electron';
import { planObservationRegion } from './observation-plan.mjs';

const exec = promisify(execFile);
function encode(image) {
  const png = image.toPNG();
  const { width, height } = image.getSize();
  return { dataUrl: `data:image/png;base64,${png.toString('base64')}`, width, height, sha256: createHash('sha256').update(png).digest('hex') };
}

export async function captureObservation({ binary, display, settings, selection, signal, excludeWindowIds, reference = false }) {
  const start = performance.now();
  const directory = await mkdtemp(path.join(tmpdir(), 'hcompanion-'));
  const output = path.join(directory, 'screen.png');
  try {
    const { stdout } = await exec(binary, ['--display', String(display.id), '--exclude-pid', String(process.pid), '--exclude-window-ids', excludeWindowIds.join(','), '--output', output], {
      timeout: 30_000, maxBuffer: 64 * 1024, signal,
    });
    signal?.throwIfAborted();
    const metadata = JSON.parse(stdout);
    const image = nativeImage.createFromBuffer(await readFile(output), { scaleFactor: 1 });
    signal?.throwIfAborted();
    const source = image.getSize();
    if (image.isEmpty() || source.width !== metadata.width || source.height !== metadata.height) {
      throw new Error('Dimensions de capture incohérentes : observation rejetée.');
    }
    const plan = planObservationRegion({ source, screenBounds: display.bounds, settings, selection, windows: metadata.windows });
    const { cropRect } = plan;
    // PNG comes from a byte buffer with scaleFactor 1; crop uses real pixels.
    const detail = encode(image.crop(cropRect));
    const global = plan.includeGlobal ? encode(image.resize({ width: Math.min(640, source.width), quality: 'best' })) : null;
    // This overview is for local review only. buildRequest() only sends detail/global.
    const localReference = reference ? encode(image.resize({ width: Math.min(1024, source.width), quality: 'best' })) : undefined;
    return {
      frameId: randomUUID(), capturedAt: metadata.captureCompletedAt, preparedAt: new Date().toISOString(),
      captureInterval: { startedAt: metadata.captureStartedAt, completedAt: metadata.captureCompletedAt },
      sourceWidth: source.width, sourceHeight: source.height,
      cropRect, screenBounds: { ...display.bounds }, selection: settings.selection, fallbackReason: plan.fallbackReason,
      requestedRegion: plan.requestedRegion, regionDisposition: plan.regionDisposition,
      ...(plan.selectedWindow ? { selectedWindow: plan.selectedWindow } : {}),
      ...(plan.windowFallbackReason ? { windowFallbackReason: plan.windowFallbackReason } : {}),
      ...(localReference ? { reference: localReference } : {}),
      detail, global, preparationMs: performance.now() - start, gazeAgeMs: plan.gazeAgeMs,
      headAgeMs: selection.headAgeMs ?? null,
      ...(selection.headDiagnostic ? { headDiagnostic: selection.headDiagnostic } : {}),
      signalUsed: selection.signalUsed ?? (plan.fallbackReason ? 'full' : settings.selection),
      ...(selection.signalReason ? { signalReason: selection.signalReason } : {}),
      simulated: false, captureMethod: 'ScreenCaptureKit · fenêtres H-Companion exclues',
    };
  } catch (error) {
    throw new Error(error.stderr?.trim() || error.message || 'Capture impossible.');
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
