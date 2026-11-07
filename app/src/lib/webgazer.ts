import type { GazeSample } from './types';
import { extractHeadPose, type HeadPose } from './head-pose';

type Prediction = { x: number; y: number } | null;
type WebGazer = {
  params: { faceMeshSolutionPath: string };
  begin(): Promise<WebGazer>;
  pause(): WebGazer;
  clearData(): Promise<void>;
  clearGazeListener(): WebGazer;
  setGazeListener(listener: (prediction: Prediction, elapsed: number) => void): WebGazer;
  setRegression(name: string): WebGazer;
  removeMouseEventListeners(): WebGazer;
  recordScreenPosition(x: number, y: number, type: 'click'): WebGazer;
  getRegression(): Array<{ getData(): unknown[] }>;
  getTracker(): { getPositions(): unknown };
  saveDataAcrossSessions(value: boolean): WebGazer;
  showPredictionPoints(value: boolean): WebGazer;
  showVideoPreview(value: boolean): WebGazer;
};

declare global { interface Window { webgazer?: WebGazer } }

let scriptPromise: Promise<WebGazer> | undefined;

function loadWebGazer(): Promise<WebGazer> {
  if (window.webgazer) return Promise.resolve(window.webgazer);
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = new URL('/vendor/webgazer.js', window.location.href).href;
    script.async = true;
    const timer = window.setTimeout(() => fail(), 20_000);
    const fail = () => {
      window.clearTimeout(timer);
      script.remove();
      scriptPromise = undefined;
      reject(new Error('WebGazer local ne se charge pas. Relancez npm run assets puis l’application.'));
    };
    script.onerror = fail;
    script.onload = () => {
      window.clearTimeout(timer);
      if (window.webgazer) resolve(window.webgazer);
      else fail();
    };
    document.head.append(script);
  });
  return scriptPromise;
}

export function cameraErrorMessage(error: unknown): string {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return 'Accès caméra refusé. Autorisez H-Companion dans Réglages Système → Confidentialité et sécurité → Caméra, puis relancez l’app.';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'Aucune webcam disponible. Connectez une caméra puis réessayez.';
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return 'La caméra est indisponible ou utilisée par une autre application.';
  }
  return error instanceof Error ? error.message : 'Impossible de démarrer le suivi du regard.';
}

/** One instance per tracker window. No camera access until start() is called. */
export class WebGazerTracker {
  private api?: WebGazer;
  private disposed = false;
  private ready = false;
  private lastCallbackAt = 0;
  private sampleSerial = 0;
  private recordedSerial = -1;
  private lastPositions: unknown;

  constructor(private readonly onSample: (sample: GazeSample | null, head: HeadPose | null) => void) {}

  async start(): Promise<void> {
    const api = await loadWebGazer();
    if (this.disposed) return;
    this.api = api;
    api.params.faceMeshSolutionPath = new URL('/vendor/mediapipe/face_mesh', window.location.href).href;
    api.saveDataAcrossSessions(false).setRegression('ridge').showPredictionPoints(false).showVideoPreview(false);
    await api.clearData();
    if (this.disposed) return;
    api.setGazeListener((data) => {
      if (this.disposed) return;
      this.sampleSerial += 1;
      this.lastCallbackAt = performance.now();
      // This is emission time, NOT the source camera-frame timestamp or tracker latency.
      const sample = data && Number.isFinite(data.x) && Number.isFinite(data.y)
        ? { x: data.x, y: data.y, emittedAt: Date.now() }
        : null;
      // WebGazer 3.5.3 retains its previous mesh when a face disappears.
      // Only a new array identifies landmarks from this inference, even when
      // the eye regression has not yet learned enough to predict a gaze point.
      const positions = api.getTracker().getPositions();
      const head = positions && positions !== this.lastPositions ? extractHeadPose(positions) : null;
      this.lastPositions = positions;
      this.onSample(sample, head);
    });
    try {
      await api.begin();
      // begin() installs capture-phase listeners. Never train on desktop/agent clicks.
      api.removeMouseEventListeners();
      await api.clearData();
      if (this.disposed) this.releaseCamera();
      else this.ready = true;
    } catch (error) {
      this.dispose();
      throw error;
    }
  }

  /** Called only by a deliberate fixation on one of our calibration targets. */
  recordCalibrationPoint(x: number, y: number): boolean {
    if (!this.api || !this.ready || this.disposed || this.recordedSerial === this.sampleSerial) return false;
    if (performance.now() - this.lastCallbackAt > 500) return false;
    const regression = this.api.getRegression()[0];
    const before = regression.getData();
    const beforeLength = before.length;
    const lastBefore = before.at(-1);
    this.api.recordScreenPosition(x, y, 'click');
    this.recordedSerial = this.sampleSerial;
    // With no detected eyes, WebGazer ignores the label. Do not count that as a sample.
    const after = regression.getData();
    return after.length > beforeLength || (after.length > 0 && after.at(-1) !== lastBefore);
  }

  private releaseCamera(): void {
    this.api?.pause();
    this.api?.clearGazeListener();
    this.api?.removeMouseEventListeners();
    const video = document.getElementById('webgazerVideoFeed') as HTMLVideoElement | null;
    if (video?.srcObject instanceof MediaStream) {
      for (const track of video.srcObject.getTracks()) track.stop();
    }
    // Upstream end() leaves the camera running and may remove DOM during in-flight inference.
    // Keep its hidden nodes until this dedicated window is destroyed; explicitly stop tracks.
    const container = document.getElementById('webgazerVideoContainer');
    if (container) container.style.display = 'none';
  }

  dispose(): void {
    this.disposed = true;
    this.ready = false;
    this.releaseCamera();
  }
}
