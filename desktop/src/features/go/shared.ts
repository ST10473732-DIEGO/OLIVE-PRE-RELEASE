import {createContext, useContext, useEffect, useRef, type RefObject} from 'react';
import type {BrowserAction, BrowserState, BrowserTab} from '../../../electron/browser';
import logo from '../../../../assets/branding/olive-mark.svg';

/** The OLIVE desktop icon, reused byte-for-byte as OLIVE GO's mark. */
export const OLIVE_MARK = logo;

export type Invoke = <T = BrowserState>(action:BrowserAction) => Promise<T | undefined>;

export const hostOf = (url:string) => {try {return new URL(url).host;} catch {return '';}};
export const pathOf = (url:string) => {try {const u=new URL(url);return (u.pathname==='/'?'':u.pathname)+u.search+u.hash;} catch {return '';}};
export const isBlank = (tab?:BrowserTab) => !tab || tab.url==='about:blank';
/** A stable letter tile colour per host, for sites without a stored icon. */
export function hostColor(host:string):string {
  let hash=0; for(const char of host) hash=(hash*31+char.charCodeAt(0))>>>0;
  return `hsl(${hash%360} 38% 34%)`;
}
export const hostLetter = (host:string) => (host.replace(/^www\./,'')[0]||'?').toUpperCase();
export function formatBytes(value:number):string {
  if(!Number.isFinite(value) || value<0) return '?';
  if(value<1024) return `${value} B`;
  if(value<1024*1024) return `${Math.round(value/1024)} KB`;
  if(value<1024*1024*1024) return `${(value/1024/1024).toFixed(value<10*1024*1024?1:0)} MB`;
  return `${(value/1024/1024/1024).toFixed(2)} GB`;
}
export function dayLabel(time:number):string {
  const date=new Date(time), today=new Date(); today.setHours(0,0,0,0);
  const diff=Math.floor((today.getTime()-new Date(date.getFullYear(),date.getMonth(),date.getDate()).getTime())/86400000);
  if(diff<=0) return 'Today';
  if(diff===1) return 'Yesterday';
  if(diff<7) return date.toLocaleDateString(undefined,{weekday:'long'});
  return date.toLocaleDateString(undefined,{day:'numeric',month:'long',year:date.getFullYear()===today.getFullYear()?undefined:'numeric'});
}

/** Overlays that float over the page area register here so the native view
 *  can be kept clear of them: the page is moved below the lowest overlay. */
export type OverlayRegistry = {register:(element:HTMLElement)=>()=>void; bump:()=>void};
export const OverlayContext = createContext<OverlayRegistry>({register:()=>()=>undefined, bump:()=>undefined});
export function useOverlay(ref:RefObject<HTMLElement | null>, open:boolean) {
  const registry=useContext(OverlayContext);
  useEffect(()=>{
    if(!open || !ref.current) return;
    return registry.register(ref.current);
  },[open, ref, registry]);
}

/** Closes on Escape or on a pointer press outside the element. */
export function useDismiss(ref:RefObject<HTMLElement | null>, open:boolean, close:()=>void) {
  const latest=useRef(close); latest.current=close;
  useEffect(()=>{
    if(!open) return;
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.stopPropagation();latest.current();}};
    const press=(event:PointerEvent)=>{if(ref.current && !ref.current.contains(event.target as Node)) latest.current();};
    document.addEventListener('keydown',key,true);
    document.addEventListener('pointerdown',press,true);
    return()=>{document.removeEventListener('keydown',key,true);document.removeEventListener('pointerdown',press,true);};
  },[open, ref]);
}
