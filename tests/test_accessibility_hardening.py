"""Qt/Kate observation hardening against a fake AT-SPI tree (no live session)."""
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROLES = ('FRAME', 'WINDOW', 'DIALOG', 'DOCUMENT_WEB', 'DOCUMENT_FRAME', 'PASSWORD_TEXT', 'VIEWPORT', 'SCROLL_PANE',
         'FILLER', 'PANEL', 'LIST', 'COMBO_BOX', 'TABLE', 'TREE_TABLE', 'TREE', 'LIST_BOX', 'PUSH_BUTTON',
         'TABLE_CELL', 'TEXT', 'APPLICATION')
STATES = ('VISIBLE', 'SHOWING', 'ACTIVE', 'DEFUNCT', 'ENABLED', 'SELECTED', 'FOCUSED', 'EDITABLE', 'BUSY')


class Node:
    def __init__(self, role, name='', children=(), states=('VISIBLE', 'SHOWING', 'ENABLED'), bounds=(10, 10, 50, 20),
                 toolkit='', fail=None):
        self.role, self.name, self.children = role, name, list(children)
        self.states, self.bounds, self.toolkit, self.fail = set(states), bounds, toolkit, fail
        self.child_reads = 0
        self.text_reads = 0

    def _check(self):
        if self.fail:
            raise self.fail

    def get_role(self):
        self._check()
        return self.role

    def get_role_name(self):
        return self.role.lower().replace('_', ' ')

    def get_name(self):
        return self.name

    def get_state_set(self):
        self._check()
        return SimpleNamespace(contains=lambda state: state in self.states)

    def get_component_iface(self):
        return SimpleNamespace(get_extents=lambda _: SimpleNamespace(
            x=self.bounds[0], y=self.bounds[1], width=self.bounds[2], height=self.bounds[3]))

    def get_child_count(self):
        return len(self.children)

    def get_child_at_index(self, index):
        self.child_reads += 1
        return self.children[index]

    def get_text_iface(self):
        self.text_reads += 1
        return None

    def get_action_iface(self):
        return None

    def get_document_iface(self):
        return None

    def get_relation_set(self):
        return []

    def get_toolkit_name(self):
        return self.toolkit


