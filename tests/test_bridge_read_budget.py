import unittest
from unittest.mock import AsyncMock
from olive.bridge.host import Host

class ReadBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_refreshes_do_not_exhaust_effect_replay_history(self):
        host=Host(lambda _:None)
        host.execute=AsyncMock(return_value={'fixture':True})
        for i in range(2100):
            await host.handle({'v':1,'id':str(i),'method':'runtime.snapshot','args':{}})
        self.assertEqual(len(host.requests),0)
        action={'v':1,'id':'effect','method':'chat.new','args':{}}
        await host.handle(action);await host.handle(action)
        self.assertEqual(host.execute.await_count,2101)
        self.assertEqual(len(host.requests),1)
        with self.assertRaises(ValueError):
            await host.handle(dict(action,method='runtime.shutdown'))
        host.closed=True
        with self.assertRaises(RuntimeError):
            await host.handle({'v':1,'id':'later','method':'runtime.snapshot','args':{}})
