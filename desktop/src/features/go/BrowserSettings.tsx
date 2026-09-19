import {useEffect, useState} from 'react';
import type {BrowserPreferences, BrowserState, SearchEngine} from '../../../electron/browser';
import {searchEngines, searchLabel, searchNote, defaultPreferences} from '../../../electron/browser';

/** The Browser category inside OLIVE Settings. It edits the same preferences
 *  the Customise panel does, through the same browser state file; there is
 *  no second store. */
export default function BrowserSettings({report}:{report:(error:unknown)=>void}) {
  const [preferences,setPreferences]=useState<BrowserPreferences>(defaultPreferences);
  useEffect(()=>{
    let live=true;
    void window.olive.browser({action:'state'}).then(value=>{if(live && value && 'preferences' in (value as BrowserState)) setPreferences((value as BrowserState).preferences);}).catch(report);
    const stop=window.olive.onBrowserState(value=>{if(live) setPreferences(value.preferences);});
    return()=>{live=false;stop();};
  },[report]);
  const update=(patch:{engine?:SearchEngine; suggestions?:boolean; sections?:Partial<BrowserPreferences['sections']>})=>
    void window.olive.browser({action:'preferences',...patch}).then(value=>{if(value && 'preferences' in (value as BrowserState)) setPreferences((value as BrowserState).preferences);}).catch(report);
  return <section>
    <h2>OLIVE GO</h2>
    <label className="field">
      Search engine
      <select aria-label="Search engine" value={preferences.engine} onChange={e=>update({engine:e.target.value as SearchEngine})}>
        {searchEngines.map(engine=><option key={engine} value={engine}>{searchLabel(engine)}</option>)}
      </select>
    </label>
    <p className="small muted">Typed text that isn't an address is searched here. Addresses and search text are validated before anything is opened.{searchNote(preferences.engine)?` ${searchNote(preferences.engine)}`:''}</p>
    <label className="check-field">
      <input type="checkbox" checked={preferences.suggestions} onChange={e=>update({suggestions:e.target.checked})}/>
      Search suggestions
    </label>
    <p className="small muted">Sends what you type in the address field to {searchLabel(preferences.engine)} as you type. Off by default, never used in private tabs, and never on when this is off.</p>
    <h2>New tab page</h2>
    {([['favourites','Favourites'],['recent','Recent'],['quick','Quick actions'],['ask','Ask OLIVE in the field']] as const).map(([key,label])=>
      <label key={key} className="check-field">
        <input type="checkbox" checked={preferences.sections[key]} onChange={e=>update({sections:{[key]:e.target.checked}})}/>
        {label}
      </label>)}
    <h2>Always on</h2>
    <p className="small muted">
      Pages run sandboxed with no access to OLIVE. Camera, microphone, location, notifications, clipboard reading and device access are blocked for every site.
      Downloads always ask where to save and never open themselves. HTTP authentication and unsupported protocols go to your system browser after a prompt.
      Private tabs keep nothing after they close; downloaded files and anything sent to Chat stay where they were put.
    </p>
  </section>;
}
