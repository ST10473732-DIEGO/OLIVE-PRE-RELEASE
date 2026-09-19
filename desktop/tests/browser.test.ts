import {describe,it,expect} from 'vitest';
import {navigationURL,browserAction,describeLoadError,suggestURL,searchLabel,searchNote,defaultPreferences} from '../electron/browser';
describe('Browser URL and command boundary',()=>{
  it('uses encoded Google searches and validated URLs',()=>{
    expect(navigationURL('olive & calculator')).toBe('https://www.google.com/search?q=olive%20%26%20calculator');
    expect(navigationURL('example.com/path')).toBe('https://example.com/path');
    expect(navigationURL('http://127.0.0.1:8080/test')).toBe('http://127.0.0.1:8080/test');
    for(const url of ['javascript:alert(1)','file:///secret','dmdo://app/index.html','https://user:secret@example.com','data:text/html,hi'])expect(()=>navigationURL(url)).toThrow();
    expect(()=>browserAction.parse({action:'executeJavaScript',code:'process.exit()'})).toThrow();
  });
  it('builds every search provider from a fixed map, never from caller text',()=>{
    expect(navigationURL('olive go','google')).toBe('https://www.google.com/search?q=olive%20go');
    expect(navigationURL('olive go','duckduckgo')).toBe('https://duckduckgo.com/?q=olive%20go');
    expect(navigationURL('olive go','bing')).toBe('https://www.bing.com/search?q=olive%20go');
    expect(navigationURL('example.org','bing')).toBe('https://example.org/');
    expect(navigationURL('olive go','brave')).toBe('https://search.brave.com/search?q=olive%20go');
    expect(navigationURL('olive go','ecosia')).toBe('https://www.ecosia.org/search?q=olive%20go');
    expect(searchLabel('brave')).toBe('Brave Search');
    expect(navigationURL('olive go','ahmia')).toBe('https://ahmia.fi/search/?q=olive%20go');
    // Ahmia has no suggestion endpoint: nothing is fetched for it, and its note says what .onion results need.
    expect(suggestURL('ahmia','olive')).toBe('');
    expect(searchNote('ahmia')).toContain('Tor');
    expect(suggestURL('google','a b')).toBe('https://suggestqueries.google.com/complete/search?client=firefox&q=a%20b');
    expect(searchLabel('duckduckgo')).toBe('DuckDuckGo');
    // An unknown engine is refused by the contract, not silently templated.
    expect(()=>browserAction.parse({action:'preferences',engine:'evil'})).toThrow();
    expect(defaultPreferences.engine).toBe('google');
    expect(defaultPreferences.suggestions).toBe(false);
  });
  it('accepts the OLIVE GO actions and rejects malformed ones',()=>{
    expect(browserAction.parse({action:'pin',id:'6f2f4e5e-7c9b-4a2f-9a1e-0f7a4b6c8d9e',pinned:true}).action).toBe('pin');
    expect(browserAction.parse({action:'clear-data',history:true,cookies:false,cache:false}).action).toBe('clear-data');
    expect(browserAction.parse({action:'suggest',text:'olive'})).toMatchObject({private:false});
    expect(()=>browserAction.parse({action:'move',id:'not-a-uuid',index:1})).toThrow();
    expect(()=>browserAction.parse({action:'favourite-reorder',urls:new Array(201).fill('https://a.example')})).toThrow();
    expect(()=>browserAction.parse({action:'preferences',sections:{weather:true}})).toThrow();
  });
  it('turns Chromium net errors into a sentence and keeps the code',()=>{
    expect(describeLoadError(-105,'ERR_NAME_NOT_RESOLVED','intranet.example').title).toBe("This page didn't load");
    expect(describeLoadError(-105,'ERR_NAME_NOT_RESOLVED','intranet.example').detail).toContain("intranet.example couldn't be found");
    expect(describeLoadError(-201,'ERR_CERT_DATE_INVALID','bank.example').detail).toContain('does not bypass certificate checks');
    expect(describeLoadError(-999,'ERR_SOMETHING','x.example').detail).toContain('ERR_SOMETHING');
  });
});
