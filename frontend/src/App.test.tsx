import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { fetchHealth } from "./api/health";
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

const mockedFetchHealth = vi.mocked(fetchHealth);
const mockedFetchOnlineMaterialStatus = vi.mocked(fetchOnlineMaterialStatus);
const mockedFetchMaterials = vi.mocked(fetchMaterials);
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
const removedCopyPattern = new RegExp(
  [
    ["退出", "登录"].join(""),
    ["个人", "网盘"].join(""),
    ["NAS", " 登录"].join(""),
    ["to", "ken"].join(""),
  ].join("|"),
  "i",
);

const cleanBottomPreset = {
  id: "preset-clean-bottom",
  name: "清爽底部字幕",
  schema_version: 2,
  renderer_mode: "ass_plus",
  is_favorite: false,
  is_modified: false,
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
  ],
};

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("AutoVideo shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });

  it("renders the Chinese product navigation", async () => {
    renderApp();

    expect(await screen.findByRole("heading", { name: "混剪工作台" })).toBeInTheDocument();
    expect(screen.getByText("素材库")).toBeInTheDocument();
    expect(screen.getByText("字幕模板")).toBeInTheDocument();
    expect(screen.getByText("BGM 管理")).toBeInTheDocument();
    expect(screen.getByText("音色中心")).toBeInTheDocument();
    expect(screen.getByText("功能提取处理")).toBeInTheDocument();
    expect(screen.getByText("任务与输出")).toBeInTheDocument();
    expect(screen.getByText("系统设置")).toBeInTheDocument();
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

    expect(screen.getByRole("heading", { name: "字幕模板" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "字幕" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("status")).toHaveTextContent("可用模板 1 个");
  });

  it("opens subtitle templates from mobile navigation and updates active state", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕" }));

    expect(screen.getByRole("heading", { name: "字幕模板" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "字幕" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute(
      "aria-current",
      "page",
    );
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

  it("can use existing local material for a shot", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "material-real-1",
        original_filename: "oil-bottle.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "upload",
        download_url: "/api/materials/material-real-1/download",
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
    await user.click(screen.getByRole("button", { name: "选择 oil-bottle.mp4" }));

    expect(screen.getByText("oil-bottle.mp4")).toBeInTheDocument();
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
        source_type: "upload",
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

  it("shows create failure with collapsible error details", async () => {
    const user = userEvent.setup();
    mockedFetchMaterials.mockResolvedValue([
      {
        id: "material-real-1",
        original_filename: "oil-bottle.mp4",
        content_type: "video/mp4",
        size_bytes: 128,
        created_at: "2026-06-14T00:00:00+00:00",
        source_type: "upload",
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
});
