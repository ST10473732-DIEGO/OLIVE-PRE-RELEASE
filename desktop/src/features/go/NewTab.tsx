import {useEffect, useId, useRef, useState, type RefObject} from 'react';
import {Search, EyeOff, Download, Plus, SlidersHorizontal, Star, X} from 'lucide-react';
import type {BrowserPreferences, BrowserRecord, BrowserTab} from '../../../electron/browser';
import {OLIVE_MARK, hostOf, hostColor, hostLetter, useDismiss, type Invoke} from './shared';
import {SuggestionList, useSuggestionKeys, type Submit} from './AddressField';
import {useSuggestions, type Suggestion} from './useSuggestions';

const TILE_LIMIT = 12;
const RECENT_LIMIT = 6;

function Tile({record, onOpen, onRemove}:{record:BrowserRecord; onOpen:()=>void; onRemove:()=>void}) {
  const host=hostOf(record.url);
  return <div className="go-tile">
    <button type="button" className="box" aria-label={`Open ${record.title||host}`} title={record.url} onClick={onOpen} style={record.favicon?undefined:{background:hostColor(host),color:'#fff'}}>
      {record.favicon?<img src={record.favicon} alt=""/>:hostLetter(host)}
    </button>
    <span className="lbl" title={record.title}>{record.title||host.replace(/^www\./,'')}</span>
    <button type="button" className="go-tile-remove" aria-label={`Remove ${record.title||host} from favourites`} onClick={onRemove}><X size={11}/></button>
  </div>;
}

