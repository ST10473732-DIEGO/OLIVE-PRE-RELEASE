export interface ResearchSummary {
  id: string;
  question: string;
  status: string;
  activity: string;
  project_id?: string;
  updated_at: string;
}
export interface ResearchSource {
  id: string;
  title: string;
  url: string;
  domain: string;
  status: string;
  retrieved_at: string;
  publication_date?: string;
  quality: Record<string, unknown>;
}
export interface ResearchEvidence {
  id: string;
  source_id: string;
  claim: string;
  quote: string;
  subquestion: string;
}
export interface ResearchSession extends ResearchSummary {
  plan: Record<string, unknown>;
  final_report: string;
  error: string;
  sources: ResearchSource[];
  evidence: ResearchEvidence[];
  findings: { text: string; kind: string; evidence_ids: string[] }[];
  settings: { depth: string };
}
