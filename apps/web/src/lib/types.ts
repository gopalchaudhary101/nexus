/** Strict API types — mirror of the backend Pydantic schemas. No `any`. */

export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: "UPLOADED" | "PROCESSING" | "INDEXING" | "READY" | "FAILED";
  status_detail: string;
  doc_type: string;
  doc_type_confidence: number;
  page_count: number;
  created_at: string;
}

export interface DocumentEntity {
  kind: string;
  value: string;
  field: string;
  confidence: number;
  evidence: string;
  page: number;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  page: number;
  text: string;
  score?: number | null;
}

export interface DocumentDetail extends Document {
  text_preview: string;
  entities: DocumentEntity[];
  chunks: DocumentChunk[];
  chunk_count: number;
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  document_name: string;
  doc_type: string;
  page: number;
  chunk_index: number;
  text: string;
  vector_score: number;
  bm25_score: number;
  score: number;
}

export interface CitedSource {
  document_id: string;
  document_name: string;
  page: number;
  chunk_index: number;
  similarity: number;
  ref: string;
}

export interface AskResult {
  question: string;
  answer: string;
  confidence: number;
  grounded: boolean;
  sources: CitedSource[];
  provider: string;
}

export interface Overview {
  needs_attention: number;
  upcoming: number;
  risk_signals: number;
  recurring_monthly: number;
  recurring_currency: string;
  documents: number;
  ready_documents: number;
  pending_documents: number;
  knowledge_coverage: number;
  pending_approvals: number;
  recent: FeedItem[];
}

export interface FeedItem {
  severity: string;
  kind: string;
  title: string;
  detail: string;
  ref: string;
}

export interface Subscription {
  id: string;
  merchant: string;
  raw_merchant: string;
  amount: number;
  currency: string;
  frequency: string;
  occurrences: number;
  last_date: string;
  next_due: string;
  monthly_equivalent: number;
  annualized_cost: number;
  status: "ACTIVE" | "LAPSED";
  confidence: number;
  price_increase: { from: number; to: number; pct: number; date: string } | null;
  notes: string[];
}

export interface Anomaly {
  transaction_id: string;
  date: string;
  description: string;
  amount: number;
  currency: string;
  label: "NORMAL" | "UNUSUAL" | "HIGHLY_UNUSUAL";
  score: number;
  model: string;
  explanations: { feature: string; value: number; z: number; why: string }[];
  note: string;
}

export interface Deadline {
  id: string;
  title: string;
  kind: string;
  due_date: string;
  days_remaining: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  source: string;
  source_ref: string;
  amount: number | null;
  currency: string;
  importance: number;
  notes: string;
}

export interface ForecastPoint {
  month: string;
  value: number;
  lo: number;
  hi: number;
}

export interface Forecast {
  ok: boolean;
  message: string;
  model: string;
  history: { month: string; total: number }[];
  points: ForecastPoint[];
  trend_pct_mom: number | null;
}

export interface RiskSignal {
  id: string;
  label: string;
  weight: number;
  evidence: string;
}

export interface RiskReport {
  id: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  score: number;
  signals: RiskSignal[];
  components: Record<string, number | string>;
  disclaimer: string;
  subject: string;
}

export type AgentStepType = "PLANNER" | "TOOL" | "DATA" | "MODEL" | "LLM" | "REPORT" | "GATE";

export interface AgentStep {
  seq: number;
  type: AgentStepType;
  name: string;
  detail: string;
  status: "OK" | "PENDING_APPROVAL" | "FAILED" | "SKIPPED";
  duration_ms: number;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at: string;
}

export interface AgentTask {
  id: string;
  request: string;
  intent: string;
  status: "PENDING" | "RUNNING" | "WAITING_APPROVAL" | "COMPLETED" | "FAILED";
  response_text: string;
  result: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
  steps: AgentStep[];
}

export interface AgentTaskList {
  items: AgentTask[];
  total: number;
}

export interface Approval {
  id: string;
  run_id: string | null;
  tool: string;
  risk_class: "SENSITIVE" | "CONSEQUENTIAL";
  args: Record<string, unknown>;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXECUTED" | "FAILED" | "EXPIRED";
  result: Record<string, unknown> | null;
  created_at: string;
  decided_at: string | null;
}

export interface AnalyticsOverview {
  documents: number;
  chunks: number;
  transactions: number;
  subscriptions: number;
  deadlines: number;
  risks: number;
  agent_runs: number;
  audit_events: number;
  storage_bytes: number;
}

export interface SpendingMonth {
  month: string;
  total: number;
  recurring: number;
  other: number;
}

export interface SpendingSeries {
  currency: string;
  months: SpendingMonth[];
}

export interface RagQuality {
  evaluated: boolean;
  message: string | null;
  generated_at: string | null;
  n_cases: number | null;
  metrics: {
    retrieval_precision_at_1: number;
    retrieval_recall_at_5: number;
    citation_accuracy: number;
    answer_correctness: number;
    latency_ms_avg: number;
  } | null;
  rows: EvalRow[];
}

export interface EvalRow {
  id: string;
  question: string;
  expected_doc: string;
  top1_doc: string;
  answer: string;
  precision_at_1: number;
  recall_at_5: number;
  citation_accuracy: number;
  answer_correctness: number;
  latency_ms: number;
}

export interface RiskAnalytics {
  total: number;
  by_level: Record<string, number>;
  top_signals: { label: string; count: number }[];
  recent: { id: string; subject: string; level: string; score: number; created_at: string }[];
}

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  attrs: Record<string, unknown>;
}

export interface GraphEdge {
  src: string;
  rel: string;
  dst: string;
}

export interface KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body: string;
  severity: string;
  read: boolean;
  created_at: string;
}

export interface HealthInfo {
  status: string;
  service: string;
  version: string;
  llm_provider: string;
  embed_provider: string;
  db: string;
  pgvector: boolean;
}
