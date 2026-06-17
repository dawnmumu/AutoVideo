export interface SubtitleTemplateSet {
  id: string;
  name: string;
  schema_version: number;
  renderer_mode?: string;
  is_favorite?: boolean;
  is_modified?: boolean;
  tracks?: unknown[];
  blocks: unknown[];
  template_variants?: Record<string, unknown[]>;
  templates?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface SubtitleTemplateSetList {
  items: SubtitleTemplateSet[];
  presets: SubtitleTemplateSet[];
}

export interface SubtitleTemplateValidationResult {
  ok: boolean;
  normalized?: SubtitleTemplateSet;
  warnings: string[];
}

export interface SubtitleTemplatePreviewRequest {
  template_set: SubtitleTemplateSet;
  template_type?: string;
  aspect_ratio?: string;
  sample_text?: string;
  duration_ms?: number;
}

export interface SubtitleTemplatePreviewResult {
  status: string;
  renderer?: string;
  image_url?: string | null;
  video_url?: string | null;
  message?: string;
  [key: string]: unknown;
}

export class SubtitleTemplateApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = "SubtitleTemplateApiError";
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
    throw new SubtitleTemplateApiError(responseErrorCode(payload, response.status), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function writeJson<T>(url: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  return readJson(
    await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function fetchSubtitleTemplateSets(): Promise<SubtitleTemplateSetList> {
  return readJson(await fetch("/api/subtitle-template-sets"));
}

export async function createSubtitleTemplateSet(input: {
  name: string;
  preset_id?: string | null;
  source_id?: string | null;
}): Promise<SubtitleTemplateSet> {
  return writeJson("/api/subtitle-template-sets", "POST", input);
}

export async function updateSubtitleTemplateSet(
  templateSetId: string,
  patch: Partial<SubtitleTemplateSet>,
): Promise<SubtitleTemplateSet> {
  return writeJson(`/api/subtitle-template-sets/${encodeURIComponent(templateSetId)}`, "PUT", patch);
}

export async function deleteSubtitleTemplateSet(templateSetId: string): Promise<void> {
  return readJson(
    await fetch(`/api/subtitle-template-sets/${encodeURIComponent(templateSetId)}`, {
      method: "DELETE",
    }),
  );
}

export async function updateSubtitlePresetOverride(
  presetId: string,
  patch: Partial<SubtitleTemplateSet>,
): Promise<SubtitleTemplateSet> {
  return writeJson(
    `/api/subtitle-template-sets/presets/${encodeURIComponent(presetId)}`,
    "PUT",
    patch,
  );
}

export async function resetSubtitlePresetOverride(presetId: string): Promise<void> {
  return readJson(
    await fetch(`/api/subtitle-template-sets/presets/${encodeURIComponent(presetId)}`, {
      method: "DELETE",
    }),
  );
}

export async function validateSubtitleTemplateSet(
  templateSet: SubtitleTemplateSet,
): Promise<SubtitleTemplateValidationResult> {
  return writeJson("/api/subtitle-template-sets/validate", "POST", templateSet);
}

export async function previewSubtitleTemplateSet(
  input: SubtitleTemplatePreviewRequest,
): Promise<SubtitleTemplatePreviewResult> {
  return writeJson("/api/subtitle-template-sets/preview", "POST", input);
}

export async function previewSubtitleTimeline(
  input: SubtitleTemplatePreviewRequest,
): Promise<SubtitleTemplatePreviewResult> {
  return writeJson("/api/subtitle-template-sets/preview-timeline", "POST", input);
}
