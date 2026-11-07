import type { GazeSample, Rect } from './types';

export type HeatTarget = { id: string; rect: Rect; label?: string; weight?: number };
export type HeatState = {
  center: { x: number; y: number }; sigma: number; spacing: number;
  circles: Array<{ x: number; y: number; r: number; p: number; central: boolean }>;
  targets: Array<{ id: string; label?: string; rect: Rect; p: number; intent?: number }>;
  best: { id: string; rect: Rect; p: number; intent?: number } | null; pNone: number; roi: Rect;
} | null;

export const DEFAULTS: Record<string, unknown>;
export class GazeHeatmap {
  constructor(cfg: { canvas: HTMLCanvasElement; color?: [number, number, number]; maxAlpha?: number;
    options?: Record<string, unknown>; onUpdate?: (state: HeatState) => void });
  opts: Record<string, unknown>;
  push(sample: GazeSample | null): void;
  setPointer(x: number | null, y?: number): void;
  setUncertainty(px: number | undefined): void;
  setTargets(targets: HeatTarget[] | null): void;
  start(): void;
  stop(): void;
}
