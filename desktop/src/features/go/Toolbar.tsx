import type {ReactNode} from 'react';
import {House, ArrowLeft, ArrowRight, RotateCw, X, Menu} from 'lucide-react';
import type {BrowserTab} from '../../../electron/browser';

export function Toolbar({tab, onHome, onBack, onForward, onReload, onStop, onMenu, menuOpen, downloading, children}:{
  tab?:BrowserTab; onHome:()=>void; onBack:()=>void; onForward:()=>void; onReload:()=>void; onStop:()=>void;
  onMenu:()=>void; menuOpen:boolean; downloading:boolean; children:ReactNode;
}) {
  const loading=!!tab?.loading;
  return <div className="go-bar" role="toolbar" aria-label="Navigation">
    <div className="go-bar-group">
      <button type="button" className="go-ib" aria-label="Home" title="Home (Alt+Home)" onClick={onHome}><House size={16}/></button>
      <span className="go-sep" aria-hidden="true"/>
      <button type="button" className="go-ib" aria-label="Back" title="Back (Alt+Left)" disabled={!tab?.back} onClick={onBack}><ArrowLeft size={16}/></button>
      <button type="button" className="go-ib" aria-label="Forward" title="Forward (Alt+Right)" disabled={!tab?.forward} onClick={onForward}><ArrowRight size={16}/></button>
      {loading
        ? <button type="button" className="go-ib" aria-label="Stop loading" title="Stop (Esc)" onClick={onStop}><X size={16}/></button>
        : <button type="button" className="go-ib" aria-label="Reload" title="Reload (F5)" disabled={!tab || tab.url==='about:blank'} onClick={onReload}><RotateCw size={16}/></button>}
    </div>
    {children}
    <button type="button" className="go-ib" aria-label="OLIVE GO menu" aria-expanded={menuOpen} aria-haspopup="menu" title="Menu" onClick={onMenu}><Menu size={16}/>{downloading && <span className="go-badge" aria-hidden="true"/>}</button>
    {loading && <span className="go-progress" role="progressbar" aria-label="Page loading" aria-valuetext="Loading"/>}
  </div>;
}
