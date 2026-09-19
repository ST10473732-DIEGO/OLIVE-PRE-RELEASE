import {useEffect, useMemo, useRef, useState} from 'react';
import type {BrowserRecord, BrowserTab} from '../../../electron/browser';
import {hostOf, type Invoke} from './shared';

export type Suggestion =
  | {kind:'url'; url:string; title:string; favicon:string; complete:boolean; source:'tab'|'history'}
  | {kind:'favourite'; url:string; title:string; favicon:string}
  | {kind:'search'; text:string}
  | {kind:'ask'; text:string};

const LIMIT = 8;
const looksLikeAddress = (text:string) => /^[a-z][a-z\d+.-]*:/i.test(text) || /^(localhost|(?:[a-z\d-]+\.)+[a-z\d-]+)(:\d+)?([/?#].*)?$/i.test(text.trim());
/** Everything a person could mean by the text, ranked: what they already have
 *  first, then the engine (only when allowed), then the explicit hand-off. */
export function useSuggestions(options:{
  text:string; open:boolean; tabs:BrowserTab[]; history:BrowserRecord[]; favourites:BrowserRecord[];
  remote:boolean; isPrivate:boolean; invoke:Invoke; engineLabel:string; askEnabled:boolean;
}) {
  const {text, open, tabs, history, favourites, remote, isPrivate, invoke, engineLabel, askEnabled} = options;
  const query=text.trim().toLowerCase();
  const local=useMemo<Suggestion[]>(()=>{
    if(!query) return [];
    const seen=new Set<string>(), out:Suggestion[]=[];
    const match=(url:string,title:string)=>{
      const host=hostOf(url).replace(/^www\./,'');
      const plain=url.replace(/^https?:\/\/(www\.)?/,'');
      return host.startsWith(query) || plain.startsWith(query) || title.toLowerCase().includes(query) || plain.includes(query);
    };
    // Private tabs only see what happened inside their own session: open private tabs.
    const tabSource=tabs.filter(t=>t.private===isPrivate && t.url!=='about:blank');
    for(const tab of tabSource) if(!seen.has(tab.url) && match(tab.url,tab.title)) {seen.add(tab.url); out.push({kind:'url',url:tab.url,title:tab.title,favicon:tab.favicon,complete:false,source:'tab'});}
    if(!isPrivate) {
      const recent=[...history].reverse();
      for(const item of recent) {if(out.length>=5) break; if(!seen.has(item.url) && match(item.url,item.title)) {seen.add(item.url); out.push({kind:'url',url:item.url,title:item.title,favicon:item.favicon||'',complete:false,source:'history'});}}
      for(const item of favourites) {if(out.length>=6) break; if(!seen.has(item.url) && match(item.url,item.title)) {seen.add(item.url); out.push({kind:'favourite',url:item.url,title:item.title,favicon:item.favicon||''});}}
    }
    // The first address whose host starts with the text can be completed with Tab.
    const first=out.find((s):s is Extract<Suggestion,{kind:'url'}>=>s.kind==='url' && hostOf(s.url).replace(/^www\./,'').startsWith(query));
    if(first) first.complete=true;
    return out;
  },[query, tabs, history, favourites, isPrivate]);

  const [engine,setEngine]=useState<{for:string; items:string[]; note:string}>({for:'',items:[],note:''});
  const generation=useRef(0);
  useEffect(()=>{
    if(!open || !query || !remote || isPrivate || looksLikeAddress(text)) {setEngine({for:query,items:[],note:''}); return;}
    const id=++generation.current;
    const timer=setTimeout(()=>{
      void invoke<{items:string[]; enabled:boolean; error:string}>({action:'suggest',text:text.trim(),private:isPrivate}).then(result=>{
        if(id!==generation.current) return;
        if(!result) return;
        setEngine({for:query,items:result.items||[],note:result.error||''});
      });
    },150);
    return()=>clearTimeout(timer);
  },[query, text, open, remote, isPrivate, invoke]);

  const items=useMemo<Suggestion[]>(()=>{
    if(!query) return [];
    const out:Suggestion[]=[...local];
    const seen=new Set(out.map(s=>s.kind==='search'?s.text:''));
    if(!looksLikeAddress(text)) {
      if(!seen.has(query)) out.push({kind:'search',text:text.trim()});
      if(engine.for===query) for(const item of engine.items) {if(out.length>=LIMIT-1) break; if(item.toLowerCase()!==query && !seen.has(item.toLowerCase())) {seen.add(item.toLowerCase()); out.push({kind:'search',text:item});}}
    }
    const trimmed=out.slice(0,LIMIT-(askEnabled?1:0));
    if(askEnabled) trimmed.push({kind:'ask',text:text.trim()});
    return trimmed;
  },[local, engine, query, text, askEnabled]);

  return {items, note: remote && !isPrivate && engine.for===query ? engine.note : '', engineLabel};
}
