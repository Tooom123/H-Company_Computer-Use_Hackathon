// Local WebGazer + MediaPipe face mesh for the vision page (same pinned version and layout as Édouard's
// app/scripts/copy-webgazer.mjs): nothing is fetched from a CDN, no face image leaves this computer.
import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const source = new URL("../node_modules/webgazer/", import.meta.url);
const target = new URL("../vendor/", import.meta.url);
const pkg = JSON.parse(await readFile(new URL("package.json", source), "utf8"));
if (pkg.version !== "3.5.3") throw new Error(`Expected WebGazer 3.5.3; installed ${pkg.version}. Review the adapter first.`);
await mkdir(target, { recursive: true });
await cp(new URL("dist/webgazer.js", source), new URL("webgazer.js", target));
await cp(new URL("dist/mediapipe", source), new URL("mediapipe", target), { recursive: true });
await cp(new URL("LICENSE.md", source), new URL("WebGazer-LICENSE.md", target));
await writeFile(new URL("webgazer-version.json", target), JSON.stringify({ version: pkg.version, license: pkg.license }, null, 2) + "\n");
console.log(`Prepared local WebGazer ${pkg.version} + MediaPipe in ${fileURLToPath(target)}`);
