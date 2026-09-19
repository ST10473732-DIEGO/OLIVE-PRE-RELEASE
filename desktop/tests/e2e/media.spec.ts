import {test,expect,_electron as electron} from '@playwright/test';
import {mkdtemp,mkdir,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {openSpace} from './shell';
import {captureMail} from './m4-capture';

test('REIMAGINE real image import, resize, preserved original and honest generation setup',async()=>{
  test.setTimeout(90000);
  const profile=await mkdtemp(path.join(tmpdir(),'olive-media-')),source=path.join(profile,'synthetic.png');
  await promisify(execFile)(path.resolve('../.venv/Scripts/python.exe'),['-c','from PIL import Image; import sys; Image.new("RGB",(80,60),"red").save(sys.argv[1])',source],{windowsHide:true});
  const original=await readFile(source);
  const app=await electron.launch({args:[path.resolve('.')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:1'}});
  try{
    const page=await app.firstWindow();await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();await openSpace(page,'Chat');
    await expect(page.getByLabel('OLIVE preset')).toBeEnabled({timeout:60000});await page.getByLabel('OLIVE preset').selectOption('reimagine');await page.getByRole('button',{name:'Open media tools',exact:true}).click();
    const sheet=page.getByRole('dialog',{name:'OLIVE REIMAGINE',exact:true});await expect(sheet).toContainText('Generation: Needs setup');
    await app.evaluate(({dialog},source)=>{dialog.showOpenDialog=async(first:Electron.BaseWindow|Electron.OpenDialogOptions,second?:Electron.OpenDialogOptions)=>{const options=second||(first as Electron.OpenDialogOptions);if(options.title!=='Preserve an original image for REIMAGINE')throw new Error('Unexpected file request');return {canceled:false,filePaths:[source]};};},source);
    await sheet.getByRole('button',{name:'Import original image',exact:true}).click();
    await expect(sheet.getByLabel('Media input')).not.toHaveValue('');await sheet.getByLabel('Media width').fill('32');await sheet.getByLabel('Media height').fill('24');await sheet.getByRole('button',{name:'Create output artifact',exact:true}).click();
    await expect(sheet.getByRole('status')).toContainText('completed',{timeout:15000});
    const status=await page.evaluate(()=>window.olive.call('media.status',{})) as {artifacts:{id:string;path:string;kind:string}[]};
    const output=status.artifacts.find(a=>a.kind==='image')!;expect(output).toBeTruthy();expect(await readFile(source)).toEqual(original);
    const verified=await promisify(execFile)(path.resolve('../.venv/Scripts/python.exe'),['-c','from PIL import Image; import sys; i=Image.open(sys.argv[1]); assert i.size==(32,24); assert i.getpixel((0,0))==(255,0,0,255); print("actual raster verified")',output.path],{windowsHide:true});expect(verified.stdout).toContain('actual raster verified');
    await sheet.getByRole('button',{name:'Inspect artifact',exact:true}).first().click();await expect(sheet.getByAltText('Selected media artifact')).toBeVisible();
    const evidence=path.resolve('../artifacts/core/functionality/media');await mkdir(evidence,{recursive:true});await captureMail(page,app,path.join(evidence,'image-edit.png'));
    await sheet.getByLabel('Media operation').selectOption('generate');await sheet.getByLabel('Media prompt').fill('A green olive on a white table');await expect(sheet.getByRole('button',{name:'Create output artifact',exact:true})).toBeDisabled();
    expect(status.artifacts).toHaveLength(2);
  }finally{await app.close();}
});
