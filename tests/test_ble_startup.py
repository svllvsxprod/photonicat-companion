import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'router'))
import companion


class BleStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_adapter_retried_without_blocking_lan(self):
        engine = companion.Engine(companion.Crypto(bytes(range(32))),
                                  SimpleNamespace(notifying=False))
        engine.cached = {'battery': 75}
        bus = Mock()
        setup = AsyncMock(side_effect=[RuntimeError('adapter absent'), bus])
        sent = []

        async def send(frame):
            sent.append(engine.crypto.open(frame.strip()))

        with patch.object(companion, 'setup_ble', setup):
            task = asyncio.create_task(companion.start_ble_when_ready(
                b'key', engine, None, None, None, retry_delay=.02))
            await asyncio.sleep(.005)
            engine.pending += 1
            await engine.handle('lan-test', engine.crypto.seal(
                {'op': 'hello', 'seq': 1, 'challenge': 'a' * 32}), send=send)
            self.assertTrue(sent[0]['ok'])
            self.assertFalse(task.done())
            await asyncio.wait_for(task, 1)
        self.assertIs(engine.bus, bus)
        self.assertEqual(setup.await_count, 2)

    async def test_cancel_stops_retry(self):
        setup = AsyncMock(side_effect=RuntimeError('adapter absent'))
        with patch.object(companion, 'setup_ble', setup):
            task = asyncio.create_task(companion.start_ble_when_ready(
                b'key', SimpleNamespace(), None, None, None, retry_delay=60))
            await asyncio.sleep(.005)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(setup.await_count, 1)

    async def test_failed_setup_cleans_exports_and_disconnects(self):
        bus = Mock()
        bus.connect = AsyncMock(return_value=bus)
        bus.introspect = AsyncMock(side_effect=RuntimeError('BlueZ not ready'))
        with patch.object(companion, 'MessageBus', return_value=bus):
            with self.assertRaisesRegex(RuntimeError, 'BlueZ not ready'):
                await companion.setup_ble(bytes(range(32)), None,
                    companion.GattService(), companion.Characteristic(companion.RX, ['write']),
                    companion.Characteristic(companion.TX, ['notify']))
        bus.disconnect.assert_called_once()
        self.assertEqual(bus.unexport.call_count, 5)

    async def test_cancelled_setup_cleans_connection(self):
        bus = Mock()
        bus.connect = AsyncMock(side_effect=asyncio.CancelledError)
        with patch.object(companion, 'MessageBus', return_value=bus):
            with self.assertRaises(asyncio.CancelledError):
                await companion.setup_ble(b'key', None, None, None, None)
        bus.disconnect.assert_called_once()
