export interface DesktopControl {
  runtime_id: number[];
  name: string;
  control_type: string;
  actions: string[];
  password?: boolean;
  value?: string;
}
export interface DesktopState {
  available?: boolean;
  unavailable_reason?: string;
  active: boolean;
  stopped: boolean;
  provider: string;
  can_pause: boolean;
  can_resume: boolean;
  settings: {
    enabled: boolean;
    screen_observation: boolean;
    vision_fallback: boolean;
    keyboard_policy: string;
    mouse_policy: string;
  };
  session: {
    id: string;
    task: string;
    application: string;
    status: string;
    current_action: string;
    verification: string;
    history: { action: string; status: string; application: string }[];
  } | null;
  observation: { controls?: DesktopControl[] };
  workflow_phases: { operation: string; status: string }[];
}
export type Operation = (
  fn: () => Promise<unknown>,
  message: string,
) => Promise<void>;
