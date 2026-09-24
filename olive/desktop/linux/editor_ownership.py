"""Task history binds a newly created Save As dialog, never its empty filename."""
from dataclasses import dataclass


@dataclass
class EditorOwnership:
    pid: int
    created: float
    document_window: str
    isolated: bool
    before_save: frozenset = frozenset()
    save_requested: bool = False
    dialog_id: str = ''

    def expect_save(self, windows):
        active = [w for w in windows if w.get('active')]
        if len(active) != 1 or active[0]['id'] != self.document_window or self.save_requested:
            raise PermissionError('The task document is no longer active')
        self.before_save = frozenset(w['id'] for w in windows)
        self.save_requested = True

    def admit(self, window, created, controls):
        if not self.save_requested or window['pid'] != self.pid or created != self.created:
            raise PermissionError('No matching task-owned save action')
        if self.dialog_id:
            if window['id'] != self.dialog_id:
                raise PermissionError('Save dialog identity changed')
            return
        labels = {c.get('name', '').casefold() for c in controls if c.get('enabled')}
        if not {'save', 'cancel'} <= labels or window['id'] in self.before_save:
            raise PermissionError('Pre-existing or unidentified save dialog preserved')
        if window.get('transient_for') != self.document_window and not self.isolated:
            raise PermissionError('Save dialog parent is not attributable to this task')
        self.dialog_id = window['id']
