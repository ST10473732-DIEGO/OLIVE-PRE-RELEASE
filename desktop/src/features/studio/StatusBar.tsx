import { AlertCircle, AlertTriangle, Bug, GitBranch, Laptop, Loader2, MonitorSmartphone } from "lucide-react";

// Studio V2 §9: a 22 px status bar that only reports. Every item is a labelled
// button or plain text; nothing is shown that the runtime or Monaco did not
// report. Interpreters and SDKs are named, never shown as absolute paths.
export interface StatusBarProps {
  remote?: { device: string; online: boolean };
  branch?: string;
  branchDirty?: boolean;
  errors: number;
  warnings: number;
  openProblems: () => void;
  debugText?: string;
  debugPaused?: boolean;
  openDebug?: () => void;
  running?: string;
  cursor?: string;
  indentation?: string;
  encoding?: string;
  eol?: string;
  language?: string;
  runtime?: string;
  codeIntelligence?: { text: string; failed: boolean };
  openOutput?: () => void;
  saveStatus: string;
}
export function StatusBar(props: StatusBarProps) {
  return (
    <footer className="studio-status" aria-label="Studio status">
      <div className="status-left">
        {props.remote ? (
          <span className="status-item status-remote" data-online={props.remote.online || undefined} title={props.remote.online ? `Remote workspace on ${props.remote.device}` : `${props.remote.device} is offline`}>
            <MonitorSmartphone size={12} aria-hidden="true" />
            {props.remote.device}
            {!props.remote.online && " · offline"}
          </span>
        ) : (
          <span className="status-item status-local" title="Files, builds and runs are on this device">
            <Laptop size={12} aria-hidden="true" />
            Local
          </span>
        )}
        {props.branch && (
          <span className="status-item" title={props.branchDirty ? "Current branch · uncommitted changes" : "Current branch"}>
            <GitBranch size={12} aria-hidden="true" />
            {props.branch}
            {props.branchDirty ? "*" : ""}
          </span>
        )}
        <button
          className="status-item"
          aria-label={`Problems: ${props.errors} ${props.errors === 1 ? "error" : "errors"}, ${props.warnings} ${props.warnings === 1 ? "warning" : "warnings"}`}
          title="Open Problems"
          onClick={props.openProblems}
        >
          <AlertCircle size={12} aria-hidden="true" />
          {props.errors}
          <AlertTriangle size={12} aria-hidden="true" />
          {props.warnings}
        </button>
        {props.debugText && (
          <button className="status-item status-debug" data-paused={props.debugPaused || undefined} onClick={props.openDebug} title="Open Run and Debug">
            <Bug size={12} aria-hidden="true" />
            {props.debugText}
          </button>
        )}
        {props.running && (
          <span className="status-item status-running" role="status">
            <Loader2 size={12} className="spin" aria-hidden="true" />
            {props.running}
          </span>
        )}
      </div>
      <div className="status-right">
        <span className="save-status status-item" role="status">
          {props.saveStatus}
        </span>
        {props.cursor && <span className="status-item">{props.cursor}</span>}
        {props.indentation && <span className="status-item">{props.indentation}</span>}
        {props.encoding && <span className="status-item" title="Studio opens UTF-8 text files only">{props.encoding}</span>}
        {props.eol && <span className="status-item" title="Line endings are preserved on save">{props.eol}</span>}
        {props.language && <span className="status-item">{props.language}</span>}
        {props.runtime && <span className="status-item" title="Interpreter or SDK">{props.runtime}</span>}
        {props.codeIntelligence?.text && (
          <button
            className="status-item"
            data-warning={props.codeIntelligence.failed || undefined}
            title={props.codeIntelligence.failed ? "Code intelligence stopped · open Problems" : "Code intelligence"}
            aria-label={`Code intelligence: ${props.codeIntelligence.text}`}
            onClick={props.codeIntelligence.failed ? props.openProblems : props.openOutput}
          >
            {props.codeIntelligence.failed && <AlertTriangle size={12} aria-hidden="true" />}
            {"{ }"} {props.codeIntelligence.text}
          </button>
        )}
      </div>
    </footer>
  );
}
