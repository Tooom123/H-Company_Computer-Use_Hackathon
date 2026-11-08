// WebGazer, wrapped the way Édouard's app does it (app/src/lib/webgazer.ts), in plain JS for the test page:
// local WebGazer 3.5.3 + MediaPipe (npm run assets), ridge regression, nothing saved across sessions,
// NEVER trained on mouse clicks (only on our explicit calibration points), camera really stopped on stop().

let scriptPromise;

function loadWebGazer() {
  if (window.webgazer) return Promise.resolve(window.webgazer);
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = new URL("./vendor/webgazer.js", location.href).href;
    script.async = true;
    const timer = setTimeout(() => fail(), 20000);
    const fail = () => {
      clearTimeout(timer);
      script.remove();
      scriptPromise = undefined;
      reject(new Error("Local WebGazer did not load: run `npm run assets` in heatmap/."));
    };
    script.onerror = fail;
    script.onload = () => {
      clearTimeout(timer);
      if (window.webgazer) resolve(window.webgazer);
      else fail();
    };
    document.head.append(script);
  });
  return scriptPromise;
}

export function cameraErrorMessage(error) {
  const name = error?.name || "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") return "Camera access refused: allow it in the browser's address bar, then reload.";
  if (name === "NotFoundError" || name === "DevicesNotFoundError") return "No webcam found.";
  if (name === "NotReadableError" || name === "TrackStartError") return "The camera is busy in another app.";
  return error?.message || "Could not start gaze tracking.";
}

export class WebGazerTracker {
  /** @param {(sample: {x:number,y:number,emittedAt:number}|null) => void} onSample */
  constructor(onSample) {
    this.onSample = onSample;
    this.api = null;
    this.ready = false;
    this.disposed = false;
    this.serial = 0;
    this.recordedSerial = -1;
    this.lastCallbackAt = 0;
  }

  async start() {
    const api = await loadWebGazer();
    if (this.disposed) return;
    this.api = api;
    api.params.faceMeshSolutionPath = new URL("./vendor/mediapipe/face_mesh", location.href).href;
    api.saveDataAcrossSessions(false).setRegression("ridge").showPredictionPoints(false);
    api.applyKalmanFilter(true); // smooths the raw predictions a little; the heatmap does the rest
    api.showVideoPreview(true).showFaceOverlay(true).showFaceFeedbackBox(true);
    // Smaller preview than the default 320x240 (read by begin(); setVideoViewerSize() only works after it).
    api.params.videoViewerWidth = 240;
    api.params.videoViewerHeight = 180;
    await api.clearData();
    api.setGazeListener((data) => {
      if (this.disposed) return;
      this.serial += 1;
      this.lastCallbackAt = performance.now();
      // Emission time, not the camera-frame time (see docs/gaze-research-protocol.md).
      const ok = data && Number.isFinite(data.x) && Number.isFinite(data.y);
      this.onSample(ok ? { x: data.x, y: data.y, emittedAt: performance.now() } : null);
    });
    await api.begin();
    api.removeMouseEventListeners(); // begin() listens to every click: never learn from them
    await api.clearData();
    if (this.disposed) this.releaseCamera();
    else this.ready = true;
  }

  /** One deliberate calibration click while looking at (x, y). False when no face/eyes: not counted. */
  recordCalibrationPoint(x, y) {
    if (!this.api || !this.ready || this.recordedSerial === this.serial) return false;
    if (performance.now() - this.lastCallbackAt > 500) return false;
    const regression = this.api.getRegression()[0];
    const before = regression.getData();
    const beforeLength = before.length;
    const lastBefore = before.at(-1);
    this.api.recordScreenPosition(x, y, "click");
    this.recordedSerial = this.serial;
    const after = regression.getData();
    return after.length > beforeLength || (after.length > 0 && after.at(-1) !== lastBefore);
  }

  showPreview(on) {
    this.api?.showVideoPreview(on).showFaceOverlay(on).showFaceFeedbackBox(on);
  }

  async recalibrate() {
    await this.api?.clearData();
  }

  releaseCamera() {
    this.api?.pause();
    this.api?.clearGazeListener();
    this.api?.removeMouseEventListeners();
    const video = document.getElementById("webgazerVideoFeed");
    if (video?.srcObject instanceof MediaStream) for (const t of video.srcObject.getTracks()) t.stop();
    const box = document.getElementById("webgazerVideoContainer");
    if (box) box.style.display = "none";
  }

  dispose() {
    this.disposed = true;
    this.ready = false;
    this.releaseCamera();
  }
}
