import {useEffect, useId, useRef, useState, type KeyboardEvent, type RefObject} from 'react';
import {Search, Sparkles, Star, Globe, Lock, LockOpen} from 'lucide-react';
import type {BrowserRecord, BrowserTab} from '../../../electron/browser';
import {hostOf, pathOf, isBlank, hostColor, hostLetter, useOverlay, useDismiss, type Invoke} from './shared';
import {useSuggestions, type Suggestion} from './useSuggestions';

export type Submit = {url?:string; search?:string; newTab?:boolean; ask?:string};

function Favicon({favicon, url}:{favicon:string; url:string}) {
  const host=hostOf(url);
  if(favicon) return <span className="go-favicon"><img src={favicon} alt=""/></span>;
  return <span className="go-favicon" style={{background:hostColor(host),color:'#fff',fontSize:9,fontWeight:600}}>{hostLetter(host)}</span>;
}

/** The dropdown under a field. Shared by the toolbar and the new tab page. */
export function SuggestionList({items, selected, query, onChoose, note, engineLabel, listId}:{
  items:Suggestion[]; selected:number; query:string; onChoose:(item:Suggestion, newTab?:boolean)=>void; note:string; engineLabel:string; listId:string;
}) {
  const ref=useRef<HTMLDivElement>(null);
  useOverlay(ref, items.length>0);
  if(!items.length) return null;
  const q=query.trim().toLowerCase();
  const highlight=(text:string)=>{
    const at=text.toLowerCase().indexOf(q);
    if(!q || at<0) return text;
    return <>{text.slice(0,at)}<b>{text.slice(at,at+q.length)}</b>{text.slice(at+q.length)}</>;
  };
  return <div ref={ref} className="go-suggest" role="listbox" id={listId} aria-label="Suggestions">
    {items.map((item,index)=>{
      const key=item.kind==='search'||item.kind==='ask'?item.kind+item.text:item.kind+item.url;
      const common={role:'option' as const,'aria-selected':index===selected,id:`${listId}-${index}`,onMouseDown:(e:React.MouseEvent)=>{e.preventDefault();onChoose(item,e.button===1||e.altKey);}};
      if(item.kind==='url') return <button key={key} className="go-suggest-row" {...common}>
        <Favicon favicon={item.favicon} url={item.url}/>
        <span className="main">{highlight(item.title||hostOf(item.url))}</span>
        <span className="dim">— {hostOf(item.url).replace(/^www\./,'')}{pathOf(item.url).slice(0,60)}</span>
        <span className="k">{item.complete?'Tab to complete':item.source==='tab'?'Open tab':''}</span>
      </button>;
      if(item.kind==='favourite') return <button key={key} className="go-suggest-row" {...common}>
        <Favicon favicon={item.favicon} url={item.url}/>
        <span className="main">{highlight(item.title||hostOf(item.url))}</span>
        <span className="dim">— {hostOf(item.url).replace(/^www\./,'')}</span>
        <span className="k">Favourite</span>
      </button>;
      if(item.kind==='search') return <button key={key} className="go-suggest-row" {...common}>
        <span className="go-favicon"><Search size={14}/></span>
        <span className="main">{highlight(item.text)}</span>
        <span className="k">{engineLabel}</span>
      </button>;
      return <button key={key} className="go-suggest-row ai" {...common}>
        <Sparkles size={16}/>
        <span className="main">Ask OLIVE about “{item.text}”</span>
        <span className="k">Ctrl+Enter</span>
      </button>;
    })}
    {note && <div className="go-suggest-note">{note}. Showing what this device already knows.</div>}
  </div>;
}

/** Keyboard model for a field with a suggestion list. */
export function useSuggestionKeys(options:{items:Suggestion[]; text:string; setText:(t:string)=>void; submit:(value:Submit)=>void; choose:(item:Suggestion,newTab?:boolean)=>void; close:()=>void; open:boolean; setOpen:(v:boolean)=>void}) {
  const {items, text, setText, submit, choose, close, open, setOpen}=options;
  const [selected,setSelected]=useState(-1);
  useEffect(()=>{setSelected(-1);},[text, items.length]);
  const onKeyDown=(event:KeyboardEvent<HTMLInputElement>)=>{
    if(event.key==='ArrowDown'){event.preventDefault();if(!open)setOpen(true);setSelected(s=>Math.min(items.length-1,s+1));return;}
    if(event.key==='ArrowUp'){event.preventDefault();setSelected(s=>Math.max(-1,s-1));return;}
    if(event.key==='Escape'){event.preventDefault();close();return;}
    if(event.key==='Tab' && !event.shiftKey){
      const target=selected>=0?items[selected]:items.find(i=>i.kind==='url' && i.complete);
      if(target && (target.kind==='url'||target.kind==='favourite')){event.preventDefault();setText(target.url.replace(/^https?:\/\/(www\.)?/,''));return;}
    }
    if(event.key==='Enter'){
      event.preventDefault();
      if(event.ctrlKey){if(text.trim())submit({ask:text.trim()});return;}
      const target=selected>=0?items[selected]:undefined;
      if(target){choose(target,event.altKey);return;}
      if(text.trim()) submit({search:text.trim(),newTab:event.altKey});
    }
  };
  return {selected, setSelected, onKeyDown};
}

