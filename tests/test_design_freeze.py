import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.check_design_freeze import verify

class DesignFreezeTests(unittest.TestCase):
    def test_detects_untracked_additions_deletions_and_modifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(['git','init','-q',str(root)],check=True)
            frozen=root/'desktop/src';frozen.mkdir(parents=True)
            for name in ['edit.ts','delete.ts']:(frozen/name).write_text('original')
            subprocess.run(['git','add','.'],cwd=root,check=True)
            tree=subprocess.check_output(['git','write-tree'],cwd=root,text=True).strip()
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps({'design_base':tree,'roots':['desktop/src'],'sha256':{f'desktop/src/{name}':hashlib.sha256(b'original').hexdigest() for name in ['edit.ts','delete.ts']}}))
            self.assertEqual(verify(root,manifest)['changed'],[])
            (frozen/'edit.ts').write_text('changed')
            (frozen/'delete.ts').unlink()
            (frozen/'new.ts').write_text('untracked')
            result=verify(root,manifest)
            self.assertEqual(result['added'],['desktop/src/new.ts'])
            self.assertEqual(result['deleted'],['desktop/src/delete.ts'])
            self.assertEqual(result['changed'],['desktop/src/edit.ts'])
            replacement = root/'replacement'
            frozen.rename(replacement)
            try:
                frozen.symlink_to(replacement, target_is_directory=True)
            except OSError:
                return  # Windows without symlink privilege; byte checks above still ran.
            result=verify(root,manifest)
            self.assertEqual(result['added'],['desktop/src'])
            self.assertEqual(result['deleted'],['desktop/src/delete.ts','desktop/src/edit.ts'])
