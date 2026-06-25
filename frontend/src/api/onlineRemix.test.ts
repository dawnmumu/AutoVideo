import { afterEach, describe, expect, it, vi } from "vitest";

import { createOnlineMixTask } from "./onlineRemix";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("online remix API", () => {
  it("preserves structured error detail payloads", async () => {
    const detail = {
      code: "MATERIAL_LIBRARY_NOT_READY",
      job: {
        id: "job-1",
        status: "queued",
        stage: "scanning",
        progress: { current: 0, total: 3 },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      createOnlineMixTask({
        title: "任务",
        script: {
          id: "script-1",
          title: "脚本",
          topic: "主题",
          aspect_ratio: "9:16",
          duration_seconds: 5,
          provider: "heuristic",
          created_at: "2026-06-25T00:00:00+00:00",
          shots: [],
        },
        asset_strategy: "manual",
        provider: "auto",
        shot_assets: [],
        shot_materials: [],
        options: {
          aspect_ratio: "9:16",
          resolution: "1080p",
        },
        material_source_mode: "local",
      }),
    ).rejects.toMatchObject({
      code: "MATERIAL_LIBRARY_NOT_READY",
      status: 409,
      detail,
    });
  });
});
