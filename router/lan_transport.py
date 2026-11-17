"""Bounded LAN framing for the existing authenticated Companion protocol.

No plaintext control/discovery endpoint. Uplink local addresses are refused even
if a firewall rule is misconfigured. Session keys never cross this transport.
"""
import asyncio
import ipaddress
import json
import secrets
import time
from pathlib import Path

PORT = 24862
DEVICES = {'br-lan', 'br-pcwifi', 'br-pcdirect'}


def client_addresses(interfaces, config=None, sharing=False):
    config = config or {}
    devices = DEVICES | {config.get('lan_bridge'), config.get('wifi_bridge'), config.get('direct_bridge')}
    result = set()
    for link in interfaces:
        # WAN sharing has its own owned subnet; never admit WAN uplink addresses.
        for address in link.get('addr_info', []):
            local = address.get('local', '')
            if address.get('family') == 'inet' and (
                link.get('ifname') in devices or (
                    sharing and link.get('ifname') == config.get('wan_device')
                    and local == config.get('share_address'))
            ):
                result.add(local)
    return result


class LanTransport:
    def __init__(self, engine):
        self.engine = engine
        self.connections = 0
        self.allowed = set()
        self.server = None
        self.refresh_task = None

    async def refresh_addresses(self):
        process = await asyncio.create_subprocess_exec(
            'ip', '-j', '-4', 'addr', stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 3)
            config_path = Path('/etc/photonicat-vpn/ports.json')
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            role = Path('/var/run/photonicat-wan-guard-role')
            sharing = role.exists() and role.read_text().strip() == 'share'
            self.allowed = client_addresses(json.loads(output), config, sharing) if process.returncode == 0 else set()
        except Exception:
            self.allowed = set()
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def refresh_loop(self):
        while True:
            await self.refresh_addresses()
            await asyncio.sleep(5)

    async def start(self):
        await self.refresh_addresses()
        self.server = await asyncio.start_server(self.accept, '0.0.0.0', PORT, limit=49152)
        self.refresh_task = asyncio.create_task(self.refresh_loop())

    async def accept(self, reader, writer):
        peer = writer.get_extra_info('peername')
        local = writer.get_extra_info('sockname')
        if (self.connections >= 8 or not peer or not local or
                local[0] not in self.allowed or not ipaddress.ip_address(peer[0]).is_private):
            writer.close()
            return
        self.connections += 1
        device = 'lan:' + secrets.token_hex(16)
        authenticated = False
        recent = []
        try:
            while True:
                data = await asyncio.wait_for(reader.readline(), 120 if authenticated else 8)
                if not data or not data.endswith(b'\n') or len(data) > 49152:
                    break
                now = time.monotonic()
                recent = [t for t in recent if now - t < 1]
                if len(recent) >= 4 or self.engine.pending >= 4:
                    break
                recent.append(now)
                replied = False
                async def send(output):
                    nonlocal replied
                    writer.write(output)
                    await asyncio.wait_for(writer.drain(), 5)
                    replied = True
                self.engine.pending += 1
                await self.engine.handle(device, data.strip(), send=send)
                if not replied:
                    break
                authenticated = device in self.engine.sessions
        except (OSError, ValueError, asyncio.TimeoutError):
            pass
        finally:
            self.engine.sessions.pop(device, None)
            self.connections -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
