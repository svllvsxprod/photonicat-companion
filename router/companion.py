#!/usr/bin/python3
"""Authenticated BLE telemetry and capability-based stock firmware controls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "vendor"))
import asyncio
import json
import logging
import secrets
import subprocess
import time
import urllib.request
import urllib.error
import re
import hmac
import hashlib
from dbus_next import Variant, BusType, DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property
from dbus_next.constants import PropertyAccess
from crypto import Crypto
from control import Controls, ControlError, modem_status
import vpn_control

ROOT = "/dev/photonicat/companion"
SERVICE = "b8b3c190-78b7-4f23-9c44-743d94c0a001"
RX = "b8b3c190-78b7-4f23-9c44-743d94c0a002"
TX = "b8b3c190-78b7-4f23-9c44-743d94c0a003"
LOG = logging.getLogger("photonicat-companion")
_previous_cpu = None


def read(path, default=""):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def number(path, scale=1):
    try:
        return float(read(path)) / scale
    except ValueError:
        return None


def ubus(obj, name, default=None):
    try:
        return json.loads(subprocess.check_output(
            ["ubus", "call", obj, name], timeout=2, stderr=subprocess.DEVNULL))
    except (subprocess.SubprocessError, ValueError):
        return default if default is not None else {}


def local_json(path, port=80):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
            result = json.load(response)
            return result if isinstance(result, dict) else {}
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def cpu_percent(previous, current):
    # Exclude guest/guest_nice: Linux already includes these in user/nice.
    if previous is None or len(current) < 4 or len(previous) < 4:
        return None
    delta = [b - a for a, b in zip(previous[:8], current[:8])]
    if any(x < 0 for x in delta) or sum(delta) <= 0:
        return None
    idle = delta[3] + (delta[4] if len(delta) > 4 else 0)
    return round(100 * (sum(delta) - idle) / sum(delta), 1)


def remaining_time(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if re.fullmatch(r"<?\s*\d{1,4}:[0-5]\d", value) else None


def collect():
    global _previous_cpu
    battery = "/sys/class/power_supply/battery/"
    temps = [number(str(p / "temp"), 1000) for p in Path("/sys/class/thermal").glob("thermal_zone*")]
    networks = ubus("network.interface", "dump").get("interface", [])
    default_networks = [
        n for n in networks if n.get("up") and any(
            r.get("mask") == 0 and r.get("target") == "0.0.0.0"
            for r in n.get("route", []))]
    wan = min(default_networks, key=lambda n: n.get("metric", 0), default={})
    interface = wan.get("l3_device", "")
    stat = f"/sys/class/net/{interface}/statistics/" if re.fullmatch(r"[\w.-]+", interface) else "/nonexistent/"
    radios = ubus("network.wireless", "status")
    clients, ssids = {}, []
    for radio in radios.values():
        for ap in radio.get("interfaces", []):
            name = ap.get("ifname", "")
            if not re.fullmatch(r"[\w.-]+", name):
                continue
            state = ubus(f"hostapd.{name}", "get_status")
            if state.get("ssid"):
                ssids.append(state["ssid"])
            clients.update(ubus(f"hostapd.{name}", "get_clients").get("clients", {}))
    leases = []
    for line in read("/tmp/dhcp.leases").splitlines():
        row = line.split()
        if len(row) >= 4:
            leases.append({"name": row[3] if row[3] != "*" else "Устройство",
                           "ip": row[2], "wifi": row[1].lower() in clients})
    mem = {}
    for line in read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            mem[parts[0].rstrip(":")] = int(parts[1])
    release = {}
    for line in read("/etc/openwrt_release").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            release[k] = v.strip("'\"")
    cpu = [int(x) for x in read("/proc/stat", "cpu").splitlines()[0].split()[1:9]]
    cpu_usage = cpu_percent(_previous_cpu, cpu)
    _previous_cpu = cpu
    # Same sources as the stock display, independent of which LCD page is awake.
    dashboard = local_json("/api/v1/dashboard.json")
    remaining = remaining_time(dashboard.get("battery_remaining_time"))
    if not dashboard:
        remaining = remaining_time(local_json("/api/v1/go_data.json", 8081).get("RemainingTime"))
    traffic = local_json("/api/v1/data_stats.json?network_type=mobile")
    modem = modem_status()
    return {
        "battery": number(battery + "capacity"),
        "charging": read(battery + "status") == "Charging",
        "voltage": number(battery + "voltage_now", 1e6),
        "power": number(battery + "power_now", 1e6),
        "remaining_time": remaining,
        "cpu_percent": cpu_usage,
        "mobile_today_bytes": traffic.get("today_used"),
        "mobile_month_bytes": traffic.get("month_used"),
        "temperature": max((x for x in temps if x is not None), default=None),
        "uptime": float(read("/proc/uptime", "0 0").split()[0]),
        "wan_up": wan.get("up", False), "wan_interface": interface,
        "rx_bytes": number(stat + "rx_bytes"),
        "tx_bytes": number(stat + "tx_bytes"),
        "sample_time": time.monotonic(),
        "wifi_up": bool(ssids), "ssid": ", ".join(ssids),
        "wifi_clients": len(clients), "leases": leases[:30],
        "memory_total": mem.get("MemTotal", 0), "memory_available": mem.get("MemAvailable", 0),
        "firmware": release.get("DISTRIB_ID", "") + " " + release.get("DISTRIB_RELEASE", ""),
        "kernel": read("/proc/sys/kernel/osrelease"),
        "modem_present": None if modem is None else modem.get("mode") not in (None, "", "none"),
        "service_version": "0.2.0",
    }


class GattService(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.GattService1")

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return SERVICE

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return True


class Characteristic(ServiceInterface):
    def __init__(self, uuid, flags):
        super().__init__("org.bluez.GattCharacteristic1")
        self.uuid, self.flags = uuid, flags
        self.notifying = False
        self.value = b""
        self.handler = None

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self.uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return ROOT + "/service0"

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return self.flags

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> "ay":
        return self.value

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> "b":
        return self.notifying

    @method()
    def StartNotify(self):
        self.notifying = True
        self.emit_properties_changed({"Notifying": True})

    @method()
    def StopNotify(self):
        self.notifying = False
        self.emit_properties_changed({"Notifying": False})

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}"):
        if self.handler:
            self.handler(bytes(value), options)
        else:
            raise DBusError("org.bluez.Error.NotPermitted", "Read only")


class Manager(ServiceInterface):
    def __init__(self, objects):
        super().__init__("org.freedesktop.DBus.ObjectManager")
        self.objects = objects

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":
        return self.objects


class Advertisement(ServiceInterface):
    def __init__(self, identity):
        super().__init__("org.bluez.LEAdvertisement1")
        self.identity = identity

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return [SERVICE]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return "PCat-" + self.identity

    @method()
    def Release(self):
        LOG.info("Advertisement released")


class Engine:
    def __init__(self, crypto, tx):
        self.crypto, self.tx = crypto, tx
        self.buffers = {}
        self.sessions = {}
        self.cached = {}
        self.lock = asyncio.Lock()
        self.pending = 0
        self.recent = []
        self.controls = Controls()
        self.control_lock = asyncio.Lock()
        self.capabilities = {}

    def receive(self, packet, options):
        if not packet or len(packet) > 512:
            return
        device = options.get("device", Variant("o", "/")).value
        # Cap unauthenticated input state. A packet starts with 1 or continues with 0.
        if packet[0] == 1:
            if len(self.buffers) >= 8:
                self.buffers.clear()
            self.buffers[device] = b""
        elif packet[0] != 0 or device not in self.buffers:
            return
        data = self.buffers.get(device, b"") + packet[1:]
        if len(data) > 49152:
            self.buffers.pop(device, None)
            return
        self.buffers[device] = data
        if data.endswith(b"\n"):
            self.buffers.pop(device, None)
            now = time.monotonic()
            self.recent = [t for t in self.recent if now - t < 1]
            if self.pending >= 2 or len(self.recent) >= 4:
                return
            self.recent.append(now)
            self.pending += 1
            asyncio.create_task(self.handle(device, data.strip()))

    async def handle(self, device, data):
        try:
            request = self.crypto.open(data)
            seq, op = request.get("seq"), request.get("op")
            if not isinstance(seq, int) or seq < 0:
                return
            now = time.monotonic()
            self.sessions = {k: v for k, v in self.sessions.items() if now - v["time"] < 300}
            if op == "hello":
                challenge = request.get("challenge", "")
                if not isinstance(challenge, str) or len(challenge) != 32:
                    return
                sid = secrets.token_hex(16)
                self.sessions[device] = {"sid": sid, "seq": seq, "time": now}
                result = {"seq": seq, "sid": sid, "challenge": challenge, "ok": True}
            else:
                session = self.sessions.get(device)
                if not session or request.get("sid") != session["sid"] or seq <= session["seq"]:
                    return
                session.update(seq=seq, time=now)
                result = {"seq": seq, "sid": session["sid"], "ok": op == "status"}
                if op == "status":
                    result["status"] = {
                        **self.cached,
                        "settings": self.capabilities,
                        "sample_age": max(0, time.monotonic() - self.cached.get("sample_time", 0)),
                    }
                elif op in ("vpn_get", "vpn_set"):
                    async with self.control_lock:
                        try:
                            if op == "vpn_set":
                                outcome = await asyncio.to_thread(vpn_control.execute, request.get("args"), self.controls.revision)
                                result.update(outcome)
                            vpn = await asyncio.to_thread(vpn_control.snapshot, self.controls.revision)
                            result.update(ok=True, vpn=vpn)
                        except vpn_control.VpnError as exc:
                            result.update(ok=False, error=str(exc))
                elif op in ("sms_list", "sms_read"):
                    import sms_control
                    try:
                        outcome = await asyncio.to_thread(sms_control.execute, op, request.get("args", {}))
                        result.update(ok=True, **outcome)
                    except ControlError as exc:
                        result.update(ok=False, error=str(exc))
                elif op in ("settings", "wifi_set", "screen_set", "fan_set", "reboot"):
                    async with self.control_lock:
                        try:
                            if op != "settings":
                                outcome = await asyncio.to_thread(self.controls.execute, op, request.get("args"))
                                result.update(outcome)
                            self.capabilities = await asyncio.to_thread(self.controls.snapshot)
                            result.update(ok=True, settings=self.capabilities)
                        except ControlError as exc:
                            result.update(ok=False, error=str(exc))
                else:
                    result["error"] = "Unsupported operation"
            async with self.lock:
                if not self.tx.notifying:
                    return
                output = self.crypto.seal(result) + b"\n"
                # 19-byte data payload works even with the minimum ATT MTU (23).
                for offset in range(0, len(output), 19):
                    chunk = bytes([1 if offset == 0 else 0]) + output[offset:offset + 19]
                    self.tx.value = chunk
                    self.tx.emit_properties_changed({"Value": chunk})
                    await asyncio.sleep(0.008)
                if op == "reboot" and result.get("ok"):
                    asyncio.get_running_loop().call_later(
                        2, lambda: subprocess.Popen(["/sbin/reboot"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except (ValueError, TypeError, KeyError):
            LOG.warning("Rejected invalid request")
        except Exception:
            LOG.exception("Request failed")
        finally:
            self.pending -= 1

    async def sample(self):
        last_discovery = 0
        while True:
            try:
                self.cached = await asyncio.to_thread(collect)
                if time.monotonic() - last_discovery > 15 and not self.control_lock.locked():
                    async with self.control_lock:
                        self.capabilities = await asyncio.to_thread(self.controls.snapshot)
                    last_discovery = time.monotonic()
            except Exception:
                LOG.exception("Telemetry read failed")
            await asyncio.sleep(3)


async def main():
    key = bytes.fromhex(Path("/etc/photonicat-companion/key").read_text().strip())
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    svc, rx, tx = GattService(), Characteristic(RX, ["write"]), Characteristic(TX, ["notify"])
    engine = Engine(Crypto(key), tx)
    rx.handler = engine.receive
    service_path = ROOT + "/service0"
    objects = {service_path: {"org.bluez.GattService1": {
        "UUID": Variant("s", SERVICE), "Primary": Variant("b", True)}}}
    bus.export(service_path, svc)
    for index, char in enumerate([rx, tx]):
        path = service_path + f"/char{index}"
        bus.export(path, char)
        objects[path] = {"org.bluez.GattCharacteristic1": {
            "UUID": Variant("s", char.uuid), "Service": Variant("o", service_path),
            "Flags": Variant("as", char.flags), "Notifying": Variant("b", False),
            "Value": Variant("ay", b"")}}
    bus.export(ROOT, Manager(objects))
    ad_path = ROOT + "/advertisement0"
    identity = hmac.new(key, b"photonicat/device-id/v1", hashlib.sha256).hexdigest()[:8]
    bus.export(ad_path, Advertisement(identity))
    root_intro = await bus.introspect("org.bluez", "/")
    bluez = bus.get_proxy_object("org.bluez", "/", root_intro)
    objects = await bluez.get_interface("org.freedesktop.DBus.ObjectManager").call_get_managed_objects()
    preference_file = Path("/etc/photonicat-companion/adapter")
    preferred = read(str(preference_file)).upper()
    adapters = [(path, props["org.bluez.Adapter1"]) for path, props in objects.items()
                if "org.bluez.Adapter1" in props and "org.bluez.LEAdvertisingManager1" in props
                and "org.bluez.GattManager1" in props]
    selected = next(((path, props) for path, props in adapters
                     if props["Address"].value.upper() == preferred), None)
    if not preferred:
        powered = [(path, props) for path, props in adapters
                   if props.get("Powered", Variant("b", False)).value]
        if len(powered) > 1:
            raise RuntimeError("Multiple BLE adapters: select an address in /etc/photonicat-companion/adapter")
        selected = powered[0] if powered else None
        if selected:
            preference_file.write_text(selected[1]["Address"].value + "\n")
    if selected is None:
        raise RuntimeError("Configured BLE adapter unavailable; refusing to silently switch identity")
    adapter_path = selected[0]
    introspection = await bus.introspect("org.bluez", adapter_path)
    adapter = bus.get_proxy_object("org.bluez", adapter_path, introspection)
    await adapter.get_interface("org.bluez.GattManager1").call_register_application(ROOT, {})
    await adapter.get_interface("org.bluez.LEAdvertisingManager1").call_register_advertisement(ad_path, {})
    LOG.info("BLE companion ready; authenticated telemetry and controls")
    await engine.sample()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