export function NewTab({tab, favourites, history, tabs, preferences, engineLabel, invoke, submit, openPanel, openPrivate, focusRequest, inputRef, openAddFavourite}:{
  tab:BrowserTab; favourites:BrowserRecord[]; history:BrowserRecord[]; tabs:BrowserTab[]; preferences:BrowserPreferences; engineLabel:string;
  invoke:Invoke; submit:(value:Submit)=>void; openPanel:(panel:'history'|'favourites'|'downloads'|'customize')=>void; openPrivate:()=>void;
  focusRequest:number; inputRef:RefObject<HTMLInputElement | null>; openAddFavourite:()=>void;
}) {
  const [text,setText]=useState('');
  const [open,setOpen]=useState(false);
  const [focus,setFocus]=useState(false);
  const wrap=useRef<HTMLDivElement>(null);
  const listId=useId();
  const isPrivate=tab.private;
  useEffect(()=>{inputRef.current?.focus();},[focusRequest, inputRef, tab.id]);
  const suggestions=useSuggestions({text, open, tabs, history, favourites, remote:preferences.suggestions, isPrivate, invoke, engineLabel, askEnabled:preferences.sections.ask});
  const choose=(item:Suggestion,newTab?:boolean)=>{
    setOpen(false);setText('');
    if(item.kind==='url'||item.kind==='favourite') submit({url:item.url,newTab});
    else if(item.kind==='search') submit({search:item.text,newTab});
    else submit({ask:item.text});
  };
  const keys=useSuggestionKeys({items:suggestions.items, text, setText, submit:v=>{setOpen(false);setText('');submit(v);}, choose, close:()=>{setOpen(false);inputRef.current?.blur();}, open, setOpen});
  useDismiss(wrap, open, ()=>setOpen(false));
  // Recent is history newest first, one row per address, and never in a private tab.
  const seen=new Set<string>();
  const recent=isPrivate?[]:[...history].reverse().filter(h=>{if(seen.has(h.url))return false;seen.add(h.url);return true;}).slice(0,RECENT_LIMIT);
  const tiles=isPrivate?[]:favourites.slice(0,TILE_LIMIT);
  const showFavourites=preferences.sections.favourites && !isPrivate;
  const showRecent=preferences.sections.recent && recent.length>0;
  return <div className="go-ntp" data-private={isPrivate||undefined}>
    <img className="go-mark" src={OLIVE_MARK} alt="" width={84} height={84}/>
    <h1 className="go-wordmark">OLIVE <span>GO</span></h1>
    {isPrivate && <p className="go-sub">Private tab — nothing from this tab is saved once it closes. Files you download stay on this device, and anything you send to Chat is kept there. Private browsing is not anonymity: sites and your network still see your traffic.</p>}
    <div ref={wrap} className={`go-search ${focus?'focus':''}`}>
      <Search size={17} aria-hidden="true"/>
      <input ref={inputRef} aria-label="Search or enter address" role="combobox" aria-expanded={open && suggestions.items.length>0} aria-controls={listId} aria-activedescendant={keys.selected>=0?`${listId}-${keys.selected}`:undefined} aria-autocomplete="list" spellCheck={false} autoComplete="off"
        placeholder={isPrivate?'Search privately or enter address':'Search or enter address'} value={text}
        onChange={e=>{setText(e.target.value);setOpen(true);}} onKeyDown={keys.onKeyDown} onFocus={()=>{setFocus(true);setOpen(true);}} onBlur={()=>setFocus(false)}/>
      {preferences.sections.ask && <button type="button" className="go-ib" aria-label="Ask OLIVE" title={text.trim()?'Ask OLIVE about this (Ctrl+Enter)':'Type something, then ask OLIVE'} disabled={!text.trim()} onClick={()=>{const value=text.trim();setText('');setOpen(false);submit({ask:value});}}><span className="olive-mark go-ask-mark" aria-hidden="true"/></button>}
      {open && <SuggestionList items={suggestions.items} selected={keys.selected} query={text} onChoose={choose} note={suggestions.note} engineLabel={engineLabel} listId={listId}/>}
    </div>
    {preferences.sections.quick && <div className="go-quick">
      {preferences.sections.ask && <button type="button" className="go-chip" onClick={()=>{inputRef.current?.focus();}} title="Type a question in the field, then choose Ask OLIVE"><span className="olive-mark go-ask-mark" aria-hidden="true"/>Ask OLIVE</button>}
      {!isPrivate && <button type="button" className="go-chip" onClick={openPrivate}><EyeOff size={14}/>Private tab</button>}
      <button type="button" className="go-chip" onClick={()=>openPanel('downloads')}><Download size={14}/>Downloads</button>
    </div>}
    {showFavourites && <div className="go-favs" aria-label="Favourites">
      {tiles.map(record=><Tile key={record.url} record={record} onOpen={()=>submit({url:record.url})} onRemove={()=>void invoke({action:'favourite-remove',url:record.url})}/>)}
      {tiles.length<TILE_LIMIT && <div className="go-tile"><button type="button" className="box add" aria-label="Add favourite" title="Add the page you're on, or open Favourites" onClick={openAddFavourite}><Plus size={20}/></button><span className="lbl">Add</span></div>}
    </div>}
    {showFavourites && tiles.length===0 && <p className="go-favs-empty"><Star size={14} aria-hidden="true"/>No favourites yet. Press the star in the address bar to keep a site here.</p>}
    {showRecent && <div className="go-recent">
      <div className="h"><b>Recent</b><button type="button" onClick={()=>openPanel('history')}>Show all history</button></div>
      {recent.map(item=>{
        const host=hostOf(item.url);
        return <button key={item.url+item.time} type="button" className="go-row" title={item.url} onClick={()=>submit({url:item.url})}>
          <span className="go-favicon">{item.favicon?<img src={item.favicon} alt=""/>:<span style={{color:hostColor(host),fontWeight:600,fontSize:10}}>{hostLetter(host)}</span>}</span>
          <span className="t">{item.title||host}</span>
          <span className="u">{host.replace(/^www\./,'')}</span>
        </button>;
      })}
    </div>}
    <button type="button" className="go-btn go-customize" onClick={()=>openPanel('customize')}><SlidersHorizontal size={15}/>Customise</button>
  </div>;
}
