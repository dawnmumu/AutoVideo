export interface VoiceStatus {
  edge_tts: {
    enabled: boolean;
    provider: "edge_tts";
    requires_api_key: boolean;
    default_voice: string;
    max_preview_text_chars: number;
  };
  fish_speech: {
    configured: boolean;
    enabled: boolean;
  };
}

export interface VoiceItem {
  id: string;
  name: string;
  provider: "edge_tts";
  locale: string;
  gender: string;
  content_categories: string[];
  personalities: string[];
}

export interface VoiceList {
  provider: "edge_tts";
  total: number;
  items: VoiceItem[];
}

export interface FetchVoicesInput {
  locale?: string;
  q?: string;
}

export interface CreateVoicePreviewInput {
  text: string;
  voice_id: string;
  rate: string;
  volume: string;
  pitch: string;
}

export interface VoicePreview {
  voice_id: string;
  filename: string;
  audio_url: string;
  media_type: "audio/mpeg";
  created_at: string;
}

export class VoiceApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail: Record<string, unknown>;

  constructor(code: string, status: number, detail: Record<string, unknown> = {}) {
    super(code);
    this.name = "VoiceApiError";
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
    throw new VoiceApiError(responseErrorCode(payload, response.status), response.status, detail);
  }
  return response.json() as Promise<T>;
}

export async function fetchVoiceStatus(): Promise<VoiceStatus> {
  return readJson(await fetch("/api/voices/status"));
}

export async function fetchVoices({
  locale = "zh-CN",
  q = "",
}: FetchVoicesInput = {}): Promise<VoiceList> {
  const params = new URLSearchParams();
  if (locale) {
    params.set("locale", locale);
  }
  if (q) {
    params.set("q", q);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return readJson(await fetch(`/api/voices${suffix}`));
}

export async function createVoicePreview(input: CreateVoicePreviewInput): Promise<VoicePreview> {
  return readJson(
    await fetch("/api/voices/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}
