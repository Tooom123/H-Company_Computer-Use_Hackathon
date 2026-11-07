import { describe, expect, it } from 'vitest';
import { monoWav } from '../src/lib/voice-pilot';

describe('voice upload PCM WAV', () => {
  it('retains one second of mono audio in a standard measurable WAV', () => {
    const samples = Float32Array.from({ length: 16000 }, (_, index) => Math.sin(index / 20));
    const buffer = monoWav([samples], 16000);
    const view = new DataView(buffer);
    expect(new TextDecoder().decode(buffer.slice(0, 4))).toBe('RIFF');
    expect(new TextDecoder().decode(buffer.slice(8, 12))).toBe('WAVE');
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(40, true) / view.getUint32(28, true)).toBe(1);
    expect(view.getInt16(46, true)).toBeCloseTo(Math.round(samples[1] * 32767), 0);
  });
  it('mixes stereo before encoding and clips out-of-range values without overflow', () => {
    const view = new DataView(monoWav([new Float32Array([1, -1, 8, NaN]), new Float32Array([-1, -1, 4, 0])], 16000));
    expect([44, 46, 48, 50].map(offset => view.getInt16(offset, true))).toEqual([0, -32768, 32767, 0]);
    expect(() => monoWav([], 16000)).toThrow();
    expect(() => monoWav([new Float32Array(0)], 16000)).toThrow();
    expect(() => monoWav([new Float32Array(2), new Float32Array(1)], 16000)).toThrow();
  });
});
