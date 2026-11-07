import { performance } from 'node:perf_hooks';
import { setTimeout as delay } from 'node:timers/promises';

export function validateObservationOptions(input) {
  if (!input || ![15, 30, 60].includes(input.durationSeconds) || typeof input.showOverlay !== 'boolean') {
    throw new Error('Choisissez une durée de 15, 30 ou 60 secondes et le mode du contour.');
  }
  if (input.benchmark !== undefined && typeof input.benchmark !== 'boolean') throw new Error('Mode de test cible invalide.');
  if (input.benchmark === true && (!Number.isInteger(input.seed) || input.seed < 0 || input.seed > 0xffff_ffff)) throw new Error('La graine doit être un entier entre 0 et 4 294 967 295.');
  return { durationSeconds: input.durationSeconds, showOverlay: input.benchmark ? false : input.showOverlay,
    ...(input.benchmark ? { benchmark: true, seed: input.seed } : {}) };
}

/** Serial local sampling. Images stay in bounded memory and never enter state broadcasts. */
export class ObservationSession {
  constructor({ capture, onChange = () => {}, onFinish = () => {}, maxBytes = 64 * 1024 * 1024,
    now = () => performance.now(), wait = (ms, signal) => delay(ms, undefined, { signal }) }) {
    this.capture = capture;
    this.onChange = onChange;
    this.onFinish = onFinish;
    this.maxBytes = maxBytes;
    this.now = now;
    this.wait = wait;
    this.samples = [];
    this.bytes = 0;
    this.controller = null;
    this.finished = Promise.resolve();
    this.state = { status: 'idle', sampleCount: 0, startedAt: null, durationSeconds: 30, intervalMs: 1000 };
  }
  get active() { return this.state.status === 'running' || this.state.status === 'stopping'; }
  publish() { this.onChange({ ...this.state }); }
  start(input) {
    const options = validateObservationOptions(input);
    if (this.active) throw new Error('Une observation est déjà en cours.');
    this.samples = []; this.bytes = 0;
    const controller = new AbortController();
    this.controller = controller;
    this.state = { status: 'running', sampleCount: 0, startedAt: new Date().toISOString(), durationSeconds: options.durationSeconds, intervalMs: 1000,
      ...(options.benchmark ? { benchmark: { seed: options.seed } } : {}) };
    this.publish();
    this.finished = this.run(controller, options);
  }
  async run(controller, options) {
    const { signal } = controller;
    const timer = setTimeout(() => {
      if (signal.aborted) return;
      this.state.stopReason = 'duration';
      controller.abort();
    }, 3000 + options.durationSeconds * 1000);
    try {
      await this.wait(3000, signal);
      let nextAt = this.now();
      while (!signal.aborted) {
        await this.wait(Math.max(0, nextAt - this.now()), signal);
        signal.throwIfAborted();
        const frame = await this.capture(signal);
        signal.throwIfAborted();
        // Conservative UTF-16 estimate; base64 strings dominate the retained memory.
        const bytes = [frame.detail, frame.global, frame.reference]
          .reduce((total, image) => total + (image?.dataUrl?.length ?? 0) * 2, 1024);
        if (this.bytes + bytes > this.maxBytes) { this.state.stopReason = 'memory-limit'; break; }
        this.samples.push({ frame, annotation: null });
        this.bytes += bytes;
        this.state.sampleCount = this.samples.length;
        this.publish();
        nextAt += this.state.intervalMs;
        // Missed deadlines are skipped, never queued behind a slow capture.
        while (nextAt < this.now()) nextAt += this.state.intervalMs;
      }
    } catch (error) {
      if (!signal.aborted) {
        this.state.error = error instanceof Error ? error.message : String(error);
        this.state.stopReason = 'error';
      }
    } finally {
      clearTimeout(timer);
      this.controller = null;
      this.state.status = 'stopped';
      this.state.stopReason ??= 'user';
      this.publish();
      this.onFinish();
    }
  }
  async stop(reason = 'user') {
    if (this.active) {
      this.state.status = 'stopping'; this.state.stopReason = reason;
      this.publish(); this.controller?.abort();
    }
    await this.finished;
  }
  list() {
    return this.samples.map(({ frame: f, annotation }) => ({
      frameId: f.frameId, capturedAt: f.capturedAt, cropRect: { ...f.cropRect },
      sourceWidth: f.sourceWidth, sourceHeight: f.sourceHeight, preparationMs: f.preparationMs,
      gazeAgeMs: f.gazeAgeMs, fallbackReason: f.fallbackReason, regionDisposition: f.regionDisposition,
      selectedWindow: f.selectedWindow, annotation,
      signalUsed: f.signalUsed, signalReason: f.signalReason, headAgeMs: f.headAgeMs,
      benchmark: f.benchmark, calibrationProfile: f.calibrationProfile,
    }));
  }
  select(id) {
    if (this.active) throw new Error('Arrêtez l’observation avant de revoir une image.');
    const sample = this.samples.find(item => item.frame.frameId === id);
    if (!sample) throw new Error('Image de session introuvable ou effacée.');
    return sample.frame;
  }
  annotate({ frameId, label }) {
    this.select(frameId);
    if (!['present', 'absent', 'uncertain'].includes(label)) throw new Error('Annotation non reconnue.');
    this.samples.find(item => item.frame.frameId === frameId).annotation = label;
  }
  clear() {
    if (this.active) throw new Error('Arrêtez l’observation avant de l’effacer.');
    this.samples = []; this.bytes = 0;
    this.state = { status: 'idle', sampleCount: 0, startedAt: null, durationSeconds: 30, intervalMs: 1000 };
    this.publish();
  }
}
