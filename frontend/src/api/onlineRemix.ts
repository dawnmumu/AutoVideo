export interface ScriptShot {
  index: number;
  duration: number;
  narration: string;
  subtitle: string;
  visual_description: string;
  keywords: string[];
  delivery?: {
    style: string;
    emotion?: string | null;
    emotion_scale: number;
    speech_rate: number;
    loudness_rate: number;
    pitch?: number | null;
    pause_profile: string;
    voice_instruction?: string | null;
    context_reference?: string | null;
    voice_tag?: string | null;
    ssml?: string | null;
  };
}

export interface GeneratedScript {
  id: string;
  title: string;
  topic: string;
  aspect_ratio: string;
  duration_seconds: number;
  total_duration?: number;
  provider: string;
  created_at: string;
  shots: ScriptShot[];
  script_text?: string;
  analysis?: {
    title: string;
    shot_count: number;
    total_duration: number;
    max_single_duration?: number | null;
    segment_count: number;
    segments: Array<{
      segment_index: number;
      shot_range_start: number;
      shot_range_end: number;
      shot_count: number;
      duration: number;
    }>;
  };
}

export interface OnlineMaterialStatus {
  providers: Array<{
    provider: string;
    configured: boolean;
    enabled: boolean;
  }>;
  default_provider: string;
  candidate_token_secret_configured: boolean;
}

export interface OnlineMaterialCandidate {
  provider: string;
  asset_id: string;
  query: string;
  source_url: string;
  preview_url: string;
  candidate_token: string;
  file_variant: string;
  duration: number;
  width: number;
  height: number;
  license_note: string;
}

export interface LocalMaterial {
  id: string;
  original_filename: string;
  content_type: string | null;
  size_bytes: number;
  created_at: string;
  source_type: "upload" | "online";
  download_url?: string;
  source_provider?: string | null;
  source_asset_id?: string | null;
  source_url?: string | null;
  license_note?: string | null;
  query?: string | null;
}

export interface GenerateScriptInput {
  topic?: string;
  duration_seconds: number;
  aspect_ratio: string;
  tone: string;
  target_audience: string;
  selling_points: string[];
  provider: "auto" | "llm_only" | "heuristic";
  script_text?: string;
  max_single_duration?: number;
}

export interface SearchOnlineMaterialsInput {
  query: string;
  aspect_ratio: string;
  min_duration_seconds: number;
  provider: string;
}

export interface CreateOnlineMixTaskInput {
  title: string;
  script: GeneratedScript;
  asset_strategy: "auto" | "manual";
  provider: string;
  shot_assets: Array<{
    shot_index: number;
    candidate_token: string;
  }>;
  shot_materials: Array<{
    shot_index: number;
    material_id: string;
  }>;
  options: {
    aspect_ratio: string;
    resolution: string;
    subtitle_enabled?: boolean;
    subtitle_template_set_id?: string | null;
    subtitle_font_family?: string | null;
  };
}

export interface CreateOnlineMixTaskResponse {
  id: string;
  title: string;
  output: {
    download_url: string;
  };
}

export class OnlineRemixApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = "OnlineRemixApiError";
    this.code = code;
    this.status = status;
  }
}

function responseErrorCode(payload: unknown, status: number): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "object" &&
    payload.detail !== null &&
    "code" in payload.detail &&
    typeof payload.detail.code === "string"
  ) {
    return payload.detail.code;
  }
  return `HTTP_${status}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new OnlineRemixApiError(responseErrorCode(payload, response.status), response.status);
  }
  return response.json() as Promise<T>;
}

export async function fetchOnlineMaterialStatus(): Promise<OnlineMaterialStatus> {
  return readJson(await fetch("/api/online-materials/status"));
}

export async function fetchMaterials(): Promise<LocalMaterial[]> {
  return readJson(await fetch("/api/materials?limit=100&offset=0"));
}

export async function generateScript(input: GenerateScriptInput): Promise<GeneratedScript> {
  return readJson(
    await fetch("/api/scripts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function searchOnlineMaterials(
  input: SearchOnlineMaterialsInput,
): Promise<OnlineMaterialCandidate[]> {
  return readJson(
    await fetch("/api/online-materials/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function createOnlineMixTask(
  input: CreateOnlineMixTaskInput,
): Promise<CreateOnlineMixTaskResponse> {
  return readJson(
    await fetch("/api/online-mix/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}
