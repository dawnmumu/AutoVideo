import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  createBgmCategory,
  deleteBgmCategory,
  deleteBgmTrack,
  fetchBgmLibrary,
  updateBgmCategory,
  updateBgmTrack,
  uploadBgmTrack,
} from "./api/bgm";
import type { BgmLibrary } from "./api/bgm";
import { fetchHealth } from "./api/health";
import {
  clearMaterialLibrary,
  fetchMaterialLibrarySummary,
  fetchMaterialRawFiles,
  fetchMaterialSourceStatus,
  saveMaterialSource,
  startMaterialIndex,
} from "./api/materials";
import {
  createOnlineMixTask,
  fetchMaterials,
  fetchOnlineMaterialStatus,
  generateScript,
  searchOnlineMaterials,
} from "./api/onlineRemix";
import {
  createSubtitleTemplateSet,
  deleteSubtitleTemplateSet,
  fetchSubtitleTemplateSets,
  previewSubtitleTemplateSet,
  previewSubtitleTimeline,
  resetSubtitlePresetOverride,
  updateSubtitlePresetOverride,
  updateSubtitleTemplateSet,
  validateSubtitleTemplateSet,
} from "./api/subtitles";
import type { SubtitleTemplateSet } from "./api/subtitles";
import { deleteTask, fetchTasks } from "./api/tasks";
import {
  VoiceApiError,
  createVoicePreview,
  fetchVoiceStatus,
  fetchVoices,
} from "./api/voices";
import type { VoiceItem } from "./api/voices";
import { VoiceSelector, selectDefaultVoice } from "./components/VoiceSelector";

vi.mock("./api/health", () => ({
  fetchHealth: vi.fn(),
}));

vi.mock("./api/onlineRemix", () => ({
  fetchOnlineMaterialStatus: vi.fn(),
  fetchMaterials: vi.fn(),
  generateScript: vi.fn(),
  searchOnlineMaterials: vi.fn(),
  createOnlineMixTask: vi.fn(),
}));

vi.mock("./api/subtitles", () => ({
  fetchSubtitleTemplateSets: vi.fn(),
  createSubtitleTemplateSet: vi.fn(),
  updateSubtitleTemplateSet: vi.fn(),
  deleteSubtitleTemplateSet: vi.fn(),
  updateSubtitlePresetOverride: vi.fn(),
  resetSubtitlePresetOverride: vi.fn(),
  validateSubtitleTemplateSet: vi.fn(),
  previewSubtitleTemplateSet: vi.fn(),
  previewSubtitleTimeline: vi.fn(),
}));

vi.mock("./api/tasks", () => ({
  fetchTasks: vi.fn(),
  deleteTask: vi.fn(),
}));

vi.mock("./api/voices", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/voices")>();
  return {
    ...actual,
    fetchVoiceStatus: vi.fn(),
    fetchVoices: vi.fn(),
    createVoicePreview: vi.fn(),
  };
});

vi.mock("./api/bgm", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/bgm")>();
  return {
    ...actual,
    fetchBgmLibrary: vi.fn(),
    uploadBgmTrack: vi.fn(),
    updateBgmTrack: vi.fn(),
    deleteBgmTrack: vi.fn(),
    createBgmCategory: vi.fn(),
    updateBgmCategory: vi.fn(),
    deleteBgmCategory: vi.fn(),
  };
});

vi.mock("./api/materials", () => ({
  fetchMaterialSourceStatus: vi.fn(),
  saveMaterialSource: vi.fn(),
  startMaterialIndex: vi.fn(),
  fetchMaterialIndexJob: vi.fn(),
  fetchMaterialLibrarySummary: vi.fn(),
  fetchMaterialRawFiles: vi.fn(),
  deleteMaterialRawFile: vi.fn(),
  clearMaterialLibrary: vi.fn(),
  readableMaterialError: vi.fn((error: unknown) =>
    error instanceof Error ? error.message : "MATERIAL_ERROR",
  ),
}));

const mockedFetchHealth = vi.mocked(fetchHealth);
const mockedFetchOnlineMaterialStatus = vi.mocked(fetchOnlineMaterialStatus);
const mockedFetchMaterials = vi.mocked(fetchMaterials);
const mockedFetchTasks = vi.mocked(fetchTasks);
const mockedDeleteTask = vi.mocked(deleteTask);
const mockedGenerateScript = vi.mocked(generateScript);
const mockedSearchOnlineMaterials = vi.mocked(searchOnlineMaterials);
const mockedCreateOnlineMixTask = vi.mocked(createOnlineMixTask);
const mockedFetchSubtitleTemplateSets = vi.mocked(fetchSubtitleTemplateSets);
const mockedCreateSubtitleTemplateSet = vi.mocked(createSubtitleTemplateSet);
const mockedUpdateSubtitleTemplateSet = vi.mocked(updateSubtitleTemplateSet);
const mockedDeleteSubtitleTemplateSet = vi.mocked(deleteSubtitleTemplateSet);
const mockedUpdateSubtitlePresetOverride = vi.mocked(updateSubtitlePresetOverride);
const mockedResetSubtitlePresetOverride = vi.mocked(resetSubtitlePresetOverride);
const mockedValidateSubtitleTemplateSet = vi.mocked(validateSubtitleTemplateSet);
const mockedPreviewSubtitleTemplateSet = vi.mocked(previewSubtitleTemplateSet);
const mockedPreviewSubtitleTimeline = vi.mocked(previewSubtitleTimeline);
const mockedFetchVoiceStatus = vi.mocked(fetchVoiceStatus);
const mockedFetchVoices = vi.mocked(fetchVoices);
const mockedCreateVoicePreview = vi.mocked(createVoicePreview);
const mockedFetchBgmLibrary = vi.mocked(fetchBgmLibrary);
const mockedUploadBgmTrack = vi.mocked(uploadBgmTrack);
const mockedUpdateBgmTrack = vi.mocked(updateBgmTrack);
const mockedDeleteBgmTrack = vi.mocked(deleteBgmTrack);
const mockedCreateBgmCategory = vi.mocked(createBgmCategory);
const mockedUpdateBgmCategory = vi.mocked(updateBgmCategory);
const mockedDeleteBgmCategory = vi.mocked(deleteBgmCategory);
const mockedFetchMaterialSourceStatus = vi.mocked(fetchMaterialSourceStatus);
const mockedFetchMaterialLibrarySummary = vi.mocked(fetchMaterialLibrarySummary);
const mockedFetchMaterialRawFiles = vi.mocked(fetchMaterialRawFiles);
const mockedSaveMaterialSource = vi.mocked(saveMaterialSource);
const mockedStartMaterialIndex = vi.mocked(startMaterialIndex);
const mockedClearMaterialLibrary = vi.mocked(clearMaterialLibrary);
const removedCopyPattern = new RegExp(
  [
    ["退出", "登录"].join(""),
    ["个人", "网盘"].join(""),
    ["NAS", " 登录"].join(""),
    ["to", "ken"].join(""),
  ].join("|"),
  "i",
);
const stylesCss = readFileSync("src/styles.css", "utf-8");
const indexHtml = readFileSync("index.html", "utf-8");
const defaultSubtitlePreviewText = "这是字幕预览，支持多个位置和不同倾斜角度";

afterEach(() => {
  vi.unstubAllGlobals();
});

const cleanBottomPreset: SubtitleTemplateSet = {
  id: "preset-clean-bottom",
  name: "清晰底部字幕",
  schema_version: 2,
  renderer_mode: "ass_plus",
  favorite: false,
  is_favorite: false,
  is_modified: false,
  templates: {
    bottom: {
      font_family: "PingFang SC",
      primary_color: "#FFFFFF",
    },
    highlight: {
      font_family: "PingFang SC",
      primary_color: "#FFD54F",
    },
    punch: {
      font_family: "PingFang SC",
      primary_color: "#FFFFFF",
      font_size_scale: 1.12,
    },
  },
  blocks: [
    {
      id: "bottom-main",
      role: "bottom",
      style: {
        font_family: "PingFang SC",
        primary_color: "#FFFFFF",
      },
      spans: [],
    },
    {
      id: "highlight-main",
      role: "highlight",
      style: {
        font_family: "PingFang SC",
        primary_color: "#FFD54F",
        font_size_scale: 1.08,
      },
      spans: [],
    },
    {
      id: "punch-main",
      role: "punch",
      style: {
        font_family: "PingFang SC",
        primary_color: "#FFFFFF",
        font_size_scale: 1.12,
      },
      spans: [],
    },
  ],
};

const customCaptionTemplate: SubtitleTemplateSet = {
  ...cleanBottomPreset,
  id: "tmpl-brand-bottom",
  name: "品牌底部字幕",
  favorite: false,
  is_favorite: false,
  is_modified: true,
};

function templateFixture(overrides: Partial<SubtitleTemplateSet>): SubtitleTemplateSet {
  return {
    ...cleanBottomPreset,
    ...overrides,
    templates: {
      ...cleanBottomPreset.templates,
      ...(overrides.templates ?? {}),
    },
    blocks: overrides.blocks ?? cleanBottomPreset.blocks,
  };
}

function bgmLibraryFixture(): BgmLibrary {
  return {
    items: [
      {
        id: "bgm_calm_late",
        filename: "bgm_calm_late.mp3",
        original_filename: "late-calm.mp3",
        display_name: "静谧长夜",
        category_id: "cat_calm",
        category_name: "舒缓",
        media_type: "audio/mpeg",
        extension: "mp3",
        size_bytes: 1536,
        duration_seconds: 15,
        audio_url: "/api/bgm/tracks/bgm_calm_late/file",
        created_at: "2026-06-21T00:00:00Z",
        updated_at: "2026-06-21T00:00:00Z",
      },
      {
        id: "bgm_calm",
        filename: "bgm_calm.mp3",
        original_filename: "calm.mp3",
        display_name: "舒缓钢琴",
        category_id: "cat_calm",
        category_name: "舒缓",
        media_type: "audio/mpeg",
        extension: "mp3",
        size_bytes: 1024,
        duration_seconds: 12.5,
        audio_url: "/api/bgm/tracks/bgm_calm/file",
        created_at: "2026-06-21T00:00:00Z",
        updated_at: "2026-06-21T00:00:00Z",
      },
      {
        id: "bgm_upbeat",
        filename: "bgm_upbeat.mp3",
        original_filename: "upbeat.mp3",
        display_name: "轻快鼓点",
        category_id: "cat_upbeat",
        category_name: "欢快",
        media_type: "audio/mpeg",
        extension: "mp3",
        size_bytes: 2048,
        duration_seconds: 10,
        audio_url: "/api/bgm/tracks/bgm_upbeat/file",
        created_at: "2026-06-21T00:00:00Z",
        updated_at: "2026-06-21T00:00:00Z",
      },
    ],
    categories: [
      {
        id: "cat_calm",
        name: "舒缓",
        sort_order: 10,
        track_count: 2,
        created_at: "2026-06-21T00:00:00Z",
        updated_at: "2026-06-21T00:00:00Z",
      },
      {
        id: "cat_upbeat",
        name: "欢快",
        sort_order: 20,
        track_count: 1,
        created_at: "2026-06-21T00:00:00Z",
        updated_at: "2026-06-21T00:00:00Z",
      },
    ],
    storage_status: "ready",
    total_tracks: 3,
    supported_extensions: ["mp3", "wav", "m4a", "aac", "ogg", "flac"],
  };
}

function scriptFixture() {
  return {
    id: "script-1",
    title: "睡前精油短视频",
    topic: "睡眠精油",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-24T00:00:00+00:00",
    shots: [
      {
        index: 1,
        duration: 5,
        narration: "睡前点一滴精油，让卧室慢慢安静下来。",
        subtitle: "睡前放松",
        visual_description: "relaxing bedroom night",
        keywords: ["relaxing bedroom night"],
      },
    ],
  };
}

function unclassifiedBgmLibraryFixture(): BgmLibrary {
  const base = bgmLibraryFixture();
  return {
    ...base,
    items: [
      {
        ...base.items[1],
        id: "bgm_unclassified",
        filename: "unclassified.mp3",
        original_filename: "unclassified.mp3",
        display_name: "无分类鼓组",
        category_id: null,
        category_name: "未分类",
        audio_url: "/api/bgm/tracks/bgm_unclassified/file",
      },
    ],
    categories: [],
    total_tracks: 1,
  };
}

function assertSubtitleEditorTypeContract(template: SubtitleTemplateSet) {
  const block = template.blocks[0];
  const role = block.role;
  const style = block.style;
  const spans = block.spans;
  const fontFamily = template.templates.bottom.font_family;

  return { fontFamily, role, spans, style };
}

assertSubtitleEditorTypeContract(cleanBottomPreset);

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    ),
    queryClient,
  };
}

