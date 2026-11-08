import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { installVoicePilot, VOICE_STOP_SHORTCUT } from '../electron/voice-pilot.mjs';

const temporaryDirectories: string[] = [];

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  temporaryDirectories.splice(0).forEach(directory => rmSync(directory, { recursive: true, force: true }));
});

function fixture(shortcutAvailable: boolean) {
  vi.useFakeTimers();
  const directory = mkdtempSync(join(tmpdir(), 'hcompanion-shortcut-test-'));
  temporaryDirectories.push(directory);
  const tokenPath = join(directory, 'pilot-token');
  writeFileSync(tokenPath, 'offline-shortcut-test-token', { mode: 0o600 });
  vi.stubEnv('HCS_PILOT_URL', 'http://127.0.0.1:8767');
  vi.stubEnv('HCS_PILOT_TOKEN_FILE', tokenPath);
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const handlers = new Map<string, (...args: unknown[]) => unknown>();
  const listeners = new Map<string, (...args: unknown[]) => unknown>();
  const order: string[] = [];
  const globalShortcut = {
    register: vi.fn(() => { order.push('reserve-shortcut'); return shortcutAvailable; }),
    unregister: vi.fn(),
  };
  const ipcMain = { handle: vi.fn((name: string, handler: (...args: unknown[]) => unknown) => {
    order.push(name); handlers.set(name, handler);
  }) };
  const app = { on: vi.fn((name: string, listener: (...args: unknown[]) => unknown) => listeners.set(name, listener)), quit: vi.fn() };
  const panel = { isDestroyed: () => false, isMinimized: () => false, restore: vi.fn(), show: vi.fn(), hide: vi.fn(), focus: vi.fn() };
  return { app, ipcMain, globalShortcut, panel, systemPreferences: {}, authorize: vi.fn(), handlers, listeners, order, fetch };
}

it('cannot expose approval or start monitoring when another instance owns the stop shortcut', () => {
  const f = fixture(false);
  expect(() => installVoicePilot(f)).toThrow('raccourci d’arrêt');
  expect(f.globalShortcut.register).toHaveBeenCalledWith(VOICE_STOP_SHORTCUT, expect.any(Function));
  expect(f.ipcMain.handle).not.toHaveBeenCalled();
  expect(f.app.on).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
  expect(f.fetch).not.toHaveBeenCalled();
  // Do not release a shortcut owned by another instance after our failed reservation.
  expect(f.globalShortcut.unregister).not.toHaveBeenCalled();
});

it('reserves the stop shortcut before exposing approval and releases it on quit', () => {
  const f = fixture(true);
  installVoicePilot(f);
  expect(f.order[0]).toBe('reserve-shortcut');
  expect(f.handlers.has('voice:approve')).toBe(true);
  expect(f.handlers.has('voice:stop')).toBe(true);
  expect(vi.getTimerCount()).toBe(1);
  expect(f.fetch).not.toHaveBeenCalled();
  f.listeners.get('will-quit')?.();
  expect(vi.getTimerCount()).toBe(0);
  expect(f.globalShortcut.unregister).toHaveBeenCalledWith(VOICE_STOP_SHORTCUT);
});
