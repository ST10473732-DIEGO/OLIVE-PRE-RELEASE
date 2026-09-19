/** A navigation request, never execution authority. Domain services validate IDs. */
export interface RecordTarget {
  id: string;
  revision: number;
  kind?: string;
  chat_id?: string;
}
