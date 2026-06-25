import { useMutation, useQuery } from "@tanstack/react-query";
import { Captions, FolderOpen, RefreshCw, Search, Sparkles } from "lucide-react";
import { useState } from "react";

import { fetchHealth } from "../api/health";
import { fetchSubtitleTemplateSets } from "../api/subtitles";
import type { VoiceItem } from "../api/voices";
import {
  GeneratedScript,
  LocalMaterial,
  MaterialSourceMode,
  OnlineMaterialCandidate,
  ScriptShot,
  createOnlineMixTask,
  fetchMaterials,
  fetchOnlineMaterialStatus,
  generateScript,
  searchOnlineMaterials,
} from "../api/onlineRemix";
import { BgmSelector } from "./BgmSelector";
import type { SelectedBgm } from "./BgmSelector";
import { VoiceDropdown } from "./VoiceDropdown";
import { selectAutoSubtitleTemplate } from "./subtitleTemplateSelection";

type ShotSearchState = "idle" | "searching" | "ready" | "failed" | "empty";

function splitList(value: string): string[] {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function errorMessage(error: unknown, fallback: string): string {
  const code = errorCode(error);
  if (code === "MATERIAL_LIBRARY_NOT_READY") {
    const job = materialIndexJob(error);
    const details = [
      "本地素材库正在建立索引，完成后可重试创建任务。",
      job ? `阶段：${stageLabel(job.stage)}` : null,
      job ? progressLabel(job.progress) : null,
    ].filter((item): item is string => item !== null);
    return details.join(" ");
  }
  return error instanceof Error ? error.message : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function errorCode(error: unknown): string | null {
  if (isRecord(error) && typeof error.code === "string") {
    return error.code;
  }
  return null;
}

function materialIndexJob(error: unknown): Record<string, unknown> | null {
  if (!isRecord(error) || !isRecord(error.detail) || !isRecord(error.detail.job)) {
    return null;
  }
  return error.detail.job;
}

function stageLabel(stage: unknown): string {
  if (stage === "scanning") {
    return "扫描素材";
  }
  if (stage === "segmenting") {
    return "切分素材";
  }
  if (stage === "ready") {
    return "索引完成";
  }
  return typeof stage === "string" && stage ? stage : "等待处理";
}

function progressLabel(progress: unknown): string | null {
  if (!isRecord(progress)) {
    return null;
  }
  const current = Number(progress.current ?? 0);
  const total = Number(progress.total ?? 0);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
    return null;
  }
  return `进度：${current}/${total}`;
}

function isLocalMaterialLibrarySegment(material: LocalMaterial): boolean {
  return (
    material.source_type === "local_segment" &&
    material.source_provider === "local_material_worker"
  );
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

interface OnlineRemixWorkbenchProps {
  onOpenSubtitleTemplates?: () => void;
  onOpenBgmManagement?: () => void;
}

export function OnlineRemixWorkbench({
  onOpenSubtitleTemplates,
  onOpenBgmManagement,
}: OnlineRemixWorkbenchProps) {
  const [topic, setTopic] = useState("");
  const [durationSeconds, setDurationSeconds] = useState(30);
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [tone, setTone] = useState("自然可信");
  const [targetAudience, setTargetAudience] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [provider, setProvider] = useState("auto");
  const [materialSourceMode, setMaterialSourceMode] =
    useState<MaterialSourceMode>("hybrid");
  const [subtitleEnabled, setSubtitleEnabled] = useState(true);
  const [subtitleTemplateSetId, setSubtitleTemplateSetId] = useState("");
  const [subtitleFontFamily, setSubtitleFontFamily] = useState("");
  const [selectedVoice, setSelectedVoice] = useState<VoiceItem | null>(null);
  const [selectedBgm, setSelectedBgm] = useState<SelectedBgm>({
    enabled: true,
    categoryId: "",
    trackId: "",
    volume: 0.12,
  });
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
  const subtitleTemplates = useQuery({
    queryKey: ["subtitle-template-sets"],
    queryFn: fetchSubtitleTemplateSets,
  });
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
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

  const voicePreviewText =
    script?.shots.find((shot) => shot.narration.trim())?.narration.trim() ||
    (topic.trim()
      ? `你好，这是一条关于${topic.trim().slice(0, 20)}的视频旁白试听。`
      : "你好，这是一段视频旁白试听，你可以先听听这款人声是否适合当前视频。");

  const createTask = useMutation({
    mutationFn: () => {
      if (!script) {
        throw new Error("SCRIPT_REQUIRED");
      }
      return createOnlineMixTask({
        title: script.title,
        script,
        asset_strategy: allShotsCovered ? "manual" : "auto",
        provider,
        shot_assets: Object.entries(selectedByShot).map(([shotIndex, candidate]) => ({
          shot_index: Number(shotIndex),
          candidate_token: candidate.candidate_token,
        })),
        shot_materials: Object.entries(localMaterialByShot).map(([shotIndex, materialId]) => ({
          shot_index: Number(shotIndex),
          material_id: materialId,
        })),
        material_source_mode: materialSourceMode,
        options: {
          aspect_ratio: script.aspect_ratio,
          resolution: "1080p",
          subtitle_enabled: subtitleEnabled,
          subtitle_template_set_id: subtitleEnabled ? subtitleTemplateSetId || null : null,
          subtitle_font_family: subtitleEnabled ? subtitleFontFamily || null : null,
          voice_id: selectedVoice?.id ?? null,
          voice_name: selectedVoice?.name ?? null,
          voice_provider: selectedVoice?.provider ?? null,
          voice_locale: selectedVoice?.locale ?? null,
          voice_gender: selectedVoice?.gender ?? null,
          bgm_enabled: selectedBgm.enabled,
          bgm_category_id: selectedBgm.enabled ? selectedBgm.categoryId || null : null,
          bgm_track_id: selectedBgm.enabled ? selectedBgm.trackId || null : null,
          bgm_volume: selectedBgm.enabled ? selectedBgm.volume : null,
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
  const ffmpegOk = health.data?.checks.ffmpeg?.ok;
  const audioOutputMessage =
    ffmpegOk === true
      ? "所选旁白和 BGM 会合成到最终 MP4"
      : ffmpegOk === false
        ? "配置 FFmpeg 后，所选旁白和 BGM 会合成到最终 MP4"
        : "正在检测 FFmpeg 音频合成能力";
  const selectedCount =
    Object.keys(selectedByShot).length + Object.keys(localMaterialByShot).length;
  const requiredShotCount = script?.shots.length ?? 0;
  const coveredShotIndexes = new Set(
    [
      ...Object.keys(selectedByShot),
      ...Object.keys(localMaterialByShot),
    ].map((shotIndex) => Number(shotIndex)),
  );
  const allShotsCovered =
    script?.shots.length ? script.shots.every((shot) => coveredShotIndexes.has(shot.index)) : false;
  const customSubtitleTemplates = subtitleTemplates.data?.items ?? [];
  const presetSubtitleTemplates = subtitleTemplates.data?.presets ?? [];
  const subtitleTemplateItems = customSubtitleTemplates.concat(presetSubtitleTemplates);
  const automaticSubtitleTemplate = selectAutoSubtitleTemplate(
    customSubtitleTemplates,
    presetSubtitleTemplates,
  );
  const selectedSubtitleTemplate =
    subtitleTemplateItems.find((template) => template.id === subtitleTemplateSetId) ??
    automaticSubtitleTemplate;
  const subtitleTemplateSummary = subtitleTemplateSetId
    ? `基础模板：${selectedSubtitleTemplate?.name ?? "未找到模板"}，渲染时随机使用变体`
    : "自动随机使用模板";

  const findMaterial = (materialId: string): LocalMaterial | undefined =>
    materials.data?.find((material) => material.id === materialId);
  const localSegmentMaterials = (materials.data ?? []).filter(isLocalMaterialLibrarySegment);

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
          <span>{audioOutputMessage}</span>
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
          <select
            disabled={materialSourceMode === "local"}
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
          >
            <option value="auto">Auto</option>
            <option value="pexels">Pexels 素材</option>
            <option value="pixabay">Pixabay 素材</option>
          </select>
        </label>
        <label>
          <span>素材来源模式</span>
          <select
            value={materialSourceMode}
            onChange={(event) => setMaterialSourceMode(event.target.value as MaterialSourceMode)}
          >
            <option value="hybrid">本地优先，线上补足</option>
            <option value="local">只用本地素材库</option>
            <option value="online_free">只用线上免费素材</option>
          </select>
        </label>
        <fieldset className="subtitle-settings">
          <legend>字幕设置</legend>
          <label className="switch-row">
            <input
              checked={subtitleEnabled}
              onChange={(event) => setSubtitleEnabled(event.target.checked)}
              type="checkbox"
            />
            <span>启用字幕</span>
          </label>
          <label>
            <span>字幕模板</span>
            <select
              disabled={!subtitleEnabled || subtitleTemplates.isLoading}
              value={subtitleTemplateSetId}
              onChange={(event) => setSubtitleTemplateSetId(event.target.value)}
            >
              <option value="">自动随机使用模板</option>
              {subtitleTemplateItems.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>字幕字体</span>
            <select
              disabled={!subtitleEnabled}
              value={subtitleFontFamily}
              onChange={(event) => setSubtitleFontFamily(event.target.value)}
            >
              <option value="">跟随字幕模板</option>
              <option value="PingFang SC">PingFang SC</option>
              <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
            </select>
          </label>
          {subtitleEnabled && selectedSubtitleTemplate ? (
            <p className="subtitle-template-summary">
              {subtitleTemplateSummary}
            </p>
          ) : null}
          <button type="button" onClick={onOpenSubtitleTemplates}>
            <Captions aria-hidden="true" size={16} />
            去字幕模板页编辑
          </button>
        </fieldset>
        <VoiceDropdown
          previewText={voicePreviewText}
          value={selectedVoice}
          onChange={setSelectedVoice}
        />
        <BgmSelector
          value={selectedBgm}
          onChange={setSelectedBgm}
          onOpenBgmManagement={onOpenBgmManagement}
        />
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
                    用本地素材覆盖
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
          {localSegmentMaterials.map((material) => (
            <button
              key={material.id}
              type="button"
              onClick={() => selectLocalMaterial(localPickerShot, material.id)}
            >
              选择 <span>{material.original_filename}</span>
            </button>
          ))}
          {materials.isLoading ? <span>正在加载本地素材</span> : null}
          {localSegmentMaterials.length === 0 && !materials.isLoading ? (
            <span>暂无本地素材库片段</span>
          ) : null}
          <button type="button" onClick={() => setLocalPickerShot(null)}>
            关闭
          </button>
        </div>
      ) : null}

      {script ? (
        <div className="create-task-row">
          <button
            className="primary-action"
            disabled={createTask.isPending}
            type="button"
            onClick={() => createTask.mutate()}
          >
            <Sparkles aria-hidden="true" size={18} />
            {createTask.isPending ? "创建中" : "创建任务"}
          </button>
          <span className="selected-material">
            {allShotsCovered
              ? `手动使用 ${selectedCount} 个覆盖素材`
              : `自动使用 ${requiredShotCount} 个镜头${
                  selectedCount > 0 ? `，已手动覆盖 ${selectedCount} 个素材` : ""
                }`}
          </span>
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
