export type Value = string | number | boolean;
export interface Field {
  key: string;
  label: string;
  category: string;
  kind: string;
  default: Value;
  minimum: number | null;
  maximum: number | null;
  choices: string[] | null;
  target: "settings" | "params" | "research";
}
export interface SettingsValue {
  chat_id: string;
  model: string;
  alias: string;
  system_prompt: string;
  settings: Record<string, Value | Record<string, Value>>;
  params: Record<string, Value>;
}
