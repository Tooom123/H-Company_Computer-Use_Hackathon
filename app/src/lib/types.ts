import type { HeadZone, HeadZonePrediction } from './head-zones';
export type Rect = { x: number; y: number; width: number; height: number };
export type HeadMappingReason = 'uncalibrated' | 'invalid-pose' | 'outside-calibration-domain' | 'outside-screen' | 'valid';
export type HeadDiagnostic = { reason: HeadMappingReason | 'tracker-inactive' | 'no-pose' | 'stale' | 'invalid-timing' | 'point-rejected' | 'zone-valid' | 'zone-unavailable' | 'outside-zone-domain' | 'stabilizing'; message: string; rawPoint?: { x: number; y: number } };
export type DisplayInfo = { id: number; bounds: Rect; scaleFactor: number };
export type ObservationOptions = { durationSeconds: 15 | 30 | 60; showOverlay: boolean; benchmark?: boolean; seed?: number };
export type BenchmarkTarget = { id: string; index: number; x: number; y: number; radius: number; zone: 'edge' | 'interior'; seed: string };
export type BenchmarkScore = {
  target: BenchmarkTarget; targetPixels: { x: number; y: number; radiusX: number; radiusY: number };
  scorable: boolean; reason: null | 'unpresented' | 'transition' | 'unstable' | 'invalid-timing';
  centerContained: boolean | null; fullContained: boolean | null; areaFraction: number; fullFrame: boolean; fullFallback: boolean;
  mode: string; signalUsed?: string; presentedAt: number | null; selectionAt: number; captureCompletedAt: number; settleMs: number;
  frameId?: string; capturedAt?: string; fallbackReason?: string | null; headDiagnostic?: HeadDiagnostic; headAgeMs?: number | null; preparationMs?: number; headRegionPolicy?: 'point' | 'zones'; headZone?: HeadZone; calibrationProfile?: 'standard' | 'wide';
};
export type BenchmarkCounts = { total: number; scored: number; unscored: number; centerHits: number; fullHits: number; croppedScored: number; croppedFullHits: number; fullFrames: number; fullFallbacks: number; meanAreaFraction: number | null };
export type BenchmarkSummary = BenchmarkCounts & { byMode: Record<string, BenchmarkCounts>; bySignal: Record<string, BenchmarkCounts>; edge: BenchmarkCounts; interior: BenchmarkCounts; fallbackReasons?: Record<string, number> };
export type Settings = { selection: 'gaze' | 'head' | 'hybrid' | 'cursor' | 'full'; roiWidth: number; roiHeight: number; includeGlobal: boolean; overlay: boolean; regionScope?: 'screen' | 'window'; headRegionPolicy?: 'point' | 'zones' };
export type RuntimeStatus = { platform: string; model: string; models?: string[]; apiKeyConfigured: boolean; captureAvailable: boolean; captureError?: string; display: DisplayInfo; observationShortcutAvailable?: boolean };
export type TrackerStatus = { state: 'off' | 'calibrating' | 'tracking' | 'lost' | 'error'; message?: string; calibrationErrorPx?: number; gazeCalibrated?: boolean; headCalibrated?: boolean; headCalibrationErrorPx?: number; headMessage?: string; calibrationProfile?: 'standard' | 'wide' };
export type ObservationStatus = { status: 'idle' | 'running' | 'stopping' | 'stopped'; sampleCount: number; capturedCount?: number; discardedImageCount?: number; startedAt: string | null; durationSeconds: number; intervalMs: number; error?: string; stopReason?: string; benchmark?: { seed: number }; benchmarkSummary?: BenchmarkSummary };
export type SelectedWindow = { id: number; appName: string; bounds: Rect };
export type ObservationLabel = 'present' | 'absent' | 'uncertain';
export type LiveState = { tracker: TrackerStatus; candidate: Rect | null; sent: { frameId: string; rect: Rect } | null; observed?: { frameId: string; rect: Rect } | null; busy: 'capture' | 'inference' | null; settings: Settings; observation?: ObservationStatus; head?: { available: boolean; yaw: number | null; pitch: number | null; roll: number | null; ageMs: number | null; mappingReason?: HeadMappingReason; mappingMessage?: string; zoneMessage?: string }; benchmarkTarget?: (BenchmarkTarget & { runId: string }) | null };
export type EncodedImage = { dataUrl: string; width: number; height: number; sha256: string };
export type CaptureFrame = {
  frameId: string; capturedAt: string; sourceWidth: number; sourceHeight: number;
  preparedAt?: string; captureInterval?: { startedAt: string; completedAt: string };
  cropRect: Rect; screenBounds: Rect; selection: Settings['selection']; fallbackReason: string | null;
  requestedRegion?: { width: number; height: number };
  regionDisposition?: 'crop' | 'full-requested' | 'full-fallback' | 'full-size';
  headRegionPolicy?: 'point' | 'zones'; headZone?: HeadZone;
  reference?: EncodedImage;
  selectedWindow?: SelectedWindow;
  windowFallbackReason?: string;
  signalUsed?: Settings['selection']; signalReason?: string; headAgeMs?: number | null; headDiagnostic?: HeadDiagnostic;
  benchmark?: BenchmarkScore; calibrationProfile?: 'standard' | 'wide';
  detail: EncodedImage; global: EncodedImage | null; preparationMs: number; gazeAgeMs: number | null;
  simulated: boolean; captureMethod: string;
};
export type ObservationSample = Pick<CaptureFrame, 'frameId' | 'capturedAt' | 'cropRect' | 'sourceWidth' | 'sourceHeight' | 'preparationMs' | 'gazeAgeMs' | 'fallbackReason' | 'regionDisposition' | 'selectedWindow' | 'signalUsed' | 'signalReason' | 'headAgeMs' | 'headDiagnostic' | 'benchmark' | 'calibrationProfile' | 'headRegionPolicy' | 'headZone'> & { annotation: ObservationLabel | null };
export type InferenceResult = {
  frameId: string; requestId: string | null; startedAt: string; latencyMs: number;
  usage: { inputTokens: number | null; outputTokens: number | null; totalTokens: number | null; cachedInputTokens: number | null };
  text: string; model: string; status: 'completed' | 'failed' | 'cancelled'; error?: string; simulated: boolean;
};
export type GazeSample = { x: number; y: number; emittedAt: number };
/** Approximate FaceMesh orientation in degrees; no camera images or raw mesh cross IPC. */
export type HeadSample = { point: { x: number; y: number } | null; pose: { yaw: number; pitch: number; roll: number }; emittedAt: number; zonePrediction?: HeadZonePrediction; reason?: HeadMappingReason; rawPoint?: { x: number; y: number } };
export interface CompanionBridge {
  getStatus(): Promise<RuntimeStatus>;
  getState(): Promise<LiveState>;
  configure(settings: Settings): Promise<void>;
  startTracker(): Promise<void>;
  stopTracker(): Promise<void>;
  capture(): Promise<CaptureFrame>;
  analyze(input: { frameId: string; prompt: string; model?: string }): Promise<InferenceResult>;
  cancel(): Promise<void>;
  startObservation(options: ObservationOptions): Promise<void>;
  stopObservation(): Promise<void>;
  listObservations(): Promise<ObservationSample[]>;
  selectObservation(frameId: string): Promise<CaptureFrame>;
  annotateObservation(input: { frameId: string; label: ObservationLabel }): Promise<void>;
  clearObservations(): Promise<void>;
  onState(callback: (state: LiveState) => void): () => void;
  // Restricted by main process to the tracker window; viewport coordinates on the primary display.
  reportGaze(sample: GazeSample | null): void;
  reportHead(sample: HeadSample | null): void;
  reportTargetPresented(sample: { runId: string; index: number }): void;
  reportTracker(status: TrackerStatus): void;
  finishCalibration(): Promise<void>;
  requestCamera(): Promise<void>;
}
declare global { interface Window { companion: CompanionBridge } }
