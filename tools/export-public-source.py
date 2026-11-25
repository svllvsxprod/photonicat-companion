#!/usr/bin/env python3
"""Create a reviewable distribution from an explicit allowlist, never repo root."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'releases/private/0.7.7-beta.1'
TREES = ['mobile/lib', 'mobile/test', 'mobile/assets', 'mobile/macos', 'mobile/windows',
         'mobile/vendor/reactive_ble_mobile', 'router/vendor', 'installer', 'docs/public']
FILES = ['.gitignore', '.github/workflows/windows-build.yml', 'mobile/pubspec.yaml', 'mobile/pubspec.lock', 'mobile/analysis_options.yaml',
         'mobile/test/setup_wizard_test.dart', 'tests/setup/test_setup.py',
         'tools/build-public-payload.py', 'tools/export-public-source.py',
         'tools/build-macos.sh', 'tools/build-windows.ps1', 'tools/sign-macos.py']
FILES += ['router/'+n for n in ('companion.py','crypto.py','control.py','vpn_control.py','sms_control.py','lan_transport.py','photonicat-companion.init')]
FILES += ['vpn-service/'+n for n in ('manager.py','catalog.py','ports.py','uplink.py','gearup.py','direct_ipv6.py','photonicat-vpn.init','photonicat-ports.init')]
SKIP = {'Pods', 'ephemeral', 'xcuserdata', 'build', '.dart_tool', '.git', '__pycache__', '.gradle', '.idea'}
SUFFIXES = {'.key','.pem','.p12','.pfx','.jks','.log','.pyc','.conf'}


def admissible(path):
    return (not path.is_symlink() and not set(path.parts) & SKIP
            and path.suffix not in SUFFIXES and not path.name.startswith('.env')
            and path.name not in ('local.properties','key.properties','.DS_Store'))


def audit(data, name):
    if any(marker in data for marker in (b'-----BEGIN '+b'PRIVATE KEY-----', b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----')):
        raise ValueError('Private key detected: '+name)
    # Read an optional owner-only list in memory. Never include it in exports.
    # Entries can be populated by a local audit; they must not be committed.
    sensitive = ROOT/'releases/private/audit-values.json'
    if sensitive.exists():
        if any(value.encode() in data for value in json.loads(sensitive.read_text()) if len(value)>=8):
            raise ValueError('Owner material detected: '+name)
    if name.endswith('.tar.gz'):
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
            for member in tar.getmembers():
                if not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts:
                    raise ValueError('Unsafe archive entry')
                audit(tar.extractfile(member).read(),member.name)


def build():
    candidates = [ROOT/n for n in FILES]
    for tree in TREES:
        candidates += [p for p in (ROOT/tree).rglob('*') if p.is_file() and admissible(p.relative_to(ROOT)) and not p.is_symlink()]
    entries = {}
    for p in candidates:
        if not p.is_file() or p.is_symlink(): raise ValueError('Missing allowed source: '+str(p.relative_to(ROOT)))
        name = str(p.relative_to(ROOT));data = p.read_bytes()
        audit(data,name);entries[name]=data
    entries['README.md']=(ROOT/'docs/public/README.md').read_text().replace('](SETUP_RU.md)', '](docs/public/SETUP_RU.md)').encode()
    DEST.mkdir(parents=True,exist_ok=True)
    output=DEST/'Photonicat-0.7.7-beta.1-Desktop-Source.zip'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(entries.items()):archive.writestr('Photonicat/'+name,data)
    report={'files':len(entries),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'allowlist':True,'generic_secret_scan':'pass','owner_secret_scan':'pass' if (ROOT/'releases/private/audit-values.json').exists() else 'not supplied'}
    (DEST/'source-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':build()
