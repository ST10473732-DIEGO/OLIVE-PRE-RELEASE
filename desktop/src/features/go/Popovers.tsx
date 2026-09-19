import {useRef, useState} from 'react';
import {EyeOff, BrushCleaning, History, Star, Download, SlidersHorizontal, Search, SquareArrowOutUpRight, Minus, Plus, Lock, LockOpen, Globe} from 'lucide-react';
import type {BrowserTab} from '../../../electron/browser';
import {hostOf, useDismiss, useOverlay} from './shared';

/** The reference's Fire button, in OLIVE's words. */
export function ClearPopover({open, close, onPrivate, onClear}:{open:boolean; close:()=>void; onPrivate:()=>void; onClear:(scope:{history:boolean; cookies:boolean; cache:boolean})=>Promise<void>}) {
  const ref=useRef<HTMLDivElement>(null);
  const [confirm,setConfirm]=useState(false);
  const [scope,setScope]=useState({history:true,cookies:true,cache:true});
  const [busy,setBusy]=useState(false);
  useDismiss(ref, open, ()=>{close();setConfirm(false);});
  useOverlay(ref, open);
  if(!open) return null;
  return <div ref={ref} className="go-pop right" role="menu" aria-label="Clear">
    {!confirm ? <>
      <button type="button" className="go-pop-item" role="menuitem" onClick={()=>{close();onPrivate();}}>
        <span className="ico"><EyeOff size={16}/></span>
        <span><b>New private tab</b><small>Nothing from it is saved once it closes. Downloads stay; what you send to Chat is kept there.</small></span>
      </button>
      <div className="rule"/>
      <button type="button" className="go-pop-item" role="menuitem" onClick={()=>setConfirm(true)}>
        <span className="ico"><BrushCleaning size={16}/></span>
        <span><b>Clear browsing data…</b><small>History, cookies and site data for normal tabs. Favourites stay.</small></span>
      </button>
    </> : <>
      <div className="go-pop-title">Clear browsing data</div>
      <p>For OLIVE GO's normal tabs only. Nothing else in OLIVE is touched, and this is ordinary browser cleanup — not secure erasure.</p>
      {([['history','History and recently closed tabs'],['cookies','Cookies and site data (signs you out of sites)'],['cache','Cached files']] as const).map(([key,label])=>
        <label key={key} className="go-setting" style={{cursor:'pointer'}}>
          <input type="checkbox" checked={scope[key]} onChange={e=>setScope(s=>({...s,[key]:e.target.checked}))}/>
          <span className="l">{label}</span>
        </label>)}
      <div className="rule"/>
      <div style={{display:'flex',gap:8,justifyContent:'flex-end',padding:'4px 4px 2px'}}>
        <button type="button" className="go-btn ghost" onClick={()=>setConfirm(false)}>Cancel</button>
        <button type="button" className="go-btn primary" disabled={busy || !(scope.history||scope.cookies||scope.cache)} onClick={async()=>{setBusy(true);try{await onClear(scope);}finally{setBusy(false);setConfirm(false);close();}}}>{busy?'Clearing…':'Clear'}</button>
      </div>
    </>}
  </div>;
}

