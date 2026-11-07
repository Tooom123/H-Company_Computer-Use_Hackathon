import { mkdir, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

if (process.platform !== 'darwin') {
  console.log('Capture ScreenCaptureKit disponible uniquement sur macOS ; le panneau reste utilisable.');
  process.exit(0);
}
const root = fileURLToPath(new URL('..', import.meta.url));
const source = path.join(root, 'native/capture.swift');
const binary = path.join(root, 'out/capture');
await mkdir(path.dirname(binary), { recursive: true });
try {
  if ((await stat(binary)).mtimeMs >= (await stat(source)).mtimeMs) process.exit(0);
} catch { /* First build. */ }
const result = spawnSync('xcrun', ['swiftc', '-parse-as-library', '-module-cache-path', path.join(root, 'out/swift-module-cache'), '-O', source, '-o', binary], { stdio: 'inherit' });
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
