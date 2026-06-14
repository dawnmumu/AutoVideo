import { useMutation, useQuery } from "@tanstack/react-query";
import { FolderOpen, RefreshCw, Search, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  GeneratedScript,
  LocalMaterial,
  OnlineMaterialCandidate,
  ScriptShot,
  createOnlineMixTask,
  fetchMaterials,
  fetchOnlineMaterialStatus,
  generateScript,
  searchOnlineMaterials,
} from "../api/onlineRemix";

type ShotSearchState = "idle" | "searching" | "ready" | "failed" | "empty";

function splitList(value: string): string[] {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function providerLabel(provider: string): string {
  if (provider === "pexels") {
    return "Pexels";
  }
  if (provider === "pixabay") {
    return "Pixabay";
  }
  return provider;
}

function shotQuery(shot: ScriptShot): string {
  return shot.keywords[0] ?? shot.visual_description;
}

export function OnlineRemixWorkbench() {
  const [topic, setTopic] = useState("");
  const [durationSeconds, setDurationSeconds] = useState(30);
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [tone, setTone] = useState("自然可信");
  const [targetAudience, setTargetAudience] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [provider, setProvider] = useState("auto");
  const [script, setScript] = useState<GeneratedScript | null>(null);
  const [shotState, setShotState] = useState<Record<number, ShotSearchState>>({});
  const [openShots, setOpenShots] = useState<Record<number, boolean>>({});
  const [candidatesByShot, setCandidatesByShot] = useState<
    Record<number, OnlineMaterialCandidate[]>
  >({});
  const [keywordInputByShot, setKeywordInputByShot] = useState<Record<number, string>>({});
  const [selectedByShot, setSelectedByShot] = useState<
    Record<number, OnlineMaterialCandidate>
  >({});
  const [localMaterialByShot, setLocalMaterialByShot] = useState<Record<number, string>>({});
  const [localPickerShot, setLocalPickerShot] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  const status = useQuery({
    queryKey: ["online-material-status"],
    queryFn: fetchOnlineMaterialStatus,
  });
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: fetchMaterials,
  });

  const generate = useMutation({
    mutationFn: () =>
      generateScript({
        topic,
        provider: "auto",
        duration_seconds: durationSeconds,
        aspect_ratio: aspectRatio,
        tone,
        target_audience: targetAudience,
        selling_points: splitList(sellingPoints),
      }),
    onSuccess: (payload) => {
      setScript(payload);
      setShotState({});
      setOpenShots({});
      setCandidatesByShot({});
      setKeywordInputByShot(
        Object.fromEntries(payload.shots.map((shot) => [shot.index, shot.keywords.join(",")])),
      );
      setSelectedByShot({});
      setLocalMaterialByShot({});
      setErrors([]);
    },
    onError: (error) => {
      setErrors((current) => [...current, errorMessage(error, "SCRIPT_GENERATE_FAILED")]);
    },
  });

  const search = useMutation({
    mutationFn: (shot: ScriptShot) =>
      searchOnlineMaterials({
        query: shotQuery(shot),
        aspect_ratio: script?.aspect_ratio ?? "9:16",
        min_duration_seconds: Math.max(1, Math.round(shot.duration)),
        provider,
      }),
    onMutate: (shot) => {
      setShotState((current) => ({ ...current, [shot.index]: "searching" }));
    },
    onSuccess: (candidates, shot) => {
      setCandidatesByShot((current) => ({ ...current, [shot.index]: candidates }));
      setShotState((current) => ({
        ...current,
        [shot.index]: candidates.length > 0 ? "ready" : "empty",
      }));
    },
    onError: (error, shot) => {
      setShotState((current) => ({ ...current, [shot.index]: "failed" }));
      setErrors((current) => [
        ...current,
        `镜头 ${shot.index}: ${errorMessage(error, "ONLINE_MATERIAL_SEARCH_FAILED")}`,
      ]);
    },
  });

  const createTask = useMutation({
    mutationFn: () => {
      if (!script) {
        throw new Error("SCRIPT_REQUIRED");
      }
      return createOnlineMixTask({
        title: script.title,
        script,
        asset_strategy: "manual",
        provider,
        shot_assets: Object.entries(selectedByShot).map(([shotIndex, candidate]) => ({
          shot_index: Number(shotIndex),
          candidate_token: candidate.candidate_token,
        })),
        shot_materials: Object.entries(localMaterialByShot).map(([shotIndex, materialId]) => ({
          shot_index: Number(shotIndex),
          material_id: materialId,
        })),
        options: {
          aspect_ratio: script.aspect_ratio,
          resolution: "1080p",
        },
      });
    },
    onSuccess: () => {
      setErrors([]);
    },
    onError: (error) => {
      setErrors((current) => [...current, errorMessage(error, "CREATE_TASK_FAILED")]);
    },
  });

  const providerReady = status.data?.providers.some((item) => item.enabled) === true;
  const secretReady = status.data?.candidate_token_secret_configured === true;
  const providerStatusMessages =
    providerReady && secretReady
      ? ["线上素材源就绪"]
      : [
          providerReady ? null : "素材源未配置",
          secretReady ? null : "候选签名密钥未配置",
        ].filter((item): item is string => item !== null);
  const selectedCount =
    Object.keys(selectedByShot).length + Object.keys(localMaterialByShot).length;
  const requiredShotCount = script?.shots.length ?? 0;
  const allShotsSelected = requiredShotCount > 0 && selectedCount >= requiredShotCount;

  const findMaterial = (materialId: string): LocalMaterial | undefined =>
    materials.data?.find((material) => material.id === materialId);

  const updateScript = (updater: (current: GeneratedScript) => GeneratedScript) => {
    setScript((current) => (current ? updater(current) : current));
  };

  const updateShot = (shotIndex: number, patch: Partial<ScriptShot>) => {
    updateScript((current) => ({
      ...current,
      shots: current.shots.map((shot) =>
        shot.index === shotIndex ? { ...shot, ...patch } : shot,
      ),
    }));
  };

  const selectCandidate = (shotIndex: number, candidate: OnlineMaterialCandidate) => {
    setSelectedByShot((current) => ({ ...current, [shotIndex]: candidate }));
    setLocalMaterialByShot((current) => {
      const next = { ...current };
      delete next[shotIndex];
      return next;
    });
  };

  const selectLocalMaterial = (shotIndex: number, materialId: string) => {
    setLocalMaterialByShot((current) => ({ ...current, [shotIndex]: materialId }));
    setSelectedByShot((current) => {
      const next = { ...current };
      delete next[shotIndex];
      return next;
    });
    setLocalPickerShot(null);
  };

  return (
    <article
      aria-label="线上混剪"
      className="panel online-remix-panel"
      data-mobile-layout="collapsible-shots"
      data-testid="online-remix-workbench"
    >
      <div className="panel-heading">
        <h2>线上混剪</h2>
        <div className="status-inline" aria-live="polite">
          {providerStatusMessages.map((message) => (
            <span key={message}>{message}</span>
          ))}
        </div>
      </div>

      <form
        className="online-remix-form"
        onSubmit={(event) => {
          event.preventDefault();
          generate.mutate();
        }}
      >
        <label>
          <span>视频主题</span>
          <input value={topic} onChange={(event) => setTopic(event.target.value)} />
        </label>
        <label>
          <span>时长</span>
          <input
            inputMode="numeric"
            max="300"
            min="5"
            onChange={(event) => setDurationSeconds(Number(event.target.value))}
            type="number"
            value={durationSeconds}
          />
        </label>
        <label>
          <span>画幅</span>
          <select value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value)}>
            <option value="9:16">9:16</option>
            <option value="16:9">16:9</option>
            <option value="1:1">1:1</option>
          </select>
        </label>
        <label>
          <span>语气</span>
          <input value={tone} onChange={(event) => setTone(event.target.value)} />
        </label>
        <label>
          <span>受众</span>
          <input value={targetAudience} onChange={(event) => setTargetAudience(event.target.value)} />
        </label>
        <label>
          <span>卖点</span>
          <input value={sellingPoints} onChange={(event) => setSellingPoints(event.target.value)} />
        </label>
        <label>
          <span>素材源</span>
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="auto">Auto</option>
            <option value="pexels">Pexels 素材</option>
            <option value="pixabay">Pixabay 素材</option>
          </select>
        </label>
        <button className="primary-action" disabled={!topic.trim() || generate.isPending} type="submit">
          <Sparkles aria-hidden="true" size={18} />
          {generate.isPending ? "生成中" : "生成脚本"}
        </button>
      </form>

      {generate.isError ? (
        <div className="inline-error" role="alert">
          <span>脚本生成失败</span>
          <button type="button" onClick={() => generate.mutate()}>
            <RefreshCw aria-hidden="true" size={16} />
            重试
          </button>
        </div>
      ) : null}

      {errors.length > 0 ? (
        <details className="error-list" open>
          <summary>错误列表</summary>
          <ul>
            {errors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
        </details>
      ) : null}

      {script ? (
        <div className="shot-list">
          <label>
            <span>脚本标题</span>
            <input
              onChange={(event) =>
                updateScript((current) => ({ ...current, title: event.target.value }))
              }
              value={script.title}
            />
          </label>

          {script.shots.map((shot) => {
            const selectedMaterialId = localMaterialByShot[shot.index];
            const selectedMaterial = selectedMaterialId ? findMaterial(selectedMaterialId) : undefined;
            const searchState = shotState[shot.index] ?? "idle";
            const isOpen = openShots[shot.index] ?? shot.index === 1;

            return (
              <details
                className="shot-row"
                key={shot.index}
                onToggle={(event) => {
                  const isDetailsOpen = event.currentTarget.open;
                  setOpenShots((current) => ({
                    ...current,
                    [shot.index]: isDetailsOpen,
                  }));
                }}
                open={isOpen}
              >
                <summary>
                  <h3>镜头 {shot.index}</h3>
                  <span>{searchState}</span>
                </summary>

                <div className="shot-fields">
                  <label>
                    <span>镜头 {shot.index} 旁白</span>
                    <textarea
                      onChange={(event) =>
                        updateShot(shot.index, { narration: event.target.value })
                      }
                      value={shot.narration}
                    />
                  </label>
                  <label>
                    <span>镜头 {shot.index} 字幕</span>
                    <input
                      onChange={(event) => updateShot(shot.index, { subtitle: event.target.value })}
                      value={shot.subtitle}
                    />
                  </label>
                  <label>
                    <span>镜头 {shot.index} 时长</span>
                    <input
                      inputMode="numeric"
                      min="1"
                      onChange={(event) =>
                        updateShot(shot.index, { duration: Number(event.target.value) })
                      }
                      type="number"
                      value={shot.duration}
                    />
                  </label>
                  <label>
                    <span>镜头 {shot.index} 关键词</span>
                    <input
                      onChange={(event) => {
                        setKeywordInputByShot((current) => ({
                          ...current,
                          [shot.index]: event.target.value,
                        }));
                        updateShot(shot.index, { keywords: splitList(event.target.value) });
                      }}
                      value={keywordInputByShot[shot.index] ?? shot.keywords.join(",")}
                    />
                  </label>
                  <label>
                    <span>镜头 {shot.index} 画面</span>
                    <textarea
                      onChange={(event) =>
                        updateShot(shot.index, { visual_description: event.target.value })
                      }
                      value={shot.visual_description}
                    />
                  </label>
                </div>

                <div className="shot-actions">
                  <button
                    disabled={searchState === "searching"}
                    type="button"
                    onClick={() => search.mutate(shot)}
                  >
                    <Search aria-hidden="true" size={16} />
                    {searchState === "searching" ? "搜索中" : "搜索素材"}
                  </button>
                  <button type="button" onClick={() => setLocalPickerShot(shot.index)}>
                    <FolderOpen aria-hidden="true" size={16} />
                    改用已有本地素材
                  </button>
                </div>

                {searchState === "failed" ? (
                  <div className="inline-error" role="alert">
                    <span>镜头 {shot.index} 搜索失败</span>
                    <button type="button" onClick={() => search.mutate(shot)}>
                      <RefreshCw aria-hidden="true" size={16} />
                      重试镜头 {shot.index}
                    </button>
                  </div>
                ) : null}

                {searchState === "empty" ? (
                  <div className="inline-error" role="status">
                    <span>镜头 {shot.index} 暂无候选</span>
                    <button type="button" onClick={() => search.mutate(shot)}>
                      <RefreshCw aria-hidden="true" size={16} />
                      重试镜头 {shot.index}
                    </button>
                  </div>
                ) : null}

                {selectedMaterialId ? (
                  <span className="selected-material">
                    {selectedMaterial?.original_filename ?? selectedMaterialId}
                  </span>
                ) : null}

                {selectedByShot[shot.index] ? (
                  <span className="selected-material">
                    已选择 {providerLabel(selectedByShot[shot.index].provider)}
                  </span>
                ) : null}

                {(candidatesByShot[shot.index] ?? []).map((candidate) => (
                  <div className="candidate-row" key={candidate.candidate_token}>
                    <img
                      alt={`${providerLabel(candidate.provider)} 预览`}
                      loading="lazy"
                      src={candidate.preview_url}
                    />
                    <span>{providerLabel(candidate.provider)}</span>
                    <span>
                      {candidate.duration} 秒 · {candidate.width}×{candidate.height} ·{" "}
                      {candidate.file_variant}
                    </span>
                    <a href={candidate.source_url}>素材源详情</a>
                    <button type="button" onClick={() => selectCandidate(shot.index, candidate)}>
                      选择候选
                    </button>
                    <button type="button" onClick={() => search.mutate(shot)}>
                      替换候选
                    </button>
                  </div>
                ))}
              </details>
            );
          })}
        </div>
      ) : null}

      {localPickerShot !== null ? (
        <div aria-label="选择本地素材" className="local-material-dialog" role="dialog">
          {(materials.data ?? []).map((material) => (
            <button
              key={material.id}
              type="button"
              onClick={() => selectLocalMaterial(localPickerShot, material.id)}
            >
              选择 {material.original_filename}
            </button>
          ))}
          {materials.isLoading ? <span>正在加载本地素材</span> : null}
          {materials.data?.length === 0 ? <span>暂无本地素材</span> : null}
          <button type="button" onClick={() => setLocalPickerShot(null)}>
            关闭
          </button>
        </div>
      ) : null}

      {script ? (
        <div className="create-task-row">
          <button
            className="primary-action"
            disabled={!allShotsSelected || createTask.isPending}
            type="button"
            onClick={() => createTask.mutate()}
          >
            {createTask.isPending ? "创建中" : "创建任务"}
          </button>
          {!allShotsSelected ? (
            <span className="selected-material">
              已选择 {selectedCount}/{requiredShotCount} 个镜头
            </span>
          ) : null}
          {createTask.data ? <a href={createTask.data.output.download_url}>查看任务输出</a> : null}
        </div>
      ) : null}

      {createTask.isError ? (
        <div className="inline-error" role="alert">
          <span>创建失败</span>
          <button type="button" onClick={() => createTask.mutate()}>
            <RefreshCw aria-hidden="true" size={16} />
            重试创建
          </button>
        </div>
      ) : null}
    </article>
  );
}
