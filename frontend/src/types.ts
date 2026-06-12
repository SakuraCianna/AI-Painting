export interface DrawingObject {
  id: string;
  type: "rect" | "circle" | "ellipse" | "triangle" | "line" | "arrow" | "star" | "text";
  name?: string | null;
  geometry: Record<string, number | string>;
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

export interface CommandPlan {
  raw_text: string;
  normalized_text: string;
  operations: OperationPlanItem[];
  confidence: number;
  requires_confirmation: boolean;
  clarification_question?: string | null;
  risk_level: string;
}

export interface CommandExecutionResponse {
  message: string;
  plan: CommandPlan;
  artwork: Artwork | null;
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
}

export interface TtsSynthesisResponse {
  audio_data_url: string;
  provider: string;
  provider_label: string;
  format: string;
}
