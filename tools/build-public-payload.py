#!/usr/bin/env python3
"""Explicit allowlist only. Never copies output/, .tools credentials or router state."""
import gzip,hashlib,io,json,pathlib,subprocess,tarfile,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'mobile/assets/setup'
CACHE=ROOT/'releases/private/build-cache'
MIHOMO_URL='https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-linux-arm64-v1.19.32.gz'
MIHOMO_SHA='9dd862e28b46ff7d775f169cceebc28deccaa0a9e804237d421cd2571e0caba0'
AWG_COMMIT='b5928efb6ca19f0153958460c3d141f04abc5c2e'
ROUTER=['companion.py','crypto.py','control.py','vpn_control.py','sms_control.py','lan_transport.py']
VPN=['manager.py','catalog.py','ports.py','uplink.py','gearup.py','direct_ipv6.py']
DENY=[b'-----BEGIN '+b'PRIVATE KEY-----', b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----']


def read_url(url):
    with urllib.request.urlopen(url,timeout=60) as r:return r.read(100*1024*1024)


def build():
    OUT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    archive=CACHE/'mihomo.gz'
    if not archive.exists():archive.write_bytes(read_url(MIHOMO_URL))
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=MIHOMO_SHA:raise ValueError('Mihomo hash mismatch')
    source=CACHE/'amneziawg-go'
    if not source.exists():
        subprocess.run(['git','clone','--quiet','https://github.com/amnezia-vpn/amneziawg-go.git',str(source)],check=True)
    subprocess.run(['git','-C',str(source),'checkout','--quiet',AWG_COMMIT],check=True)
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain']).strip():raise ValueError('AWG source is not clean')
    import os
    subprocess.run(['go','build','-trimpath','-ldflags=-s -w','-o',str(CACHE/'amneziawg-go-arm64'),'.'],cwd=source,
                   env={**os.environ,'CGO_ENABLED':'0','GOOS':'linux','GOARCH':'arm64'},check=True)
    files={}
    for name in ROUTER:files['opt/photonicat-companion/'+name]=(ROOT/'router'/name).read_bytes()
    for f in (ROOT/'router/vendor').rglob('*'):
        if f.is_file() and not f.is_symlink() and f.suffix in ('.py','.txt') and '__pycache__' not in f.parts or (f.is_file() and f.name=='LICENSE'):
            files['opt/photonicat-companion/vendor/'+str(f.relative_to(ROOT/'router/vendor'))]=f.read_bytes()
    for name in VPN:files['opt/photonicat-vpn/'+name]=(ROOT/'vpn-service'/name).read_bytes()
    for name,folder in [('photonicat-companion','router'),('photonicat-vpn','vpn-service'),('photonicat-ports','vpn-service')]:
        files['etc/init.d/'+name]=(ROOT/folder/(name+'.init')).read_bytes()
    files['opt/photonicat-vpn/mihomo']=gzip.decompress(archive.read_bytes())
    files['opt/photonicat-vpn/amneziawg-go']=(CACHE/'amneziawg-go-arm64').read_bytes()
    exe=[k for k in files if k.startswith('etc/init.d/') or k.endswith(('/mihomo','/amneziawg-go'))]
    entries={'payload/'+k:v for k,v in files.items()}
    for name in ('install.py','probe.py','network.py','defaults.py'):entries[name]=(ROOT/'installer'/name).read_bytes()
    entries['manifest.json']=json.dumps({'version':'0.7.6-beta.1','files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},'executables':exe},sort_keys=True).encode()
    for name,data in entries.items():
        if any(x in data for x in DENY):raise ValueError('Private material detected in '+name)
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for name,data in sorted(entries.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
            tar.addfile(info,io.BytesIO(data))
    payload=gzip.compress(buffer.getvalue(),compresslevel=6,mtime=0)
    (OUT/'payload.tar.gz').write_bytes(payload)
    (OUT/'payload.sha256').write_text(hashlib.sha256(payload).hexdigest()+'\n')
    # Probe is an app asset for a strictly read-only first step.
    (OUT/'probe.py').write_bytes((ROOT/'installer/probe.py').read_bytes())
    (OUT/'NOTICE.txt').write_text('Photonicat Companion setup payload. No owner keys or subscriptions.\nMihomo v1.19.32: https://github.com/MetaCubeX/mihomo/tree/v1.19.32 (GPL-3.0).\nAmneziaWG: https://github.com/amnezia-vpn/amneziawg-go/tree/'+AWG_COMMIT+' (MIT).\nOther dependency licenses are retained in router/vendor.\n')
    (OUT/'AMNEZIA-LICENSE.txt').write_bytes((source/'LICENSE').read_bytes())
    (OUT/'MIHOMO-LICENSE.txt').write_bytes(read_url('https://raw.githubusercontent.com/MetaCubeX/mihomo/v1.19.32/LICENSE'))
    print(json.dumps({'payload_bytes':len(payload),'files':len(entries),'secret_scan':'pass'}))
if __name__=='__main__':build()
