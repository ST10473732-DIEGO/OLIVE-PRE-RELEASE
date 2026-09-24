"""Bounded, application-scoped AT-SPI observations; no global text harvesting."""
import time
import uuid

import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi, GLib
from .geometry import contains, intersection


class Accessibility:
    def __init__(self):
        Atspi.set_timeout(500, 1000)
        self.targets = {}
        self.revision = ''
        self.application = None
        self.window_geometry = None
        self.offset = (0, 0)

    def mapped_bounds(self, rect):
        return [rect.x + self.offset[0], rect.y + self.offset[1], rect.width, rect.height]

    def bind_geometry(self, pid, geometry):
        self.window_geometry = geometry
        self.offset = (0, 0)
        app = self.resolve(pid)
        frames = [app.get_child_at_index(i) for i in range(min(app.get_child_count(), 80))]
        frames = [w for w in frames if w and w.get_role() in (Atspi.Role.FRAME, Atspi.Role.WINDOW, Atspi.Role.DIALOG)
                  and w.get_state_set().contains(Atspi.StateType.ACTIVE)]
        if len(frames) != 1:
            return
        rect = frames[0].get_component_iface().get_extents(Atspi.CoordType.SCREEN)
        # Native Wayland Qt reports client-local coordinates for SCREEN. Bind
        # only when the independently observed KWin client dimensions agree.
        if rect.x == rect.y == 0 and [rect.width, rect.height] == geometry[2:]:
            self.offset = tuple(geometry[:2])

    def applications(self):
        desktop = Atspi.get_desktop(0)
        result = []
        for index in range(min(desktop.get_child_count(), 100)):
            app = desktop.get_child_at_index(index)
            if app is not None:
                result.append({'pid': app.get_process_id(), 'name': app.get_name()[:200]})
        return result

    def resolve(self, pid):
        desktop = Atspi.get_desktop(0)
        matches = [desktop.get_child_at_index(i) for i in range(min(desktop.get_child_count(), 100))]
        matches = [app for app in matches if app and app.get_process_id() == pid]
        if len(matches) != 1:
            raise LookupError('Requested application is not uniquely accessible')
        return matches[0]

    def activate(self, pid, region, stopped, timeout_ms=5000, allow_active_window=False):
        """Attempt one app-scoped native focus; wait for actual window/activation events.

        No KWin eval, fabricated activation token or repeated focus stealing. This
        is used once at task admission, never to undo a user's later focus change.
        """
        changed, expired = [True], [False]
        def event(value, *_):
            try:
                if value.source.get_process_id() == pid:
                    changed[0] = True
            except Exception:
                pass
        listener = Atspi.EventListener.new(event, None)
        names = ('window:create', 'window:activate', 'object:state-changed:showing')
        registered = []
        timer = None
        attempted = False
        try:
            for name in names:
                if listener.register(name):
                    registered.append(name)
            def expire():
                expired[0] = True
                return False
            timer = GLib.timeout_add(timeout_ms, expire)
            while not expired[0]:
                if stopped.is_set():
                    raise InterruptedError('Stopped while waiting for the requested application')
                if changed[0]:
                    changed[0] = False
                    try:
                        app = self.resolve(pid)
                    except LookupError:
                        app = None
                    windows = []
                    if app:
                        for index in range(min(app.get_child_count(), 80)):
                            node = app.get_child_at_index(index)
                            states = node.get_state_set() if node else None
                            if not states or not states.contains(Atspi.StateType.VISIBLE):
                                continue
                            if node.get_role() == Atspi.Role.DIALOG:
                                raise PermissionError('Requested app has a dialog; human handoff before focus')
                            if node.get_role() not in (Atspi.Role.FRAME, Atspi.Role.WINDOW):
                                continue
                            component = node.get_component_iface()
                            rect = component.get_extents(Atspi.CoordType.SCREEN) if component else None
                            if rect and contains(region, self.mapped_bounds(rect)):
                                windows.append(node)
                    if len(windows) > 1:
                        active = [w for w in windows if w.get_state_set().contains(Atspi.StateType.ACTIVE)]
                        if not allow_active_window or len(active) != 1:
                            raise ValueError('NEEDS_USER_CLARIFICATION: multiple windows of the requested app are visible')
                        windows = active
                    if len(windows) == 1:
                        node = windows[0]
                        if node.get_state_set().contains(Atspi.StateType.ACTIVE):
                            self.clear()
                            return {'pid': pid, 'active': True}
                        if not attempted:
                            attempted = True
                            # KWin activation precedes this accessibility event.
                            # Some Qt top-levels cannot grab focus themselves;
                            # wait for their real active-state event instead.
                            node.get_component_iface().grab_focus()
                            changed[0] = True
                            continue
                GLib.MainContext.default().iteration(True)
            raise TimeoutError('Requested application did not expose one active window within five seconds')
        finally:
            if timer and GLib.MainContext.default().find_source_by_id(timer):
                GLib.source_remove(timer)
            for name in registered:
                listener.deregister(name)

    def observe(self, pid, region, chrome_only=False):
        app = self.resolve(pid)
        self.targets, self.revision = {}, uuid.uuid4().hex
        self.application = pid
        deadline = time.monotonic() + 3
        controls, windows, documents = [], [], []
        text_budget = 12000
        queue = [(app, 0, '', '', False, region)]
        visited = 0
        while queue and visited < 800 and time.monotonic() < deadline and text_budget > 0:
            node, depth, window, parent, in_document, clip = queue.pop(0)
            visited += 1
            try:
                states = node.get_state_set()
                role = node.get_role()
                in_document = in_document or role in (Atspi.Role.DOCUMENT_WEB, Atspi.Role.DOCUMENT_FRAME)
                if chrome_only and in_document:
                    continue
                if states.contains(Atspi.StateType.DEFUNCT):
                    continue
                if role == Atspi.Role.PASSWORD_TEXT:
                    continue  # Neither name, value nor descendants enter an observation.
                visible = states.contains(Atspi.StateType.SHOWING) and states.contains(Atspi.StateType.VISIBLE)
                key = str(visited)
                component = node.get_component_iface()
                rect = component.get_extents(Atspi.CoordType.SCREEN) if component else None
                bounds = self.mapped_bounds(rect) if rect else None
                # GTK may expose a non-rendered viewport wrapper with sentinel
                # coordinates, while its visible children have real extents.
                # Inherit only the already observed scroll pane's exact clip.
                transparent_viewport = (role == Atspi.Role.VIEWPORT and rect and
                    states.contains(Atspi.StateType.VISIBLE) and rect.x == rect.y == -2147483648 and
                    [rect.width, rect.height] == list(clip[2:]))
                if depth > 0 and not visible and not transparent_viewport:
                    continue
                if depth == 1 and not states.contains(Atspi.StateType.ACTIVE):
                    continue
                within_source = depth == 0 or contains(clip, bounds)
                if not within_source:
                    # A clipped scroll-content container can extend outside the
                    # source while its children are visible inside it. Traverse
                    # geometry only; never read the container's out-of-source text.
                    if role not in (Atspi.Role.FILLER, Atspi.Role.PANEL, Atspi.Role.VIEWPORT,
                                    Atspi.Role.LIST, Atspi.Role.SCROLL_PANE):
                        continue
                if role in (Atspi.Role.FRAME, Atspi.Role.DIALOG, Atspi.Role.WINDOW):
                    window = key
                    windows.append({'id': key, 'name': node.get_name()[:200], 'bounds': bounds,
                                    'active': states.contains(Atspi.StateType.ACTIVE)})
                if visible and window and within_source:
                    value = ''
                    text = node.get_text_iface()
                    if text:
                        # Accessible.get_text is a deprecated interface getter;
                        # call the Text interface explicitly to avoid GI's name clash.
                        value = Atspi.Text.get_text(text, 0, min(text.get_character_count(), 2000))
                    elif role == Atspi.Role.COMBO_BOX and states.contains(Atspi.StateType.EDITABLE):
                        value = node.get_name()[:2000]
                    labels = self.labels(node)
                    actions = node.get_action_iface()
                    action_names = [actions.get_action_name(i) for i in range(min(actions.get_n_actions(), 8))] if actions else []
                    key_bindings = {actions.get_action_name(i): actions.get_key_binding(i)
                                    for i in range(min(actions.get_n_actions(), 8))} if actions else {}
                    document = node.get_document_iface()
                    if document:
                        uri = document.get_document_attribute_value('DocURL') or ''
                        if uri:
                            documents.append({'uri': uri[:2000], 'name': node.get_name()[:300]})
                    text_budget -= len(value) + len(node.get_name()[:300])
                    controls.append({'id': key, 'window': window, 'parent': parent, 'name': node.get_name()[:300],
                        'role': node.get_role_name(), 'in_document': in_document, 'value': value, 'bounds': bounds,
                        'enabled': states.contains(Atspi.StateType.ENABLED),
                        'selected': states.contains(Atspi.StateType.SELECTED),
                        'focused': states.contains(Atspi.StateType.FOCUSED),
                        'editable': states.contains(Atspi.StateType.EDITABLE), 'actions': action_names,
                        'key_bindings': key_bindings, 'labels': labels})
                    self.targets[key] = node
                if depth < 28:
                    child_clip = (clip if transparent_viewport else intersection(clip, bounds)) if role in (Atspi.Role.VIEWPORT, Atspi.Role.SCROLL_PANE) else clip
                    if child_clip is None:
                        continue
                    for index in range(min(node.get_child_count(), 80)):
                        child = node.get_child_at_index(index)
                        if child:
                            queue.append((child, depth + 1, window, key, in_document, child_clip))
            except Exception:
                continue  # Incomplete accessibility is evidence of a gap, never a target.
        return {'pid': pid, 'revision': self.revision, 'windows': windows, 'controls': controls,
                'documents': documents, 'incomplete': bool(queue), 'untrusted_content': True}

    def document_locations(self, pid, region):
        """Current document identity only; never read conversation/page contents."""
        app = self.resolve(pid)
        queue = [(app, 0)]; documents = []; visited = 0
        deadline = time.monotonic() + 3
        while queue and visited < 800 and time.monotonic() < deadline:
            node, depth = queue.pop(0); visited += 1
            states = node.get_state_set()
            if depth and not all(states.contains(s) for s in (Atspi.StateType.VISIBLE, Atspi.StateType.SHOWING)):
                continue
            if depth == 1 and not states.contains(Atspi.StateType.ACTIVE):continue
            role = node.get_role()
            if role in (Atspi.Role.DOCUMENT_WEB, Atspi.Role.DOCUMENT_FRAME):
                component = node.get_component_iface()
                rect = component.get_extents(Atspi.CoordType.SCREEN) if component else None
                document = node.get_document_iface()
                if document and rect and contains(region, self.mapped_bounds(rect)):
                    uri = document.get_document_attribute_value('DocURL') or ''
                    if uri:documents.append({'uri':uri[:2000], 'bounds':self.mapped_bounds(rect), 'ready':not states.contains(Atspi.StateType.BUSY) and node.get_child_count()>0})
                continue  # Page messages are not navigation evidence.
            if depth < 28:
                queue.extend((node.get_child_at_index(i), depth+1) for i in range(min(node.get_child_count(),80)) if node.get_child_at_index(i))
        return {'documents':documents,'incomplete':bool(queue)}

    def check(self, revision, target, bounds, region, require_focus=False):
        if revision != self.revision or target not in self.targets:
            raise ValueError('Stale observation or unknown target')
        node = self.targets[target]
        states = node.get_state_set()
        if node.get_process_id() != self.application or not all(states.contains(s) for s in
                (Atspi.StateType.SHOWING, Atspi.StateType.VISIBLE, Atspi.StateType.ENABLED)):
            raise ValueError('STALE: target state changed (' + ','.join(
                name for name, ok in [('application', node.get_process_id() == self.application),
                    ('showing', states.contains(Atspi.StateType.SHOWING)),
                    ('visible', states.contains(Atspi.StateType.VISIBLE)),
                    ('enabled', states.contains(Atspi.StateType.ENABLED))] if not ok) + '); no input')
        if states.contains(Atspi.StateType.DEFUNCT) or node.get_role() == Atspi.Role.PASSWORD_TEXT:
            raise PermissionError('Target is unavailable or secret')
        component = node.get_component_iface()
        rect = component.get_extents(Atspi.CoordType.SCREEN) if component else None
        if rect is None or self.mapped_bounds(rect) != bounds:
            raise ValueError('Target geometry changed; observe again')
        if not contains(region, bounds):
            raise PermissionError('Target left the approved display')
        parent = node
        active = False
        for _ in range(20):
            if not parent:
                break
            if parent.get_role() in (Atspi.Role.FRAME, Atspi.Role.DIALOG, Atspi.Role.WINDOW):
                active = parent.get_state_set().contains(Atspi.StateType.ACTIVE)
                break
            parent = parent.get_parent()
        if not active or (require_focus and not states.contains(Atspi.StateType.FOCUSED)):
            raise PermissionError('Target window/control lost focus; human handoff required')
        return node

    def clear(self):
        self.targets.clear()
        self.revision, self.application = '', None

    def hit_test(self, node, x, y):
        """Require the observed control or its descendant at the actual point."""
        parent = node
        for _ in range(20):
            if parent.get_role() in (Atspi.Role.FRAME, Atspi.Role.WINDOW, Atspi.Role.DIALOG):
                break
            parent = parent.get_parent()
            if not parent:
                raise ValueError('Target has no current accessible window')
        hit = parent.get_component_iface().get_accessible_at_point(
            int(x-self.offset[0]), int(y-self.offset[1]), Atspi.CoordType.SCREEN)
        for _ in range(32):
            if hit == node:
                return
            if not hit:
                break
            component = hit.get_component_iface()
            child = component.get_accessible_at_point(
                int(x-self.offset[0]), int(y-self.offset[1]), Atspi.CoordType.SCREEN)
            if child == hit:
                # Chromium's native wrapper may hit itself rather than delegate
                # to its web root. Descend only one visible child containing the
                # point. Overlapping siblings remain ambiguous, never first-match.
                children = []
                for index in range(min(hit.get_child_count(), 80)):
                    candidate = hit.get_child_at_index(index)
                    state = candidate.get_state_set() if candidate else None
                    part = candidate.get_component_iface() if candidate else None
                    if state and part and all(state.contains(s) for s in
                            (Atspi.StateType.SHOWING, Atspi.StateType.VISIBLE)) and part.contains(
                            int(x-self.offset[0]), int(y-self.offset[1]), Atspi.CoordType.SCREEN):
                        children.append(candidate)
                child = children[0] if len(children) == 1 else None
            if not child:
                # The deepest hit may be text belonging to the target.
                for _ in range(32):
                    if hit == node:
                        return
                    hit = hit.get_parent() if hit else None
                    if not hit:
                        break
                break
            hit = child
        raise ValueError('Target is occluded or accessibility hit-testing is unsupported')

    @staticmethod
    def labels(node):
        return [relation.get_target(i).get_name()[:100] for relation in (node.get_relation_set() or ())
                if relation.get_relation_type() == Atspi.RelationType.LABELLED_BY
                for i in range(min(relation.get_n_targets(), 4))]
