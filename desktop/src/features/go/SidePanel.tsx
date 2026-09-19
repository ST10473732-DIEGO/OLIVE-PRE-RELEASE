import {useEffect, useMemo, useRef, useState} from 'react';
import {X, Search, FileDown, FolderOpen, Pencil, Check, GripVertical, ExternalLink} from 'lucide-react';
import type {BrowserDownload, BrowserPreferences, BrowserRecord, SearchEngine} from '../../../electron/browser';
import {searchLabel, searchNote, searchEngines, suggestURL} from '../../../electron/browser';
import {hostOf, hostColor, hostLetter, dayLabel, formatBytes, type Invoke} from './shared';

export type Panel = 'history'|'favourites'|'downloads'|'customize';
const FINISHED = new Set(['completed','cancelled','interrupted']);

function RowIcon({favicon, url}:{favicon?:string; url:string}) {
  const host=hostOf(url);
  return <span className="go-favicon">{favicon?<img src={favicon} alt=""/>:<span style={{color:hostColor(host),fontWeight:600,fontSize:10}}>{hostLetter(host)}</span>}</span>;
}

function HistoryList({history, invoke, open, close}:{history:BrowserRecord[]; invoke:Invoke; open:(url:string,newTab?:boolean)=>void; close:()=>void}) {
  const [query,setQuery]=useState('');
  const [confirm,setConfirm]=useState(false);
  const q=query.trim().toLowerCase();
  const rows=useMemo(()=>[...history].reverse().filter(h=>!q || h.title.toLowerCase().includes(q) || h.url.toLowerCase().includes(q)),[history,q]);
  const groups:{day:string; items:BrowserRecord[]}[]=[];
  for(const item of rows){const day=dayLabel(item.time);const last=groups[groups.length-1];if(last && last.day===day)last.items.push(item);else groups.push({day,items:[item]});}
  return <>
    <label className="go-panel-search"><Search size={14} aria-hidden="true"/><input aria-label="Search history" placeholder="Search history" value={query} onChange={e=>setQuery(e.target.value)}/></label>
    <div className="go-panel-list">
      {!history.length && <div className="go-empty">Pages you visit in normal tabs appear here. Private tabs are never recorded.</div>}
      {history.length>0 && !rows.length && <div className="go-empty">Nothing in your history matches “{query}”.</div>}
      {groups.map(group=><div key={group.day}>
        <div className="go-day">{group.day}</div>
        {group.items.map(item=><div key={item.url+item.time} className="go-row" style={{paddingRight:4}}>
          <button type="button" className="go-row" style={{padding:0,height:'auto',flex:1,minWidth:0,background:'none'}} title={item.url} onClick={()=>{open(item.url);close();}} onAuxClick={e=>{if(e.button===1){e.preventDefault();open(item.url,true);}}}>
            <RowIcon favicon={item.favicon} url={item.url}/>
            <span className="t">{item.title||hostOf(item.url)}</span>
            <span className="u">{hostOf(item.url).replace(/^www\./,'')}</span>
          </button>
          <button type="button" className="go-ib" aria-label={`Remove ${item.title||item.url} from history`} onClick={()=>void invoke({action:'history-remove',url:item.url,time:item.time})}><X size={13}/></button>
        </div>)}
      </div>)}
    </div>
    <div className="go-panel-foot">
      {confirm ? <><span>Clear all history?</span><span style={{display:'flex',gap:10}}><button type="button" onClick={()=>setConfirm(false)}>Keep</button><button type="button" onClick={()=>{void invoke({action:'clear-history'});setConfirm(false);}}>Clear</button></span></>
        : <><span>{history.length} {history.length===1?'page':'pages'}</span><button type="button" disabled={!history.length} onClick={()=>setConfirm(true)}>Clear history</button></>}
    </div>
  </>;
}

