import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { fetchHealth } from "./api/health";

vi.mock("./api/health", () => ({
  fetchHealth: vi.fn(),
}));

const mockedFetchHealth = vi.mocked(fetchHealth);
const removedCopyPattern = new RegExp(
  [
    ["退出", "登录"].join(""),
    ["个人", "网盘"].join(""),
    ["NAS", " 登录"].join(""),
    ["to", "ken"].join(""),
  ].join("|"),
  "i",
);

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
});
