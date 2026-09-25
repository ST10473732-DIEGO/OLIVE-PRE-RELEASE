"""Typed file-manager steps; no shell, arbitrary chords or repeatable paste."""
from pathlib import Path
from .kwin import windows


class FileInput:
    def __init__(self, source, destination, operation):
        if operation not in {'copy', 'move'} or any(not isinstance(p, str) or not Path(p).is_absolute() or any(ord(c)<32 for c in p) for p in (source, destination)):
            raise ValueError('Invalid file transfer scope')
        self.source, self.destination, self.operation = source, destination, operation
        self.stage = 0

    def step(self, worker, step, value):
        stages = ('new_tab', 'address', 'path', 'open', 'select', self.operation, 'address', 'path', 'open', 'paste')
        if self.stage >= len(stages) or step != stages[self.stage]:
            raise PermissionError('File operation is stale or out of sequence')
        current = [w for w in windows(worker.portal.bus, worker.window['pid'], worker.stopped) if w['active']]
        if len(current) != 1 or any(current[0][k] != worker.window[k] for k in ('id', 'bounds', 'output')):
            raise PermissionError('File manager focus or geometry changed')
        if step == 'path':
            expected = str(Path(self.source).parent) if self.stage == 2 else self.destination
            if value != expected:
                raise PermissionError('Folder path is outside this transfer')
        elif value:
            raise ValueError('Unexpected file operation value')
        self.stage += 1
        if step == 'select':
            observation = worker.accessibility.observe(worker.window['pid'], worker.eis.region,
                                                       item=Path(self.source).name)
            candidates = [c for c in observation['controls'] if c.get('name') == Path(self.source).name
                          and c.get('role') in {'icon','list item','table cell'} and c.get('enabled')]
            if len(candidates) != 1:
                raise ValueError('File selection target is not unique')
            target = candidates[0]
            node = worker.accessibility.check(observation['revision'], target['id'], target['bounds'], worker.eis.region)
            parent = node.get_parent()
            selection = parent.get_selection_iface() if parent else None
            if not selection or not selection.clear_selection() or not selection.select_child(node.get_index_in_parent()):
                raise ValueError('The file manager did not expose a verified semantic selection')
            worker.accessibility.revision = ''
        elif step == 'path':
            observation = worker.accessibility.observe(worker.window['pid'], worker.eis.region)
            fields = [c for c in observation['controls'] if c.get('focused') and c.get('editable')
                      and worker.accessibility.targets[c['id']].get_editable_text_iface()]
            if len(fields) != 1:
                raise PermissionError('A unique editable location field is required')
            field = fields[0]
            node = worker.accessibility.check(observation['revision'], field['id'], field['bounds'],
                                             worker.eis.region, require_focus=True)
            if not node.get_editable_text_iface().set_text_contents(value):
                raise ValueError('The visible location field rejected the requested folder')
            worker.accessibility.revision = ''
        else:
            worker.eis.chord_codes({'new_tab':[29,20], 'address':[29,38], 'open':[28],
                'copy':[29,46], 'move':[29,45], 'paste':[29,47]}[step])
        return {'dispatched': True}
