import { describe, expect, it } from 'vitest';
import { TargetSequence } from '../electron/target-sequence.mjs';

const bounds = { x: -1470, y: 0, width: 1470, height: 956 };
const frame = { sourceWidth: 1470, sourceHeight: 956, cropRect: { x: 0, y: 0, width: 1470, height: 956 },
  selection: 'head', signalUsed: 'head', regionDisposition: 'full-size' };

describe('target presentation and capture ordering', () => {
  it('requires the current run acknowledgement and excludes its settling interval', () => {
    let now = 0;
    const sequence = new TargetSequence({ now: () => now });
    sequence.start({ seed: 42, bounds });
    expect(sequence.acknowledge({ runId: 'previous-run', index: 0 })).toBe(false);
    now = 3000;
    const unshown = sequence.beforeCapture();
    expect(sequence.score(unshown, frame)).toMatchObject({ scorable: false, reason: 'unpresented' });
    expect(sequence.acknowledge({ runId: sequence.runId, index: 0 })).toBe(true);
    now += 400;
    expect(sequence.score(sequence.beforeCapture(), frame)).toMatchObject({ scorable: false, reason: 'transition' });
    expect(sequence.acknowledge({ runId: sequence.runId, index: 0 })).toBe(false); // No clock refresh.
    now += 400;
    expect(sequence.score(sequence.beforeCapture(), frame)).toMatchObject({ scorable: true, fullContained: true });
  });

  it('holds the target throughout a slow capture, then changes it between frames', () => {
    let now = 0;
    const sequence = new TargetSequence({ now: () => now });
    sequence.start({ seed: 42, bounds });
    sequence.acknowledge({ runId: sequence.runId, index: 0 });
    now = 5900;
    const snapshot = sequence.beforeCapture()!;
    now = 7400; // Cross the nominal target change deadline during capture.
    expect(sequence.score(snapshot, frame)).toMatchObject({ scorable: true, target: { index: 0 } });
    const next = sequence.beforeCapture()!;
    expect(next.target.index).toBe(1);
    expect(next.presentedAt).toBeNull();
    expect(sequence.score(next, frame)).toMatchObject({ scorable: false, reason: 'unpresented' });
    expect(sequence.score(snapshot, frame)).toMatchObject({ scorable: false, reason: 'unstable' });
  });

  it('clears targets at stop and rejects acknowledgements from an earlier identical replay', () => {
    let now = 0;
    const targets: unknown[] = [];
    const sequence = new TargetSequence({ now: () => now, onTarget: target => targets.push(target) });
    sequence.start({ seed: 0, bounds });
    const old = sequence.beforeCapture()!;
    sequence.stop();
    expect(targets.at(-1)).toBeNull();
    expect(sequence.beforeCapture()).toBeNull();
    now = 5000;
    sequence.start({ seed: 0, bounds });
    expect(sequence.beforeCapture()!.target.x).toBe(old.target.x);
    expect(sequence.acknowledge({ runId: old.target.runId, index: 0 })).toBe(false);
    expect(sequence.beforeCapture()!.presentedAt).toBeNull();
  });
});
