import { afterEach, describe, expect, it, vi } from "vitest";

import { createOnlineMixTask, fetchMaterials } from "./onlineRemix";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("online remix API", () => {
  it("requests current-source local material worker segments for the picker", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchMaterials()).resolves.toEqual([]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/materials?limit=100&offset=0&source_type=local_segment&source_provider=local_material_worker&current_material_source=true",
    );
  });

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