function FavouritesList({favourites, invoke, open, close}:{favourites:BrowserRecord[]; invoke:Invoke; open:(url:string,newTab?:boolean)=>void; close:()=>void}) {
  const [editing,setEditing]=useState('');
  const [title,setTitle]=useState('');
  const drag=useRef<{url:string}|null>(null);
  const [over,setOver]=useState('');
  const reorder=(from:string,to:string)=>{
    if(from===to) return;
    const urls=favourites.map(f=>f.url);
    const a=urls.indexOf(from), b=urls.indexOf(to);
    if(a<0||b<0) return;
    urls.splice(a,1); urls.splice(b,0,from);
    void invoke({action:'favourite-reorder',urls});
  };
  return <>
    <div className="go-panel-list">
      {!favourites.length && <div className="go-empty">Save a page with the star in the address field, or press Ctrl+D. Your first twelve favourites become tiles on the new tab page, in this order.</div>}
      {favourites.map((item,index)=><div key={item.url}>
        <div className={`go-row ${over===item.url?'over':''}`} style={{paddingRight:4, outline: over===item.url ? '1px dashed var(--go-line-strong)' : undefined}}
          draggable onDragStart={e=>{drag.current={url:item.url};e.dataTransfer.effectAllowed='move';}} onDragOver={e=>{e.preventDefault();setOver(item.url);}} onDragLeave={()=>setOver('')} onDrop={e=>{e.preventDefault();setOver('');if(drag.current)reorder(drag.current.url,item.url);drag.current=null;}}>
          <span style={{color:'var(--faint)',cursor:'grab',display:'grid'}} aria-hidden="true"><GripVertical size={14}/></span>
          <button type="button" className="go-row" style={{padding:0,height:'auto',flex:1,minWidth:0,background:'none'}} title={item.url} onClick={()=>{open(item.url);close();}} onAuxClick={e=>{if(e.button===1){e.preventDefault();open(item.url,true);}}}>
            <RowIcon favicon={item.favicon} url={item.url}/>
            <span className="t">{item.title||hostOf(item.url)}</span>
            {index<12 && <span className="u" title="Shown on the new tab page">tile</span>}
          </button>
          <button type="button" className="go-ib" aria-label={`Rename ${item.title||item.url}`} onClick={()=>{setEditing(item.url);setTitle(item.title);}}><Pencil size={13}/></button>
          <button type="button" className="go-ib" aria-label={`Remove ${item.title||item.url} from favourites`} onClick={()=>void invoke({action:'favourite-remove',url:item.url})}><X size={13}/></button>
        </div>
        {editing===item.url && <form className="go-fav-edit" onSubmit={e=>{e.preventDefault();if(title.trim())void invoke({action:'favourite-rename',url:item.url,title:title.trim()});setEditing('');}}>
          <input aria-label="Favourite name" value={title} autoFocus onChange={e=>setTitle(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setEditing('');}}/>
          <button type="submit" className="go-ib" aria-label="Save name"><Check size={14}/></button>
        </form>}
      </div>)}
    </div>
    <div className="go-panel-foot"><span>{favourites.length} saved · drag to reorder</span></div>
  </>;
}

function DownloadRow({item, invoke}:{item:BrowserDownload; invoke:Invoke}) {
  const finished=FINISHED.has(item.state);
  const percent=item.total>0?Math.min(100,Math.round(item.received/item.total*100)):0;
  const label=item.state==='completed'?`${formatBytes(item.received)}${item.path?` · ${item.path.split(/[\\/]/).slice(-2,-1)[0]||'saved'}`:''}`
    : item.state==='cancelled'?'Cancelled'
    : item.state==='interrupted'?'Failed — the download was interrupted'
    : item.state==='choosing destination'?'Choose where to save it'
    : item.state==='paused'?`Paused · ${formatBytes(item.received)}${item.total?` of ${formatBytes(item.total)}`:''}`
    : `${formatBytes(item.received)}${item.total?` of ${formatBytes(item.total)}`:''}`;
  return <div className="go-dl">
    <span className="ico"><FileDown size={16}/></span>
    <div className="body">
      <div className="name" title={item.url}>{item.name}{item.private?' · private':''}</div>
      <div className={`meta ${item.state==='interrupted'?'error':''}`}>{label}</div>
      {!finished && <div className="bar"><i className={item.total>0?'':'indeterminate'} style={item.total>0?{width:`${percent}%`}:undefined}/></div>}
    </div>
    {!finished && <button type="button" className="go-ib" aria-label={`Cancel download ${item.name}`} title="Cancel" onClick={()=>void invoke({action:'download-cancel',id:item.id})}><X size={14}/></button>}
    {item.state==='completed' && item.path && <button type="button" className="go-ib" aria-label={`Show ${item.name} in folder`} title="Show in folder" onClick={()=>void invoke({action:'download-show',id:item.id})}><FolderOpen size={14}/></button>}
  </div>;
}

function DownloadsList({downloads, invoke}:{downloads:BrowserDownload[]; invoke:Invoke}) {
  const live=downloads.filter(d=>!FINISHED.has(d.state)).sort((a,b)=>b.started-a.started);
  const done=downloads.filter(d=>FINISHED.has(d.state)).sort((a,b)=>b.started-a.started);
  const groups:{day:string; items:BrowserDownload[]}[]=[];
  for(const item of done){const day=dayLabel(item.started);const last=groups[groups.length-1];if(last && last.day===day)last.items.push(item);else groups.push({day,items:[item]});}
  return <>
    <div className="go-panel-list">
      {!downloads.length && <div className="go-empty">Downloads from this session appear here. Every download asks where to save first and never opens itself.</div>}
      {live.map(item=><DownloadRow key={item.id} item={item} invoke={invoke}/>)}
      {groups.map(group=><div key={group.day}><div className="go-day">{group.day}</div>{group.items.map(item=><DownloadRow key={item.id} item={item} invoke={invoke}/>)}</div>)}
    </div>
    <div className="go-panel-foot"><span>This session only</span><button type="button" disabled={!done.length} onClick={()=>void invoke({action:'downloads-clear'})}>Clear finished</button></div>
  </>;
}

