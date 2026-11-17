#!/usr/bin/env python3
"""Sign a copied macOS release with an existing Keychain identity.

Usage: sign-macos.py SOURCE.app DESTINATION.app IDENTITY
Does not export keys, create certificates, or submit to Apple.
"""
import pathlib
import subprocess
import sys

source, destination = map(pathlib.Path, sys.argv[1:3])
identity = sys.argv[3]
if source.resolve() == destination.resolve():
    raise SystemExit('Use a separate destination to preserve the build artifact')
if destination.exists():
    raise SystemExit('Destination already exists; choose a new destination')
subprocess.run(['ditto', str(source), str(destination)], check=True)
frameworks = destination / 'Contents/Frameworks'
nested = [p for p in frameworks.rglob('*')
          if not p.is_symlink() and p.suffix in ('.framework', '.dylib', '.xpc')]
for path in sorted(nested, key=lambda p: len(p.parts), reverse=True):
    subprocess.run(['codesign', '--force', '--sign', identity, '--options',
                    'runtime', '--timestamp=none', str(path)], check=True)
entitlements = pathlib.Path(__file__).resolve().parents[1] / 'mobile/macos/Runner/Release.entitlements'
subprocess.run(['codesign', '--force', '--sign', identity, '--options', 'runtime',
                '--timestamp=none', '--entitlements', str(entitlements),
                str(destination)], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=2',
                str(destination)], check=True)
