import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

source = Path(__file__).resolve().parents[2] / 'mobile/assets/setup/performance.py'
spec = importlib.util.spec_from_file_location('performance', source)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        paths = {name: root / name for name in ('CONFIG', 'STATE', 'HELPER', 'HOOK', 'PLATFORM', 'WAN', 'TUN')}
        scoped = patch.multiple(profile, ROOT=root, **paths)
        scoped.start()
        self.addCleanup(scoped.stop)
        self.original = {'listeners': [{'device': 'pcmh0', 'type': 'tun', 'stack': 'gvisor', 'mtu': 1280}],
                         'secret': 'fixture', 'proxy-groups': [{'name': 'example'}]}
        profile.CONFIG.write_text(json.dumps(self.original))
        profile.WAN.write_text('01')
        profile.TUN.write_text('00')
        stock = Path.is_file
        patcher = patch.object(Path, 'is_file', lambda p: str(p) == '/usr/libexec/network/packet-steering.uc' or stock(p))
        patcher.start()
        self.addCleanup(patcher.stop)
        def run(*args):
            if args[0] == 'ubus':
                return json.dumps({'board_name': 'ariaboard,photonicat2', 'release': {'version':'26.04.1','distribution':'PhotonicatWrt'}})
            if args[0] == 'uci':
                return 'eth0' if args[-1] == 'network.wan.device' else '1'
            if args[-1] == '-v':
                return 'Mihomo Meta v1.19.32 linux arm64'
            if args[-1] == 'net-add':
                profile.WAN.write_text('00')
                profile.TUN.write_text('fc')
            return ''
        cmd = patch.object(profile, 'command', side_effect=run)
        self.run_command = cmd.start()
        self.addCleanup(cmd.stop)

    def test_install_repeat_and_restore_preserve_other_settings(self):
        self.assertEqual(profile.update('check'), 'available')
        self.assertEqual(profile.update('apply'), 'saved')
        self.assertEqual(profile.TUN.read_text(), 'fc')
        self.assertEqual(os.readlink(profile.PLATFORM), str(profile.HELPER))
        saved = json.loads(profile.CONFIG.read_text())
        self.assertTrue(profile.listener(saved)['gso'])
        self.assertEqual(profile.update('apply'), 'ready')
        saved['proxy-groups'].append({'name': 'added later'})
        profile.CONFIG.write_text(json.dumps(saved))
        self.assertEqual(profile.update('restore'), 'restored')
        restored = json.loads(profile.CONFIG.read_text())
        self.assertEqual(restored['listeners'], self.original['listeners'])
        self.assertEqual(restored['proxy-groups'], saved['proxy-groups'])
        self.assertEqual(profile.WAN.read_text(), '01')
        self.assertFalse(profile.PLATFORM.is_symlink())
        self.assertFalse(profile.STATE.exists())

    def test_reject_foreign_hook_before_any_change(self):
        profile.PLATFORM.write_text('vendor hook')
        with self.assertRaises(profile.Unsupported):
            profile.update('apply')
        self.assertFalse(profile.HELPER.exists())
        self.assertEqual(profile.PLATFORM.read_text(), 'vendor hook')

    def test_candidate_failure_rolls_back_partial_install(self):
        with patch.object(profile, 'set_config', side_effect=ValueError()):
            with self.assertRaises(ValueError):
                profile.update('apply')
        self.assertFalse(profile.STATE.exists())
        self.assertFalse(profile.HELPER.exists())
        self.assertFalse(profile.PLATFORM.is_symlink())
        self.assertEqual(json.loads(profile.CONFIG.read_text()), self.original)

    def test_preserve_custom_mtu(self):
        self.assertNotIn('mtu', profile.target_values({'stack': 'mips', 'mtu': 1420}))

