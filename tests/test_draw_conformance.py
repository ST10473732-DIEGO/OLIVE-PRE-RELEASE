"""OLIVE Draw replica conformance: the shared fixture holds in any arrival order."""
import json
import random
import tempfile
import unittest
from pathlib import Path

from olive.draw import records
from olive.draw.service import DrawService

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'olive/draw/conformance_v1.json').read_text(encoding='utf-8'))
DEVICE = 'aaaaaaaa-0000-4000-8000-000000000001'


class ConformanceTests(unittest.TestCase):
    def test_python_store_matches_the_fixture_in_any_order(self):
        rng = random.Random(3)
        for scenario in FIXTURE['scenarios']:
            for attempt in range(12):
                order = list(scenario['records'])
                rng.shuffle(order)
                with self.subTest(scenario=scenario['name'], attempt=attempt), tempfile.TemporaryDirectory() as temp:
                    draw = DrawService(Path(temp) / 'drawings.sqlite3', device_id=DEVICE)
                    with draw.store.transaction() as db:
                        for record in order:
                            self.assertEqual(records.insert(db, record), 'applied')
                        for record in order:
                            self.assertEqual(records.insert(db, record), 'duplicate')
                    did = scenario['records'][0]['drawing_id']
                    info, ops = draw.get(did), draw.visible_ops(did)
                    background = next((op['value'] for op in reversed(ops) if op['type'] == 'background'), info['background'])
                    with draw.store.transaction(read_only=True) as db:
                        order_ids = [r[0] for r in db.execute(
                            "SELECT record_id FROM draw_records WHERE drawing_id=? AND kind='op' ORDER BY sort_key", (did,))]
                    expect = scenario['expect']
                    self.assertEqual(order_ids, expect['order'])
                    self.assertEqual([op['id'] for op in ops], expect['visible'])
                    self.assertEqual((info['title'], info['trashed'], background, info['width'], info['height']),
                                     (expect['title'], expect['trashed'], expect['background'], expect['width'], expect['height']))


if __name__ == '__main__':
    unittest.main()
