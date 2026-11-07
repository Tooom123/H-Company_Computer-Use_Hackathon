#!/usr/bin/env python3
"""Create a separately identifiable macOS development shell, keeping Lab alive."""
import argparse
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('This development shell is macOS only.')
    source = ROOT / 'app/node_modules/electron/dist/Electron.app'
    target = args.output.resolve()
    if target.exists() or target.suffix != '.app':
        raise SystemExit('Choose a new .app destination; existing files are never replaced.')
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp', '-cR', str(source), str(target)], check=True)
    info = target / 'Contents/Info.plist'
    data = plistlib.loads(info.read_bytes())
    data.update(CFBundleIdentifier='dev.hcompanion.voicepilot', CFBundleName='HCompanionVoice',
                CFBundleDisplayName='H-Companion Voice',
                NSMicrophoneUsageDescription='Enregistrer votre demande et votre feedback après votre clic.')
    info.write_bytes(plistlib.dumps(data))
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(target)], check=True)
    print(target / 'Contents/MacOS/Electron')


if __name__ == '__main__':
    main()
