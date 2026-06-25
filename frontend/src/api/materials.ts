export interface MaterialSourceConfig {
  id: string;
  allowed_root_id: string;
  allowed_root_alias: string;
  source_relative_path: string;
  source_display_path: string;
  status: string;
  error_summary?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MaterialIndexJob {
  id: string;
  source_config_id: string;
  allowed_root_id: string;
  source_relative_path: string;
  status: string;
  stage: string;
  progress_current: number;
  progress_total: number;
  progress: {
    current: number;
    total: number;
  };
  raw_files_total: number;
  segments_total: number;
  failed_total: number;
  counts: {
    raw: number;
    segments: number;
    failed: number;
  };
  heartbeat_at?: string | null;
  attempt_count: number;
  error_summary?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface MaterialSourceStatus {
  allowed_roots: Array<{
    id: string;
    alias: string;
    display_name: string;
  }>;
  current_source: MaterialSourceConfig | null;
  latest_job: MaterialIndexJob | null;
}

export interface SaveMaterialSourceInput {
  allowed_root_id: string;
  source_relative_path: string;
}

export interface SaveMaterialSourceResponse {
  current_source: MaterialSourceConfig;
  job: MaterialIndexJob | null;
}

export interface StartMaterialIndexInput {
  source_config_id?: string | null;
  force?: boolean;
}

export interface StartMaterialIndexResponse {
  job_id: string;
  status: string;
}

export interface MaterialLibrarySummary {
  totals: {
    raw: number;
    segments: number;
    portrait: number;
    landscape: number;
    square: number;
    unknown: number;
    failed: number;
    [statusCount: string]: number;
  };
  current_source: MaterialSourceConfig | null;
  latest_job: MaterialIndexJob | null;
}

export interface MaterialRawFile {
  id: string;
  source_config_id?: string | null;
  allowed_root_id: string;
  source_relative_path: string;
  source_display_path: string;
  filename: string;
  size_bytes: number;
  duration_seconds?: number | null;
  orientation?: string | null;
  segments: number;
  status: string;
  error_summary?: string | null;
  asr_status?: string | null;
  ocr_status?: string | null;
  vision_status?: string | null;
  embedding_status?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MaterialRawFilesPage {
  items: MaterialRawFile[];
  limit: number;
  offset: number;
  total: number;
}

export interface MaterialDeleteResponse {
  id?: string;
  deleted: boolean;
  deleted_segments?: number;
}

export interface ClearMaterialLibraryResponse {
  deleted_raw: number;
  deleted_segments: number;
}

export class MaterialApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = "MaterialApiError";
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
    throw new MaterialApiError(responseErrorCode(payload, response.status), response.status);
  }
  return response.json() as Promise<T>;
}

const MATERIAL_ERROR_MESSAGES: Record<string, string> = {
  MATERIAL_SOURCE_ROOT_NOT_CONFIGURED: "未配置可用的素材根目录",
  MATERIAL_SOURCE_PATH_OUT_OF_SCOPE: "素材目录超出允许访问范围",
  MATERIAL_SOURCE_NOT_FOUND: "素材目录不存在或不可用",
  MATERIAL_INDEX_ALREADY_RUNNING: "素材索引任务正在运行，请稍后再试",
  MATERIAL_INDEX_JOB_NOT_FOUND: "素材索引任务不存在",
  MATERIAL_INDEX_JOB_FAILED: "素材索引任务执行失败",
  MATERIAL_INDEX_JOB_STALE: "素材索引任务已超时，请重新启动索引",
  MATERIAL_SCAN_NO_SUPPORTED_FILES: "素材目录里没有支持的视频文件",
  MATERIAL_SEGMENT_FAILED: "素材切片失败，请检查文件格式后重试",
  MATERIAL_RAW_FILE_NOT_FOUND: "素材文件不存在或已删除",
  MATERIAL_LIBRARY_CLEAR_CONFIRMATION_REQUIRED: "清空素材库需要输入确认文案",
  MATERIAL_LIBRARY_CLEAR_FAILED: "清空素材库失败，请检查文件权限后重试",
  MATERIAL_FFMPEG_UNAVAILABLE: "FFmpeg 不可用，无法处理素材",
  MATERIAL_LIBRARY_EMPTY: "素材库暂无可用素材",
  MATERIAL_LIBRARY_NOT_READY: "素材库索引尚未就绪",
  MATERIAL_NOT_FOUND: "素材不存在或已删除",
  MATERIAL_TOO_LARGE: "素材文件超过大小限制",
  TASK_MATERIAL_LIMIT_EXCEEDED: "任务素材数量超过限制",
};

export function readableMaterialError(error: unknown): string {
  if (error instanceof MaterialApiError) {
    return MATERIAL_ERROR_MESSAGES[error.code] ?? error.code;
  }
  return error instanceof Error ? error.message : "素材库操作失败";
}

export async function fetchMaterialSourceStatus(): Promise<MaterialSourceStatus> {
  return readJson(await fetch("/api/material-sources"));
}

export async function saveMaterialSource(
  input: SaveMaterialSourceInput,
): Promise<SaveMaterialSourceResponse> {
  return readJson(
    await fetch("/api/material-sources/current", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function startMaterialIndex(
  input: StartMaterialIndexInput = {},
): Promise<StartMaterialIndexResponse> {
  return readJson(
    await fetch("/api/material-index/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function fetchMaterialIndexJob(jobId: string): Promise<MaterialIndexJob> {
  return readJson(await fetch(`/api/material-index/jobs/${encodeURIComponent(jobId)}`));
}

export async function fetchMaterialLibrarySummary(): Promise<MaterialLibrarySummary> {
  return readJson(await fetch("/api/material-index/summary"));
}

export async function fetchMaterialRawFiles(input: {
  limit?: number;
  offset?: number;
  status?: string | null;
} = {}): Promise<MaterialRawFilesPage> {
  const params = new URLSearchParams();
  if (input.limit !== undefined) {
    params.set("limit", String(input.limit));
  }
  if (input.offset !== undefined) {
    params.set("offset", String(input.offset));
  }
  if (input.status) {
    params.set("status", input.status);
  }
  const query = params.toString();
  return readJson(await fetch(`/api/material-index/raw-files${query ? `?${query}` : ""}`));
}

export async function deleteMaterialRawFile(rawFileId: string): Promise<MaterialDeleteResponse> {
  return readJson(
    await fetch(`/api/material-index/raw-files/${encodeURIComponent(rawFileId)}`, {
      method: "DELETE",
    }),
  );
}

export async function clearMaterialLibrary(): Promise<ClearMaterialLibraryResponse> {
  return readJson(
    await fetch("/api/material-index/library/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: "CLEAR_MATERIAL_LIBRARY" }),
    }),
  );
}
