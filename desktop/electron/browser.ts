import {z} from 'zod';
const id = z.string().uuid();
export const searchEngines = ['google','duckduckgo','bing','brave','ecosia','ahmia'] as const;
export type SearchEngine = typeof searchEngines[number];
const engine = z.enum(searchEngines);
export const browserAction = z.discriminatedUnion('action', [
  z.object({action: z.literal('state')}),
  z.object({action: z.literal('new'), private: z.boolean().default(false), url: z.string().max(8000).default('about:blank'), after: id.optional()}),
  z.object({action: z.literal('navigate'), id, url: z.string().min(1).max(8000)}),
  z.object({action: z.enum(['select','close','back','forward','reload','stop','bookmark','read','home','duplicate','close-others','close-right','open-external']), id}),
  z.object({action: z.literal('reopen')}),
  z.object({action: z.literal('layout'), visible: z.boolean(), bounds: z.object({x:z.number().int(), y:z.number().int(), width:z.number().int().min(1), height:z.number().int().min(1)})}),
  z.object({action: z.literal('zoom'), id, factor:z.number().min(.5).max(2)}),
  z.object({action: z.literal('find'), id, text:z.string().max(300), next:z.boolean().default(false)}),
  z.object({action: z.literal('pin'), id, pinned: z.boolean()}),
  z.object({action: z.literal('move'), id, index: z.number().int().min(0).max(64)}),
  z.object({action: z.literal('download-cancel'), id}),
  z.object({action: z.literal('download-show'), id}),
  z.object({action: z.literal('downloads-clear')}),
  z.object({action: z.literal('clear-history')}),
  z.object({action: z.literal('history-remove'), url: z.string().max(8000), time: z.number()}),
  z.object({action: z.literal('favourite-remove'), url: z.string().max(8000)}),
  z.object({action: z.literal('favourite-rename'), url: z.string().max(8000), title: z.string().min(1).max(300)}),
  z.object({action: z.literal('favourite-reorder'), urls: z.array(z.string().max(8000)).max(200)}),
  z.object({action: z.literal('clear-data'), history: z.boolean(), cookies: z.boolean(), cache: z.boolean()}),
  z.object({action: z.literal('suggest'), text: z.string().min(1).max(300), private: z.boolean().default(false)}),
  z.object({action: z.literal('snapshot'), id}),
  z.object({action: z.literal('preferences'), engine: engine.optional(), suggestions: z.boolean().optional(),
    sections: z.object({favourites:z.boolean().optional(), recent:z.boolean().optional(), quick:z.boolean().optional(), ask:z.boolean().optional()}).strict().optional()}).strict(),
]);
export type BrowserAction = z.input<typeof browserAction>;
export type BrowserTab = {id:string; url:string; title:string; private:boolean; loading:boolean; back:boolean; forward:boolean; zoom:number; error:string; errorCode:number; matches:number; favicon:string; secure:'https'|'http'|'none'; pinned:boolean};
export type BrowserRecord = {url:string; title:string; time:number; favicon?:string};
export type BrowserDownload = {id:string; name:string; url:string; received:number; total:number; state:string; path:string; private:boolean; started:number};
export type BrowserPreferences = {engine:SearchEngine; suggestions:boolean; sections:{favourites:boolean; recent:boolean; quick:boolean; ask:boolean}};
export type BrowserState = {tabs:BrowserTab[]; active:string; history:BrowserRecord[]; bookmarks:BrowserRecord[]; downloads:BrowserDownload[]; preferences:BrowserPreferences; closed:number};
/** A still of the active page, shown under OLIVE GO's own popovers while the native view is hidden. */
export type BrowserSnapshot = {image:string; width:number; height:number};
export const defaultPreferences:BrowserPreferences = {engine:'google', suggestions:false, sections:{favourites:true, recent:true, quick:true, ask:true}};
/** Search providers are a fixed map; no caller can supply a template. */
const SEARCH:Record<SearchEngine,{query:string; suggest:string; label:string; note?:string}> = {
  google: {query:'https://www.google.com/search?q=', suggest:'https://suggestqueries.google.com/complete/search?client=firefox&q=', label:'Google'},
  duckduckgo: {query:'https://duckduckgo.com/?q=', suggest:'https://duckduckgo.com/ac/?type=list&q=', label:'DuckDuckGo'},
  bing: {query:'https://www.bing.com/search?q=', suggest:'https://api.bing.com/osjson.aspx?query=', label:'Bing'},
  brave: {query:'https://search.brave.com/search?q=', suggest:'https://search.brave.com/api/suggest?q=', label:'Brave Search'},
  ecosia: {query:'https://www.ecosia.org/search?q=', suggest:'https://ac.ecosia.org/?q=', label:'Ecosia'},
  // Ahmia indexes .onion sites and answers over ordinary HTTPS. Its results
  // point into the Tor network, which OLIVE GO does not route through, so an
  // .onion result opens as an unreachable page here. It offers no suggestions.
  ahmia: {query:'https://ahmia.fi/search/?q=', suggest:'', label:'Ahmia (.onion sites)', note:'Searches .onion sites over the normal web. Opening a result needs the Tor network, which OLIVE GO does not provide.'},
};
export const searchLabel = (name:SearchEngine) => SEARCH[name].label;
export const searchNote = (name:SearchEngine) => SEARCH[name].note || '';
/** Empty when the engine offers no suggestion endpoint; callers then stay local. */
export const suggestURL = (name:SearchEngine, text:string) => SEARCH[name].suggest ? SEARCH[name].suggest + encodeURIComponent(text) : '';
export function navigationURL(input:string, engine:SearchEngine='google'):string {
  const value = input.trim();
  if(value === 'about:blank') return value;
  if(!value || [...value].some(c=>c.charCodeAt(0)<32)) throw new Error('Enter a URL or search text');
  let candidate = value;
  if(!/^[a-z][a-z\d+.-]*:/i.test(value)) {
    candidate = /^(localhost|(?:[a-z\d-]+\.)+[a-z\d-]+)(:\d+)?([/?#].*)?$/i.test(value) ? 'https://'+value : SEARCH[engine].query+encodeURIComponent(value);
  }
  const url = new URL(candidate);
  if(!['http:','https:'].includes(url.protocol) || url.username || url.password) throw new Error('Only HTTP and HTTPS pages are supported. Credentials cannot be placed in URLs.');
  return url.href;
}
/** Chromium's net error codes that deserve a sentence of their own. */
export function describeLoadError(code:number, description:string, host:string):{title:string; detail:string} {
  const site = host || 'This site';
  switch(code) {
    case -105: return {title:"This page didn't load", detail:`${site} couldn't be found. Check the address, or it may be a private network name this device can't resolve.`};
    case -106: case -130: return {title:'No connection', detail:`${site} couldn't be reached. This device looks offline, or a proxy is blocking the connection.`};
    case -7: case -118: return {title:'The page took too long', detail:`${site} didn't answer in time. It may be busy or slow to reach from here.`};
    case -102: case -104: return {title:'Connection refused', detail:`${site} refused the connection. It may be down, or the port may be wrong.`};
    case -200: case -201: case -202: case -501: return {title:'Connection not secure', detail:`${site} presented a certificate OLIVE GO couldn't verify. It was not opened, and OLIVE GO does not bypass certificate checks.`};
    case -20: case -21: case -22: return {title:'Blocked', detail:`Something on this device or network blocked ${site}.`};
    default: return {title:"This page didn't load", detail:`${site} couldn't be shown${description?` (${description})`:''}. You can try again or open it in your system browser.`};
  }
}
