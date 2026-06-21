export interface BgmCategory {
  id: string;
  name: string;
  sort_order: number;
  track_count: number;
  created_at: string;
  updated_at: string;
}

export interface BgmTrack {
  id: string;
  filename: string;
  original_filename: string;
  display_name: string;
  category_id: string | null;
  category_name: string;
  media_type: string;
  extension: string;
  size_bytes: number;
  duration_seconds: number;
  audio_url: string;
  created_at: string;
  updated_at: string;
}

export interface BgmLibrary {
  items: BgmTrack[];
  categories: BgmCategory[];
  storage_status: "ready";
  total_tracks: number;
  supported_extensions: string[];
}

export class BgmApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail: Record<string, unknown>;

  constructor(code: string, status: number, detail: Record<string, unknown> = {}) {
    super(code);
    this.name = "BgmApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
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
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "object" &&
      payload.detail !== null
        ? (payload.detail as Record<string, unknown>)
        : {};
    throw new BgmApiError(responseErrorCode(payload, response.status), response.status, detail);
  }
  return response.json() as Promise<T>;
}

function detailNumber(error: BgmApiError, key: string): number | null {
  const value = error.detail[key];
  return typeof value === "number" ? value : null;
}

export function readableBgmError(error: unknown): string {
  if (error instanceof BgmApiError) {
    if (error.code === "BGM_FILE_UNSUPPORTED") {
      return "不支持的音频格式或文件中没有音频流";
    }
    if (error.code === "BGM_FILE_EMPTY") {
      return "上传的 BGM 文件为空";
    }
    if (error.code === "BGM_FILE_TOO_LARGE") {
      const limit = detailNumber(error, "max_upload_bytes");
      return limit ? `BGM 文件超过上传大小限制（${limit} 字节）` : "BGM 文件超过上传大小限制";
    }
    if (error.code === "REQUEST_TOO_LARGE") {
      const limit = detailNumber(error, "max_request_bytes");
      return limit ? `BGM 文件超过请求大小限制（${limit} 字节）` : "BGM 文件超过上传大小限制";
    }
    if (error.code === "BGM_TRACK_NOT_FOUND") {
      return "当前 BGM 不存在或已删除";
    }
    if (error.code === "BGM_CATEGORY_NOT_FOUND") {
      return "当前 BGM 分类不存在或已删除";
    }
    if (error.code === "BGM_CATEGORY_DUPLICATE") {
      return "分类名已存在";
    }
    if (error.code === "BGM_CATEGORY_NAME_REQUIRED") {
      return "请输入分类名";
    }
    if (error.code === "BGM_TRACK_NAME_REQUIRED") {
      return "请输入 BGM 名称";
    }
    if (error.code === "BGM_CATEGORY_EMPTY") {
      return "这个分类下没有可用 BGM";
    }
    if (error.code === "BGM_LIBRARY_CORRUPT") {
      return "BGM 库元数据异常，请检查数据文件";
    }
    if (error.code === "BGM_TRACK_FILE_DELETE_FAILED") {
      return "BGM 文件删除失败，请检查文件权限后重试";
    }
  }
  return error instanceof Error ? error.message : "BGM 操作失败";
}

export async function fetchBgmLibrary(): Promise<BgmLibrary> {
  return readJson(await fetch("/api/bgm"));
}

export async function uploadBgmTrack(input: {
  file: File;
  category_id?: string | null;
}): Promise<BgmTrack> {
  const formData = new FormData();
  formData.append("file", input.file);
  if (input.category_id) {
    formData.append("category_id", input.category_id);
  }
  return readJson(await fetch("/api/bgm/tracks", { method: "POST", body: formData }));
}

export async function updateBgmTrack(input: {
  id: string;
  display_name: string;
  category_id?: string | null;
}): Promise<BgmTrack> {
  const body: { display_name: string; category_id?: string | null } = {
    display_name: input.display_name,
  };
  if (input.category_id !== undefined) {
    body.category_id = input.category_id;
  }

  return readJson(
    await fetch(`/api/bgm/tracks/${encodeURIComponent(input.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteBgmTrack(trackId: string): Promise<{ id: string; deleted: boolean }> {
  return readJson(
    await fetch(`/api/bgm/tracks/${encodeURIComponent(trackId)}`, { method: "DELETE" }),
  );
}

export async function createBgmCategory(input: { name: string }): Promise<BgmCategory> {
  return readJson(
    await fetch("/api/bgm/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function updateBgmCategory(input: {
  id: string;
  name: string;
}): Promise<BgmCategory> {
  return readJson(
    await fetch(`/api/bgm/categories/${encodeURIComponent(input.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: input.name }),
    }),
  );
}

export async function deleteBgmCategory(
  categoryId: string,
): Promise<{ id: string; deleted: boolean }> {
  return readJson(
    await fetch(`/api/bgm/categories/${encodeURIComponent(categoryId)}`, { method: "DELETE" }),
  );
}
