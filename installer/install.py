"""Fresh-router transaction. Credentials travel only over the authenticated SSH channel."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import probe
from defaults import initial_config
import network

BASE=Path(__file__).resolve().parent
BACKUPS=Path('/root/photonicat-install-backups')
CONFIGS=['/etc/config/network','/etc/config/firewall','/etc/config/dhcp','/etc/sysupgrade.conf']
CREATED=['/opt/photonicat-companion','/opt/photonicat-vpn','/etc/photonicat-companion','/etc/photonicat-vpn',
         '/etc/init.d/photonicat-companion','/etc/init.d/photonicat-vpn','/etc/init.d/photonicat-ports',
         '/etc/nftables.d/30-photonicat-ports.nft']
SERVICES=['photonicat-ports','photonicat-vpn','photonicat-companion']


def run(*args):return subprocess.run(args,capture_output=True,check=True,timeout=45)

def write(path,data):
    p=Path(path);p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write(data if isinstance(data,str) else json.dumps(data))


def rollback(folder):
    for name in reversed(SERVICES):
        p=Path('/etc/init.d')/name
        if p.exists():
            subprocess.run([str(p),'stop'],capture_output=True,timeout=30)
            subprocess.run([str(p),'disable'],capture_output=True,timeout=10)
    for source in CONFIGS:
        backup=folder/(source.replace('/','_'))
        if backup.exists():shutil.copy2(backup,source)
    absent=folder/'absent-configs.json'
    if absent.exists():
        for source in json.loads(absent.read_text()):
            if source in CONFIGS:Path(source).unlink(missing_ok=True)
    for path in CREATED:
        p=Path(path)
        if p.is_dir():shutil.rmtree(p)
        else:p.unlink(missing_ok=True)
    for family in ('-4','-6'):
        for priority in (23497,23499,23500,23501,23502):
            subprocess.run(['ip',family,'rule','del','pref',str(priority)],capture_output=True,timeout=10)
        for table in (23500,23501,23502,23510):
            subprocess.run(['ip',family,'route','flush','table',str(table)],capture_output=True,timeout=10)
    subprocess.run(['nft','delete','table','inet','pcat_ports'],capture_output=True,timeout=10)
    for pkg in ('network','firewall','dhcp'):subprocess.run(['uci','revert',pkg],capture_output=True,timeout=10)
    for args in [('ubus','call','network','reload'),('/etc/init.d/firewall','reload'),('/etc/init.d/dnsmasq','reload'),('/etc/init.d/odhcpd','reload')]:
        subprocess.run(args,capture_output=True,timeout=30)
    write(folder/'result.json',{'rolled_back':True})


def watchdog(folder):
    time.sleep(300)
    # Do not undo a transaction while its installer is still changing files.
    with open('/var/lock/photonicat-install.lock','w') as installation_lock:
        fcntl.flock(installation_lock,fcntl.LOCK_EX)
        settle(folder)
    if BASE.parent == Path('/tmp') and BASE.name.startswith('photonicat-setup-'):
        shutil.rmtree(BASE, ignore_errors=True)


def settle(folder):
    with (folder/'transaction.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not (folder/'confirmed').exists() and not (folder/'result.json').exists():rollback(folder)


def preflight(report):
    if not report.get('supported'):raise ValueError('unsupported_router')
    zones={v.get('name'):v for v in probe.uci('firewall').values() if v.get('.type')=='zone'}
    if 'lan' not in zones or 'wan' not in zones or 'lan' not in probe.words(zones['lan'].get('network')):
        raise ValueError('firewall_unsupported')
    if any(Path(p).exists() for p in CREATED):raise ValueError('existing_installation')
    for package, prefixes in [('network',('pcdirect','pcwifi','pcwan')),('firewall',('pcdirect','pcwifi','pcvpn','pc_','pcat_')),('dhcp',('pcdirect','pcwifi','pcwan'))]:
        if any(k.startswith(prefixes) for k in probe.uci(package)):raise ValueError('reserved_names_in_use')
    # Refuse to claim another service's policy routing tables/rules.
    for family in ('-4','-6'):
        rules=json.loads(probe.run('ip','-j',family,'rule'))
        if any(r.get('priority') in (23497,23499,23500,23501,23502) for r in rules):raise ValueError('routing_conflict')
        routes=json.loads(probe.run('ip','-j',family,'route','show','table','all'))
        if any(str(r.get('table')) in ('23500','23501','23502','23510') for r in routes):raise ValueError('routing_conflict')
    if 'table inet pcat_ports' in probe.run('nft','list','tables'):raise ValueError('routing_conflict')


def install():
    os.umask(0o077)
    report=probe.inventory();preflight(report)
    spec=json.loads((BASE/'manifest.json').read_text())
    for name,sha in spec['files'].items():
        p=BASE/'payload'/name
        if p.is_symlink() or '..' in Path(name).parts or Path(name).is_absolute() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
            raise ValueError('payload_invalid')
    folder=BACKUPS/secrets.token_hex(12);folder.mkdir(mode=0o700,parents=True)
    for name in CONFIGS:
        if Path(name).exists():shutil.copy2(name,folder/name.replace('/','_'))
    write(folder/'absent-configs.json',[name for name in CONFIGS if not Path(name).exists()])
    write(folder/'created.json',CREATED)
    subprocess.Popen([sys.executable,str(BASE/'install.py'),'watchdog',str(folder)],
                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        for name in spec['files']:
            target=Path('/')/name
            if not (name.startswith('opt/photonicat-companion/') or name.startswith('opt/photonicat-vpn/') or name in ('etc/init.d/photonicat-companion','etc/init.d/photonicat-vpn','etc/init.d/photonicat-ports')):
                raise ValueError('payload_invalid')
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(BASE/'payload'/name,target)
            target.chmod(0o755 if name in spec['executables'] else 0o644)
        defaults=initial_config();root=Path('/etc/photonicat-vpn')
        write('/etc/photonicat-companion/key',defaults['key'])
        for sub in ('profiles','mihomo/providers'):(root/sub).mkdir(mode=0o700,parents=True,exist_ok=True)
        for name,value in [('profiles.json',defaults['profiles']),('state.json',defaults['state']),('api-secret',defaults['api_secret']),('mihomo/config.json',defaults['mihomo']),('ports.json',report['plan'])]:write(root/name,value)
        root.chmod(0o700)
        run('/opt/photonicat-vpn/mihomo','-t','-d',str(root/'mihomo'),'-f',str(root/'mihomo/config.json'))
        # Start the independent guard before adding forwarding. It starts Direct
        # for the existing LAN, while the unused protected Wi-Fi bridge fails closed.
        run('/etc/init.d/photonicat-vpn','start')
        ready=False
        for _ in range(30):
            p=subprocess.run([sys.executable,'/opt/photonicat-vpn/manager.py','status'],capture_output=True,timeout=10)
            if p.returncode==0 and json.loads(p.stdout)['mihomo'].get('running'):
                ready=True;break
            time.sleep(.5)
        if not ready:raise ValueError('vpn_start_failed')
        network.configure(report['plan'])
        for name in SERVICES:run('/etc/init.d/'+name,'enable')
        run('/etc/init.d/photonicat-ports','start')
        run('/etc/init.d/photonicat-companion','start')
        path=Path('/etc/sysupgrade.conf')
        old=path.read_text() if path.exists() else ''
        path.write_text(old+'\n'+'\n'.join(CREATED)+'\n')
        write('/etc/photonicat-companion/installation.json',{'version':spec['version'],'transaction':folder.name})
        return {'ok':True,'key':defaults['key'],'transaction':folder.name,'version':spec['version']}
    except Exception:
        with (folder/'transaction.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if not (folder/'result.json').exists():rollback(folder)
        raise ValueError('install_failed_rolled_back') from None

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='watchdog':watchdog(Path(sys.argv[2]))
    else:
        try:
            with open('/var/lock/photonicat-install.lock','w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                print(json.dumps(install()),flush=True)
        except Exception as exc:
            code=str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalpha() else 'setup_failed'
            print(json.dumps({'ok':False,'error':code}),flush=True);sys.exit(1)
