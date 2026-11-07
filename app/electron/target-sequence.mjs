import { performance } from 'node:perf_hooks';
import { randomUUID } from 'node:crypto';
import { generateTarget, evaluateTargetFrame } from './target-benchmark.mjs';

/**
 * Target positions are independent of the tracker and only change BETWEEN
 * captures. The selection algorithm never receives target coordinates.
 * A renderer acknowledgement after painting establishes a conservative lower
 * bound on fixation time; it is not a hardware presentation timestamp.
 */
export class TargetSequence {
  /** @param {{onTarget?:(target:object|null)=>void, now?:()=>number}} [options] */
  constructor({ onTarget = () => {}, now = () => performance.now() } = {}) {
    this.onTarget = onTarget; this.now = now; this.current = null;
  }
  start({ seed, bounds }) {
    this.seed = seed; this.bounds = { ...bounds }; this.runId = randomUUID();
    this.publishTarget(0);
    // First target is also visible during the three-second preparation period.
    this.nextChangeAt = this.now() + 6000;
  }
  publishTarget(index) {
    this.current = { ...generateTarget({ seed: this.seed, index, bounds: this.bounds }), runId: this.runId };
    this.presentedAt = null;
    this.onTarget({ ...this.current });
  }
  acknowledge({ runId, index } = {}) {
    if (!this.current || runId !== this.runId || index !== this.current.index || this.presentedAt !== null) return false;
    this.presentedAt = this.now();
    return true;
  }
  beforeCapture() {
    if (!this.current) return null;
    if (this.now() >= this.nextChangeAt) {
      this.publishTarget(this.current.index + 1);
      this.nextChangeAt = this.now() + 3000;
    }
    return { target: { ...this.current }, bounds: { ...this.bounds }, presentedAt: this.presentedAt, selectionAt: this.now() };
  }
  score(snapshot, frame) {
    if (!snapshot) return undefined;
    return evaluateTargetFrame({
      target: snapshot.target, bounds: snapshot.bounds,
      source: { width: frame.sourceWidth, height: frame.sourceHeight }, cropRect: frame.cropRect,
      presentedAt: snapshot.presentedAt, selectionAt: snapshot.selectionAt,
      captureCompletedAt: this.now(),
      stable: this.current?.runId === snapshot.target.runId && this.current?.index === snapshot.target.index,
      mode: frame.selection, signalUsed: frame.signalUsed, regionDisposition: frame.regionDisposition,
    });
  }
  stop() { this.current = null; this.presentedAt = null; this.onTarget(null); }
}
