import unittest
from PIL import Image, ImageDraw
from olive.desktop.target_region import filled_region, semantic_target, TargetState
from olive.desktop.visual_targets import validate_point

class TargetRegionTests(unittest.TestCase):
    def test_left_aligned_label_accepts_control_center_not_adjacent_control(self):
        image = Image.new('RGB',(640,400),'white')
        d = ImageDraw.Draw(image)
        d.rectangle((20,40,320,100),fill='#326cab')
        d.rectangle((325,40,550,100),fill='#326cab')
        label = (35,55,130,80)
        d.rectangle(label,fill='white')
        region = filled_region(image,label,[label])
        self.assertEqual(region,(20,40,321,101))
        frame = {'width':640,'height':400}
        self.assertEqual(validate_point({'action':'left_click','coordinate':[400,175]},frame,region),(256,70))
        with self.assertRaises(ValueError):
            validate_point({'action':'left_click','coordinate':[700,175]},frame,region)

    def test_background_shared_panel_and_occluded_label_abstain(self):
        image=Image.new('RGB',(640,400),'white')
        box=(35,55,130,80)
        self.assertIsNone(filled_region(image,box,[box]))
        d=ImageDraw.Draw(image);d.rectangle((20,40,550,100),fill='blue')
        self.assertIsNone(filled_region(image,box,[box,(330,55,430,80)]))
        d.rectangle((90,40,550,100),fill='white')
        self.assertIsNone(filled_region(image,box,[box]))

    def test_semantic_states_identity_and_coordinate_space(self):
        c={'id':'a','name':'Save copy','role':'push button','enabled':True,'bounds':[-1900,100,300,60]}
        o={'revision':'new','controls':[c]}
        self.assertEqual(semantic_target(o,'Save copy').bounds,(-1900,100,-1600,160))
        self.assertEqual(semantic_target(o,'Save copy','old').state,TargetState.STALE)
        self.assertEqual(semantic_target(o,'Missing').state,TargetState.NOT_VISIBLE_HERE)
        o['controls'].append(dict(c,id='b'))
        self.assertEqual(semantic_target(o,'Save copy').state,TargetState.AMBIGUOUS)
        o['controls'].pop();c['enabled']=False
        self.assertEqual(semantic_target(o,'Save copy').state,TargetState.NOT_ACTIONABLE)
        c['enabled']=True;c['occluded']=True
        self.assertEqual(semantic_target(o,'Save copy').state,TargetState.NOT_ACTIONABLE)

    def test_native_button_keyboard_activation_requires_exact_focus(self):
        from types import SimpleNamespace
        from olive.desktop.task_authority import TaskScope,validate_effect
        from olive.desktop.grounded_steps import next_step
        target={'id':'copy','name':'Copy python code','role':'button','enabled':True,'focused':False,'bounds':[10,10,80,25]}
        scope=TaskScope('Owned app','click','Copy python code');grant=SimpleNamespace(scope=scope)
        observation={'revision':'new','controls':[target]}
        focus=next_step(scope,observation,False);self.assertEqual(focus['action'],'focus')
        target['focused']=True
        press=next_step(scope,observation,False)
        self.assertEqual((press['action'],press['value']),('key','Space'))
        self.assertFalse(validate_effect(grant,press,observation)[1])
        target['name']='Different button'
        with self.assertRaises(PermissionError):validate_effect(grant,press,observation)


class StaticTextNameTests(unittest.TestCase):
    """A status label repeating a control's name is not a second click target."""

    def test_same_named_label_does_not_compete_with_the_control(self):
        button = {'id': 'b', 'name': 'Cobalt', 'role': 'push button', 'enabled': True, 'bounds': [16, 416, 728, 33]}
        label = {'id': 'l', 'name': 'Cobalt', 'role': 'label', 'enabled': True, 'bounds': [16, 505, 728, 19]}
        o = {'revision': 'r', 'controls': [button, label]}
        self.assertEqual(semantic_target(o, 'Cobalt').identity, 'b')
        o['controls'].append(dict(button, id='b2'))
        self.assertEqual(semantic_target(o, 'Cobalt').state, TargetState.AMBIGUOUS)
        self.assertEqual(semantic_target({'revision': 'r', 'controls': [label]}, 'Cobalt').state, TargetState.UNSUPPORTED)

    def test_label_only_match_still_navigates_to_an_off_screen_control(self):
        from olive.desktop.grounded_steps import next_step
        from olive.desktop.task_authority import TaskScope
        scope = TaskScope('Owned app', 'click', 'Cobalt')
        label = {'id': 'l', 'name': 'Cobalt', 'role': 'label', 'enabled': True, 'bounds': [16, 505, 728, 19]}
        pane = {'id': 's', 'name': '', 'role': 'scroll pane', 'enabled': True, 'bounds': [16, 213, 728, 236]}
        step = next_step(scope, {'revision': 'r', 'controls': [label, pane]}, False)
        self.assertEqual((step['action'], step['target']), ('scroll', 's'))
        button = {'id': 'b', 'name': 'Cobalt', 'role': 'push button', 'enabled': True, 'focused': False,
                  'bounds': [16, 416, 728, 33]}
        step = next_step(scope, {'revision': 'r', 'controls': [label, pane, button]}, False)
        self.assertEqual((step['action'], step['target']), ('focus', 'b'))


class BrowserTabMirrorTests(unittest.TestCase):
    def test_tab_titled_like_a_page_link_does_not_compete_with_the_link(self):
        from olive.desktop.grounded_steps import next_step
        from olive.desktop.task_authority import TaskScope
        scope = TaskScope('Firefox', 'click', 'OLIVE Field Guide')
        tab = {'id': 't', 'name': 'OLIVE Field Guide', 'role': 'page tab', 'enabled': True, 'in_document': False,
               'bounds': [3302, 0, 173, 44], 'actions': ['switch']}
        link = {'id': 'l', 'name': 'OLIVE Field Guide', 'role': 'link', 'enabled': True, 'in_document': True,
                'bounds': [1928, 256, 183, 30], 'actions': ['jump']}
        step = next_step(scope, {'revision': 'r', 'controls': [tab, link]}, False)
        self.assertEqual((step['action'], step['target'], step['value']), ('invoke', 'l', 'jump'))
        twin = dict(link, id='l2', bounds=[1928, 300, 183, 30])
        self.assertIsNone(next_step(scope, {'revision': 'r', 'controls': [tab, link, twin]}, False))
        # Without a page element of that name, a tab is not silently chosen either.
        other = dict(tab, id='t2')
        self.assertIsNone(next_step(scope, {'revision': 'r', 'controls': [tab, other]}, False))
