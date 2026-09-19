export interface CheckResult {
  name: string;
  state?: string;
  session_id?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  output_truncated?: boolean;
}
export interface Validation {
  id: string;
  workspace_id: string;
  state: string;
  summary: string;
  task_id?: string;
  results: CheckResult[];
}
export interface OutputChannel {
  id: string;
  workspace_id: string;
  label: string;
  text: string;
  validation?: Validation;
  runState?: string;
  acceptsInput?: boolean;
  commandState?: string;
}
export interface OutputState {
  channels: OutputChannel[];
  selected: Record<string, string>;
}
export type OutputAction =
  | { channel: OutputChannel; restore?: boolean }
  | { workspace: string; select: string };
export function outputReducer(
  state: OutputState,
  action: OutputAction,
): OutputState {
  if ("select" in action)
    return {
      ...state,
      selected: { ...state.selected, [action.workspace]: action.select },
    };
  const channel = {
    ...action.channel,
    text: action.channel.text.slice(-150000),
  };
  const existing = state.channels.some((c) => c.id === channel.id);
  const channels = [
    ...state.channels.filter((c) => c.id !== channel.id),
    channel,
  ].slice(-12);
  const selected = { ...state.selected };
  if (
    (!existing && !action.restore) ||
    !channels.some((c) => c.id === selected[channel.workspace_id])
  )
    selected[channel.workspace_id] = channel.id;
  for (const workspace of Object.keys(selected))
    if (!channels.some((c) => c.id === selected[workspace]))
      delete selected[workspace];
  return { channels, selected };
}
export function validationChannel(value: Validation): OutputChannel {
  return {
    id: value.id,
    workspace_id: value.workspace_id,
    label: `Tests · ${value.state.replaceAll("_", " ")} · ${value.id.slice(0, 6)}`,
    validation: value,
    text: `${value.summary}\n\n${(value.results || []).map((r) => `${r.name} · ${r.state || "completed"}\n${r.output_truncated ? "Earlier output omitted to keep this view bounded.\n" : ""}${r.stdout || ""}${r.stderr || ""}\nExit: ${r.exit_code ?? "not available"}`).join("\n\n")}`,
  };
}

export interface CommandOutput {
  id: string;
  workspace_id: string;
  state: string;
  summary: string;
  stdout: string;
  stderr: string;
  exit_code: number | null;
}
export function commandChannel(value: CommandOutput): OutputChannel {
  return {
    id: value.id,
    workspace_id: value.workspace_id,
    commandState: value.state,
    label: `Command · ${value.state.replaceAll("_", " ")} · ${value.id.slice(0, 6)}`,
    text: `${value.summary}\n${value.stdout}\n${value.stderr}\nExit: ${value.exit_code ?? "not available"}`,
  };
}

// Build, test and solution jobs from the Studio tooling runtime. Progress
// events carry a bounded tail; the final result carries the whole log.
export interface JobOutput {
  id: string;
  workspace_id: string;
  kind: string;
  label: string;
  command: string[];
  state: string;
  exit_code: number | null;
  output?: string;
  error?: string;
}
export function jobChannel(value: JobOutput): OutputChannel {
  const heading = `${value.label} · ${value.state}${value.exit_code !== null && value.exit_code !== undefined ? ` · exit ${value.exit_code}` : ""}`;
  return {
    id: `job:${value.id}`,
    workspace_id: value.workspace_id,
    commandState: value.state === "running" ? "running" : undefined,
    label: `${value.kind === "test" || value.kind === "test-list" ? "Tests" : "Build"} · ${value.state} · ${value.id.slice(0, 6)}`,
    text: `${heading}\n$ ${value.command.join(" ")}\n\n${value.output || ""}${value.error ? `\n${value.error}` : ""}`,
  };
}
