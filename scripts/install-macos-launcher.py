#!/usr/bin/env python3
"""Install a local Finder/Spotlight shortcut; this is not a standalone distribution build."""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=Path.home() / 'Applications/H Companion.app')
    args = parser.parse_args()
    target = args.destination.expanduser().absolute()
    if sys.platform != 'darwin' or target.suffix != '.app':
        parser.error('Use macOS and an .app destination.')
    if target.exists():
        parser.error('Destination already exists; this installer never replaces an existing app.')
    with tempfile.TemporaryDirectory(prefix='hcompanion-finder-') as temporary:
        work = Path(temporary)
        bundle = work / 'H Companion.app'
        contents = bundle / 'Contents'
        executable = contents / 'MacOS/HCompanionLauncher'
        resources = contents / 'Resources'
        executable.parent.mkdir(parents=True)
        resources.mkdir()
        subprocess.run(['/usr/bin/swiftc', str(ROOT / 'desktop/launcher/Launcher.swift'), '-O',
                        '-module-cache-path', str(work / 'swift-cache'), '-o', str(executable)], check=True)
        iconset = work / 'Companion.iconset'
        iconset.mkdir()
        source = ROOT / 'desktop/assets/companion.png'
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                suffix = '@2x' if scale == 2 else ''
                output = iconset / ('icon_{}x{}{}.png'.format(size, size, suffix))
                subprocess.run(['/usr/bin/sips', '-z', str(size * scale), str(size * scale),
                                str(source), '--out', str(output)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset), '-o',
                        str(resources / 'Companion.icns')], check=True)
        (resources / 'launcher.json').write_text(json.dumps({'repository': str(ROOT)}, indent=2) + '\n')
        with (contents / 'Info.plist').open('wb') as stream:
            plistlib.dump({'CFBundleIdentifier': 'ai.hcompanion.local-launcher', 'CFBundleName': 'H Companion',
                          'CFBundleDisplayName': 'H Companion', 'CFBundleExecutable': 'HCompanionLauncher',
                          'CFBundlePackageType': 'APPL', 'CFBundleIconFile': 'Companion.icns',
                          'CFBundleShortVersionString': '0.1.0', 'CFBundleVersion': '1',
                          'LSMinimumSystemVersion': '12.0', 'LSUIElement': True,
                          'NSHighResolutionCapable': True,
                          'NSMicrophoneUsageDescription': 'Record your request only while you hold the H Companion talk shortcut.'}, stream)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(bundle)], check=True,
                       stdout=subprocess.DEVNULL)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundle, target)
    print('Installed local H Companion shortcut: ' + str(target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