export function MainMenu({open, close, tab, onPanel, onFind, onZoom, onExternal, findText, setFindText, matches, findNext}:{
  open:boolean; close:()=>void; tab?:BrowserTab; onPanel:(panel:'history'|'favourites'|'downloads'|'customize')=>void;
  onFind:(text:string,next:boolean)=>void; onZoom:(factor:number)=>void; onExternal:()=>void;
  findText:string; setFindText:(v:string)=>void; matches:number; findNext:()=>void;
}) {
  const ref=useRef<HTMLDivElement>(null);
  useDismiss(ref, open, close);
  useOverlay(ref, open);
  if(!open) return null;
  const zoom=tab?.zoom||1, page=!!tab && tab.url!=='about:blank';
  const steps=[.5,.67,.75,.8,.9,1,1.1,1.25,1.5,1.75,2];
  const step=(dir:1|-1)=>{const i=steps.findIndex(s=>Math.abs(s-zoom)<0.01);const next=steps[Math.max(0,Math.min(steps.length-1,(i<0?5:i)+dir))];onZoom(next);};
  return <div ref={ref} className="go-pop right menu go-menu-compact" role="menu" aria-label="OLIVE GO menu">
    <button type="button" className="go-pop-item" role="menuitem" onClick={()=>{close();onPanel('history');}}><span className="ico"><History size={15}/></span><b>History</b><span className="k">Ctrl+H</span></button>
    <button type="button" className="go-pop-item" role="menuitem" onClick={()=>{close();onPanel('favourites');}}><span className="ico"><Star size={15}/></span><b>Favourites</b></button>
    <button type="button" className="go-pop-item" role="menuitem" onClick={()=>{close();onPanel('downloads');}}><span className="ico"><Download size={15}/></span><b>Downloads</b><span className="k">Ctrl+J</span></button>
    <div className="rule"/>
    <div className="go-zoom" aria-label="Page zoom">
      <button type="button" className="go-ib" aria-label="Zoom out" disabled={!page || zoom<=.5} onClick={()=>step(-1)}><Minus size={14}/></button>
      <span className="v">{Math.round(zoom*100)}%</span>
      <button type="button" className="go-ib" aria-label="Zoom in" disabled={!page || zoom>=2} onClick={()=>step(1)}><Plus size={14}/></button>
      <button type="button" className="go-btn ghost" style={{height:28,padding:'0 10px'}} disabled={!page || zoom===1} onClick={()=>onZoom(1)}>Reset</button>
    </div>
    <div className="go-find">
      <Search size={14} aria-hidden="true"/>
      <input aria-label="Find in page" placeholder="Find in page" disabled={!page} value={findText} onChange={e=>{setFindText(e.target.value);onFind(e.target.value,false);}} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();findNext();}}}/>
      <span className="n" aria-live="polite">{findText?matches:''}</span>
    </div>
    <div className="rule"/>
    <button type="button" className="go-pop-item" role="menuitem" onClick={()=>{close();onPanel('customize');}}><span className="ico"><SlidersHorizontal size={15}/></span><b>Customise</b></button>
    <button type="button" className="go-pop-item" role="menuitem" disabled={!page} onClick={()=>{close();onExternal();}}><span className="ico"><SquareArrowOutUpRight size={15}/></span><b>Open in system browser</b></button>
  </div>;
}

export function SiteInfo({open, close, tab}:{open:boolean; close:()=>void; tab?:BrowserTab}) {
  const ref=useRef<HTMLDivElement>(null);
  useDismiss(ref, open, close);
  useOverlay(ref, open);
  if(!open || !tab) return null;
  const host=hostOf(tab.url);
  return <div ref={ref} className="go-pop" role="dialog" aria-label="Site information" style={{left:'50%',transform:'translateX(-50%)',maxWidth:'min(340px, calc(100% - 20px))'}}>
    <div className="go-pop-title" style={{display:'flex',alignItems:'center',gap:8}}>
      {tab.secure==='https'?<Lock size={15} style={{color:'var(--olive)'}}/>:tab.secure==='http'?<LockOpen size={15}/>:<Globe size={15}/>}
      {host||'This page'}
    </div>
    <p>{tab.error?"This page didn't load, so there is no connection to describe.":tab.secure==='https'?'This page was delivered over an encrypted connection (HTTPS). That protects the data in transit; it says nothing about whether the site itself is trustworthy.':tab.secure==='http'?'This connection is not encrypted. Anything you enter here can be read on the way.':'No connection information for this page.'}</p>
    <div className="go-pop-title">Blocked for every site</div>
    <ul><li>Camera, microphone and location</li><li>Notifications and clipboard reading</li><li>USB, Bluetooth and serial devices</li><li>HTTP authentication prompts</li></ul>
    <p>Sites that need one of these open in your system browser.</p>
  </div>;
}
