import assert from "node:assert/strict";
import test from "node:test";
import { CALIBRATION, VALIDATION, accuracyLabel, quantile, rate, toPixels, validationError } from "./gaze-calibration.js";

test("Édouard's standard grids: 9 to learn, 4 different ones to measure", () => {
  assert.equal(CALIBRATION.length, 9);
  assert.equal(VALIDATION.length, 4);
  for (const v of VALIDATION) assert.ok(!CALIBRATION.some((c) => c.x === v.x && c.y === v.y));
  assert.deepEqual(toPixels([{ x: 0.5, y: 0.25 }], 1000, 800), [{ x: 500, y: 200 }]);
});

test("error: one median per target, then the median of targets", () => {
  const t = { x: 100, y: 100 };
  const runs = [
    { target: t, samples: [{ x: 110, y: 100 }, { x: 130, y: 100 }, { x: 400, y: 100 }] }, // 30 (outlier ignored)
    { target: t, samples: [{ x: 100, y: 150 }] }, // 50
    { target: t, samples: [{ x: 100, y: 200 }] }, // 100
    { target: t, samples: [] }, // face lost
  ];
  assert.deepEqual(validationError(runs), { medianPx: 50, worstPx: 100, targets: 3, missing: 1 });
  assert.equal(validationError([{ target: t, samples: [] }]), null);
});

test("helpers", () => {
  assert.equal(quantile([1, 2, 3, 4], 0.5), 2.5);
  assert.equal(quantile([], 0.5), null);
  assert.equal(accuracyLabel(80), "good");
  assert.match(accuracyLabel(300), /recalibrate/);
  const ts = Array.from({ length: 80 }, (_, i) => i * 33.3); // a 30 Hz tracker for 2.6 s
  assert.equal(rate(ts, 2633), 30); // only the last 2 s count
});
