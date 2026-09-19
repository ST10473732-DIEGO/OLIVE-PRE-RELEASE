import {useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type MouseEvent as ReactMouseEvent} from 'react';
import {Plus, X, BrushCleaning, Pin, PinOff, Copy, RotateCcw, EyeOff} from 'lucide-react';
import type {BrowserTab} from '../../../electron/browser';
import {OLIVE_MARK, hostOf, hostColor, hostLetter, useDismiss, useOverlay} from './shared';

type Actions = {
  select:(id:string)=>void; close:(id:string)=>void; add:(after?:string)=>void; addPrivate:()=>void; reopen:()=>void;
  pin:(id:string,pinned:boolean)=>void; duplicate:(id:string)=>void; move:(id:string,index:number)=>void;
  closeOthers:(id:string)=>void; closeRight:(id:string)=>void; openClear:()=>void; clearOpen:boolean;
};

function TabIcon({tab}:{tab:BrowserTab}) {
  if(tab.loading && tab.url!=='about:blank') return <span className="go-favicon"><span className="go-spinner" aria-hidden="true"/></span>;
  if(tab.url==='about:blank') return <span className="go-favicon"><img src={OLIVE_MARK} alt=""/></span>;
  if(tab.favicon) return <span className="go-favicon"><img src={tab.favicon} alt=""/></span>;
  const host=hostOf(tab.url);
  return <span className="go-favicon" style={{background:hostColor(host),color:'#fff',fontSize:9,fontWeight:600}}>{hostLetter(host)}</span>;
}

