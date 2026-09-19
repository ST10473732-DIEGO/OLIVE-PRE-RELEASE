export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  hash: string;
  cid?: string;
  untrusted: boolean;
}
export interface MailRecord {
  id: string;
  kind: "draft" | "message";
  revision: number;
  subject: string;
  from: string;
  to: string[];
  cc: string[];
  bcc: string[];
  text: string;
  html: string;
  folder: string;
  read: boolean;
  starred: boolean;
  attachments: Attachment[];
  connection_id: string;
  project_id: string;
  thread_id: string;
  source_id?: string;
  references?: string;
  in_reply_to?: string;
  reply_to?: string[];
  body_cached?: boolean;
  submission_state?: string;
  remote_state?: string;
  remote_operation?: { state: string; action: string };
  remote?: { mailbox: string; uid: number; uidvalidity: number };
  warnings?: string[];
}
export interface Endpoint {
  host: string;
  port: number;
  tls: "tls" | "starttls";
}
export interface Connection {
  auth_type?: "google_oauth";
  id: string;
  revision: number;
  name: string;
  sender: string;
  username: string;
  smtp: Endpoint | null;
  imap: Endpoint | null;
  enabled: boolean;
  state: string;
  credential_ref: string | null;
  sync_enabled: boolean;
  sent_folder: string;
  sent_copy: boolean;
  ca_pem: string;
  sync_status?: {
    state: string;
    last_success?: string;
    count?: number;
    category?: string;
    mailbox?: string;
  };
  test_status?: {
    configuration_revision: number;
    updated_at: string;
    results: Record<
      string,
      { status: string; category?: string; capabilities?: string[] }
    >;
  };
}
export interface Submission {
  id: string;
  state: string;
  fingerprint: string;
  preview: Record<string, unknown>;
  accepted: string[];
  rejected: Record<string, unknown>;
  category?: string;
  sent_copy_state?: string;
}
export interface ImportPreview {
  preview_id: string;
  hash: string;
  subject: string;
  from: string;
  count: number;
  size: number;
  duplicate_id: string | null;
  warnings: string[];
  attachments: Attachment[];
}
export function draftBody(record: MailRecord) {
  return {
    from: record.from,
    to: record.to,
    cc: record.cc,
    bcc: record.bcc,
    subject: record.subject,
    text: record.text,
    attachments: record.attachments.map((a) => a.id),
    connection_id: record.connection_id,
    project_id: record.project_id,
    source_id: record.source_id || "",
    thread_id: record.thread_id,
    references: record.references || "",
    in_reply_to: record.in_reply_to || "",
  };
}
export const outcomeLabel: Record<string, string> = {
  prepared: "Awaiting review",
  submitting: "Submitting",
  accepted: "Accepted by your mail server",
  partially_accepted: "Some recipients accepted",
  failed: "Failed",
  outcome_uncertain: "Outcome uncertain — do not resend blindly",
  cancelled: "Cancelled before submission",
};