export function AddressField({tab, favourites, history, tabs, preferences, invoke, submit, onSave, onAskPage, savedPop, onSiteInfo, focusRequest, inputRef}:{
  tab?:BrowserTab; favourites:BrowserRecord[]; history:BrowserRecord[]; tabs:BrowserTab[];
  preferences:{engine:string; engineLabel:string; suggestions:boolean; ask:boolean};
  invoke:Invoke; submit:(value:Submit)=>void; onSave:()=>void; onAskPage:()=>void; savedPop:boolean; onSiteInfo:()=>void;
  focusRequest:number; inputRef:RefObject<HTMLInputElement | null>;
}) {
  const [editing,setEditing]=useState(false);
  const [text,setText]=useState('');
  const [open,setOpen]=useState(false);
  const listId=useId();
  const wrap=useRef<HTMLDivElement>(null);
  const blank=isBlank(tab);
  const url=blank?'':tab?.url||'';
  const saved=!!tab && !blank && favourites.some(f=>f.url===tab.url);
  useEffect(()=>{if(!editing)setText(url);},[url, editing]);
  // Switching tabs, or the page moving on while the field isn't being typed in, ends editing.
  useEffect(()=>{setEditing(false);setOpen(false);},[tab?.id]);
  useEffect(()=>{if(editing && document.activeElement!==inputRef.current){setEditing(false);setOpen(false);}},[url]);
  useEffect(()=>{if(focusRequest){setEditing(true);setText(url);requestAnimationFrame(()=>{inputRef.current?.focus();inputRef.current?.select();});}},[focusRequest]);
  const suggestions=useSuggestions({text, open:editing&&open, tabs, history, favourites, remote:preferences.suggestions, isPrivate:!!tab?.private, invoke, engineLabel:preferences.engineLabel, askEnabled:preferences.ask});
  const finish=()=>{setEditing(false);setOpen(false);setText(url);};
  const choose=(item:Suggestion,newTab?:boolean)=>{
    finish();
    if(item.kind==='url'||item.kind==='favourite') submit({url:item.url,newTab});
    else if(item.kind==='search') submit({search:item.text,newTab});
    else submit({ask:item.text});
  };
  const keys=useSuggestionKeys({items:suggestions.items, text, setText, submit:v=>{finish();submit(v);}, choose, close:()=>{finish();inputRef.current?.blur();}, open, setOpen});
  useDismiss(wrap, editing, ()=>{finish();});
  const host=hostOf(url), path=pathOf(url);
  return <div ref={wrap} className={`go-field ${editing?'focus':''}`}>
    {blank || editing ? <span className="go-site-lead"><Search size={15}/></span>
      : <button type="button" className={`go-site ${tab?.secure==='http'?'http':''}`} aria-label={tab?.secure==='https'?'Delivered over an encrypted connection. Site information':tab?.secure==='http'?'Connection is not encrypted. Site information':'No connection to describe. Site information'} title={tab?.secure==='https'?'Encrypted connection (HTTPS) — not a statement about the site':tab?.secure==='http'?'Not encrypted (HTTP)':'No connection to describe'} onClick={onSiteInfo}>
        {tab?.secure==='https'?<Lock size={14}/>:tab?.secure==='http'?<LockOpen size={14}/>:<Globe size={14}/>}
      </button>}
    {editing ? <input ref={inputRef} aria-label="Search or enter address" role="combobox" aria-expanded={open && suggestions.items.length>0} aria-controls={listId} aria-activedescendant={keys.selected>=0?`${listId}-${keys.selected}`:undefined} aria-autocomplete="list" spellCheck={false} autoComplete="off" value={text} placeholder={tab?.private?'Search privately or enter address':'Search or enter address'} onChange={e=>{setText(e.target.value);setOpen(true);}} onKeyDown={keys.onKeyDown} onFocus={()=>setOpen(true)}/>
      : <button type="button" className="go-field-display" aria-label={url?`Address: ${url}. Edit address`:'Search or enter address'} onClick={()=>{setEditing(true);setText(url);requestAnimationFrame(()=>{inputRef.current?.focus();inputRef.current?.select();});}}>
        {url ? <><span className="host">{host}</span><span className="path">{path}</span></> : <span className="ph">{tab?.private?'Search privately or enter address':'Search or enter address'}</span>}
      </button>}
    {!editing && tab && !blank && <span className="go-field-actions">
      <button type="button" className={`go-ib ${saved?'saved':''} ${savedPop?'pop':''}`} aria-pressed={saved} aria-label={saved?'Remove from favourites':'Add to favourites'} title={tab.private?'Favourites are off in private tabs':saved?'Saved to favourites (Ctrl+D)':'Add to favourites (Ctrl+D)'} disabled={tab.private} onClick={onSave}><Star size={15}/></button>
      {preferences.ask && <button type="button" className="go-ib" aria-label="Ask OLIVE about this page" title="Ask OLIVE about this page" onClick={onAskPage}><Sparkles size={15}/></button>}
    </span>}
    {editing && open && <SuggestionList items={suggestions.items} selected={keys.selected} query={text} onChoose={choose} note={suggestions.note} engineLabel={preferences.engineLabel} listId={listId}/>}
  </div>;
}
