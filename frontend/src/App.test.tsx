import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
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
import type { SubtitleTemplateSet } from "./api/subtitles";
import { fetchTasks } from "./api/tasks";

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
}));

const mockedFetchHealth = vi.mocked(fetchHealth);
const mockedFetchOnlineMaterialStatus = vi.mocked(fetchOnlineMaterialStatus);
const mockedFetchMaterials = vi.mocked(fetchMaterials);
const mockedFetchTasks = vi.mocked(fetchTasks);
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
const stylesCss = readFileSync("src/styles.css", "utf-8");
const defaultSubtitlePreviewText = "这是字幕预览，支持多个位置和不同倾斜角度";

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

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

function previewTopPercent(testId: string): number {
  const value = screen.getByTestId(testId).style.top;
  return Number.parseFloat(value);
}

describe("AutoVideo shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState(null, "", "/");
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
    expect(screen.getByRole("link", { name: "字幕模板" })).toBeInTheDocument();
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

    expect(window.location.hash).toBe("#subtitles");
    expect(screen.getByRole("heading", { name: "字幕模板", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("管理默认字幕样式与预览")).toBeInTheDocument();
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

  it("uses a readable neutral preview canvas instead of a black frame", () => {
    expect(stylesCss).toMatch(
      /\.subtitle-preview-frame \{[\s\S]*?background:\s*linear-gradient\([\s\S]*?#f8fafc/,
    );
    expect(stylesCss).not.toMatch(/\.subtitle-preview-frame \{[\s\S]*?background:\s*#111827;/);
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

  it("keeps enabled mobile navigation entries before disabled placeholders", async () => {
    renderApp();

    await screen.findByRole("heading", { name: "混剪工作台" });

    const mobileNav = screen.getByRole("navigation", { name: "移动端导航" });
    const labels = Array.from(mobileNav.querySelectorAll("a, span")).map((item) =>
      item.textContent?.trim(),
    );
    expect(labels.slice(0, 3)).toEqual(["混剪", "字幕", "任务"]);
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

  it("creates a custom subtitle template and marks a preset as default", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "字幕模板" }));

    expect(await screen.findByRole("button", { name: "设为默认" })).toBeInTheDocument();
    expect(screen.getByLabelText("示例文本")).toBeInTheDocument();
    expect(screen.getAllByLabelText("字体")).toHaveLength(3);
    expect(screen.getAllByLabelText("主色")).toHaveLength(3);
    expect(screen.getByRole("group", { name: "底部字幕" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "强调字幕" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "冲击字幕" })).toBeInTheDocument();
    expect(screen.getByLabelText("预览画幅")).toHaveValue("9:16");
    expect(screen.getAllByLabelText("字号比例")).toHaveLength(3);
    expect(screen.getAllByLabelText("描边宽度")).toHaveLength(3);
    expect(screen.getAllByLabelText("阴影强度")).toHaveLength(3);
    expect(screen.getAllByLabelText("垂直位置")).toHaveLength(3);
    expect(screen.getAllByLabelText("最大宽度")).toHaveLength(3);
    expect(screen.getAllByLabelText("旋转")).toHaveLength(3);
    expect(screen.getAllByLabelText("倾斜")).toHaveLength(3);
    expect(screen.queryByLabelText("局部关键词")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("局部高亮色")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存局部高亮" })).not.toBeInTheDocument();
    expect(screen.getAllByText("局部样式")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "新增底部字幕局部样式" })).toBeDisabled();
    expect(screen.getByTestId("subtitle-preview-frame")).toHaveStyle({ aspectRatio: "9 / 16" });

    await user.selectOptions(screen.getByLabelText("预览画幅"), "16:9");
    expect(screen.getByTestId("subtitle-preview-frame")).toHaveStyle({ aspectRatio: "16 / 9" });
    await user.click(screen.getByRole("button", { name: "设为默认" }));
    await user.click(screen.getByRole("button", { name: "从预设新建" }));

    expect(mockedCreateSubtitleTemplateSet).toHaveBeenCalledWith({
      name: "我的清晰底部字幕",
      preset_id: "preset-clean-bottom",
    });
    expect(mockedUpdateSubtitlePresetOverride).toHaveBeenCalledWith({
      id: "preset-clean-bottom",
      patch: { is_favorite: true },
    });
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
    const fontScaleInput = await screen.findByLabelText(
      "强调字幕局部样式 1 字号比例",
    ) as HTMLInputElement;
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

    expect(previewCaption).toHaveStyle({ textShadow: "0 1px 1px #000000" });

    await user.clear(shadowInput);
    await user.type(shadowInput, "6");

    expect(previewCaption).toHaveStyle({ textShadow: "0 3px 6px #000000" });
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
    expect(within(subtitleWorkbench).getAllByLabelText("主色")[0]).toBeDisabled();
    expect(within(subtitleWorkbench).getByRole("button", { name: "还原预设" })).not.toBeDisabled();

    await user.click(within(subtitleWorkbench).getByRole("button", { name: "设为默认" }));
    expect(mockedUpdateSubtitlePresetOverride).toHaveBeenCalledWith({
      id: "builtin-clean-bottom",
      patch: { is_favorite: true },
    });
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

  it("selects a custom subtitle template before a favorite preset by default", async () => {
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

  it("keeps API preset order when no custom or favorite preset is available", async () => {
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
      favorite: false,
      is_favorite: false,
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

  it("selects the newest favorite custom subtitle template like the backend", async () => {
    const olderFavorite = templateFixture({
      id: "tmpl-brand-old",
      name: "旧版品牌字幕",
      favorite: true,
      is_favorite: true,
      is_modified: true,
      created_at: "2026-06-01T00:00:00+00:00",
      updated_at: "2026-06-10T00:00:00+00:00",
    });
    const newerFavorite = templateFixture({
      id: "tmpl-brand-new",
      name: "新版品牌字幕",
      favorite: true,
      is_favorite: true,
      is_modified: true,
      created_at: "2026-06-02T00:00:00+00:00",
      updated_at: "2026-06-12T00:00:00+00:00",
    });
    mockedFetchSubtitleTemplateSets.mockResolvedValue({
      items: [olderFavorite, newerFavorite],
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
    const primaryColor = screen.getAllByLabelText("主色")[0] as HTMLInputElement;

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
    const primaryColor = screen.getAllByLabelText("主色")[0] as HTMLInputElement;
    const fontScale = screen.getAllByLabelText("字号比例")[0] as HTMLInputElement;

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
    await user.click(screen.getByRole("button", { name: "校验模板" }));

    expect(mockedValidateSubtitleTemplateSet).toHaveBeenCalledWith(
      expect.objectContaining({ id: "preset-clean-bottom" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("主色格式无效");
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
    await user.click(screen.getByRole("button", { name: "校验模板" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("主色格式无效");

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

    const primaryColor = screen.getAllByLabelText("主色")[0] as HTMLInputElement;
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
    const primaryColor = screen.getAllByLabelText("主色")[0] as HTMLInputElement;

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
    const primaryColor = screen.getAllByLabelText("主色")[0] as HTMLInputElement;

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
        aspect_ratio: "9:16",
        sample_text: "AI 自动完成重复工作",
      }),
    );
    expect(mockedPreviewSubtitleTimeline).toHaveBeenCalledWith(
      expect.objectContaining({
        template_type: "bottom",
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