export function TabStrip({tabs, active, closed, actions}:{tabs:BrowserTab[]; active:string; closed:number; actions:Actions}) {
  const [menu,setMenu]=useState<{id:string; x:number; y:number}|null>(null);
  const [dragging,setDragging]=useState('');
  const [fresh,setFresh]=useState<Set<string>>(new Set());
  const known=useRef<Set<string>>(new Set());
  const menuRef=useRef<HTMLDivElement>(null);
  const scroller=useRef<HTMLDivElement>(null);
  const drag=useRef<{id:string; startX:number; moved:boolean}|null>(null);
  const anyPrivate=tabs.some(t=>t.private);
  useDismiss(menuRef, !!menu, ()=>setMenu(null));
  useOverlay(menuRef, !!menu);
  // Tabs that just appeared grow in; everything already known stays still.
  useEffect(()=>{
    const added=tabs.filter(t=>!known.current.has(t.id)).map(t=>t.id);
    for(const tab of tabs) known.current.add(tab.id);
    if(added.length && known.current.size>added.length){setFresh(new Set(added));const t=setTimeout(()=>setFresh(new Set()),200);return()=>clearTimeout(t);}
  },[tabs]);
  useEffect(()=>{
    const el=scroller.current?.querySelector<HTMLElement>('.go-tab.active');
    el?.scrollIntoView({block:'nearest',inline:'nearest'});
  },[active, tabs.length]);
  const onPointerDown=(event:ReactPointerEvent<HTMLDivElement>, id:string)=>{
    if(event.button!==0) return;
    drag.current={id,startX:event.clientX,moved:false};
  };
  const onPointerMove=(event:ReactPointerEvent<HTMLDivElement>)=>{
    const d=drag.current; if(!d) return;
    if(!d.moved && Math.abs(event.clientX-d.startX)>6){d.moved=true;setDragging(d.id);(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);}
  };
  const onPointerUp=(event:ReactPointerEvent<HTMLDivElement>)=>{
    const d=drag.current; drag.current=null;
    if(!d) return;
    setDragging('');
    if(!d.moved) return;
    const elements=[...(scroller.current?.querySelectorAll<HTMLElement>('.go-tab')||[])];
    let index=elements.length-1;
    for(let i=0;i<elements.length;i++){const r=elements[i].getBoundingClientRect();if(event.clientX<r.left+r.width/2){index=i;break;}}
    const from=tabs.findIndex(t=>t.id===d.id);
    if(from>=0 && index!==from) actions.move(d.id, index>from?index-1:index);
  };
  const onContext=(event:ReactMouseEvent, id:string)=>{event.preventDefault();setMenu({id,x:event.clientX,y:event.clientY});};
  const target=menu?tabs.find(t=>t.id===menu.id):undefined;
  const at=menu?tabs.findIndex(t=>t.id===menu.id):-1;
  return <div className="go-tabs">
    {anyPrivate && <span className="go-private-pill" title="Private tabs keep nothing after they close">Private</span>}
    <div ref={scroller} className="go-tabs-scroll" role="tablist" aria-label="Browser tabs" onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={()=>{drag.current=null;setDragging('');}}>
      {tabs.map(tab=>{
        const selected=tab.id===active;
        const title=tab.url==='about:blank'?'New tab':tab.title||hostOf(tab.url)||'Loading…';
        return <div key={tab.id} role="tab" aria-selected={selected} tabIndex={selected?0:-1} aria-label={(tab.private?'Private · ':'')+title}
          className={`go-tab ${selected?'active':''} ${tab.pinned?'pinned':''} ${tab.loading?'loading':''} ${fresh.has(tab.id)?'entering':''} ${dragging===tab.id?'dragging':''}`}
          title={tab.private?`Private · ${title}`:title}
          onPointerDown={e=>onPointerDown(e,tab.id)} onClick={()=>{if(!drag.current?.moved)actions.select(tab.id);}}
          onAuxClick={e=>{if(e.button===1){e.preventDefault();actions.close(tab.id);}}}
          onContextMenu={e=>onContext(e,tab.id)}
          onKeyDown={e=>{
            if(e.key==='Enter'||e.key===' '){e.preventDefault();actions.select(tab.id);}
            if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();actions.close(tab.id);}
            if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const i=tabs.findIndex(t=>t.id===tab.id);const next=tabs[(i+(e.key==='ArrowRight'?1:tabs.length-1))%tabs.length];if(next){actions.select(next.id);requestAnimationFrame(()=>scroller.current?.querySelector<HTMLElement>('.go-tab.active')?.focus());}}
          }}>
          {tab.private && <span className="go-private-dot" aria-hidden="true"/>}
          <TabIcon tab={tab}/>
          {!tab.pinned && <span className="go-tab-title">{tab.private?`Private · ${title}`:title}</span>}
          {!tab.pinned && <button type="button" className="go-tab-close" aria-label={`Close ${title}`} title="Close tab (Ctrl+W)" tabIndex={-1} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();actions.close(tab.id);}}><X size={12}/></button>}
        </div>;
      })}
      <button type="button" className="go-tab-new" aria-label="New tab" title="New tab (Ctrl+T)" onClick={()=>actions.add()}><Plus size={16}/></button>
    </div>
    <div className="go-tabs-end">
      <button type="button" className="go-ib" aria-label="Clear" aria-expanded={actions.clearOpen} aria-haspopup="menu" title="Private tab, or clear browsing data" onClick={actions.openClear}><BrushCleaning size={16}/></button>
    </div>
    {menu && target && <div ref={menuRef} className="go-context" role="menu" aria-label="Tab options" style={{left:Math.min(menu.x, window.innerWidth-230), top:menu.y}}>
      <button role="menuitem" onClick={()=>{setMenu(null);actions.add(target.id);}}><Plus size={14}/>New tab to the right</button>
      <button role="menuitem" onClick={()=>{setMenu(null);actions.addPrivate();}}><EyeOff size={14}/>New private tab</button>
      <div className="rule"/>
      <button role="menuitem" onClick={()=>{setMenu(null);actions.pin(target.id,!target.pinned);}}>{target.pinned?<PinOff size={14}/>:<Pin size={14}/>}{target.pinned?'Unpin':'Pin'}</button>
      <button role="menuitem" onClick={()=>{setMenu(null);actions.duplicate(target.id);}}><Copy size={14}/>Duplicate</button>
      <div className="rule"/>
      <button role="menuitem" onClick={()=>{setMenu(null);actions.close(target.id);}}><X size={14}/>Close</button>
      <button role="menuitem" disabled={tabs.filter(t=>!t.pinned).length<=1} onClick={()=>{setMenu(null);actions.closeOthers(target.id);}}>Close others</button>
      <button role="menuitem" disabled={at<0 || !tabs.slice(at+1).some(t=>!t.pinned)} onClick={()=>{setMenu(null);actions.closeRight(target.id);}}>Close to the right</button>
      <div className="rule"/>
      <button role="menuitem" disabled={!closed} onClick={()=>{setMenu(null);actions.reopen();}}><RotateCcw size={14}/>Reopen closed tab</button>
    </div>}
  </div>;
}