function renderVoiceSelectorHarness({
  previewText = "睡前点一滴精油，让卧室慢慢安静下来。",
  initialVoice = null,
}: {
  previewText?: string;
  initialVoice?: VoiceItem | null;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  function Harness() {
    const [selectedVoice, setSelectedVoice] = useState<VoiceItem | null>(initialVoice);

    return (
      <VoiceSelector
        compact
        previewText={previewText}
        value={selectedVoice}
        onChange={setSelectedVoice}
      />
    );
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}

function previewTopPercent(testId: string): number {
  const value = screen.getByTestId(testId).style.top;
  return Number.parseFloat(value);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

describe("material API client", () => {
  async function actualMaterialApi() {
    return vi.importActual<typeof import("./api/materials")>("./api/materials");
  }

  function jsonResponse(payload: unknown, init: ResponseInit = {}) {
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  }

  it("calls material source and index endpoints with the backend DTO shape", async () => {
    const api = await actualMaterialApi();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = String(url);
      if (requestUrl === "/api/material-sources") {
        return jsonResponse({
          allowed_roots: [{ id: "demo", alias: "demo", display_name: "demo" }],
          current_source: null,
          latest_job: null,
        });
      }
      if (requestUrl === "/api/material-sources/current") {
        return jsonResponse({ current_source: { id: "source_1" }, job: null });
      }
      if (requestUrl === "/api/material-index/jobs") {
        return jsonResponse({ job_id: "job_1", status: "queued" });
      }
      if (requestUrl === "/api/material-index/jobs/job_1") {
        return jsonResponse({ id: "job_1", status: "queued" });
      }
      if (requestUrl === "/api/material-index/summary") {
        return jsonResponse({
          totals: { raw: 1, segments: 2, portrait: 1, landscape: 1, square: 0, unknown: 0, failed: 0 },
          current_source: null,
          latest_job: null,
        });
      }
      if (requestUrl === "/api/material-index/raw-files?limit=25&offset=50&status=failed") {
        return jsonResponse({ items: [], limit: 25, offset: 50, total: 0 });
      }
      if (requestUrl === "/api/material-index/raw-files/raw_1") {
        return jsonResponse({ id: "raw_1", deleted: true, deleted_segments: 1 });
      }
      if (requestUrl === "/api/material-index/library/clear") {
        return jsonResponse({ deleted_raw: 1, deleted_segments: 2 });
      }
      throw new Error(`Unexpected request: ${requestUrl} ${init?.method ?? "GET"}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.fetchMaterialSourceStatus()).resolves.toMatchObject({
      allowed_roots: [{ id: "demo", alias: "demo", display_name: "demo" }],
    });
    await expect(
      api.saveMaterialSource({ allowed_root_id: "demo", source_relative_path: "clips" }),
    ).resolves.toMatchObject({ current_source: { id: "source_1" } });
    await expect(api.startMaterialIndex({ source_config_id: "source_1", force: true })).resolves.toEqual({
      job_id: "job_1",
      status: "queued",
    });
    await expect(api.fetchMaterialIndexJob("job_1")).resolves.toMatchObject({ id: "job_1" });
    await expect(api.fetchMaterialLibrarySummary()).resolves.toMatchObject({
      totals: { raw: 1, segments: 2, portrait: 1, landscape: 1, failed: 0 },
    });
    await expect(
      api.fetchMaterialRawFiles({ limit: 25, offset: 50, status: "failed" }),
    ).resolves.toMatchObject({ limit: 25, offset: 50, total: 0 });
    await expect(api.deleteMaterialRawFile("raw_1")).resolves.toEqual({
      id: "raw_1",
      deleted: true,
      deleted_segments: 1,
    });
    await expect(api.clearMaterialLibrary()).resolves.toEqual({
      deleted_raw: 1,
      deleted_segments: 2,
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/material-sources");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/material-sources/current",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ allowed_root_id: "demo", source_relative_path: "clips" }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/material-index/jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ source_config_id: "source_1", force: true }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/material-index/library/clear",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ confirm: "CLEAR_MATERIAL_LIBRARY" }),
      }),
    );
  });

  it("maps material API errors to readable messages", async () => {
    const api = await actualMaterialApi();

    expect(
      api.readableMaterialError(new api.MaterialApiError("MATERIAL_SCAN_NO_SUPPORTED_FILES", 400)),
    ).toBe("素材目录里没有支持的视频文件");
    expect(api.readableMaterialError(new api.MaterialApiError("MATERIAL_SEGMENT_FAILED", 500))).toBe(
      "素材切片失败，请检查文件格式后重试",
    );
    expect(
      api.readableMaterialError(
        new api.MaterialApiError("MATERIAL_LIBRARY_CLEAR_CONFIRMATION_REQUIRED", 400),
      ),
    ).toBe("清空素材库需要输入确认文案");
  });
});

describe("AutoVideo shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState(null, "", "/");
    document.title = "AutoVideo";
    mockedFetchHealth.mockResolvedValue({
      app: "AutoVideo",
      status: "degraded",
      environment: "development",
      data_dir: "/tmp/autovideo",
      checks: {
        ffmpeg: {
          name: "ffmpeg",
          ok: false,
          required: true,
          message: "未找到 FFmpeg，可执行文件：ffmpeg",
        },
        fish_speech: {
          name: "fish_speech",
          ok: false,
          required: false,
          message: "Fish Speech 未配置，音色复刻功能将保持禁用",
        },
      },
    });
    mockedFetchOnlineMaterialStatus.mockResolvedValue({
      providers: [{ provider: "pexels", configured: true, enabled: true }],
      default_provider: "auto",
      candidate_token_secret_configured: true,
    });
    mockedFetchMaterials.mockResolvedValue([]);
    mockedFetchTasks.mockResolvedValue([]);
    mockedDeleteTask.mockResolvedValue(undefined);
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [],
      presets: [cleanBottomPreset],
    });
    mockedCreateSubtitleTemplateSet.mockResolvedValue(cleanBottomPreset);
    mockedUpdateSubtitleTemplateSet.mockResolvedValue(cleanBottomPreset);
    mockedDeleteSubtitleTemplateSet.mockResolvedValue(undefined);
    mockedUpdateSubtitlePresetOverride.mockResolvedValue(cleanBottomPreset);
    mockedResetSubtitlePresetOverride.mockResolvedValue(undefined);
    mockedValidateSubtitleTemplateSet.mockResolvedValue({
      ok: true,
      normalized: cleanBottomPreset,
      warnings: [],
    });
    mockedPreviewSubtitleTemplateSet.mockResolvedValue({
      mime_type: "image/png",
      data: "base64-png",
      resolution: { width: 1080, height: 1920 },
      warnings: [],
    });
    mockedPreviewSubtitleTimeline.mockResolvedValue({
      mime_type: "video/mp4",
      data: "base64-mp4",
      duration_ms: 1200,
      resolution: { width: 1080, height: 1920 },
      warnings: [],
    });
    mockedFetchVoiceStatus.mockResolvedValue({
      edge_tts: {
        enabled: true,
        provider: "edge_tts",
        requires_api_key: false,
        default_voice: "zh-CN-XiaoxiaoNeural",
        max_preview_text_chars: 180,
      },
      fish_speech: {
        configured: false,
        enabled: false,
      },
    });
    mockedFetchVoices.mockResolvedValue({
      provider: "edge_tts",
      total: 2,
      items: [
        {
          id: "zh-CN-XiaoxiaoNeural",
          name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
          provider: "edge_tts",
          locale: "zh-CN",
          gender: "Female",
          content_categories: ["General"],
          personalities: ["Warm", "Friendly"],
        },
        {
          id: "en-US-JennyNeural",
          name: "Microsoft Jenny Online (Natural) - English (United States)",
          provider: "edge_tts",
          locale: "en-US",
          gender: "Female",
          content_categories: ["General"],
          personalities: ["Friendly"],
        },
      ],
    });
    mockedCreateVoicePreview.mockResolvedValue({
      voice_id: "zh-CN-XiaoxiaoNeural",
      filename: "edge-tts-preview.mp3",
      audio_url: "/api/voices/previews/edge-tts-preview.mp3",
      media_type: "audio/mpeg",
      created_at: "2026-06-20T08:00:00+08:00",
    });
    const bgmLibrary = bgmLibraryFixture();
    mockedFetchBgmLibrary.mockResolvedValue(bgmLibrary);
    mockedUploadBgmTrack.mockImplementation(async ({ file, category_id }) => ({
      ...bgmLibrary.items[0],
      original_filename: file.name,
      display_name: file.name.replace(/\.[^.]+$/, ""),
      category_id: category_id ?? null,
      category_name: category_id ? "舒缓" : "未分类",
    }));
    mockedUpdateBgmTrack.mockResolvedValue(bgmLibrary.items[0]);
    mockedDeleteBgmTrack.mockResolvedValue({ id: "bgm_calm", deleted: true });
    mockedCreateBgmCategory.mockResolvedValue(bgmLibrary.categories[0]);
    mockedUpdateBgmCategory.mockResolvedValue(bgmLibrary.categories[0]);
    mockedDeleteBgmCategory.mockResolvedValue({ id: "cat_calm", deleted: true });
  });

  it.each([
    ["/", "混剪工作台", "混剪工作台 - AutoVideo"],
    ["/#subtitles", "字幕模板", "字幕模板 - AutoVideo"],
    ["/#bgm", "BGM 管理", "BGM 管理 - AutoVideo"],
    ["/#voices", "音色中心", "音色中心 - AutoVideo"],
    ["/#tasks", "任务与输出", "任务与输出 - AutoVideo"],
  ])("sets the browser title for %s", async (route, heading, title) => {
    window.history.pushState(null, "", route);

    renderApp();

    expect(await screen.findByRole("heading", { name: heading, level: 1 })).toBeInTheDocument();
    expect(document.title).toBe(title);
  });

  it("uses the default remix page title before the app hydrates", () => {
    expect(indexHtml).toMatch(/<title>混剪工作台 - AutoVideo<\/title>/);
  });

  it("renders the Chinese product navigation", async () => {
    renderApp();

    expect(await screen.findByRole("heading", { name: "混剪工作台" })).toBeInTheDocument();
    expect(screen.getByText("素材库")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "字幕模板" })).toBeInTheDocument();
    expect(screen.getByText("BGM 管理")).toBeInTheDocument();
    expect(screen.getByText("音色中心")).toBeInTheDocument();
    expect(screen.getByText("功能提取处理")).toBeInTheDocument();
    expect(screen.getByText("任务与输出")).toBeInTheDocument();
    expect(screen.getByText("系统设置")).toBeInTheDocument();
  });

  it("enables material library navigation", async () => {
    window.location.hash = "#materials";
    renderApp();

    expect(await screen.findByRole("heading", { name: "素材库", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "素材库" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "主导航" })).toHaveTextContent("素材库");
    expect(document.title).toBe("素材库 - AutoVideo");
  });

  it("renders material source config, job status, stats, and raw files", async () => {
    mockedFetchMaterialSourceStatus.mockResolvedValue({
      allowed_roots: [{ id: "demo", alias: "demo", display_name: "demo" }],
      current_source: null,
      latest_job: null,
    });
    mockedFetchMaterialLibrarySummary.mockResolvedValue({
      totals: { raw: 1, segments: 2, portrait: 1, landscape: 0, square: 0, unknown: 0, failed: 0 },
      current_source: null,
      latest_job: null,
    });
    mockedFetchMaterialRawFiles.mockResolvedValue({
      items: [
        {
          id: "raw_1",
          allowed_root_id: "demo",
          source_relative_path: "clips/clip.mp4",
          filename: "clip.mp4",
          source_display_path: "demo/clips/clip.mp4",
          size_bytes: 1024,
          duration_seconds: 12,
          orientation: "portrait",
          segments: 2,
          status: "ready",
          error_summary: null,
          created_at: "2026-06-25T00:00:00Z",
          updated_at: "2026-06-25T00:00:00Z",
        },
      ],
      limit: 50,
      offset: 0,
      total: 1,
    });
    window.location.hash = "#materials";
    renderApp();

    expect(await screen.findByLabelText("允许根目录")).toBeInTheDocument();
    expect(screen.getByLabelText("子目录")).toBeInTheDocument();
    expect(screen.getByText("clip.mp4")).toBeInTheDocument();
    expect(screen.getByText("2 个切片")).toBeInTheDocument();
  });

  it("material workbench uses accessible expandable rows and clear confirmation", async () => {
    mockedFetchMaterialSourceStatus.mockResolvedValue({
      allowed_roots: [{ id: "demo", alias: "demo", display_name: "demo" }],
      current_source: {
        id: "source_1",
        allowed_root_id: "demo",
        allowed_root_alias: "demo",
        source_display_path: "demo/clips",
        source_relative_path: "clips",
        status: "active",
        created_at: "2026-06-25T00:00:00Z",
        updated_at: "2026-06-25T00:00:00Z",
      },
      latest_job: {
        id: "job_1",
        source_config_id: "source_1",
        allowed_root_id: "demo",
        source_relative_path: "clips",
        status: "running",
        stage: "segmenting",
        progress_current: 1,
        progress_total: 2,
        progress: { current: 1, total: 2 },
        raw_files_total: 1,
        segments_total: 1,
        failed_total: 0,
        counts: { raw: 1, segments: 1, failed: 0 },
        attempt_count: 1,
        error_summary: null,
        created_at: "2026-06-25T00:00:00Z",
      },
    });
    mockedFetchMaterialLibrarySummary.mockResolvedValue({
      totals: { raw: 1, segments: 2, portrait: 1, landscape: 0, square: 0, unknown: 0, failed: 0 },
      current_source: null,
      latest_job: null,
    });
    mockedFetchMaterialRawFiles.mockResolvedValue({
      items: [
        {
          id: "raw_1",
          allowed_root_id: "demo",
          source_relative_path: "clips/clip.mp4",
          filename: "clip.mp4",
          source_display_path: "demo/clips/clip.mp4",
          size_bytes: 1024,
          duration_seconds: 12,
          orientation: "portrait",
          segments: 2,
          status: "ready",
          error_summary: null,
          created_at: "2026-06-25T00:00:00Z",
          updated_at: "2026-06-25T00:00:00Z",
        },
      ],
      limit: 50,
      offset: 0,
      total: 1,
    });
    window.location.hash = "#materials";
    renderApp();
    expect(await screen.findByRole("status", { name: "素材索引状态" })).toHaveAttribute(
      "aria-live",
      "polite",
    );
    const rowButton = await screen.findByRole("button", { name: /展开 clip.mp4/ });
    expect(rowButton).toHaveAttribute("aria-expanded", "false");
    rowButton.focus();
    await userEvent.keyboard("{Enter}");
    expect(rowButton).toHaveAttribute("aria-expanded", "true");
    const clearButton = screen.getByRole("button", { name: "清空素材库" });
    clearButton.focus();
    await userEvent.click(clearButton);
    expect(await screen.findByRole("dialog", { name: "清空素材库确认" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "取消清空" }));
    expect(clearButton).toHaveFocus();
  });

  it("refreshes remix material picker cache after material library mutations", async () => {
    const user = userEvent.setup();
    const currentSource = {
      id: "source_1",
      allowed_root_id: "demo",
      allowed_root_alias: "demo",
      source_display_path: "demo/clips",
      source_relative_path: "clips",
      status: "active",
      created_at: "2026-06-25T00:00:00Z",
      updated_at: "2026-06-25T00:00:00Z",
    };
    mockedFetchMaterialSourceStatus.mockResolvedValue({
      allowed_roots: [{ id: "demo", alias: "demo", display_name: "demo" }],
      current_source: currentSource,
      latest_job: null,
    });
    mockedFetchMaterialLibrarySummary.mockResolvedValue({
      totals: { raw: 0, segments: 0, portrait: 0, landscape: 0, square: 0, unknown: 0, failed: 0 },
      current_source: currentSource,
      latest_job: null,
    });
    mockedFetchMaterialRawFiles.mockResolvedValue({
      items: [],
      limit: 50,
      offset: 0,
      total: 0,
    });
    mockedSaveMaterialSource.mockResolvedValue({ current_source: currentSource, job: null });
    mockedStartMaterialIndex.mockResolvedValue({ job_id: "job_1", status: "queued" });
    mockedClearMaterialLibrary.mockResolvedValue({ deleted_raw: 0, deleted_segments: 0 });
    renderApp();

    await waitFor(() => expect(mockedFetchMaterials).toHaveBeenCalled());
    let materialsFetchCount = mockedFetchMaterials.mock.calls.length;

    await user.click(screen.getByRole("link", { name: "素材库" }));
    await screen.findByRole("article", { name: "素材库" });
    await user.click(screen.getByRole("button", { name: "保存来源" }));
    await waitFor(() =>
      expect(mockedFetchMaterials.mock.calls.length).toBeGreaterThan(materialsFetchCount),
    );
    materialsFetchCount = mockedFetchMaterials.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "开始索引" }));
    await waitFor(() =>
      expect(mockedFetchMaterials.mock.calls.length).toBeGreaterThan(materialsFetchCount),
    );
    materialsFetchCount = mockedFetchMaterials.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "清空素材库" }));
    await user.click(await screen.findByRole("button", { name: "确认清空" }));
    await waitFor(() =>
      expect(mockedFetchMaterials.mock.calls.length).toBeGreaterThan(materialsFetchCount),
    );
  });

  it("marks the active desktop and mobile navigation items", async () => {
    renderApp();

    await screen.findByRole("heading", { name: "混剪工作台" });

    expect(screen.getByRole("link", { name: "混剪工作台" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "混剪" })).toHaveAttribute("aria-current", "page");
  });

  it("opens subtitle templates from desktop navigation and updates active state", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));

    expect(window.location.hash).toBe("#subtitles");
    expect(screen.getByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("管理字幕样式与预览")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "线上混剪" })).not.toBeInTheDocument();
    expect(document.querySelector("section#remix")).toHaveAttribute("hidden");
    expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "字幕" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("status")).toHaveTextContent("可用模板 1 个");
  });

  it("opens subtitle templates from a direct hash link", async () => {
    window.history.pushState(null, "", "/#subtitles");

    renderApp();

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByLabelText("视频主题")).not.toBeInTheDocument();
  });

  it("uses a single-column grid style for the subtitle workspace", async () => {
    window.history.pushState(null, "", "/#subtitles");

    renderApp();

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    const subtitleSection = document.querySelector("section#subtitles") as HTMLElement;
    expect(subtitleSection).toHaveClass("content-grid", "single-column");
  });

  it("keeps subtitle preview controls inside a bounded middle column", async () => {
    window.history.pushState(null, "", "/#subtitles");

    renderApp();

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    const previewPanel = screen.getByRole("region", { name: "字幕预览" });
    const previewStack = previewPanel.querySelector(".subtitle-preview-stack");

    expect(previewStack).toHaveAttribute("data-layout", "bounded-preview-controls");
    expect(within(previewStack as HTMLElement).getByLabelText("示例文本")).toBeInTheDocument();
    expect(within(previewStack as HTMLElement).getByTestId("subtitle-preview-frame")).toBeInTheDocument();
    expect(within(previewStack as HTMLElement).getByRole("button", { name: "精准预览" })).toBeInTheDocument();
  });

  it("stacks the subtitle workbench before compact desktop columns can overflow", () => {
    expect(stylesCss).toMatch(
      /@media \(max-width: 1160px\) \{[\s\S]*?\.subtitle-workbench-grid \{[\s\S]*?grid-template-columns: 1fr;/,
    );
  });

  it("uses the target dark video preview canvas", () => {
    expect(stylesCss).toMatch(/\.subtitle-preview-screen \{[\s\S]*?background:\s*#0b0f14;/);
    expect(stylesCss).toMatch(/\.subtitle-preview-frame \{[\s\S]*?background:\s*#101820;/);
    expect(stylesCss).toMatch(
      /\.subtitle-preview-safe-area \{[\s\S]*?border-top:\s*1px dashed rgba\(255,\s*255,\s*255,\s*0\.22\);/,
    );
    expect(stylesCss).not.toMatch(/\.subtitle-preview-frame \{[\s\S]*?background:\s*linear-gradient/);
  });

  it("scales rendered subtitle previews to the live preview screen width", () => {
    expect(stylesCss).toMatch(
      /\.subtitle-preview-panel img,\s*\.subtitle-preview-panel video \{[\s\S]*?width:\s*min\(100%,\s*360px\);/,
    );
  });

  it("keeps the workbench voice dropdown responsive without hover-only dependencies", () => {
    expect(stylesCss).toMatch(
      /@media \(max-width: 1160px\) \{[\s\S]*?\.voice-selector-filters[\s\S]*?grid-template-columns:\s*1fr;/,
    );
    expect(stylesCss).toMatch(
      /@media \(max-width: 760px\) \{[\s\S]*?\.voice-selector-filters[\s\S]*?grid-template-columns:\s*1fr;/,
    );
    expect(stylesCss).toMatch(
      /\.voice-selector input,\s*\.voice-selector select,\s*\.voice-dropdown select,\s*\.voice-dropdown button,\s*\.voice-selector button \{[\s\S]*?min-height:\s*44px;/,
    );
    expect(stylesCss).toMatch(
      /\.voice-dropdown,\s*\.voice-selector,\s*\.bgm-selector \{[\s\S]*?grid-column:\s*1 \/ -1;/,
    );
    expect(stylesCss).toMatch(
      /\.voice-dropdown select \{[\s\S]*?min-width:\s*0;[\s\S]*?text-overflow:\s*ellipsis;/,
    );
    expect(stylesCss).toMatch(
      /\.voice-dropdown label,\s*\.voice-dropdown \.voice-selected-summary \{[\s\S]*?min-width:\s*0;/,
    );
    expect(stylesCss).toMatch(
      /\.voice-preview-audio \{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*100%;/,
    );
    expect(stylesCss).toMatch(
      /\.voice-selector \.voice-search-input input \{[^}]*border:\s*0;[^}]*padding:\s*8px 0;[^}]*min-height:\s*44px;[^}]*min-width:\s*0;[^}]*\}/,
    );
    expect(stylesCss).not.toMatch(/\.voice-selector[^{,]*:hover/);
  });

  it("returns to the remix workspace through hash navigation", async () => {
    const user = userEvent.setup();
    window.history.pushState(null, "", "/#subtitles");
    renderApp();

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "混剪工作台" }));

    expect(window.location.hash).toBe("#remix");
    expect(await screen.findByLabelText("视频主题")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "混剪工作台" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("syncs the active section when the hash changes", async () => {
    renderApp();

    await screen.findByLabelText("视频主题");
    window.history.pushState(null, "", "/#subtitles");
    window.dispatchEvent(new HashChangeEvent("hashchange"));

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("normalizes unknown hashes to the remix workspace", async () => {
    window.history.pushState(null, "", "/#unknown");

    renderApp();

    expect(await screen.findByLabelText("视频主题")).toBeInTheDocument();
    expect(window.location.hash).toBe("#remix");
    expect(screen.getByRole("link", { name: "混剪工作台" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("opens subtitle templates from mobile navigation and updates active state", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕" }));

    expect(window.location.hash).toBe("#subtitles");
    expect(screen.getByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "字幕" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("opens the voice center from navigation and lists Microsoft Edge TTS voices", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "音色中心" }));

    expect(window.location.hash).toBe("#voices");
    expect(screen.getByRole("heading", { name: "音色中心", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("微软 Edge TTS 免费音色试听")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "音色中心" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "音色" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("button", { name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByLabelText("试听文案")).toHaveAttribute("maxlength", "180");
    expect(screen.getByLabelText("试听文案长度")).toHaveTextContent("18 / 180");
    expect(screen.getByRole("button", { name: "音色复刻" })).toBeDisabled();
    expect(screen.getByText("未配置 AUTOVIDEO_FISH_SPEECH_URL")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Microsoft Jenny Online (Natural) - English (United States)" })).toBeInTheDocument();
    expect(mockedFetchVoiceStatus).toHaveBeenCalled();
    expect(mockedFetchVoices).toHaveBeenCalledWith({ locale: "zh-CN", q: "" });
  });

  it("opens BGM management from navigation and renders library controls", async () => {
    renderApp();

    await userEvent.click(screen.getByRole("link", { name: "BGM 管理" }));

    expect(window.location.hash).toBe("#bgm");
    expect(await screen.findByRole("article", { name: "BGM 管理" })).toBeInTheDocument();
    expect(screen.getByLabelText("BGM 音频文件")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上传 BGM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新增分类" })).toBeInTheDocument();
    expect(screen.getAllByText("舒缓钢琴").length).toBeGreaterThan(0);
    expect(
      within(screen.getByRole("article", { name: "舒缓钢琴" })).getByText(/更新 2026/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("试听 舒缓钢琴")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_calm/file",
    );
  });

  it("clears the BGM file input after a successful upload", async () => {
    renderApp();

    await userEvent.click(screen.getByRole("link", { name: "BGM 管理" }));
    const fileInput = (await screen.findByLabelText("BGM 音频文件")) as HTMLInputElement;
    const file = new File(["fake audio bytes"], "new-track.mp3", { type: "audio/mpeg" });

    await userEvent.upload(fileInput, file);
    expect(fileInput.files?.[0]).toBe(file);
    await userEvent.click(screen.getByRole("button", { name: "上传 BGM" }));

    await waitFor(() =>
      expect(mockedUploadBgmTrack).toHaveBeenCalledWith({
        file,
        category_id: null,
      }),
    );
    await waitFor(() => expect(fileInput.value).toBe(""));
    expect(fileInput.files).toHaveLength(0);
  });

  it("uses the latest BGM draft name when category changes after editing", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: "BGM 管理" }));
    const trackCard = await screen.findByRole("article", { name: "舒缓钢琴" });
    const nameInput = within(trackCard).getByLabelText("BGM 名称");
    const categorySelect = within(trackCard).getByLabelText("分类");

    await user.clear(nameInput);
    await user.type(nameInput, "晨间钢琴");
    await user.selectOptions(categorySelect, "cat_upbeat");

    await waitFor(() =>
      expect(mockedUpdateBgmTrack.mock.calls.map(([input]) => input)).toContainEqual({
        id: "bgm_calm",
        display_name: "晨间钢琴",
        category_id: "cat_upbeat",
      }),
    );
    expect(mockedUpdateBgmTrack.mock.calls.map(([input]) => input)).not.toContainEqual({
      id: "bgm_calm",
      display_name: "舒缓钢琴",
      category_id: "cat_upbeat",
    });
  });

  it("clears a deleted upload category before uploading a BGM file", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    try {
      renderApp();

      await user.click(screen.getByRole("link", { name: "BGM 管理" }));
      await user.selectOptions(await screen.findByLabelText("上传分类"), "cat_calm");
      await user.click(
        within(screen.getByRole("region", { name: "BGM 分类" })).getByRole("button", {
          name: "删除分类 舒缓",
        }),
      );

      await waitFor(() =>
        expect(mockedDeleteBgmCategory.mock.calls.map(([categoryId]) => categoryId)).toContain(
          "cat_calm",
        ),
      );
      const fileInput = screen.getByLabelText("BGM 音频文件") as HTMLInputElement;
      const file = new File(["fake audio bytes"], "after-delete.mp3", { type: "audio/mpeg" });

      await user.upload(fileInput, file);
      await user.click(screen.getByRole("button", { name: "上传 BGM" }));

      await waitFor(() =>
        expect(mockedUploadBgmTrack).toHaveBeenCalledWith({
          file,
          category_id: null,
        }),
      );
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it("creates a Microsoft Edge TTS preview from the selected voice", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "音色中心" }));
    await user.clear(await screen.findByLabelText("试听文案"));
    await user.type(screen.getByLabelText("试听文案"), "你好，欢迎使用 AutoVideo。");
    await user.click(screen.getByRole("button", { name: "生成试听" }));

    await waitFor(() => {
      expect(mockedCreateVoicePreview).toHaveBeenCalledWith({
        text: "你好，欢迎使用 AutoVideo。",
        voice_id: "zh-CN-XiaoxiaoNeural",
        rate: "+0%",
        volume: "+0%",
        pitch: "+0Hz",
      });
    });
    expect(await screen.findByLabelText("音色试听音频")).toHaveAttribute(
      "src",
      "/api/voices/previews/edge-tts-preview.mp3",
    );
  });

  it("shows actionable voice preview errors in Chinese", async () => {
    const user = userEvent.setup();
    mockedCreateVoicePreview.mockRejectedValueOnce(
      new VoiceApiError("VOICE_PREVIEW_TEXT_TOO_LONG", 400, { max_chars: 6 }),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "音色中心" }));
    await user.click(screen.getByRole("button", { name: "生成试听" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("试听文案不能超过 6 个字");
  });

  it("selects the default voice through the shared VoiceSelector helper", () => {
    const voiceItems: VoiceItem[] = [
      {
        id: "en-US-JennyNeural",
        name: "Microsoft Jenny Online (Natural) - English (United States)",
        provider: "edge_tts",
        locale: "en-US",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Friendly"],
      },
      {
        id: "zh-CN-XiaoxiaoNeural",
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
        provider: "edge_tts",
        locale: "zh-CN",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Warm", "Friendly"],
      },
    ];

    expect(
      selectDefaultVoice(voiceItems, "zh-CN-XiaoxiaoNeural", null, {
        preserveCurrentVoice: false,
      })?.id,
    ).toBe("zh-CN-XiaoxiaoNeural");
    expect(
      selectDefaultVoice(voiceItems, "zh-CN-XiaoxiaoNeural", "en-US-JennyNeural", {
        preserveCurrentVoice: false,
      })?.id,
    ).toBe("zh-CN-XiaoxiaoNeural");
    expect(
      selectDefaultVoice(voiceItems, "zh-CN-XiaoxiaoNeural", "en-US-JennyNeural", {
        preserveCurrentVoice: true,
      })?.id,
    ).toBe("en-US-JennyNeural");
    expect(
      selectDefaultVoice(voiceItems, null, null, { preserveCurrentVoice: false })?.id,
    ).toBe("en-US-JennyNeural");
    expect(
      selectDefaultVoice(voiceItems, "missing-default", "missing-current", {
        preserveCurrentVoice: true,
      })?.id,
    ).toBe("en-US-JennyNeural");
    expect(
      selectDefaultVoice([], "zh-CN-XiaoxiaoNeural", null, {
        preserveCurrentVoice: false,
      }),
    ).toBeNull();
  });

  it("waits for voice status before falling back to the first VoiceSelector voice", async () => {
    let resolveStatus: (
      value: Awaited<ReturnType<typeof fetchVoiceStatus>>,
    ) => void = () => undefined;
    const statusPromise = new Promise<Awaited<ReturnType<typeof fetchVoiceStatus>>>((resolve) => {
      resolveStatus = resolve;
    });
    mockedFetchVoiceStatus.mockReturnValueOnce(statusPromise);
    mockedFetchVoices.mockResolvedValueOnce({
      provider: "edge_tts",
      total: 2,
      items: [
        {
          id: "en-US-JennyNeural",
          name: "Microsoft Jenny Online (Natural) - English (United States)",
          provider: "edge_tts",
          locale: "en-US",
          gender: "Female",
          content_categories: ["General"],
          personalities: ["Friendly"],
        },
        {
          id: "zh-CN-XiaoxiaoNeural",
          name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
          provider: "edge_tts",
          locale: "zh-CN",
          gender: "Female",
          content_categories: ["General"],
          personalities: ["Warm", "Friendly"],
        },
      ],
    });
    renderVoiceSelectorHarness();

    const firstVoice = await screen.findByRole("button", {
      name: "Microsoft Jenny Online (Natural) - English (United States)",
    });
    const defaultVoice = screen.getByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    });
    expect(firstVoice).toHaveAttribute("aria-pressed", "false");
    expect(defaultVoice).toHaveAttribute("aria-pressed", "false");

    await act(async () => {
      resolveStatus({
        edge_tts: {
          enabled: true,
          provider: "edge_tts",
          requires_api_key: false,
          default_voice: "zh-CN-XiaoxiaoNeural",
          max_preview_text_chars: 180,
        },
        fish_speech: {
          configured: false,
          enabled: false,
        },
      });
      await statusPromise;
    });

    await waitFor(() => {
      expect(defaultVoice).toHaveAttribute("aria-pressed", "true");
    });
    expect(firstVoice).toHaveAttribute("aria-pressed", "false");
  });

  it("falls back to the first VoiceSelector voice when status fails", async () => {
    mockedFetchVoiceStatus.mockRejectedValueOnce(new VoiceApiError("VOICE_STATUS_FAILED", 503));
    renderVoiceSelectorHarness();

    expect(
      await screen.findByRole("button", {
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("falls back to the first VoiceSelector voice when status has no default voice", async () => {
    mockedFetchVoiceStatus.mockResolvedValueOnce({
      edge_tts: {
        enabled: true,
        provider: "edge_tts",
        requires_api_key: false,
        default_voice: "",
        max_preview_text_chars: 180,
      },
      fish_speech: {
        configured: false,
        enabled: false,
      },
    });
    renderVoiceSelectorHarness();

    expect(
      await screen.findByRole("button", {
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("falls back to the first VoiceSelector voice when the default voice is missing from the list", async () => {
    mockedFetchVoiceStatus.mockResolvedValueOnce({
      edge_tts: {
        enabled: true,
        provider: "edge_tts",
        requires_api_key: false,
        default_voice: "missing-voice",
        max_preview_text_chars: 180,
      },
      fish_speech: {
        configured: false,
        enabled: false,
      },
    });
    renderVoiceSelectorHarness();

    expect(
      await screen.findByRole("button", {
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps a manually selected VoiceSelector voice instead of the Edge TTS default voice", async () => {
    const user = userEvent.setup();
    mockedFetchVoices.mockResolvedValueOnce({
      provider: "edge_tts",
      total: 2,
      items: [
        {
          id: "en-US-JennyNeural",
          name: "Microsoft Jenny Online (Natural) - English (United States)",
          provider: "edge_tts",
          locale: "en-US",
          gender: "Female",
          content_categories: ["General"],
          personalities: ["Friendly"],
        },
        {
          id: "zh-CN-XiaoxiaoNeural",
          name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
          provider: "edge_tts",
          locale: "zh-CN",
          gender: "Female",
          content_categories: ["General"],
          personalities: ["Warm", "Friendly"],
        },
      ],
    });
    renderVoiceSelectorHarness();

    await user.click(
      await screen.findByRole("button", {
        name: "Microsoft Jenny Online (Natural) - English (United States)",
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: "Microsoft Jenny Online (Natural) - English (United States)",
        }),
      ).toHaveAttribute("aria-pressed", "true");
    });
  });

  it("keeps an initial controlled VoiceSelector voice instead of the Edge TTS default voice", async () => {
    renderVoiceSelectorHarness({
      initialVoice: {
        id: "en-US-JennyNeural",
        name: "Microsoft Jenny Online (Natural) - English (United States)",
        provider: "edge_tts",
        locale: "en-US",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Friendly"],
      },
    });

    const initialVoice = await screen.findByRole("button", {
      name: "Microsoft Jenny Online (Natural) - English (United States)",
    });
    const defaultVoice = screen.getByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    });

    await waitFor(() => {
      expect(initialVoice).toHaveAttribute("aria-pressed", "true");
    });
    expect(defaultVoice).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the selected VoiceSelector voice when filters have no matching voices", async () => {
    const user = userEvent.setup();
    const selectedVoice: VoiceItem = {
      id: "zh-CN-XiaoxiaoNeural",
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
      provider: "edge_tts",
      locale: "zh-CN",
      gender: "Female",
      content_categories: ["General"],
      personalities: ["Warm", "Friendly"],
    };
    const fallbackVoice: VoiceItem = {
      id: "en-US-JennyNeural",
      name: "Microsoft Jenny Online (Natural) - English (United States)",
      provider: "edge_tts",
      locale: "en-US",
      gender: "Female",
      content_categories: ["General"],
      personalities: ["Friendly"],
    };
    mockedFetchVoices.mockImplementation(({ q = "" } = {}) =>
      Promise.resolve({
        provider: "edge_tts",
        total: q ? 0 : 2,
        items: q ? [] : [selectedVoice, fallbackVoice],
      }),
    );
    renderVoiceSelectorHarness({ initialVoice: selectedVoice });

    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    });
    await user.type(screen.getByLabelText("搜索音色"), "missing");

    expect(await screen.findByText("没有匹配音色")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText("Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)"),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText("未选择音色")).not.toBeInTheDocument();
  });

  it("renders VoiceSelector with the default Edge TTS voice", async () => {
    renderVoiceSelectorHarness();

    expect(await screen.findByRole("group", { name: "旁白音色" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", {
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("音色语言")).toHaveDisplayValue("中文");
    expect(mockedFetchVoiceStatus).toHaveBeenCalledTimes(1);
    expect(mockedFetchVoices).toHaveBeenCalledWith({ locale: "zh-CN", q: "" });
  });

  it("shows an FFmpeg audio mix capability loading state before health is known", async () => {
    const health = deferred<Awaited<ReturnType<typeof fetchHealth>>>();
    mockedFetchHealth.mockReturnValueOnce(health.promise);

    renderApp();

    expect(
      await screen.findByText("正在检测 FFmpeg 音频合成能力"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("配置 FFmpeg 后，所选旁白和 BGM 会合成到最终 MP4"),
    ).not.toBeInTheDocument();

    await act(async () => {
      health.resolve({
        app: "AutoVideo",
        status: "degraded",
        environment: "development",
        data_dir: "/tmp/autovideo",
        checks: {
          ffmpeg: {
            name: "ffmpeg",
            ok: false,
            required: true,
            message: "未找到 FFmpeg，可执行文件：ffmpeg",
          },
          fish_speech: {
            name: "fish_speech",
            ok: false,
            required: false,
            message: "Fish Speech 未配置，音色复刻功能将保持禁用",
          },
        },
      });
      await health.promise;
    });
  });

  it("states selected narration and BGM need FFmpeg before final output mix", async () => {
    renderApp();

    expect(
      await screen.findByText("配置 FFmpeg 后，所选旁白和 BGM 会合成到最终 MP4"),
    ).toBeInTheDocument();
  });

  it("states selected narration and BGM are mixed when FFmpeg is available", async () => {
    mockedFetchHealth.mockResolvedValueOnce({
      app: "AutoVideo",
      status: "ok",
      environment: "development",
      data_dir: "/tmp/autovideo",
      checks: {
        ffmpeg: {
          name: "ffmpeg",
          ok: true,
          required: true,
          message: "FFmpeg 可用",
        },
        fish_speech: {
          name: "fish_speech",
          ok: false,
          required: false,
          message: "Fish Speech 未配置，音色复刻功能将保持禁用",
        },
      },
    });
    renderApp();

    expect(
      await screen.findByText("所选旁白和 BGM 会合成到最终 MP4"),
    ).toBeInTheDocument();
  });

  it("previews the selected VoiceSelector voice with provided narration text", async () => {
    const user = userEvent.setup();
    renderVoiceSelectorHarness({ previewText: "睡前点一滴精油，让卧室慢慢安静下来。" });

    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    });
    await user.click(screen.getByRole("button", { name: "试听旁白音色" }));

    await waitFor(() => {
      expect(mockedCreateVoicePreview).toHaveBeenCalledWith({
        text: "睡前点一滴精油，让卧室慢慢安静下来。",
        voice_id: "zh-CN-XiaoxiaoNeural",
        rate: "+0%",
        volume: "+0%",
        pitch: "+0Hz",
      });
    });
  });

  it("clears VoiceSelector preview audio after selected voice changes", async () => {
    const user = userEvent.setup();
    renderVoiceSelectorHarness({ previewText: "睡前点一滴精油，让卧室慢慢安静下来。" });

    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    });
    await user.click(screen.getByRole("button", { name: "试听旁白音色" }));
    expect(await screen.findByLabelText("旁白音色试听音频")).toHaveAttribute(
      "src",
      "/api/voices/previews/edge-tts-preview.mp3",
    );

    await user.click(
      screen.getByRole("button", {
        name: "Microsoft Jenny Online (Natural) - English (United States)",
      }),
    );

    await waitFor(() => {
      expect(screen.queryByLabelText("旁白音色试听音频")).not.toBeInTheDocument();
    });
  });

  it("keeps enabled mobile navigation entries including BGM before future disabled entries", async () => {
    renderApp();

    const mobileNav = screen.getByRole("navigation", { name: "移动端导航" });
    const labels = Array.from(mobileNav.querySelectorAll("a, span")).map((item) =>
      item.textContent?.trim(),
    );

    expect(labels.slice(0, 6)).toEqual(["混剪", "素材", "字幕", "BGM", "音色", "任务"]);
  });

  it("declares responsive BGM workbench styles without hover-only dependencies", () => {
    expect(stylesCss).toMatch(/\.bgm-workbench-grid \{[\s\S]*?grid-template-columns:/);
    expect(stylesCss).toMatch(/\.bgm-list-panel \{[\s\S]*?grid-column:\s*1 \/ -1;/);
    expect(stylesCss).not.toMatch(
      /\.bgm-track-row \{[\s\S]*?grid-template-columns:\s*minmax\(180px,\s*1fr\) minmax\(220px,\s*1fr\) minmax\(150px,\s*0\.7fr\) minmax\(130px,\s*0\.55fr\) max-content;/,
    );
    expect(stylesCss).toMatch(
      /@media \(max-width: 760px\) \{[\s\S]*?\.bgm-workbench-grid \{[\s\S]*?grid-template-columns: 1fr;/,
    );
    expect(stylesCss).toMatch(
      /\.bgm-management-panel input,\s*\.bgm-management-panel select,\s*\.bgm-management-panel button \{[\s\S]*?min-height:\s*44px;/,
    );
    expect(stylesCss).toMatch(
      /\.bgm-audio-player \{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*100%;/,
    );
    expect(stylesCss).not.toMatch(/\.bgm-management-panel[^{,]*:hover/);
  });

  it("opens the task output list and links rendered videos for download", async () => {
    const user = userEvent.setup();
    mockedFetchTasks.mockResolvedValue([
      {
        id: "task-video-1",
        title: "中小企业 AI 效率",
        status: "succeeded",
        material_ids: ["material-1", "material-2"],
        options: {
          aspect_ratio: "9:16",
          resolution: "1080x1920",
          subtitle_enabled: true,
        },
        output: {
          download_url: "/api/tasks/task-video-1/output",
          filename: "output.mp4",
          media_type: "video/mp4",
          kind: "video",
          render_status: "subtitle_burned",
        },
        created_at: "2026-06-18T09:30:00+08:00",
        updated_at: "2026-06-18T09:31:30+08:00",
      },
    ]);
    renderApp();

    await user.click(await screen.findByRole("link", { name: "任务与输出" }));

    expect(window.location.hash).toBe("#tasks");
    expect(screen.getByRole("heading", { name: "任务与输出", level: 1 })).toBeInTheDocument();
    const taskCard = await screen.findByRole("article", { name: "中小企业 AI 效率" });
    expect(within(taskCard).getByText("成功")).toBeInTheDocument();
    expect(within(taskCard).getByText("素材 2 个")).toBeInTheDocument();
    expect(within(taskCard).getByText("9:16")).toBeInTheDocument();
    expect(within(taskCard).getByText("1080x1920")).toBeInTheDocument();
    expect(within(taskCard).getByText("渲染 字幕已烧录")).toBeInTheDocument();
    expect(within(taskCard).queryByText("渲染 subtitle_burned")).not.toBeInTheDocument();
    const downloadLink = within(taskCard).getByRole("link", { name: "下载视频" });
    expect(downloadLink).toHaveAttribute("href", "/api/tasks/task-video-1/output");
    expect(downloadLink).toHaveAttribute("download", "中小企业 AI 效率.mp4");
    expect(mockedFetchTasks).toHaveBeenCalledWith({ limit: 50, offset: 0 });
  });

  it("labels manifest-only task outputs as manifest downloads", async () => {
    const user = userEvent.setup();
    mockedFetchTasks.mockResolvedValue([
      {
        id: "task-manifest-1",
        title: "未渲染任务",
        status: "succeeded",
        material_ids: ["material-1"],
        options: {},
        output: {
          download_url: "/api/tasks/task-manifest-1/output",
          filename: "manifest.json",
          media_type: "application/json",
          kind: "manifest",
          render_status: "manifest_only",
          failure_reason: "FFmpeg 不可用，仅保留任务清单。",
        },
        created_at: "2026-06-18T09:30:00+08:00",
        updated_at: "2026-06-18T09:31:30+08:00",
      },
    ]);
    renderApp();

    await user.click(await screen.findByRole("link", { name: "任务与输出" }));

    const taskCard = await screen.findByRole("article", { name: "未渲染任务" });
    const downloadLink = within(taskCard).getByRole("link", { name: "下载清单" });
    expect(downloadLink).toHaveAttribute("href", "/api/tasks/task-manifest-1/output");
    expect(downloadLink).toHaveAttribute("download", "未渲染任务.json");
    expect(within(taskCard).queryByRole("link", { name: "下载视频" })).not.toBeInTheDocument();
    expect(within(taskCard).getByText("FFmpeg 不可用，仅保留任务清单。")).toBeInTheDocument();
  });

  it("shows partial render failure reasons without offering video download", async () => {
    const user = userEvent.setup();
    mockedFetchTasks.mockResolvedValue([
      {
        id: "task-partial-1",
        title: "字幕烧录失败",
        status: "succeeded",
        material_ids: ["material-1"],
        options: { subtitle_enabled: true },
        output: {
          download_url: "/api/tasks/task-partial-1/output",
          filename: "output.base.mp4",
          media_type: "video/mp4",
          kind: "partial_video",
          render_status: "subtitle_burn_failed",
          failure_reason: "字幕烧录失败：ASS 字幕滤镜不可用。",
        },
        created_at: "2026-06-18T09:30:00+08:00",
        updated_at: "2026-06-18T09:31:30+08:00",
      },
    ]);
    renderApp();

    await user.click(await screen.findByRole("link", { name: "任务与输出" }));

    const taskCard = await screen.findByRole("article", { name: "字幕烧录失败" });
    expect(within(taskCard).getByText("部分输出")).toBeInTheDocument();
    expect(within(taskCard).getByText("字幕烧录失败：ASS 字幕滤镜不可用。")).toBeInTheDocument();
    expect(within(taskCard).queryByRole("link", { name: "下载视频" })).not.toBeInTheDocument();
    expect(within(taskCard).getByText("输出未完成")).toBeInTheDocument();
  });

  it("deletes a task from the task output list after confirmation", async () => {
    const user = userEvent.setup();
    mockedDeleteTask.mockResolvedValue();
    mockedFetchTasks.mockResolvedValue([
      {
        id: "task-delete-1",
        title: "可删除任务",
        status: "succeeded",
        material_ids: ["material-1"],
        options: { aspect_ratio: "16:9" },
        output: {
          download_url: "/api/tasks/task-delete-1/output",
          filename: "manifest.json",
          media_type: "application/json",
          kind: "manifest",
        },
        created_at: "2026-06-18T09:30:00+08:00",
        updated_at: "2026-06-18T09:31:30+08:00",
      },
    ]);
    renderApp();

    await user.click(await screen.findByRole("link", { name: "任务与输出" }));
    const taskCard = await screen.findByRole("article", { name: "可删除任务" });

    await user.click(within(taskCard).getByRole("button", { name: "删除任务 可删除任务" }));

    expect(
      within(taskCard).getByRole("group", { name: "确认删除 可删除任务" }),
    ).toBeInTheDocument();

    await user.click(within(taskCard).getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(mockedDeleteTask).toHaveBeenCalledWith("task-delete-1");
    });
    expect(screen.queryByRole("article", { name: "可删除任务" })).not.toBeInTheDocument();
    expect(screen.getByText("已删除任务：可删除任务")).toBeInTheDocument();
    expect(screen.getByText("暂无历史任务")).toBeInTheDocument();
  });

  it("keeps the task card operable when task deletion fails", async () => {
    const user = userEvent.setup();
    mockedDeleteTask.mockRejectedValue(new Error("HTTP_500"));
    mockedFetchTasks.mockResolvedValue([
      {
        id: "task-delete-fails-1",
        title: "删除失败任务",
        status: "succeeded",
        material_ids: ["material-1"],
        options: { aspect_ratio: "16:9" },
        output: {
          download_url: "/api/tasks/task-delete-fails-1/output",
          filename: "manifest.json",
          media_type: "application/json",
          kind: "manifest",
        },
        created_at: "2026-06-18T09:30:00+08:00",
        updated_at: "2026-06-18T09:31:30+08:00",
      },
    ]);
    renderApp();

    await user.click(await screen.findByRole("link", { name: "任务与输出" }));
    const taskCard = await screen.findByRole("article", { name: "删除失败任务" });

    await user.click(within(taskCard).getByRole("button", { name: "删除任务 删除失败任务" }));
    await user.click(within(taskCard).getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("任务删除失败，请稍后重试。")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "删除失败任务" })).toBeInTheDocument();
    const confirmation = within(taskCard).getByRole("group", { name: "确认删除 删除失败任务" });
    expect(within(confirmation).getByRole("button", { name: "确认删除" })).toBeEnabled();
    const cancelButton = within(confirmation).getByRole("button", { name: "取消" });
    expect(cancelButton).toBeEnabled();

    await user.click(cancelButton);

    expect(
      within(taskCard).queryByRole("group", { name: "确认删除 删除失败任务" }),
    ).not.toBeInTheDocument();
  });

  it("shows an empty task output state from a direct hash link", async () => {
    window.history.pushState(null, "", "/#tasks");
    renderApp();

    expect(await screen.findByRole("heading", { name: "任务与输出", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("暂无历史任务")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "任务与输出" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("creates a custom subtitle template without exposing default template controls", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));

    expect(screen.queryByRole("button", { name: "设为默认" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("示例文本")).toBeInTheDocument();
    expect(screen.getAllByLabelText("文本")).toHaveLength(3);
    expect(screen.getAllByLabelText("字体")).toHaveLength(3);
    expect(screen.getAllByLabelText("颜色")).toHaveLength(3);
    expect(screen.getAllByLabelText("背景")).toHaveLength(3);
    expect(screen.getAllByLabelText("强调色")).toHaveLength(3);
    expect(screen.getAllByLabelText("括号装饰")).toHaveLength(3);
    expect(screen.getAllByLabelText("描边")).toHaveLength(3);
    expect(screen.getAllByLabelText("阴影")).toHaveLength(3);
    expect(screen.getByRole("group", { name: "底部字幕" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "强调字幕" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "冲击字幕" })).toBeInTheDocument();
    expect(screen.getByLabelText("预览画幅")).toHaveValue("9:16");
    expect(screen.getAllByLabelText("横向位置 %")).toHaveLength(3);
    expect(screen.getAllByLabelText("纵向位置 %")).toHaveLength(3);
    expect(screen.getAllByLabelText("对齐")).toHaveLength(3);
    expect(screen.getAllByLabelText("字号")).toHaveLength(3);
    expect(screen.getAllByLabelText("描边宽度")).toHaveLength(3);
    expect(screen.getAllByLabelText("阴影强度")).toHaveLength(3);
    expect(screen.getAllByLabelText("最大宽度")).toHaveLength(3);
    expect(screen.getAllByLabelText("旋转")).toHaveLength(3);
    expect(screen.getAllByLabelText("X 倾斜")).toHaveLength(3);
    expect(screen.getAllByLabelText("Y 倾斜")).toHaveLength(3);
    expect(screen.queryByLabelText("局部关键词")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("局部高亮色")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存局部高亮" })).not.toBeInTheDocument();
    expect(screen.getAllByText("局部样式")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "新增底部字幕局部样式" })).toBeDisabled();
    expect(screen.getByTestId("subtitle-preview-frame")).toHaveStyle({ aspectRatio: "9 / 16" });

    await user.selectOptions(screen.getByLabelText("预览画幅"), "16:9");
    expect(screen.getByTestId("subtitle-preview-frame")).toHaveStyle({ aspectRatio: "16 / 9" });
    await user.click(screen.getByRole("button", { name: "从预设新建" }));

    expect(mockedCreateSubtitleTemplateSet).toHaveBeenCalledWith({
      name: "我的清晰底部字幕",
      preset_id: "preset-clean-bottom",
    });
    expect(mockedUpdateSubtitlePresetOverride).not.toHaveBeenCalled();
    expect(mockedUpdateSubtitleTemplateSet).not.toHaveBeenCalled();
  });

  it("renders bottom highlight and punch captions with local span preview", async () => {
    const user = userEvent.setup();
    const threeRoleTemplate = templateFixture({
      id: "tmpl-three-role-local",
      name: "三段字幕模板",
      is_modified: true,
      templates: {
        bottom: {
          font_family: "PingFang SC",
          primary_color: "#FFFFFF",
          x_percent: 50,
          y_percent: 78,
        },
        highlight: {
          font_family: "PingFang SC",
          primary_color: "#FFD54F",
          font_size_scale: 1.12,
          x_percent: 50,
          y_percent: 50,
        },
        punch: {
          font_family: "PingFang SC",
          primary_color: "#FFFFFF",
          font_size_scale: 1.2,
          rotate: -5,
          x_percent: 50,
          y_percent: 28,
        },
      },
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", x_percent: 50, y_percent: 78 },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F", x_percent: 50, y_percent: 50 },
          spans: [
            {
              selector: { type: "keyword", value: "字幕" },
              style: {
                primary_color: "#00E5FF",
                font_family: "Noto Sans CJK SC",
                font_scale: 1.18,
                outline_width: 4,
              },
            },
          ],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", x_percent: 50, y_percent: 28 },
          spans: [
            {
              selector: { type: "range", start: 0, end: 2 },
              style: { primary_color: "#FF4D4F", font_scale: 1.22 },
            },
          ],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [threeRoleTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "三段字幕模板" }));
    const previewFrame = screen.getByTestId("subtitle-preview-frame");

    expect(within(previewFrame).getByTestId("subtitle-preview-caption-bottom")).toHaveTextContent(
      defaultSubtitlePreviewText,
    );
    expect(screen.getByLabelText("示例文本")).toHaveValue(defaultSubtitlePreviewText);
    expect(within(previewFrame).getByTestId("subtitle-preview-caption-highlight")).toHaveStyle({
      color: "#FFD54F",
    });
    expect(within(previewFrame).getByTestId("subtitle-preview-caption-punch")).toHaveStyle({
      transform: "translate(-50%, -50%) rotate(-5deg) skewX(0deg) skewY(0deg)",
    });
    expect(within(previewFrame).getByTestId("subtitle-preview-local-span-highlight-0")).toHaveStyle({
      color: "#00E5FF",
      fontFamily: "Noto Sans CJK SC",
    });
    expect(within(previewFrame).getByTestId("subtitle-preview-local-span-punch-0")).toHaveTextContent(
      "这是",
    );
  });

  it("separates role lanes in the combined subtitle preview when template positions overlap", async () => {
    const user = userEvent.setup();
    const overlappingTemplate = templateFixture({
      id: "tmpl-overlap-lanes",
      name: "重叠位置模板",
      is_modified: true,
      templates: {
        bottom: { ...cleanBottomPreset.templates.bottom, y_percent: 78 },
        highlight: { ...cleanBottomPreset.templates.highlight, y_percent: 78 },
        punch: { ...cleanBottomPreset.templates.punch, y_percent: 50 },
      },
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", y_percent: 78 },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F", y_percent: 78 },
          spans: [],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", y_percent: 50 },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [overlappingTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "重叠位置模板" }));

    expect(await screen.findByTestId("subtitle-preview-caption-bottom")).toHaveStyle({
      top: "78%",
    });
    expect(await screen.findByTestId("subtitle-preview-caption-highlight")).toHaveStyle({
      top: "52%",
    });
    expect(await screen.findByTestId("subtitle-preview-caption-punch")).toHaveStyle({
      top: "30%",
    });
  });

  it("does not preview local keyword spans when the keyword is absent", async () => {
    const user = userEvent.setup();
    const missingKeywordTemplate = templateFixture({
      id: "tmpl-missing-keyword-span",
      name: "缺失关键词模板",
      is_modified: true,
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [
            {
              selector: { type: "keyword", value: "不存在" },
              style: { primary_color: "#FF4D4F" },
            },
          ],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F" },
          spans: [],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [missingKeywordTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "缺失关键词模板" }));

    expect(screen.queryByTestId("subtitle-preview-local-span-bottom-0")).not.toBeInTheDocument();
    expect(await screen.findByTestId("subtitle-preview-caption-bottom")).toHaveTextContent(
      defaultSubtitlePreviewText,
    );
  });

  it("keeps role lanes separated when the fallback lane is already occupied", async () => {
    const user = userEvent.setup();
    const fallbackConflictTemplate = templateFixture({
      id: "tmpl-fallback-lane-conflict",
      name: "默认车道冲突模板",
      is_modified: true,
      templates: {
        bottom: { ...cleanBottomPreset.templates.bottom, y_percent: 52 },
        highlight: { ...cleanBottomPreset.templates.highlight, y_percent: 52 },
        punch: { ...cleanBottomPreset.templates.punch, y_percent: 30 },
      },
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", y_percent: 52 },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F", y_percent: 52 },
          spans: [],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", y_percent: 30 },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [fallbackConflictTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "默认车道冲突模板" }));

    expect(await screen.findByTestId("subtitle-preview-caption-bottom")).toHaveStyle({
      top: "52%",
    });
    expect(await screen.findByTestId("subtitle-preview-caption-highlight")).toHaveStyle({
      top: "64%",
    });
    expect(await screen.findByTestId("subtitle-preview-caption-punch")).toHaveStyle({
      top: "30%",
    });
  });

  it("uses wider lane gaps for combined subtitle previews in 16:9", async () => {
    const user = userEvent.setup();
    const landscapeConflictTemplate = templateFixture({
      id: "tmpl-landscape-lane-conflict",
      name: "横屏车道冲突模板",
      is_modified: true,
      templates: {
        bottom: { ...cleanBottomPreset.templates.bottom, y_percent: 52 },
        highlight: { ...cleanBottomPreset.templates.highlight, y_percent: 52 },
        punch: { ...cleanBottomPreset.templates.punch, y_percent: 52 },
      },
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", y_percent: 52 },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F", y_percent: 52 },
          spans: [],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF", y_percent: 52 },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [landscapeConflictTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "横屏车道冲突模板" }));
    await user.selectOptions(screen.getByLabelText("预览画幅"), "16:9");

    const bottomTop = previewTopPercent("subtitle-preview-caption-bottom");
    const highlightTop = previewTopPercent("subtitle-preview-caption-highlight");
    const punchTop = previewTopPercent("subtitle-preview-caption-punch");

    expect(Math.abs(highlightTop - bottomTop)).toBeGreaterThanOrEqual(18);
    expect(Math.abs(punchTop - bottomTop)).toBeGreaterThanOrEqual(18);
    expect(Math.abs(punchTop - highlightTop)).toBeGreaterThanOrEqual(18);
  });

  it("edits local subtitle styles per role", async () => {
    const user = userEvent.setup();
    const localStyleTemplate = templateFixture({
      id: "tmpl-local-style-editor",
      name: "局部样式模板",
      is_modified: true,
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F" },
          spans: [
            {
              selector: { type: "keyword", value: "AI" },
              style: { primary_color: "#00E5FF", font_family: "PingFang SC", font_scale: 1.1 },
            },
          ],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [localStyleTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockImplementation(async ({ id, patch }) => ({
      ...localStyleTemplate,
      ...patch,
      id,
    }));
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "局部样式模板" }));
    const keywordInput = await screen.findByLabelText("强调字幕局部样式 1 关键词");

    await user.clear(keywordInput);
    await user.type(keywordInput, "重复");
    await user.tab();

    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          id: "tmpl-local-style-editor",
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "highlight",
                spans: [
                  expect.objectContaining({
                    selector: { type: "keyword", value: "重复" },
                    style: expect.objectContaining({ primary_color: "#00E5FF" }),
                  }),
                ],
              }),
            ]),
          }),
        }),
      ),
    );

    await user.selectOptions(screen.getByLabelText("强调字幕局部样式 1 动画"), "fade");

    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          id: "tmpl-local-style-editor",
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "highlight",
                spans: [
                  expect.objectContaining({
                    animation: { type: "fade" },
                    selector: { type: "keyword", value: "重复" },
                    style: expect.objectContaining({ primary_color: "#00E5FF" }),
                  }),
                ],
              }),
            ]),
          }),
        }),
      ),
    );

    await user.click(screen.getByRole("button", { name: "新增冲击字幕局部样式" }));

    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "punch",
                spans: [
                  expect.objectContaining({
                    selector: expect.objectContaining({ type: "keyword" }),
                    style: expect.objectContaining({ primary_color: "#FFD54F" }),
                  }),
                ],
              }),
            ]),
          }),
        }),
      ),
    );
  });

  it("keeps local numeric style input drafts editable until blur", async () => {
    const user = userEvent.setup();
    const localStyleTemplate = templateFixture({
      id: "tmpl-local-style-numeric-drafts",
      name: "局部数字输入模板",
      is_modified: true,
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F" },
          spans: [
            {
              selector: { type: "keyword", value: "AI" },
              style: { primary_color: "#00E5FF", font_family: "PingFang SC", font_scale: 1.1 },
            },
          ],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [
            {
              selector: { type: "range", start: 0, end: 2 },
              style: { primary_color: "#FF4D4F", font_scale: 1.05 },
            },
          ],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [localStyleTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockImplementation(async ({ id, patch }) => ({
      ...localStyleTemplate,
      ...patch,
      id,
    }));
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "局部数字输入模板" }));
    const fontScaleInput = await screen.findByLabelText("强调字幕局部样式 1 字号") as HTMLInputElement;
    const rangeStartInput = await screen.findByLabelText(
      "冲击字幕局部样式 1 开始",
    ) as HTMLInputElement;

    await user.clear(fontScaleInput);
    expect(fontScaleInput).toHaveValue("");
    await user.type(fontScaleInput, "1.2");
    expect(fontScaleInput).toHaveValue("1.2");
    await user.tab();

    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          id: "tmpl-local-style-numeric-drafts",
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "highlight",
                spans: [
                  expect.objectContaining({
                    style: expect.objectContaining({ font_scale: 1.2 }),
                  }),
                ],
              }),
            ]),
          }),
        }),
      ),
    );

    await user.clear(rangeStartInput);
    expect(rangeStartInput).toHaveValue("");
    await user.type(rangeStartInput, "1");
    expect(rangeStartInput).toHaveValue("1");
    await user.tab();

    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          id: "tmpl-local-style-numeric-drafts",
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "punch",
                spans: [
                  expect.objectContaining({
                    selector: expect.objectContaining({ start: 1 }),
                  }),
                ],
              }),
            ]),
          }),
        }),
      ),
    );
  });

  it("does not save unchanged local subtitle span fields on blur", async () => {
    const user = userEvent.setup();
    const localStyleTemplate = templateFixture({
      id: "tmpl-local-style-noop-blur",
      name: "局部样式无变更模板",
      is_modified: true,
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: { font_family: "PingFang SC", primary_color: "#FFD54F" },
          spans: [
            {
              selector: { type: "keyword", value: "AI" },
              style: { primary_color: "#00E5FF", font_family: "PingFang SC", font_scale: 1.1 },
              animation: { type: "fade" },
            },
          ],
        },
        {
          id: "punch-main",
          role: "punch",
          style: { font_family: "PingFang SC", primary_color: "#FFFFFF" },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [localStyleTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockImplementation(async ({ id, patch }) => ({
      ...localStyleTemplate,
      ...patch,
      id,
    }));
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "局部样式无变更模板" }));
    const keywordInput = await screen.findByLabelText("强调字幕局部样式 1 关键词");

    keywordInput.focus();
    await user.tab();

    expect(mockedUpdateSubtitleTemplateSet).not.toHaveBeenCalled();
  });

  it("updates target-aligned subtitle block fields in the live preview", async () => {
    const user = userEvent.setup();
    const targetFieldsTemplate = templateFixture({
      id: "tmpl-target-fields",
      name: "目标字段模板",
      is_modified: true,
      templates: {
        bottom: {
          font_family: "Noto Sans CJK SC",
          font_size_scale: 1,
          primary_color: "#FFFFFF",
          outline_color: "#111111",
          outline_width: 4,
          shadow_color: "#000000",
          shadow_depth: 2,
          x_percent: 50,
          y_percent: 78,
          alignment: "center",
          skew_y_deg: 0,
        },
      },
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: {
            font_family: "Noto Sans CJK SC",
            font_size_scale: 1,
            primary_color: "#FFFFFF",
            outline_color: "#111111",
            outline_width: 4,
            shadow_color: "#000000",
            shadow_depth: 2,
            x_percent: 50,
            y_percent: 78,
            alignment: "center",
            skew_y_deg: 0,
          },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [targetFieldsTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "目标字段模板" }));
    const caption = await screen.findByTestId("subtitle-preview-caption-bottom");
    const textInput = screen.getAllByLabelText("文本")[0] as HTMLInputElement;
    const xInput = screen.getAllByLabelText("横向位置 %")[0] as HTMLInputElement;
    const yInput = screen.getAllByLabelText("纵向位置 %")[0] as HTMLInputElement;
    const alignSelect = screen.getAllByLabelText("对齐")[0] as HTMLSelectElement;
    const colorInput = screen.getAllByLabelText("颜色")[0] as HTMLInputElement;
    const outlineColorInput = screen.getAllByLabelText("描边")[0] as HTMLInputElement;
    const shadowColorInput = screen.getAllByLabelText("阴影")[0] as HTMLInputElement;
    const ySkewInput = screen.getAllByLabelText("Y 倾斜")[0] as HTMLInputElement;

    await user.clear(textInput);
    await user.type(textInput, "底部字幕预览");
    expect(caption).toHaveTextContent("底部字幕预览");

    await user.clear(xInput);
    await user.type(xInput, "40");
    expect(caption.style.left).toBe("40%");
    await user.tab();

    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          id: "tmpl-target-fields",
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "bottom",
                position: expect.objectContaining({ x: 0.4, y: 0.78, anchor: "center" }),
                style: expect.objectContaining({ x_percent: 40 }),
              }),
            ]),
          }),
        }),
      ),
    );

    await user.clear(yInput);
    await user.type(yInput, "62");
    expect(caption.style.top).toBe("62%");
    await user.tab();

    await user.selectOptions(alignSelect, "left");
    expect(caption.style.textAlign).toBe("left");
    expect(caption.style.transform).toContain("translate(0, -50%)");
    await waitFor(() =>
      expect(mockedUpdateSubtitleTemplateSet).toHaveBeenLastCalledWith(
        expect.objectContaining({
          id: "tmpl-target-fields",
          patch: expect.objectContaining({
            blocks: expect.arrayContaining([
              expect.objectContaining({
                role: "bottom",
                position: expect.objectContaining({ x: 0.4, y: 0.62, anchor: "left" }),
                style: expect.objectContaining({ alignment: "left", y_percent: 62 }),
              }),
            ]),
          }),
        }),
      ),
    );

    await user.clear(colorInput);
    await user.type(colorInput, "#FFF176");
    expect(caption.style.webkitTextFillColor).toBe("rgb(255, 241, 118)");

    await user.clear(outlineColorInput);
    await user.type(outlineColorInput, "#FF5252");
    expect(caption.style.webkitTextStroke).toContain("#FF5252");

    await user.clear(shadowColorInput);
    await user.type(shadowColorInput, "#123456");
    expect(caption.style.textShadow).toContain("#123456");

    await user.clear(ySkewInput);
    await user.type(ySkewInput, "8");
    expect(caption.style.transform).toContain("skewY(8deg)");
  });

  it("updates the live subtitle preview style without adding caption boards", async () => {
    const user = userEvent.setup();
    const greenTemplate = templateFixture({
      id: "preset-green-preview",
      name: "Green Box 绿框口播",
      templates: {
        bottom: {
          font_family: "Noto Sans CJK SC",
          font_size: 54,
          font_size_scale: 1.25,
          max_width: 0.7,
          outline_color: "#0B3D1A",
          outline_width: 5,
          primary_color: "#101820",
          rotate: -4,
          shadow_depth: 2,
          skew: 6,
        },
      },
      blocks: [
        {
          id: "green-bottom",
          role: "bottom",
          style: {
            font_family: "Noto Sans CJK SC",
            font_size: 54,
            font_size_scale: 1.25,
            max_width: 0.7,
            outline_color: "#0B3D1A",
            outline_width: 5,
            primary_color: "#101820",
            rotate: -4,
            shadow_depth: 2,
            skew: 6,
          },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [],
      presets: [cleanBottomPreset, greenTemplate],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    const previewCaption = await screen.findByTestId("subtitle-preview-caption-bottom");

    expect(previewCaption).toHaveStyle({
      color: "#FFFFFF",
      fontSize: "16px",
      maxWidth: "86%",
      transform: "translate(-50%, -50%) rotate(0deg) skewX(0deg) skewY(0deg)",
    });
    expect(previewCaption.style.backgroundColor).toBe("");

    await user.click(screen.getByRole("button", { name: "Green Box 绿框口播" }));

    expect(previewCaption).toHaveStyle({
      color: "#101820",
      fontSize: "20px",
      maxWidth: "70%",
      transform: "translate(-50%, -50%) rotate(-4deg) skewX(6deg) skewY(0deg)",
    });
    expect(previewCaption.style.backgroundColor).toBe("");
  });

  it("keeps target fill colors visible for high-outline subtitle presets", async () => {
    const user = userEvent.setup();
    const boldYellowTemplate = templateFixture({
      id: "preset-bold-yellow-preview",
      name: "醒目黄黑大字",
      templates: {
        bottom: {
          font_family: "Noto Sans CJK SC",
          font_weight: 800,
          primary_color: "#FFFFFF",
          accent_color: "#FFB300",
          outline_color: "#111111",
          outline_width: 4,
          shadow_color: "#000000",
          shadow_depth: 2,
        },
        highlight: {
          font_family: "Noto Sans CJK SC",
          font_weight: 800,
          primary_color: "#FFFFFF",
          accent_color: "#FFB300",
          outline_color: "#111111",
          outline_width: 4,
          shadow_color: "#000000",
          shadow_depth: 2,
        },
        punch: {
          font_family: "Noto Sans CJK SC",
          font_weight: 900,
          primary_color: "#FFF176",
          accent_color: "#FF5252",
          outline_color: "#111111",
          outline_width: 5,
          shadow_color: "#000000",
          shadow_depth: 3,
          y_percent: 50,
        },
      },
      blocks: [
        {
          id: "bottom-main",
          role: "bottom",
          style: {
            font_family: "Noto Sans CJK SC",
            font_weight: 800,
            primary_color: "#FFFFFF",
            accent_color: "#FFB300",
            outline_color: "#111111",
            outline_width: 4,
            shadow_color: "#000000",
            shadow_depth: 2,
          },
          spans: [
            {
              selector: { type: "keyword", value: "字幕" },
              style: { primary_color: "#FFB300", outline_color: "#111111", font_scale: 1.06 },
            },
          ],
        },
        {
          id: "highlight-main",
          role: "highlight",
          style: {
            font_family: "Noto Sans CJK SC",
            font_weight: 800,
            primary_color: "#FFFFFF",
            accent_color: "#FFB300",
            outline_color: "#111111",
            outline_width: 4,
            shadow_color: "#000000",
            shadow_depth: 2,
          },
          spans: [
            {
              selector: { type: "keyword", value: "预览" },
              style: {
                primary_color: "#FFB300",
                outline_color: "#111111",
                font_scale: 1.16,
                outline_width: 5,
              },
            },
          ],
        },
        {
          id: "punch-main",
          role: "punch",
          style: {
            font_family: "Noto Sans CJK SC",
            font_weight: 900,
            primary_color: "#FFF176",
            accent_color: "#FF5252",
            outline_color: "#111111",
            outline_width: 5,
            shadow_color: "#000000",
            shadow_depth: 3,
            y_percent: 50,
          },
          spans: [
            {
              selector: { type: "range", start: 0, end: 2 },
              style: { primary_color: "#FF5252", accent_color: "#FFF176", font_scale: 1.28 },
            },
          ],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [],
      presets: [boldYellowTemplate],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));

    const bottom = await screen.findByTestId("subtitle-preview-caption-bottom");
    expect(screen.getByTestId("subtitle-preview-screen")).toBeInTheDocument();
    expect(bottom.style.color).toBe("rgb(255, 255, 255)");
    expect(bottom.style.fontWeight).toBe("800");
    expect(bottom.style.paintOrder).toBe("stroke fill");
    expect(bottom.style.webkitTextFillColor).toBe("rgb(255, 255, 255)");
    expect(bottom.style.webkitTextStroke).toBe("1px #111111");
    expect(bottom.style.backgroundColor).toBe("");
    expect(bottom.style.webkitTextStroke).not.toBe("2px #111111");
    const bottomSpan = await screen.findByTestId("subtitle-preview-local-span-bottom-0");
    expect(bottomSpan.style.color).toBe("rgb(255, 179, 0)");
    expect(bottomSpan.style.webkitTextFillColor).toBe("rgb(255, 179, 0)");
    expect(bottomSpan.style.webkitTextStroke).toBe("1px #111111");
    const punchSpan = await screen.findByTestId("subtitle-preview-local-span-punch-0");
    expect(punchSpan.style.color).toBe("rgb(255, 82, 82)");
    expect(punchSpan.style.webkitTextFillColor).toBe("rgb(255, 82, 82)");
  });

  it("does not add caption boards for custom subtitle colors", async () => {
    const user = userEvent.setup();
    const colorTemplate = templateFixture({
      id: "tmpl-color-preview",
      name: "彩色字幕模板",
      is_modified: true,
      templates: {
        bottom: {
          ...cleanBottomPreset.templates.bottom,
          primary_color: "#777777",
        },
        highlight: {
          ...cleanBottomPreset.templates.highlight,
          primary_color: "#38BDF8",
        },
        punch: {
          ...cleanBottomPreset.templates.punch,
          primary_color: "#FFD54F",
        },
      },
      blocks: [
        {
          id: "gray-bottom",
          role: "bottom",
          style: {
            font_family: "PingFang SC",
            primary_color: "#777777",
          },
          spans: [],
        },
        {
          id: "blue-highlight",
          role: "highlight",
          style: {
            font_family: "PingFang SC",
            primary_color: "#38BDF8",
          },
          spans: [],
        },
        {
          id: "yellow-punch",
          role: "punch",
          style: {
            font_family: "PingFang SC",
            primary_color: "#FFD54F",
          },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [colorTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "彩色字幕模板" }));

    const captions = [
      await screen.findByTestId("subtitle-preview-caption-bottom"),
      await screen.findByTestId("subtitle-preview-caption-highlight"),
      await screen.findByTestId("subtitle-preview-caption-punch"),
    ];
    expect(captions[0]).toHaveStyle({ color: "#777777" });
    expect(captions[1]).toHaveStyle({ color: "#38BDF8" });
    expect(captions[2]).toHaveStyle({ color: "#FFD54F" });
    captions.forEach((caption) => {
      expect(caption.style.backgroundColor).toBe("");
    });
  });

  it("does not define a visible caption board in preview CSS", () => {
    expect(stylesCss).toMatch(
      /\.subtitle-preview-caption \{[\s\S]*?background:\s*transparent;[\s\S]*?padding:\s*0;/,
    );
    expect(stylesCss).not.toMatch(/\.subtitle-preview-caption \{[\s\S]*?background:\s*rgba/);
  });

  it("uses edited shadow before legacy shadow depth in the live subtitle preview", async () => {
    const user = userEvent.setup();
    const shadowTemplate = templateFixture({
      id: "tmpl-shadow-preview",
      name: "阴影预览模板",
      is_modified: true,
      templates: {
        bottom: {
          ...cleanBottomPreset.templates.bottom,
          shadow: 1,
          shadow_depth: 1,
        },
      },
      blocks: [
        {
          id: "shadow-bottom",
          role: "bottom",
          style: {
            font_family: "PingFang SC",
            primary_color: "#FFFFFF",
            shadow: 1,
            shadow_depth: 1,
          },
          spans: [],
        },
      ],
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [shadowTemplate],
      presets: [cleanBottomPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "阴影预览模板" }));
    const previewCaption = await screen.findByTestId("subtitle-preview-caption-bottom");
    const shadowInput = screen.getAllByLabelText("阴影强度")[0] as HTMLInputElement;

    expect(previewCaption.style.textShadow).toBe(
      "0.55px 0.55px 1.1px #000000, 0 0 0.5px #111111",
    );

    await user.clear(shadowInput);
    await user.type(shadowInput, "6");

    expect(previewCaption.style.textShadow).toBe(
      "3.3px 3.3px 6.6px #000000, 0 0 0.5px #111111",
    );
  });

  it("creates a new custom subtitle template from a selected custom template source", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedCreateSubtitleTemplateSet.mockResolvedValue({
      ...customCaptionTemplate,
      id: "tmpl-brand-copy",
      name: "我的品牌底部字幕",
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "品牌底部字幕" }));
    await user.click(screen.getByRole("button", { name: "从预设新建" }));

    expect(mockedCreateSubtitleTemplateSet).toHaveBeenCalledWith({
      name: "我的品牌底部字幕",
      source_id: "tmpl-brand-bottom",
    });
    expect(mockedCreateSubtitleTemplateSet).not.toHaveBeenCalledWith(
      expect.objectContaining({ preset_id: "tmpl-brand-bottom" }),
    );
  });

  it("treats API presets without preset id prefixes as locked presets", async () => {
    const user = userEvent.setup();
    const apiPreset = templateFixture({
      id: "builtin-clean-bottom",
      name: "内置底部字幕",
      favorite: false,
      is_favorite: false,
      is_modified: false,
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [],
      presets: [apiPreset],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    const subtitleWorkbench = screen.getByRole("article", { name: "字幕模板" });
    expect(within(subtitleWorkbench).getByText("当前模板：内置底部字幕")).toBeInTheDocument();
    expect(within(subtitleWorkbench).getAllByLabelText("颜色")[0]).toBeDisabled();
    expect(within(subtitleWorkbench).getByRole("button", { name: "还原预设" })).not.toBeDisabled();

    expect(within(subtitleWorkbench).queryByRole("button", { name: "设为默认" })).not.toBeInTheDocument();
    expect(within(subtitleWorkbench).queryByText("默认")).not.toBeInTheDocument();
    expect(mockedUpdateSubtitlePresetOverride).not.toHaveBeenCalled();
    expect(mockedUpdateSubtitleTemplateSet).not.toHaveBeenCalled();

    await user.click(within(subtitleWorkbench).getByRole("button", { name: "从预设新建" }));
    expect(mockedCreateSubtitleTemplateSet).toHaveBeenCalledWith({
      name: "我的内置底部字幕",
      preset_id: "builtin-clean-bottom",
    });
    expect(mockedCreateSubtitleTemplateSet).not.toHaveBeenCalledWith(
      expect.objectContaining({ source_id: "builtin-clean-bottom" }),
    );
  });

  it("clears template action errors after switching templates or editing preview text", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedCreateSubtitleTemplateSet.mockRejectedValue(new Error("CREATE_FAILED"));
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(screen.getByRole("button", { name: "从预设新建" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("字幕模板新建失败");

    await user.click(screen.getByRole("button", { name: "品牌底部字幕" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "从预设新建" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("字幕模板新建失败");

    await user.clear(screen.getByLabelText("示例文本"));
    await user.type(screen.getByLabelText("示例文本"), "新的预览文案");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("selects a custom subtitle template before legacy favorite preset metadata", async () => {
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [
        {
          ...cleanBottomPreset,
          favorite: true,
          is_favorite: true,
        },
      ],
    });
    window.history.pushState(null, "", "/#subtitles");

    renderApp();

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("当前模板：品牌底部字幕")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "品牌底部字幕" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "清晰底部字幕" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("keeps API preset order even when legacy favorite preset metadata is available", async () => {
    const user = userEvent.setup();
    const firstPreset = templateFixture({
      id: "preset-api-first",
      name: "API 首个预设",
      favorite: false,
      is_favorite: false,
      created_at: "2026-06-01T00:00:00+00:00",
      updated_at: "2026-06-01T00:00:00+00:00",
    });
    const newerPreset = templateFixture({
      id: "preset-newer-second",
      name: "较新的第二预设",
      favorite: true,
      is_favorite: true,
      created_at: "2026-06-02T00:00:00+00:00",
      updated_at: "2026-06-12T00:00:00+00:00",
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [],
      presets: [firstPreset, newerPreset],
    });
    renderApp();

    expect(
      await screen.findByText("自动随机使用模板", { selector: ".subtitle-template-summary" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "去字幕模板页编辑" }));

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    const subtitleWorkbench = screen.getByRole("article", { name: "字幕模板" });
    expect(within(subtitleWorkbench).getByText("当前模板：API 首个预设")).toBeInTheDocument();
    expect(within(subtitleWorkbench).getByRole("button", { name: "API 首个预设" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("selects the newest custom subtitle template and ignores legacy favorite metadata", async () => {
    const olderFavorite = templateFixture({
      id: "tmpl-brand-old",
      name: "旧版品牌字幕",
      favorite: true,
      is_favorite: true,
      is_modified: true,
      created_at: "2026-06-01T00:00:00+00:00",
      updated_at: "2026-06-10T00:00:00+00:00",
    });
    const newerTemplate = templateFixture({
      id: "tmpl-brand-new",
      name: "新版品牌字幕",
      favorite: false,
      is_favorite: false,
      is_modified: true,
      created_at: "2026-06-02T00:00:00+00:00",
      updated_at: "2026-06-12T00:00:00+00:00",
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [olderFavorite, newerTemplate],
      presets: [
        templateFixture({
          id: "preset-clean-new",
          name: "新版预设字幕",
          favorite: true,
          is_favorite: true,
          updated_at: "2026-06-14T00:00:00+00:00",
        }),
      ],
    });
    renderApp();

    expect(
      await screen.findByText("自动随机使用模板", { selector: ".subtitle-template-summary" }),
    ).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "去字幕模板页编辑" }));

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    const subtitleWorkbench = screen.getByRole("article", { name: "字幕模板" });
    expect(within(subtitleWorkbench).getByText("当前模板：新版品牌字幕")).toBeInTheDocument();
    expect(within(subtitleWorkbench).getByRole("button", { name: "新版品牌字幕" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps custom style edits visible while a style save is pending", async () => {
    const user = userEvent.setup();
    let resolveUpdate: ((template: SubtitleTemplateSet) => void) | undefined;
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpdate = resolve;
        }),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "品牌底部字幕" }));
    const primaryColor = screen.getAllByLabelText("颜色")[0] as HTMLInputElement;

    await user.clear(primaryColor);
    await user.type(primaryColor, "#123456");
    await user.tab();

    expect(mockedUpdateSubtitleTemplateSet).toHaveBeenCalled();
    expect(primaryColor).toHaveValue("#123456");
    expect(primaryColor).not.toBeDisabled();

    resolveUpdate?.({
      ...customCaptionTemplate,
      templates: {
        ...customCaptionTemplate.templates,
        bottom: {
          ...customCaptionTemplate.templates.bottom,
          primary_color: "#123456",
        },
      },
    });
  });

  it("ignores stale style save responses after a newer draft is saved", async () => {
    const user = userEvent.setup();
    const requests: Array<{
      resolve: (template: SubtitleTemplateSet) => void;
    }> = [];
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockImplementation(
      () =>
        new Promise((resolve) => {
          requests.push({ resolve });
        }),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "品牌底部字幕" }));
    const primaryColor = screen.getAllByLabelText("颜色")[0] as HTMLInputElement;
    const fontScale = screen.getAllByLabelText("字号")[0] as HTMLInputElement;

    await user.clear(primaryColor);
    await user.type(primaryColor, "#111111");
    await user.tab();
    await user.clear(fontScale);
    await user.type(fontScale, "1.6");
    await user.tab();

    await waitFor(() => expect(requests).toHaveLength(2));

    await act(async () => {
      requests[1].resolve(
        templateFixture({
          ...customCaptionTemplate,
          templates: {
            ...customCaptionTemplate.templates,
            bottom: {
              ...customCaptionTemplate.templates.bottom,
              primary_color: "#111111",
              font_size_scale: 1.6,
            },
          },
        }),
      );
    });
    expect(fontScale).toHaveValue("1.6");

    await act(async () => {
      requests[0].resolve(
        templateFixture({
          ...customCaptionTemplate,
          templates: {
            ...customCaptionTemplate.templates,
            bottom: {
              ...customCaptionTemplate.templates.bottom,
              primary_color: "#111111",
              font_size_scale: 1,
            },
          },
        }),
      );
    });

    expect(primaryColor).toHaveValue("#111111");
    expect(fontScale).toHaveValue("1.6");
  });

  it("shows subtitle validation warnings near the editor", async () => {
    const user = userEvent.setup();
    mockedValidateSubtitleTemplateSet.mockResolvedValueOnce({
      ok: false,
      normalized: null,
      warnings: ["主色格式无效"],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(screen.getByRole("button", { name: "检查模板" }));

    expect(mockedValidateSubtitleTemplateSet).toHaveBeenCalledWith(
      expect.objectContaining({ id: "preset-clean-bottom" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "模板检查发现问题：主色格式无效",
    );
  });

  it("shows subtitle validation success after a clean check", async () => {
    const user = userEvent.setup();
    mockedValidateSubtitleTemplateSet.mockResolvedValueOnce({
      ok: true,
      normalized: cleanBottomPreset,
      warnings: [],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(screen.getByRole("button", { name: "检查模板" }));

    const validationStatus = await screen.findByText(
      "模板格式正常，可用于预览和渲染。",
      { selector: ".subtitle-validation-feedback" },
    );
    expect(validationStatus).toHaveAttribute("role", "status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears subtitle validation warnings after switching templates", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedValidateSubtitleTemplateSet.mockResolvedValueOnce({
      ok: false,
      normalized: null,
      warnings: ["主色格式无效"],
    });
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(screen.getByRole("button", { name: "检查模板" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "模板检查发现问题：主色格式无效",
    );

    await user.click(screen.getByRole("button", { name: "品牌底部字幕" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears stale preview errors when custom subtitle style changes", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedPreviewSubtitleTemplateSet.mockRejectedValueOnce(
      new Error("SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "精准预览" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("预览渲染不可用");

    const primaryColor = screen.getAllByLabelText("颜色")[0] as HTMLInputElement;
    await user.clear(primaryColor);
    await user.type(primaryColor, "#223344");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows safe error feedback when saving subtitle style fails", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockRejectedValueOnce(new Error("SECRET_TOKEN_LEAK"));
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    const primaryColor = screen.getAllByLabelText("颜色")[0] as HTMLInputElement;

    await user.clear(primaryColor);
    await user.type(primaryColor, "#334455");
    await user.tab();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("字幕模板保存失败");
    expect(alert).not.toHaveTextContent("SECRET_TOKEN_LEAK");
  });

  it("clears subtitle save errors when preview inputs change", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [cleanBottomPreset],
    });
    mockedUpdateSubtitleTemplateSet.mockRejectedValueOnce(new Error("SAVE_FAILED"));
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(await screen.findByRole("button", { name: "品牌底部字幕" }));
    const primaryColor = screen.getAllByLabelText("颜色")[0] as HTMLInputElement;

    await user.clear(primaryColor);
    await user.type(primaryColor, "#334455");
    await user.tab();
    expect(await screen.findByRole("alert")).toHaveTextContent("字幕模板保存失败");

    await user.clear(screen.getByLabelText("示例文本"));
    await user.type(screen.getByLabelText("示例文本"), "新的预览文案");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders precise image and timeline previews from the selected template", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.clear(screen.getByLabelText("示例文本"));
    await user.type(screen.getByLabelText("示例文本"), "AI 自动完成重复工作");
    await user.click(screen.getByRole("button", { name: "精准预览" }));
    await user.click(screen.getByRole("button", { name: "时间线预览" }));

    expect(mockedPreviewSubtitleTemplateSet).toHaveBeenCalledWith(
      expect.objectContaining({
        template_type: "bottom",
        template_types: ["bottom", "highlight", "punch"],
        aspect_ratio: "9:16",
        sample_text: "AI 自动完成重复工作",
      }),
    );
    expect(mockedPreviewSubtitleTimeline).toHaveBeenCalledWith(
      expect.objectContaining({
        template_type: "bottom",
        template_types: ["bottom", "highlight", "punch"],
        duration_ms: 1200,
      }),
    );
    expect(await screen.findByRole("img", { name: "字幕精准预览" })).toHaveAttribute(
      "src",
      expect.stringContaining("data:image/png;base64,"),
    );
    expect(screen.getByTestId("subtitle-timeline-preview")).toHaveAttribute(
      "src",
      expect.stringContaining("data:video/mp4;base64,"),
    );
  });

  it("keeps subtitle workbench keyboard, loading, error, and mobile semantics accessible", async () => {
    const user = userEvent.setup();
    let resolvePreview: (value: Awaited<ReturnType<typeof previewSubtitleTemplateSet>>) => void;
    mockedPreviewSubtitleTemplateSet.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePreview = resolve;
      }),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    const precisePreview = screen.getByRole("button", { name: "精准预览" });
    await user.click(precisePreview);
    expect(precisePreview).toBeDisabled();
    resolvePreview!({
      mime_type: "image/png",
      data: btoa("preview"),
      resolution: { width: 1080, height: 1920 },
      warnings: [],
    });
    expect(await screen.findByRole("img", { name: "字幕精准预览" })).toBeInTheDocument();

    mockedPreviewSubtitleTemplateSet.mockRejectedValueOnce(
      new Error("SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"),
    );
    await user.click(screen.getByRole("button", { name: "精准预览" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("预览渲染不可用");
    expect(screen.getByRole("region", { name: "字幕模板列表" })).toHaveAttribute(
      "data-mobile-layout",
      "horizontal-scroll-on-mobile",
    );
    expect(screen.getByRole("button", { name: "清晰底部字幕" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "清晰底部字幕" })).not.toHaveAttribute(
      "aria-selected",
    );
    screen.getByRole("button", { name: "精准预览" }).focus();
    await user.tab();
    expect(document.activeElement).toHaveAccessibleName("时间线预览");
  });

  it("shows renderer unavailable feedback when timeline preview fails", async () => {
    const user = userEvent.setup();
    mockedPreviewSubtitleTimeline.mockRejectedValueOnce(
      new Error("SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(screen.getByRole("button", { name: "时间线预览" }));

    expect(mockedPreviewSubtitleTimeline).toHaveBeenCalledWith(
      expect.objectContaining({
        template_type: "bottom",
        template_types: ["bottom", "highlight", "punch"],
        duration_ms: 1200,
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("预览渲染不可用");
  });

  it("clears stale preview errors when preview inputs change", async () => {
    const user = userEvent.setup();
    mockedPreviewSubtitleTemplateSet.mockRejectedValueOnce(
      new Error("SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"),
    );
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));
    await user.click(screen.getByRole("button", { name: "精准预览" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("预览渲染不可用");

    await user.clear(screen.getByLabelText("示例文本"));
    await user.type(screen.getByLabelText("示例文本"), "换一条示例字幕");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("submits subtitle options when creating online mix task", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "AI 办公",
      topic: "AI 办公",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "office",
          keywords: ["office"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "AI 办公",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "AI 办公");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await user.selectOptions(await screen.findByLabelText("字幕模板"), "preset-clean-bottom");
    await user.selectOptions(screen.getByLabelText("字幕字体"), "Noto Sans CJK SC");
    expect(screen.getByText("基础模板：清晰底部字幕，渲染时随机使用变体")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "去字幕模板页编辑" }));
    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "混剪工作台" }));
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          subtitle_enabled: true,
          subtitle_template_set_id: "preset-clean-bottom",
          subtitle_font_family: "Noto Sans CJK SC",
        }),
      }),
    );
  });

  it("previews the sorted automatic BGM for category-only selection", async () => {
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByLabelText("启用 BGM")).toBeChecked();
    expect(within(bgmSelector).getByLabelText("BGM 分类")).toHaveValue("cat_calm");
    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("");
    expect(within(bgmSelector).getByText("BGM 音量 12%")).toBeInTheDocument();
    expect(
      within(bgmSelector).getByRole("option", { name: "从当前分类自动选择" }),
    ).toBeInTheDocument();
    expect(within(bgmSelector).getByRole("option", { name: "静谧长夜" })).toBeInTheDocument();
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_calm/file",
    );
  });

  it("previews category-only BGM using the backend auto selection key", async () => {
    const base = bgmLibraryFixture();
    mockedFetchBgmLibrary.mockResolvedValue({
      ...base,
      categories: [
        {
          id: "cat_sort",
          name: "排序校验",
          sort_order: 1,
          track_count: 2,
          created_at: "2026-06-21T00:00:00Z",
          updated_at: "2026-06-21T00:00:00Z",
        },
      ],
      items: [
        {
          ...base.items[0],
          id: "bgm_alpha_z",
          filename: "zeta.mp3",
          original_filename: "zeta.mp3",
          display_name: "Alpha",
          category_id: "cat_sort",
          category_name: "排序校验",
          audio_url: "/api/bgm/tracks/bgm_alpha_z/file",
        },
        {
          ...base.items[1],
          id: "bgm_alpha_a",
          filename: "alpha.mp3",
          original_filename: "alpha.mp3",
          display_name: "alpha",
          category_id: "cat_sort",
          category_name: "排序校验",
          audio_url: "/api/bgm/tracks/bgm_alpha_a/file",
        },
      ],
      total_tracks: 2,
    });
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByLabelText("BGM 分类")).toHaveValue("cat_sort");
    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("");
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_alpha_a/file",
    );
  });

  it("previews category-only BGM using Python casefold-compatible ordering", async () => {
    const base = bgmLibraryFixture();
    mockedFetchBgmLibrary.mockResolvedValue({
      ...base,
      categories: [
        {
          id: "cat_casefold",
          name: "Casefold 校验",
          sort_order: 1,
          track_count: 2,
          created_at: "2026-06-21T00:00:00Z",
          updated_at: "2026-06-21T00:00:00Z",
        },
      ],
      items: [
        {
          ...base.items[0],
          id: "bgm_fzz",
          filename: "fzz.mp3",
          original_filename: "fzz.mp3",
          display_name: "fzz",
          category_id: "cat_casefold",
          category_name: "Casefold 校验",
          audio_url: "/api/bgm/tracks/bgm_fzz/file",
        },
        {
          ...base.items[1],
          id: "bgm_ligature_ff",
          filename: "ligature.mp3",
          original_filename: "ligature.mp3",
          display_name: "\uFB00oo",
          category_id: "cat_casefold",
          category_name: "Casefold 校验",
          audio_url: "/api/bgm/tracks/bgm_ligature_ff/file",
        },
      ],
      total_tracks: 2,
    });
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByLabelText("BGM 分类")).toHaveValue("cat_casefold");
    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("");
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_ligature_ff/file",
    );
  });

  it("previews category-only BGM using Python 3.12 casefold over JS lower changes", async () => {
    const base = bgmLibraryFixture();
    mockedFetchBgmLibrary.mockResolvedValue({
      ...base,
      categories: [
        {
          id: "cat_unicode_version",
          name: "Unicode 版本校验",
          sort_order: 1,
          track_count: 2,
          created_at: "2026-06-21T00:00:00Z",
          updated_at: "2026-06-21T00:00:00Z",
        },
      ],
      items: [
        {
          ...base.items[0],
          id: "bgm_a7cb",
          filename: "a7cb.mp3",
          original_filename: "a7cb.mp3",
          display_name: "\uA7CBaa",
          category_id: "cat_unicode_version",
          category_name: "Unicode 版本校验",
          audio_url: "/api/bgm/tracks/bgm_a7cb/file",
        },
        {
          ...base.items[1],
          id: "bgm_0264",
          filename: "0264.mp3",
          original_filename: "0264.mp3",
          display_name: "\u0264zz",
          category_id: "cat_unicode_version",
          category_name: "Unicode 版本校验",
          audio_url: "/api/bgm/tracks/bgm_0264/file",
        },
      ],
      total_tracks: 2,
    });
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByLabelText("BGM 分类")).toHaveValue(
      "cat_unicode_version",
    );
    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("");
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_0264/file",
    );
  });

  it("keeps category-only automatic BGM selection scoped to the current category", async () => {
    const user = userEvent.setup();
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    await user.selectOptions(await within(bgmSelector).findByLabelText("BGM 分类"), "cat_upbeat");

    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("");
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_upbeat/file",
    );
  });

  it("sends category-only BGM when creating an online remix task", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "AI 办公",
      topic: "AI 办公",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "office",
          keywords: ["office"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "AI 办公",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "AI 办公");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByLabelText("脚本标题");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_enabled: true,
          bgm_category_id: "cat_calm",
          bgm_track_id: null,
          bgm_volume: 0.12,
        }),
      }),
    );
  });

  it("sends an explicit unclassified BGM track when no categories exist", async () => {
    const user = userEvent.setup();
    mockedFetchBgmLibrary.mockResolvedValue(unclassifiedBgmLibraryFixture());
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "无分类 BGM 短视频",
      topic: "无分类 BGM",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "studio",
          keywords: ["studio"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "无分类 BGM 短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByLabelText("BGM 分类")).toHaveDisplayValue("未分类");
    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("bgm_unclassified");
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_unclassified/file",
    );

    await user.type(await screen.findByLabelText("视频主题"), "无分类 BGM");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByLabelText("脚本标题");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_enabled: true,
          bgm_category_id: null,
          bgm_track_id: "bgm_unclassified",
          bgm_volume: 0.12,
        }),
      }),
    );
  });

  it("sends disabled BGM options when the BGM library is empty", async () => {
    const user = userEvent.setup();
    mockedFetchBgmLibrary.mockResolvedValue({
      ...bgmLibraryFixture(),
      categories: [],
      items: [],
      total_tracks: 0,
    });
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "空 BGM 库短视频",
      topic: "空 BGM 库",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "studio",
          keywords: ["studio"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "空 BGM 库短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByText("暂无可试听 BGM")).toBeInTheDocument();
    expect(within(bgmSelector).getByRole("button", { name: "去 BGM 管理页" })).toBeInTheDocument();
    await waitFor(() => {
      expect(within(bgmSelector).getByLabelText("启用 BGM")).not.toBeChecked();
    });

    await user.type(await screen.findByLabelText("视频主题"), "空 BGM 库");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByLabelText("脚本标题");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_enabled: false,
          bgm_category_id: null,
          bgm_track_id: null,
          bgm_volume: null,
        }),
      }),
    );
  });

  it("clears a stale explicit BGM track before creating an online remix task", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "旧曲目清理短视频",
      topic: "旧曲目清理",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "studio",
          keywords: ["studio"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "旧曲目清理短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    const { queryClient } = renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    await user.selectOptions(await within(bgmSelector).findByLabelText("具体 BGM"), "bgm_calm_late");

    act(() => {
      queryClient.setQueryData<BgmLibrary>(["bgm-library"], {
        ...bgmLibraryFixture(),
        items: bgmLibraryFixture().items.filter((track) => track.id !== "bgm_calm_late"),
        total_tracks: 2,
      });
    });

    await waitFor(() => {
      expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("");
    });
    expect(within(bgmSelector).getByLabelText("BGM 试听音频")).toHaveAttribute(
      "src",
      "/api/bgm/tracks/bgm_calm/file",
    );

    await user.type(await screen.findByLabelText("视频主题"), "旧曲目清理");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByLabelText("脚本标题");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_enabled: true,
          bgm_category_id: "cat_calm",
          bgm_track_id: null,
        }),
      }),
    );
    expect(mockedCreateOnlineMixTask).not.toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_track_id: "bgm_calm_late",
        }),
      }),
    );
  });

  it("clears a stale BGM category when the library returns no categories", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "分类删除短视频",
      topic: "分类删除",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "studio",
          keywords: ["studio"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "分类删除短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    const { queryClient } = renderApp();

    const bgmSelector = await screen.findByRole("group", { name: "BGM 设置" });
    expect(await within(bgmSelector).findByLabelText("BGM 分类")).toHaveValue("cat_calm");

    act(() => {
      queryClient.setQueryData<BgmLibrary>(["bgm-library"], unclassifiedBgmLibraryFixture());
    });

    await waitFor(() => {
      expect(within(bgmSelector).getByLabelText("BGM 分类")).toHaveDisplayValue("未分类");
    });
    expect(within(bgmSelector).getByLabelText("具体 BGM")).toHaveValue("bgm_unclassified");

    await user.type(await screen.findByLabelText("视频主题"), "分类删除");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByLabelText("脚本标题");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_enabled: true,
          bgm_category_id: null,
          bgm_track_id: "bgm_unclassified",
        }),
      }),
    );
    expect(mockedCreateOnlineMixTask).not.toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          bgm_category_id: "cat_calm",
        }),
      }),
    );
  });

  it("keeps BGM selector mobile controls touch friendly", () => {
    expect(stylesCss).toMatch(/\.bgm-selector \{[\s\S]*?grid-template-columns:/);
    expect(stylesCss).toMatch(/\.bgm-selector \{[\s\S]*?gap:\s*12px;/);
    expect(stylesCss).toMatch(/\.bgm-selector \{[\s\S]*?min-width:\s*0;/);
    expect(stylesCss).toMatch(
      /\.bgm-selector input,\s*\.bgm-selector select,\s*\.bgm-selector button \{[\s\S]*?min-height:\s*44px;/,
    );
    expect(stylesCss).toMatch(
      /\.bgm-selector-preview \{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\) max-content;/,
    );
    expect(stylesCss).toMatch(
      /@media \(max-width: 760px\) \{[\s\S]*?\.bgm-selector-preview \{[\s\S]*?grid-template-columns:\s*1fr;/,
    );
    expect(stylesCss).toMatch(
      /\.bgm-selector-audio \{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*100%;/,
    );
  });

  it("shows workbench voice selection as a dropdown with the default Edge TTS voice", async () => {
    renderApp();

    const voiceDropdown = await screen.findByRole("combobox", { name: "旁白音色" });
    expect(voiceDropdown).toHaveDisplayValue("Xiaoxiao · zh-CN · Female");
    expect(
      await screen.findByText("Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("搜索音色")).toBeInTheDocument();
    expect(screen.getByLabelText("音色语言")).toHaveDisplayValue("中文");
    expect(mockedFetchVoiceStatus).toHaveBeenCalledTimes(1);
    expect(mockedFetchVoices).toHaveBeenCalledWith({ locale: "zh-CN", q: "" });
  });

  it("filters workbench dropdown voices by language and search while keeping native select", async () => {
    const user = userEvent.setup();
    renderApp();

    await screen.findByRole("combobox", { name: "旁白音色" });
    await user.selectOptions(screen.getByLabelText("音色语言"), "en-US");
    await user.type(screen.getByLabelText("搜索音色"), "Jenny");

    await waitFor(() => {
      expect(mockedFetchVoices).toHaveBeenCalledWith({ locale: "en-US", q: "Jenny" });
    });
    expect(screen.getByRole("combobox", { name: "旁白音色" })).toBeInTheDocument();
  });

  it("keeps workbench voice controls loading and prevents null voice submission while status is pending", async () => {
    const user = userEvent.setup();
    const status = deferred<Awaited<ReturnType<typeof fetchVoiceStatus>>>();
    mockedFetchVoiceStatus.mockReturnValue(status.promise);
    mockedGenerateScript.mockResolvedValueOnce({
      id: "script-1",
      title: "状态未完成短视频",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白 1",
          subtitle: "字幕 1",
          visual_description: "relaxing bedroom night",
          keywords: ["relaxing bedroom night"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValueOnce({
      id: "task-1",
      title: "状态未完成短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    const voiceDropdown = await screen.findByRole("combobox", { name: "旁白音色" });
    expect(voiceDropdown).toBeDisabled();
    expect(screen.getByRole("status", { name: "旁白音色状态" })).toHaveTextContent(
      "正在读取音色状态",
    );
    expect(screen.getByRole("button", { name: "试听旁白音色" })).toBeDisabled();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByDisplayValue("状态未完成短视频");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({
          options: expect.objectContaining({
            voice_id: "zh-CN-XiaoxiaoNeural",
          }),
        }),
      );
    });
    expect(mockedCreateOnlineMixTask).not.toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          voice_id: null,
        }),
      }),
    );
  });

  it("changes the workbench narration voice from the dropdown without submitting the form", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "旁白音色" }),
      "en-US-JennyNeural",
    );

    expect(mockedGenerateScript).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "旁白音色" })).toHaveDisplayValue(
      "Jenny · en-US · Female",
    );
  });

  it("previews the selected workbench voice with the first script narration", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValueOnce({
      id: "script-1",
      title: "睡前精油短视频",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "睡前点一滴精油，让卧室慢慢安静下来。",
          subtitle: "睡前放松",
          visual_description: "relaxing bedroom night",
          keywords: ["relaxing bedroom night"],
        },
      ],
    });
    renderApp();

    await screen.findByRole("combobox", { name: "旁白音色" });
    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByDisplayValue("睡前精油短视频");
    await user.click(screen.getByRole("button", { name: "试听旁白音色" }));

    await waitFor(() => {
      expect(mockedCreateVoicePreview).toHaveBeenCalledWith({
        text: "睡前点一滴精油，让卧室慢慢安静下来。",
        voice_id: "zh-CN-XiaoxiaoNeural",
        rate: "+0%",
        volume: "+0%",
        pitch: "+0Hz",
      });
    });
  });

  it("clears workbench preview audio when the preview text changes", async () => {
    const user = userEvent.setup();
    renderApp();

    await screen.findByRole("combobox", { name: "旁白音色" });
    await user.click(screen.getByRole("button", { name: "试听旁白音色" }));
    expect(await screen.findByLabelText("旁白音色试听音频")).toHaveAttribute(
      "src",
      "/api/voices/previews/edge-tts-preview.mp3",
    );

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");

    await waitFor(() => {
      expect(screen.queryByLabelText("旁白音色试听音频")).not.toBeInTheDocument();
    });
  });

  it("does not render removed auth or netdisk copy", async () => {
    renderApp();
    await screen.findByRole("heading", { name: "混剪工作台" });

    expect(screen.queryByText(removedCopyPattern)).not.toBeInTheDocument();
  });

  it("shows runtime check feedback", async () => {
    renderApp();

    await screen.findByText("运行环境需检查");
    const runtimeStatus = screen.getByRole("status");

    expect(runtimeStatus).toHaveTextContent("运行环境需检查");
    expect(screen.getByText("未找到 FFmpeg，可执行文件：ffmpeg")).toBeInTheDocument();
  });

  it("renders the online remix form and provider status", async () => {
    mockedFetchOnlineMaterialStatus.mockResolvedValue({
      providers: [{ provider: "pexels", configured: false, enabled: false }],
      default_provider: "auto",
      candidate_token_secret_configured: false,
    });
    renderApp();

    expect(await screen.findByLabelText("视频主题")).toBeInTheDocument();
    expect(screen.getByLabelText("时长")).toBeInTheDocument();
    expect(screen.getByLabelText("画幅")).toBeInTheDocument();
    expect(screen.getByLabelText("语气")).toBeInTheDocument();
    expect(screen.getByLabelText("受众")).toBeInTheDocument();
    expect(screen.getByLabelText("卖点")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成脚本" })).toBeInTheDocument();
    expect(screen.getByText("候选签名密钥未配置")).toBeInTheDocument();
  });

  it("shows the custom subtitle template summary for automatic randomized subtitle selection", async () => {
    const user = userEvent.setup();
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [customCaptionTemplate],
      presets: [
        {
          ...cleanBottomPreset,
          favorite: true,
          is_favorite: true,
        },
      ],
    });
    renderApp();

    expect(
      await screen.findByText("自动随机使用模板", { selector: ".subtitle-template-summary" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "去字幕模板页编辑" }));

    expect(await screen.findByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    const subtitleWorkbench = screen.getByRole("article", { name: "字幕模板" });
    expect(within(subtitleWorkbench).getByText("当前模板：品牌底部字幕")).toBeInTheDocument();
    expect(within(subtitleWorkbench).getByRole("button", { name: "品牌底部字幕" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows material provider missing when only candidate secret is configured", async () => {
    mockedFetchOnlineMaterialStatus.mockResolvedValue({
      providers: [{ provider: "pexels", configured: false, enabled: false }],
      default_provider: "auto",
      candidate_token_secret_configured: true,
    });
    renderApp();

    expect(await screen.findByText("素材源未配置")).toBeInTheDocument();
  });

  it("shows online material ready when provider and candidate secret are configured", async () => {
    renderApp();

    expect(await screen.findByText("线上素材源就绪")).toBeInTheDocument();
  });

  it("generates script and shows per-shot candidate actions", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "睡前精油短视频",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 10,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "relaxing bedroom night",
          keywords: ["relaxing bedroom night"],
        },
      ],
    });
    mockedSearchOnlineMaterials.mockResolvedValue([
      {
        provider: "pexels",
        asset_id: "123",
        query: "relaxing bedroom night",
        source_url: "https://www.pexels.com/video/123/",
        preview_url: "https://images.pexels.com/videos/123/preview.jpg",
        candidate_token: "signed-token",
        file_variant: "hd",
        duration: 8.5,
        width: 1080,
        height: 1920,
        license_note: "Pexels source metadata retained",
      },
    ]);
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));

    expect(await screen.findByText("镜头 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "搜索素材" }));
    expect(await screen.findByRole("button", { name: "选择候选" })).toBeInTheDocument();
    expect(screen.getByText("Pexels")).toBeInTheDocument();
    expect(screen.getByText("8.5 秒 · 1080×1920 · hd")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Pexels 预览" })).toHaveAttribute(
      "src",
      "https://images.pexels.com/videos/123/preview.jpg",
    );
    expect(screen.getByRole("button", { name: "替换候选" })).toBeInTheDocument();
  });

  it("keeps per-shot partial failure recoverable", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "睡前精油短视频",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 10,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白 1",
          subtitle: "字幕 1",
          visual_description: "relaxing bedroom night",
          keywords: ["relaxing bedroom night"],
        },
        {
          index: 2,
          duration: 5,
          narration: "旁白 2",
          subtitle: "字幕 2",
          visual_description: "oil bottle close up",
          keywords: ["oil bottle"],
        },
      ],
    });
    mockedSearchOnlineMaterials.mockRejectedValueOnce(
      new Error("ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED"),
    );
    mockedSearchOnlineMaterials.mockResolvedValueOnce([]);
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await user.click((await screen.findAllByRole("button", { name: "搜索素材" }))[0]);

    expect(await screen.findByText("镜头 1 搜索失败")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试镜头 1" }));
    expect(mockedSearchOnlineMaterials).toHaveBeenCalledTimes(2);
  });

  it("can use existing local segment material for a shot", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "material-segment-1",
        original_filename: "oil-bottle-segment.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "local_segment",
        source_provider: "local_material_worker",
        source_asset_id: "seg_1",
        download_url: "/api/materials/material-segment-1/download",
      },
    ]);
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "本地素材脚本",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "oil bottle",
          keywords: ["oil bottle"],
        },
      ],
    });
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await user.click(await screen.findByRole("button", { name: "用本地素材覆盖" }));

    expect(await screen.findByRole("dialog", { name: "选择本地素材" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "选择 oil-bottle-segment.mp4" }));

    expect(screen.getByText("oil-bottle-segment.mp4")).toBeInTheDocument();
  });

  it("filters upload and online materials out of the local material picker", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "material-upload-1",
        original_filename: "uploaded-oil.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "upload",
        download_url: "/api/materials/material-upload-1/download",
      },
      {
        id: "material-online-1",
        original_filename: "pexels-oil.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "online",
        source_provider: "pexels",
        source_asset_id: "123",
        source_url: "https://www.pexels.com/video/123/",
        download_url: "/api/materials/material-online-1/download",
      },
      {
        id: "material-segment-1",
        original_filename: "local-segment-oil.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "local_segment",
        source_provider: "local_material_worker",
        source_asset_id: "seg_1",
        download_url: "/api/materials/material-segment-1/download",
      },
    ]);
    mockedGenerateScript.mockResolvedValue(scriptFixture());
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await user.click(await screen.findByRole("button", { name: "用本地素材覆盖" }));

    const dialog = await screen.findByRole("dialog", { name: "选择本地素材" });
    expect(within(dialog).queryByText("uploaded-oil.mp4")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("pexels-oil.mp4")).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "选择 local-segment-oil.mp4" }),
    ).toBeInTheDocument();
  });

  it("submits local material source mode when creating a remix task", async () => {
    mockedGenerateScript.mockResolvedValue(scriptFixture());
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task_1",
      title: "任务",
      output: { download_url: "/api/tasks/task_1/output" },
    });
    renderApp();

    await userEvent.type(screen.getByLabelText("视频主题"), "睡眠精油");
    await userEvent.selectOptions(screen.getByLabelText("素材来源模式"), "local");
    await userEvent.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByText("镜头 1");
    await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({ material_source_mode: "local" }),
      );
    });
  });

  it("can select local segment material returned from fetchMaterials", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "mat_seg_1",
        original_filename: "local-segment-bedroom-portrait.mp4",
        content_type: "video/mp4",
        size_bytes: 2048,
        created_at: "2026-06-24T00:00:00+00:00",
        source_type: "local_segment",
        source_provider: "local_material_worker",
        source_asset_id: "seg_1",
        license_note: "本地素材库",
        download_url: "/api/materials/mat_seg_1/download",
      },
    ]);
    mockedGenerateScript.mockResolvedValue(scriptFixture());
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task_1",
      title: "任务",
      output: { download_url: "/api/tasks/task_1/output" },
    });
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "睡眠精油");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    const localOverrideButtons = await screen.findAllByRole("button", { name: "用本地素材覆盖" });
    await user.click(localOverrideButtons[0]);

    expect(await screen.findByRole("dialog", { name: "选择本地素材" })).toBeInTheDocument();
    expect(screen.getByText("local-segment-bedroom-portrait.mp4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "选择 local-segment-bedroom-portrait.mp4" }));
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({
          shot_materials: expect.arrayContaining([{ shot_index: 1, material_id: "mat_seg_1" }]),
        }),
      );
    });
  });

  it("clears stale local material selections when the material picker data changes", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "mat_old",
        original_filename: "old-local-segment.mp4",
        content_type: "video/mp4",
        size_bytes: 2048,
        created_at: "2026-06-24T00:00:00+00:00",
        source_type: "local_segment",
        source_provider: "local_material_worker",
        source_asset_id: "old_seg",
        license_note: "本地素材库",
        download_url: "/api/materials/mat_old/download",
      },
    ]);
    mockedGenerateScript.mockResolvedValue({
      ...scriptFixture(),
      shots: [
        ...scriptFixture().shots,
        {
          index: 2,
          duration: 5,
          narration: "第二段旁白",
          subtitle: "第二段字幕",
          visual_description: "warm studio light",
          keywords: ["warm studio light"],
        },
      ],
    });
    mockedSearchOnlineMaterials.mockResolvedValue([
      {
        provider: "pexels",
        asset_id: "pexels_1",
        query: "warm studio light",
        source_url: "https://www.pexels.com/video/1/",
        preview_url: "https://images.example/preview.jpg",
        candidate_token: "candidate-token-1",
        file_variant: "hd",
        duration: 5,
        width: 1080,
        height: 1920,
        license_note: "Pexels",
      },
    ]);
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task_1",
      title: "任务",
      output: { download_url: "/api/tasks/task_1/output" },
    });
    const { queryClient } = renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "睡眠精油");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    const staleLocalOverrideButtons = await screen.findAllByRole("button", {
      name: "用本地素材覆盖",
    });
    await user.click(staleLocalOverrideButtons[0]);
    await user.click(await screen.findByRole("button", { name: "选择 old-local-segment.mp4" }));
    expect(screen.getByText("old-local-segment.mp4")).toBeInTheDocument();

    await user.click(screen.getByText("镜头 2"));
    await user.click(screen.getAllByRole("button", { name: "搜索素材" })[1]);
    await user.click(await screen.findByRole("button", { name: "选择候选" }));
    expect(screen.getByText("已选择 Pexels")).toBeInTheDocument();

    act(() => {
      queryClient.setQueryData(["materials"], []);
    });

    await waitFor(() => {
      expect(screen.queryByText("old-local-segment.mp4")).not.toBeInTheDocument();
      expect(screen.queryByText("mat_old")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({
          shot_assets: [{ shot_index: 2, candidate_token: "candidate-token-1" }],
          shot_materials: [],
        }),
      );
    });
  });

  it("submits edited script fields and selected real material id", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "material-real-1",
        original_filename: "oil-bottle.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "local_segment",
        source_provider: "local_material_worker",
        source_asset_id: "seg_1",
        download_url: "/api/materials/material-real-1/download",
      },
    ]);
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "原始标题",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "原始旁白",
          subtitle: "字幕",
          visual_description: "oil bottle",
          keywords: ["oil bottle"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "任务",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await user.clear(await screen.findByLabelText("脚本标题"));
    await user.type(screen.getByLabelText("脚本标题"), "编辑后的标题");
    await user.clear(screen.getByLabelText("镜头 1 旁白"));
    await user.type(screen.getByLabelText("镜头 1 旁白"), "编辑后的旁白");
    await user.clear(screen.getByLabelText("镜头 1 时长"));
    await user.type(screen.getByLabelText("镜头 1 时长"), "8");
    await user.clear(screen.getByLabelText("镜头 1 关键词"));
    await user.type(screen.getByLabelText("镜头 1 关键词"), "sleep oil,calm");
    await user.click(screen.getByRole("button", { name: "用本地素材覆盖" }));
    await user.click(await screen.findByRole("button", { name: "选择 oil-bottle.mp4" }));
    expect(screen.getByText("手动使用 1 个覆盖素材")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        script: expect.objectContaining({
          title: "编辑后的标题",
          shots: [
            expect.objectContaining({
              duration: 8,
              keywords: ["sleep oil", "calm"],
              narration: "编辑后的旁白",
            }),
          ],
        }),
        asset_strategy: "manual",
        shot_materials: [{ shot_index: 1, material_id: "material-real-1" }],
      }),
    );
  });

  it("creates an automatic online mix task without manual shot selection", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "咖啡店早高峰",
      topic: "咖啡店早高峰",
      aspect_ratio: "9:16",
      duration_seconds: 10,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "第一杯咖啡递到通勤者手里。",
          subtitle: "第一杯咖啡",
          visual_description: "coffee shop morning counter",
          keywords: ["coffee shop morning"],
        },
        {
          index: 2,
          duration: 5,
          narration: "她带着热咖啡走进清晨街道。",
          subtitle: "清晨出发",
          visual_description: "woman walking with coffee morning street",
          keywords: ["woman coffee morning"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValue({
      id: "task-1",
      title: "咖啡店早高峰",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "咖啡店早高峰");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByText("镜头 1");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_strategy: "auto",
        provider: "auto",
        shot_assets: [],
        shot_materials: [],
      }),
    );
    expect(screen.queryByText("已选择 0/2 个镜头")).not.toBeInTheDocument();
  });

  it("sends the selected voice when creating an online remix task", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValueOnce({
      id: "script-1",
      title: "睡前精油短视频",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白 1",
          subtitle: "字幕 1",
          visual_description: "relaxing bedroom night",
          keywords: ["relaxing bedroom night"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValueOnce({
      id: "task-1",
      title: "睡前精油短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    await screen.findByRole("combobox", { name: "旁白音色" });
    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByDisplayValue("睡前精油短视频");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({
          options: expect.objectContaining({
            voice_id: "zh-CN-XiaoxiaoNeural",
            voice_name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
            voice_provider: "edge_tts",
            voice_locale: "zh-CN",
            voice_gender: "Female",
          }),
        }),
      );
    });
  });

  it("uses the manually selected workbench voice when creating an online remix task", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValueOnce({
      id: "script-1",
      title: "英文旁白短视频",
      topic: "咖啡店早高峰",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白 1",
          subtitle: "字幕 1",
          visual_description: "coffee shop morning counter",
          keywords: ["coffee shop morning"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValueOnce({
      id: "task-1",
      title: "英文旁白短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    await user.selectOptions(
      await screen.findByRole("combobox", { name: "旁白音色" }),
      "en-US-JennyNeural",
    );
    expect(screen.getByRole("combobox", { name: "旁白音色" })).toHaveDisplayValue(
      "Jenny · en-US · Female",
    );
    await user.type(await screen.findByLabelText("视频主题"), "咖啡店早高峰");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByDisplayValue("英文旁白短视频");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({
          options: expect.objectContaining({
            voice_id: "en-US-JennyNeural",
            voice_name: "Microsoft Jenny Online (Natural) - English (United States)",
            voice_provider: "edge_tts",
            voice_locale: "en-US",
            voice_gender: "Female",
          }),
        }),
      );
    });
  });

  it("creates an online remix task with null voice fields when the voice service is unavailable", async () => {
    const user = userEvent.setup();
    mockedFetchVoices.mockRejectedValueOnce(new VoiceApiError("VOICE_LIST_FAILED", 503));
    mockedGenerateScript.mockResolvedValueOnce({
      id: "script-1",
      title: "无音色服务短视频",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白 1",
          subtitle: "字幕 1",
          visual_description: "relaxing bedroom night",
          keywords: ["relaxing bedroom night"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockResolvedValueOnce({
      id: "task-1",
      title: "无音色服务短视频",
      output: { download_url: "/api/tasks/task-1/output" },
    });
    renderApp();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "无法读取 Edge TTS 音色，请检查网络后重试。",
    );
    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByDisplayValue("无音色服务短视频");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    await waitFor(() => {
      expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
        expect.objectContaining({
          options: expect.objectContaining({
            voice_id: null,
            voice_name: null,
            voice_provider: null,
            voice_locale: null,
            voice_gender: null,
          }),
        }),
      );
    });
  });

  it("shows create failure with collapsible error details", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "material-real-1",
        original_filename: "oil-bottle.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "local_segment",
        source_provider: "local_material_worker",
        source_asset_id: "seg_1",
        download_url: "/api/materials/material-real-1/download",
      },
    ]);
    mockedGenerateScript.mockResolvedValue({
      id: "script-1",
      title: "失败脚本",
      topic: "精油睡眠放松",
      aspect_ratio: "9:16",
      duration_seconds: 5,
      provider: "heuristic",
      created_at: "2026-06-14T00:00:00+00:00",
      shots: [
        {
          index: 1,
          duration: 5,
          narration: "旁白",
          subtitle: "字幕",
          visual_description: "oil bottle",
          keywords: ["oil bottle"],
        },
      ],
    });
    mockedCreateOnlineMixTask.mockRejectedValue(new Error("ONLINE_MATERIAL_DOWNLOAD_FAILED"));
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await user.click(screen.getByRole("button", { name: "用本地素材覆盖" }));
    await user.click(await screen.findByRole("button", { name: "选择 oil-bottle.mp4" }));
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(await screen.findByText("创建失败")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试创建" })).toBeInTheDocument();
    expect(screen.getByText("错误列表")).toBeInTheDocument();
    expect(screen.getByText("ONLINE_MATERIAL_DOWNLOAD_FAILED")).toBeInTheDocument();
  });

  it("shows material library indexing recovery details when creating a task", async () => {
    const user = userEvent.setup();
    mockedGenerateScript.mockResolvedValue(scriptFixture());
    mockedCreateOnlineMixTask.mockRejectedValue(
      Object.assign(new Error("MATERIAL_LIBRARY_NOT_READY"), {
        code: "MATERIAL_LIBRARY_NOT_READY",
        detail: {
          code: "MATERIAL_LIBRARY_NOT_READY",
          job: {
            id: "job-1",
            status: "queued",
            stage: "scanning",
            progress: { current: 1, total: 4 },
          },
        },
      }),
    );
    renderApp();

    await user.type(await screen.findByLabelText("视频主题"), "睡眠精油");
    await user.click(screen.getByRole("button", { name: "生成脚本" }));
    await screen.findByText("镜头 1");
    await user.click(screen.getByRole("button", { name: "创建任务" }));

    expect(await screen.findByText("创建失败")).toBeInTheDocument();
    expect(screen.getByText(/本地素材库正在建立索引/)).toBeInTheDocument();
    expect(screen.getByText(/阶段：扫描素材/)).toBeInTheDocument();
    expect(screen.getByText(/进度：1\/4/)).toBeInTheDocument();
    expect(screen.queryByText("MATERIAL_LIBRARY_NOT_READY")).not.toBeInTheDocument();
  });

  it("renders mobile collapsible shots and vertical candidate cards", async () => {
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    renderApp();

    const workbench = await screen.findByTestId("online-remix-workbench");
    expect(workbench).toHaveClass("online-remix-panel");
    expect(workbench).toHaveAttribute("data-mobile-layout", "collapsible-shots");
  });
});

describe("subtitle api client contracts", () => {
  it("updates custom templates with an object input contract", async () => {
    const actual = await vi.importActual<typeof import("./api/subtitles")>("./api/subtitles");
    const originalFetch = globalThis.fetch;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(cleanBottomPreset), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    globalThis.fetch = fetchMock;

    try {
      await actual.updateSubtitleTemplateSet({
        id: "template/one",
        patch: { name: "更新后的模板" },
      });
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/subtitle-template-sets/template%2Fone",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ name: "更新后的模板" }),
      }),
    );
  });

  it("updates preset overrides with an object input contract", async () => {
    const actual = await vi.importActual<typeof import("./api/subtitles")>("./api/subtitles");
    const originalFetch = globalThis.fetch;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(cleanBottomPreset), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    globalThis.fetch = fetchMock;

    try {
      await actual.updateSubtitlePresetOverride({
        id: "preset/clean",
        patch: { is_favorite: true },
      });
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/subtitle-template-sets/presets/preset%2Fclean",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ is_favorite: true }),
      }),
    );
  });

  it("resolves delete responses with no content", async () => {
    const actual = await vi.importActual<typeof import("./api/subtitles")>("./api/subtitles");
    const originalFetch = globalThis.fetch;
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    globalThis.fetch = fetchMock;

    try {
      await expect(actual.deleteSubtitleTemplateSet("template/one")).resolves.toBeUndefined();
      await expect(actual.resetSubtitlePresetOverride("preset/clean")).resolves.toBeUndefined();
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/subtitle-template-sets/template%2Fone",
      { method: "DELETE" },
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/subtitle-template-sets/presets/preset%2Fclean",
      { method: "DELETE" },
    );
  });

  it("deletes video tasks with a no-content response", async () => {
    const actual = await vi.importActual<typeof import("./api/tasks")>("./api/tasks");
    const originalFetch = globalThis.fetch;
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    globalThis.fetch = fetchMock;

    try {
      await expect(actual.deleteTask("task/one")).resolves.toBeUndefined();
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task%2Fone", { method: "DELETE" });
  });

  it("throws structured subtitle api errors with code and status", async () => {
    const actual = await vi.importActual<typeof import("./api/subtitles")>("./api/subtitles");
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "SUBTITLE_TEMPLATE_INVALID" } }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );

    let thrownError: unknown;
    try {
      await actual.validateSubtitleTemplateSet(cleanBottomPreset);
    } catch (error) {
      thrownError = error;
    } finally {
      globalThis.fetch = originalFetch;
    }

    expect(thrownError).toBeInstanceOf(actual.SubtitleTemplateApiError);
    expect(thrownError).toMatchObject({
      code: "SUBTITLE_TEMPLATE_INVALID",
      status: 400,
    });
  });
});
