import {useEffect,useState} from 'react';
import {Sheet} from '../../components/Sheet';
import {call} from '../../services/api';
type Artifact={id:string;name:string;kind:string;path:string;sha256:string;source_id:string;provenance:unknown};
type Status={image_editing:string;image_generation:string;video_editing:string;generative_video:string;engine:{endpoint?:string;checkpoints?:string[]};artifacts:Artifact[];jobs:{id:string;state:string;progress:string;error:string;artifact?:Artifact}[]};
export function MediaTools({open,close}:{open:boolean;close:(value:boolean)=>void}) {
  const [status,setStatus]=useState<Status>(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [source,setSource]=useState(''),[operation,setOperation]=useState<'resize'|'crop'|'generate'|'image-to-image'>('resize');
  const [width,setWidth]=useState(512),[height,setHeight]=useState(512),[left,setLeft]=useState(0),[top,setTop]=useState(0);
  const [prompt,setPrompt]=useState(''),[checkpoint,setCheckpoint]=useState(''),[url,setUrl]=useState('http://127.0.0.1:8188');
  const [preview,setPreview]=useState(''),[details,setDetails]=useState<Artifact>();
  const refresh=()=>call<Status>('media.status',{}).then(setStatus).catch(e=>setError(String(e)));
  useEffect(()=>{if(!open)return;void refresh();const timer=setInterval(()=>void refresh(),1000);return()=>clearInterval(timer);},[open]);
  const generate=operation==='generate'||operation==='image-to-image';
  return <Sheet open={open} onOpenChange={close} title="OLIVE REIMAGINE" description="Create real local media artifacts. Original inputs are preserved.">
    <p>Image editing: {status?.image_editing||'Checking'}. Generation: {status?.image_generation||'Checking'}.</p>
    <p className="muted">Video editing: {status?.video_editing}. Generative video: {status?.generative_video}.</p>
    {error&&<p role="alert">{error}</p>}
    <div className="project-form">
      <button disabled={busy} onClick={()=>{setBusy(true);setError('');void window.olive.fileAction({action:'media-import'}).then(value=>{if(value)setSource((value as Artifact).id);return refresh();}).catch(e=>setError(String(e))).finally(()=>setBusy(false));}}>Import original image</button>
      <label>Input image<select aria-label="Media input" value={source} onChange={e=>setSource(e.target.value)}><option value="">Select a preserved image</option>{status?.artifacts.map(a=><option key={a.id} value={a.id}>{a.name} · {a.kind}</option>)}</select></label>
      <label>Operation<select aria-label="Media operation" value={operation} onChange={e=>setOperation(e.target.value as typeof operation)}><option value="resize">Resize image</option><option value="crop">Crop image</option><option value="generate">Generate image · ComfyUI</option><option value="image-to-image">Generative image edit · ComfyUI</option></select></label>
      <div className="row"><label>Width<input aria-label="Media width" type="number" min="16" max="2048" value={width} onChange={e=>setWidth(Number(e.target.value))}/></label><label>Height<input aria-label="Media height" type="number" min="16" max="2048" value={height} onChange={e=>setHeight(Number(e.target.value))}/></label></div>
      {operation==='crop'&&<div className="row"><label>Left<input aria-label="Crop left" type="number" min="0" value={left} onChange={e=>setLeft(Number(e.target.value))}/></label><label>Top<input aria-label="Crop top" type="number" min="0" value={top} onChange={e=>setTop(Number(e.target.value))}/></label></div>}
      {generate&&<><label>Prompt<textarea aria-label="Media prompt" value={prompt} onChange={e=>setPrompt(e.target.value)}/></label><label>Installed checkpoint<select value={checkpoint} onChange={e=>setCheckpoint(e.target.value)}><option value="">Choose the actual engine model</option>{status?.engine.checkpoints?.map(name=><option key={name}>{name}</option>)}</select></label><p className="muted">Fixed built-in workflow: one image, Euler sampler, 20 steps, CFG 7, seed 0. Image-to-image strength is 0.65. Use an ordinary compatible checkpoint; distilled/Turbo models need their own tuned workflow.</p></>}
      <button disabled={busy||(!source&&operation!=='generate')||(generate&&(!checkpoint||!prompt))} onClick={()=>{setBusy(true);setError('');void call('media.start',{request:{operation,source_id:source,width,height,left,top,prompt,checkpoint,seed:0,steps:20,cfg:7}}).then(refresh).catch(e=>setError(String(e))).finally(()=>setBusy(false));}}>Create output artifact</button>
    </div>
    {status?.jobs.map(job=><div key={job.id}><p role="status">{job.state} · {job.progress}</p>{job.error&&<p role="alert">{job.error}</p>}{['queued','running'].includes(job.state)&&<button onClick={()=>void call('media.cancel',{job_id:job.id}).then(refresh).catch(e=>setError(String(e)))}>Cancel media job</button>}</div>)}
    <h3>Artifacts</h3>{status?.artifacts.slice().reverse().map(a=><div key={a.id} className="row wrap"><span>{a.name} · {a.kind}</span><button onClick={()=>{setDetails(a);void call<{image:string}>('media.preview',{artifact_id:a.id}).then(r=>setPreview(r.image)).catch(e=>setError(String(e)));}}>Inspect artifact</button><button onClick={()=>void window.olive.fileAction({action:'media-export',artifact_id:a.id}).catch(e=>setError(String(e)))}>Export new copy</button></div>)}
    {details&&<div><img src={preview||undefined} alt="Selected media artifact" style={{maxWidth:'100%',maxHeight:350}}/><p className="small">SHA-256: {details.sha256}</p><pre style={{maxHeight:160,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(details.provenance,null,2)}</pre></div>}
    <details><summary>Local generation setup</summary><p>Use a dedicated ComfyUI instance bound to loopback, started with custom nodes disabled. Install a reviewed compatible checkpoint separately. This connection neither downloads dependencies nor enables hosted services.</p><label>Local engine address<input value={url} onChange={e=>setUrl(e.target.value)}/></label><button disabled={busy} onClick={()=>{setBusy(true);setError('');void call<Status>('media.configure',{url}).then(setStatus).catch(e=>setError(String(e))).finally(()=>setBusy(false));}}>Check dedicated local engine</button></details>
    {status?.engine.endpoint&&<button disabled={busy||status.jobs.some(j=>['queued','running'].includes(j.state))} onClick={()=>{setBusy(true);setError('');void call<Status>('media.disconnect',{}).then(value=>{setStatus(value);setCheckpoint('');}).catch(e=>setError(String(e))).finally(()=>setBusy(false));}}>Release and disconnect engine</button>}
  </Sheet>;
}