class HardenedObservationTests(unittest.TestCase):
    def setUp(self):
        gi, repository = ModuleType('gi'), ModuleType('gi.repository')
        gi.require_version = Mock()
        atspi = SimpleNamespace(set_timeout=Mock(), Role=SimpleNamespace(**{r: r for r in ROLES}),
                                StateType=SimpleNamespace(**{s: s for s in STATES}),
                                CoordType=SimpleNamespace(SCREEN=0), RelationType=SimpleNamespace(LABELLED_BY=1),
                                Text=SimpleNamespace(get_text=Mock(return_value='')))
        repository.Atspi, repository.GLib = atspi, SimpleNamespace()
        path = Path(__file__).resolve().parents[1] / 'olive/desktop/linux/accessibility.py'
        spec = importlib.util.spec_from_file_location('olive.desktop.linux._hardened_accessibility', path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'gi': gi, 'gi.repository': repository}):
            spec.loader.exec_module(self.module)
        self.access = self.module.Accessibility()
        self.region = [0, 0, 2000, 2000]

    def app(self, toolkit, view_role='TABLE', rows=1000, fail=None):
        self.rows = [Node('TABLE_CELL', f'file{i}.txt', bounds=(20, 40 + i, 40, 1)) for i in range(rows)]
        self.rows[3].name = 'report.pdf'
        self.view = Node(view_role, 'Files', self.rows, bounds=(10, 30, 500, 1500))
        self.save = Node('PUSH_BUTTON', 'Save', fail=fail)
        self.filename = Node('TEXT', 'File name', states=('VISIBLE', 'SHOWING', 'ENABLED', 'EDITABLE'))
        window = Node('DIALOG', 'Save File — Kate', [self.view, self.filename, self.save],
                      states=('VISIBLE', 'SHOWING', 'ACTIVE', 'ENABLED'), bounds=(0, 0, 1000, 1800))
        root = Node('APPLICATION', 'kate', [window], toolkit=toolkit, bounds=(0, 0, 1000, 1800))
        self.access.resolve = Mock(return_value=root)
        return root

    def test_qt_item_views_are_not_enumerated_or_read(self):
        self.app('Qt')
        result = self.access.observe(4242, self.region)
        self.assertEqual(result['profile'], 'qt')
        self.assertEqual(result['pruned_item_views'], 1)
        self.assertEqual(self.view.child_reads, 0)
        self.assertTrue(all(row.text_reads == 0 for row in self.rows))
        names = {c['name'] for c in result['controls']}
        self.assertTrue({'Save', 'File name', 'Files'} <= names)
        self.assertFalse(any(n.startswith('file') for n in names))

    def test_exact_item_query_reads_names_only_within_budget(self):
        self.app('Qt', rows=600)
        self.rows[5].states.add('SELECTED')
        result = self.access.observe(4242, self.region, item='report.pdf')
        rows = [c for c in result['controls'] if c['role'] == 'table cell']
        self.assertEqual(sorted(c['name'] for c in rows), ['file5.txt', 'report.pdf'])
        self.assertEqual(self.view.child_reads, self.module.ITEM_QUERY_ROWS)
        self.assertTrue(all(row.text_reads == 0 for row in self.rows))

    def test_gtk_lists_keep_existing_semantics(self):
        self.app('GTK', view_role='LIST', rows=5)
        result = self.access.observe(4242, self.region)
        self.assertEqual(result['profile'], 'default')
        self.assertIn('report.pdf', {c['name'] for c in result['controls']})

    def test_vanished_app_aborts_immediately_and_is_never_reread(self):
        self.app('Qt', fail=RuntimeError('atspi_error: The application no longer exists'))
        with patch.object(self.module, '_alive', return_value=False):
            with self.assertRaises(self.module.ObservationAborted) as raised:
                self.access.observe(4242, self.region)
        self.assertEqual(raised.exception.category, 'APP_CRASHED_DURING_OBSERVATION')
        self.assertEqual(self.access.revision, '')
        self.access.resolve.reset_mock()
        with self.assertRaises(self.module.ObservationAborted):
            self.access.observe(4242, self.region)
        self.access.resolve.assert_not_called()
        # A replacement Qt process gets the smaller degraded traversal profile.
        self.app('Qt')
        self.assertEqual(self.access.observe(5555, self.region)['profile'], 'qt_degraded')

    def test_bus_error_on_live_app_stops_this_traversal_without_blacklisting(self):
        self.app('Qt', fail=RuntimeError('GDBus.Error:org.freedesktop.DBus.Error.NoReply: timeout'))
        with patch.object(self.module, '_alive', return_value=True):
            with self.assertRaises(self.module.ObservationAborted) as raised:
                self.access.observe(4242, self.region)
        self.assertEqual(raised.exception.category, 'ACCESSIBILITY_BUS_ERROR')
        self.assertNotIn(4242, self.access.crashed)

    def test_benign_interface_error_is_a_gap_not_an_abort(self):
        self.app('Qt', fail=RuntimeError('org.freedesktop.DBus.Error.UnknownMethod'))
        with patch.object(self.module, '_alive', return_value=True):
            result = self.access.observe(4242, self.region)
        self.assertNotIn('Save', {c['name'] for c in result['controls']})

    def test_repeated_scans_are_rate_limited(self):
        self.app('Qt')
        with patch.object(self.module.time, 'sleep') as sleep:
            self.access.observe(4242, self.region)
            self.access.observe(4242, self.region)
        sleep.assert_called_once()
        self.assertLessEqual(sleep.call_args.args[0], self.module.MIN_INTERVAL)


if __name__ == '__main__':
    unittest.main()


class DocumentPriorityTests(HardenedObservationTests):
    def test_showing_page_content_is_read_before_extra_browser_chrome(self):
        panels = [Node('PANEL', f'tabs {p}', [Node('PUSH_BUTTON', f'Tab {p}.{i}') for i in range(80)]) for p in range(12)]
        link = Node('PUSH_BUTTON', 'OLIVE Field Guide')
        page = Node('DOCUMENT_WEB', 'Owned results page', [link])
        window = Node('FRAME', 'Firefox', [*panels, page],
                      states=('VISIBLE', 'SHOWING', 'ACTIVE', 'ENABLED'), bounds=(0, 0, 1000, 1800))
        self.access.resolve = Mock(return_value=Node('APPLICATION', 'Firefox', [window], toolkit='Gecko',
                                                     bounds=(0, 0, 1000, 1800)))
        result = self.access.observe(4242, self.region)
        self.assertIn('OLIVE Field Guide', {c['name'] for c in result['controls']})
        self.assertTrue(result['incomplete'])
