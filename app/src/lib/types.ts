export type Rect = { x: number; y: number; width: number; height: number };
export type DisplayInfo = { id: number; bounds: Rect; scaleFactor: number };
export type Settings = { selection: 'gaze' | 'cursor' | 'full'; roiWidth: number; roiHeight: number; includeGlobal: boolean; overlay: boolean; regionScope?: 'screen' | 'window' };
export type RuntimeStatus = { platform: string; model: string; models?: string[]; apiKeyConfigured: boolean; captureAvailable: boolean; captureError?: string; display: DisplayInfo; observationShortcutAvailable?: boolean };
export type TrackerStatus = { state: 'off' | 'calibrating' | 'tracking' | 'lost' | 'error'; message?: string; calibrationErrorPx?: number };
export type ObservationStatus = { status: 'idle' | 'running' | 'stopping' | 'stopped'; sampleCount: number; startedAt: string | null; durationSeconds: number; intervalMs: number; error?: string; stopReason?: string };
export type SelectedWindow = { id: number; appName: string; bounds: Rect };
export type ObservationLabel = 'present' | 'absent' | 'uncertain';
export type LiveState = { tracker: TrackerStatus; candidate: Rect | null; sent: { frameId: string; rect: Rect } | null; observed?: { frameId: string; rect: Rect } | null; busy: 'capture' | 'inference' | null; settings: Settings; observation?: ObservationStatus };
export type EncodedImage = { dataUrl: string; width: number; height: number; sha256: string };
export type CaptureFrame = {
  frameId: string; capturedAt: string; sourceWidth: number; sourceHeight: number;
  preparedAt?: string; captureInterval?: { startedAt: string; completedAt: string };
  cropRect: Rect; screenBounds: Rect; selection: Settings['selection']; fallbackReason: string | null;
  requestedRegion?: { width: number; height: number };
  regionDisposition?: 'crop' | 'full-requested' | 'full-fallback' | 'full-size';
  reference?: EncodedImage;
  selectedWindow?: SelectedWindow;
  windowFallbackReason?: string;
  detail: EncodedImage; global: EncodedImage | null; preparationMs: number; gazeAgeMs: number | null;
  simulated: boolean; captureMethod: string;
};
export type ObservationSample = Pick<CaptureFrame, 'frameId' | 'capturedAt' | 'cropRect' | 'sourceWidth' | 'sourceHeight' | 'preparationMs' | 'gazeAgeMs' | 'fallbackReason' | 'regionDisposition' | 'selectedWindow'> & { annotation: ObservationLabel | null };
export type InferenceResult = {
  frameId: string; requestId: string | null; startedAt: string; latencyMs: number;
  usage: { inputTokens: number | null; outputTokens: number | null; totalTokens: number | null; cachedInputTokens: number | null };
  text: string; model: string; status: 'completed' | 'failed' | 'cancelled'; error?: string; simulated: boolean;
};
export type GazeSample = { x: number; y: number; emittedAt: number };
export interface CompanionBridge {
  getStatus(): Promise<RuntimeStatus>;
  getState(): Promise<LiveState>;
  configure(settings: Settings): Promise<void>;
  startTracker(): Promise<void>;
  stopTracker(): Promise<void>;
  capture(): Promise<CaptureFrame>;
  analyze(input: { frameId: string; prompt: string; model?: string }): Promise<InferenceResult>;
  cancel(): Promise<void>;
  startObservation(options: { durationSeconds: 15 | 30 | 60; showOverlay: boolean }): Promise<void>;
  stopObservation(): Promise<void>;
  listObservations(): Promise<ObservationSample[]>;
  selectObservation(frameId: string): Promise<CaptureFrame>;
  annotateObservation(input: { frameId: string; label: ObservationLabel }): Promise<void>;
  clearObservations(): Promise<void>;
  onState(callback: (state: LiveState) => void): () => void;
  // Restricted by main process to the tracker window; viewport coordinates on the primary display.
  reportGaze(sample: GazeSample | null): void;
  reportTracker(status: TrackerStatus): void;
  finishCalibration(): Promise<void>;
  requestCamera(): Promise<void>;
}
declare global { interface Window { companion: CompanionBridge } }
