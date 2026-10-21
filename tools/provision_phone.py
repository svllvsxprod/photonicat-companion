"""Bind the debug app over already-authorized USB without printing/storing its secret locally."""
import subprocess, os, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
adb=os.environ.get('ADB') or shutil.which('adb')
if not adb: raise RuntimeError('Install Android platform-tools or set ADB')
key=subprocess.check_output(['ssh',os.environ['PHOTONICAT_SSH_TARGET'],
    'cat /etc/photonicat-companion/key']).strip()
if len(key)!=64 or any(c not in b'0123456789abcdef' for c in key):
    raise RuntimeError('Router key is invalid')
subprocess.run([adb,'shell',"run-as dev.svllvsx.photonicat sh -c 'umask 077; mkdir -p files; cat > files/bootstrap.key'"],input=key,check=True)
print('Binding delivered to private app storage over USB.')