function Customize({preferences, invoke, openSettings, theme}:{preferences:BrowserPreferences; invoke:Invoke; openSettings:()=>void; theme:string}) {
  const set=(patch:Parameters<Invoke>[0] & {action:'preferences'})=>void invoke(patch);
  const Toggle=({label, small, on, onChange}:{label:string; small?:string; on:boolean; onChange:(v:boolean)=>void})=>
    <div className="go-setting"><span className="l">{label}{small && <small>{small}</small>}</span><button type="button" role="switch" aria-checked={on} aria-label={label} className="go-toggle" onClick={()=>onChange(!on)}/></div>;
  return <>
    <div className="go-panel-list">
      <div className="go-day">Search engine</div>
      <div role="radiogroup" aria-label="Search engine">
        {searchEngines.map(engine=><button key={engine} type="button" role="radio" aria-checked={preferences.engine===engine} className="go-setting go-radio" onClick={()=>set({action:'preferences',engine:engine as SearchEngine})}>
          <span className="l">{searchLabel(engine)}{searchNote(engine) && <small>{searchNote(engine)}</small>}</span>
          {preferences.engine===engine && <Check size={15} aria-hidden="true"/>}
        </button>)}
      </div>
      <Toggle label="Search suggestions" small={suggestURL(preferences.engine,'a')?`Sends what you type to ${searchLabel(preferences.engine)} as you type. Off in private tabs.`:`${searchLabel(preferences.engine)} offers no suggestions; only what this device already knows is shown.`} on={preferences.suggestions} onChange={v=>set({action:'preferences',suggestions:v})}/>
      <div className="go-day">New tab page</div>
      <Toggle label="Favourites" on={preferences.sections.favourites} onChange={v=>set({action:'preferences',sections:{favourites:v}})}/>
      <Toggle label="Recent" on={preferences.sections.recent} onChange={v=>set({action:'preferences',sections:{recent:v}})}/>
      <Toggle label="Quick actions" on={preferences.sections.quick} onChange={v=>set({action:'preferences',sections:{quick:v}})}/>
      <Toggle label="Ask OLIVE in the field" small="Shows the Ask OLIVE action in the address field and suggestions" on={preferences.sections.ask} onChange={v=>set({action:'preferences',sections:{ask:v}})}/>
      <div className="go-day">Appearance</div>
      <div className="go-setting"><span className="l">Theme<small>Follows OLIVE's theme</small></span><span className="v">{theme==='light'?'Light':'Dark'}</span></div>
    </div>
    <div className="go-panel-foot"><button type="button" onClick={openSettings}>All browser settings <ExternalLink size={12} style={{verticalAlign:'-2px'}}/></button><span>OLIVE Settings → Browser</span></div>
  </>;
}

export function SidePanel({panel, setPanel, history, favourites, downloads, preferences, invoke, open, openSettings, theme}:{
  panel:Panel; setPanel:(p:Panel|'')=>void; history:BrowserRecord[]; favourites:BrowserRecord[]; downloads:BrowserDownload[];
  preferences:BrowserPreferences; invoke:Invoke; open:(url:string,newTab?:boolean)=>void; openSettings:()=>void; theme:string;
}) {
  const ref=useRef<HTMLElement>(null);
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape' && ref.current?.contains(document.activeElement)){setPanel('');}};
    document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);
  },[setPanel]);
  const titles:Record<Panel,string>={history:'History',favourites:'Favourites',downloads:'Downloads',customize:'Customise'};
  return <aside ref={ref} className="go-panel" aria-label={titles[panel]}>
    <div className="go-panel-head"><h2>{titles[panel]}</h2><button type="button" className="go-ib" aria-label="Close panel" onClick={()=>setPanel('')}><X size={16}/></button></div>
    {panel!=='customize' && <div className="go-seg" role="tablist" aria-label="Panel">
      {(['history','favourites','downloads'] as const).map(p=><button key={p} type="button" role="tab" aria-selected={panel===p} onClick={()=>setPanel(p)}>{titles[p]}</button>)}
    </div>}
    {panel==='history' && <HistoryList history={history} invoke={invoke} open={open} close={()=>setPanel('')}/>}
    {panel==='favourites' && <FavouritesList favourites={favourites} invoke={invoke} open={open} close={()=>setPanel('')}/>}
    {panel==='downloads' && <DownloadsList downloads={downloads} invoke={invoke}/>}
    {panel==='customize' && <Customize preferences={preferences} invoke={invoke} openSettings={openSettings} theme={theme}/>}
  </aside>;
}
