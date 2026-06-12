export type DrawingGeometryValue =
  | number
  | string
  | Array<Record<string, number | string>>
  | Record<string, number | string>
  | undefined;

export interface DrawingObject {
  id: string;
  type: "rect" | "circle" | "ellipse" | "triangle" | "line" | "arrow" | "star" | "text" | "polygon" | "path" | "bezier" | "image";
  name?: string | null;
  layer_id: string;
  group_id?: string | null;
  semantic_tags: string[];
  transform: Record<string, unknown>;
  geometry: Record<string, DrawingGeometryValue>;
  style: {
    fill?: string;
    stroke?: string;
    strokeWidth?: number;
    opacity?: number;
  };
  z_index: number;
}

export interface Artwork {
  id: string;
  title: string;
  width: number;
  height: number;
  background: string;
  objects: DrawingObject[];
  created_at: string;
  updated_at: string;
}

export interface OperationPlanItem {
  operation_type: string;
  payload: Record<string, unknown>;
}

export interface ScenePlanStep {
  step_id: string;
  title: string;
  intent: string;
  target: Record<string, unknown>;
  operation_indexes: number[];
}

export interface ScenePlan {
  intent: string;
  summary: string;
  steps: ScenePlanStep[];
  expected_object_count?: number | null;
}

export interface CommandPlan {
  raw_text: string;
  normalized_text: string;
  operations: OperationPlanItem[];
  scene_plan?: ScenePlan | null;
  confidence: number;
  requires_confirmation: boolean;
  clarification_question?: string | null;
  risk_level: string;
  explanation?: string | null;
  planner_source: string;
}

export interface CommandExecutionResponse {
  message: string;
  plan: CommandPlan;
  artwork: Artwork | null;
  metrics: CommandExecutionMetrics;
}

export interface AsrProvidersResponse {
  providers: string[];
  provider_labels: Record<string, string>;
  primary_provider?: string | null;
  fallback_provider: string;
}

export interface AsrTranscriptionResponse {
  text: string;
  provider: string;
  provider_label: string;
  attempts: Array<{
    provider: string;
    status: string;
    message: string;
    latency_ms?: number | null;
  }>;
  metrics: AsrTranscriptionMetrics;
}

export interface AsrTranscriptionMetrics {
  total_ms?: number | null;
  audio_bytes?: number | null;
  attempt_count: number;
  successful_provider?: string | null;
  fallback_count: number;
}

export interface CommandExecutionMetrics {
  rule_parse_ms?: number | null;
  llm_planner_ms?: number | null;
  planner_total_ms?: number | null;
  execute_ms?: number | null;
  total_ms?: number | null;
  llm_attempted: boolean;
  llm_succeeded: boolean;
  fallback_used: boolean;
  planner_source?: string | null;
}

export interface LatencyMetricStats {
  count: number;
  average_ms?: number | null;
  p50_ms?: number | null;
  p75_ms?: number | null;
  p95_ms?: number | null;
  max_ms?: number | null;
}

export interface LatencyMetricsSummary {
  artwork_id?: string | null;
  limit: number;
  sample_count: number;
  success_count: number;
  failed_count: number;
  needs_confirmation_count: number;
  canceled_count: number;
  planner_sources: Record<string, number>;
  metrics: Record<string, LatencyMetricStats>;
  latest_created_at?: string | null;
}

export interface TtsSynthesisResponse {
  audio_data_url: string;
  provider: string;
  provider_label: string;
  format: string;
}
