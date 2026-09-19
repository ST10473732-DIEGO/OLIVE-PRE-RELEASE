import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.studio_tooling import winforms


def control(kind,name,parent=''):
    return {'id':'id_'+name,'name':name,'type':kind,'parent':parent,'x':16,'y':16,'width':120,'height':32,
            'text':name,'checked':False,'items':[],'dock':'None','handler':''}


class WinFormsDesignerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        async def deny(request):return ConfirmationResponse(False)
        self.s=ServiceContainer(lambda *args:None,deny,self.root/'profile',migrate=False)
        winforms.create(self.root/'App','Synthetic Form','net10.0')
        self.workspace=self.s.data.create_workspace('Fixture',str(self.root/'App'))
        self.designer=self.s.studio_tooling.designer

    async def asyncTearDown(self):
        await self.s.shutdown();self.temp.cleanup()

    async def test_event_code_survives_reopen_and_external_divergence_blocks_save(self):
        initial=await self.designer.call(self.workspace['id'])
        layout=initial['layout'];button=control('Button','calculate');button['handler']='Calculate_Click';layout['controls']=[button]
        saved=await self.designer.call(self.workspace['id'],layout,initial['revision'])
        event=self.root/'App/Events/Calculate_Click.cs';event.write_text(event.read_text().replace('// Add your C# event code here.','Text = "User code retained";'))
        expected=event.read_bytes();layout['controls'][0]['text']='Compute'
        await self.designer.call(self.workspace['id'],layout,saved['revision'])
        self.assertEqual(event.read_bytes(),expected)
        opened=await self.designer.call(self.workspace['id']);self.assertEqual(opened['layout']['controls'][0]['text'],'Compute')
        generated=self.root/'App'/winforms.GENERATED;generated.write_text(generated.read_text()+'// external edit\n')
        divergent=await self.designer.call(self.workspace['id']);self.assertTrue(divergent['diverged'])
        with self.assertRaises(PermissionError):await self.designer.call(self.workspace['id'],layout,opened['revision'])
        self.assertTrue(generated.read_text().endswith('// external edit\n'));self.assertEqual(event.read_bytes(),expected)

    async def test_stale_revision_dirty_buffer_and_scoped_deny_keep_files(self):
        opened=await self.designer.call(self.workspace['id']);layout=opened['layout'];layout['controls']=[control('Label','result')]
        saved=await self.designer.call(self.workspace['id'],layout,opened['revision'])
        with self.assertRaises(PermissionError):await self.designer.call(self.workspace['id'],layout,opened['revision'])
        service=self.s.studio.service(self.workspace['id']);service.open_file(winforms.GENERATED);service.update(winforms.GENERATED,'// user typing')
        before=(self.root/'App'/winforms.GENERATED).read_bytes()
        with self.assertRaises(PermissionError):await self.designer.call(self.workspace['id'],layout,saved['revision'])
        self.assertEqual((self.root/'App'/winforms.GENERATED).read_bytes(),before)
        self.s.permissions.save({},scopes=[{'permission':'filesystem.read','path':str(self.root/'App'/winforms.GENERATED),'decision':'deny'}])
        with self.assertRaises(PermissionError):await self.designer.call(self.workspace['id'])

    def test_safe_subset_rejects_cycles_unknown_code_and_event_path_escapes(self):
        layout=json.loads(winforms.initial_files('Fixture','net10.0')[winforms.MANIFEST]);panel=control('Panel','panel');panel['parent']=panel['id'];layout['controls']=[panel]
        with self.assertRaises(ValueError):winforms.generate(layout)
        panel['parent']='';panel['handler']='../steal'
        with self.assertRaises(ValueError):winforms.generate(layout)
        panel['handler']='';panel['constructor']='arbitrary()'
        with self.assertRaises(ValueError):winforms.generate(layout)

    async def test_all_supported_controls_compile_with_the_installed_sdk(self):
        import shutil
        if not shutil.which('dotnet'):self.skipTest('Installed .NET SDK required')
        layout=(await self.designer.call(self.workspace['id']))
        layout['layout']['controls']=[control(kind,kind.lower()+'1') for kind in winforms.CONTROLS]
        await self.designer.call(self.workspace['id'],layout['layout'],layout['revision'])
        from olive.services.run_service import RunService,ExecutionPolicy
        environment=RunService.dotnet_environment(str(self.root/'App'),ExecutionPolicy('approved').environment())
        process=await asyncio.create_subprocess_exec('dotnet','build','App.csproj','--nologo',cwd=self.root/'App',env=environment,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        output,_=await asyncio.wait_for(process.communicate(),60)
        self.assertEqual(process.returncode,0,output.decode(errors='replace'))
        self.assertTrue((self.root/'App/bin/Debug/net10.0-windows/App.exe').is_file())
