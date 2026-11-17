"""Fresh, empty per-owner configuration. No example accounts or shared keys."""
import secrets


def initial_config():
    token = secrets.token_urlsafe(32)
    config = {
        'allow-lan': False, 'bind-address': '127.0.0.1', 'mode': 'rule',
        'log-level': 'error', 'ipv6': True, 'routing-mark': 23499,
        'external-controller': '127.0.0.1:19090', 'secret': token,
        'profile': {'store-selected': True},
        'dns': {'enable': True, 'listen': '127.0.0.1:10553', 'ipv6': True,
                'enhanced-mode': 'redir-host', 'default-nameserver': ['1.1.1.1','8.8.8.8'],
                'nameserver': ['https://1.1.1.1/dns-query#PC-Mihomo'],
                'proxy-server-nameserver': ['https://1.1.1.1/dns-query']},
        'proxies': [{'name': 'PC-Amnezia', 'type': 'direct', 'interface-name': 'pcawg0', 'routing-mark':23501}],
        'proxy-providers': {},
        'proxy-groups': [{'name':'PC-Mihomo','type':'select','proxies':['REJECT'],'use':[]},
                         {'name':'PC-Active','type':'select','proxies':['PC-Mihomo','PC-Amnezia']}],
        'listeners': [{'name':'mihomo-tun','type':'tun','device':'pcmh0','stack':'gvisor',
                       'auto-route':False,'auto-detect-interface':False,'dns-hijack':[],
                       'inet4-address':['198.19.0.1/30'],'inet6-address':['fd70:ca7::1/126'],
                       'mtu':1280,'proxy':'PC-Mihomo'}] + [
                         {'name':name,'type':'mixed','listen':'127.0.0.1','port':port,'proxy':group}
                         for name,port,group in [('active',17880,'PC-Active'),('amnezia',17881,'PC-Amnezia'),('mihomo',17882,'PC-Mihomo')]],
        'rules':['MATCH,PC-Active'],
    }
    return {'key':secrets.token_hex(32), 'api_secret':token, 'mihomo':config,
            'profiles':[], 'state':{'active':'mihomo','amneziawg':None,'mihomo':None}}
