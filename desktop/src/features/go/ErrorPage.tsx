import {RotateCw, SquareArrowOutUpRight} from 'lucide-react';
import type {BrowserTab} from '../../../electron/browser';
import {describeLoadError} from '../../../electron/browser';
import {OliveLogo} from '../../components/OliveLogo';
import {hostOf} from './shared';

export function ErrorPage({tab, onRetry, onExternal}:{tab:BrowserTab; onRetry:()=>void; onExternal:()=>void}) {
  const host=hostOf(tab.url).replace(/^www\./,'');
  // Codes at or below -1000 are OLIVE GO's own (protocol, popup, login, process) and carry their own sentence.
  const own=tab.errorCode<=-1000;
  const described=own?{title:'OLIVE GO stopped here',detail:tab.error}:describeLoadError(tab.errorCode, tab.error, host);
  return <div className="go-error" role="alert">
    <OliveLogo className="go-mark" size={40}/>
    <h2>{described.title}</h2>
    <p>{described.detail}</p>
    <div className="row">
      <button type="button" className="go-btn primary" onClick={onRetry}><RotateCw size={15}/>Try again</button>
      {tab.url!=='about:blank' && <button type="button" className="go-btn" onClick={onExternal}><SquareArrowOutUpRight size={15}/>Open in system browser</button>}
    </div>
    {!own && <code>{tab.error} ({tab.errorCode})</code>}
  </div>;
}
