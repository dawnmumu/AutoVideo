import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, RefreshCw, Save, Search, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  clearMaterialLibrary,
  deleteMaterialRawFile,
  fetchMaterialLibrarySummary,
  fetchMaterialRawFiles,
  fetchMaterialSourceStatus,
  readableMaterialError,
  saveMaterialSource,
  startMaterialIndex,
} from "../api/materials";
import type { MaterialIndexJob, MaterialRawFile } from "../api/materials";

const RAW_FILE_LIMIT = 50;

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds?: number | null): string {
  if (!Number.isFinite(seconds ?? NaN) || !seconds) {
    return "未知时长";
  }
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function normalizePath(value: string): string {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : ".";
}

function jobProgressText(job: MaterialIndexJob | null | undefined): string {
  if (!job) {
    return "暂无素材索引任务";
  }
  const current = job.progress?.current ?? job.progress_current ?? 0;
  const total = job.progress?.total ?? job.progress_total ?? 0;
  const progress = total > 0 ? `，进度 ${current}/${total}` : "";
  return `${job.status} / ${job.stage}${progress}`;
}

function rawStatusText(rawFile: MaterialRawFile): string {
  const details = [
    rawFile.orientation ? `方向 ${rawFile.orientation}` : null,
    rawFile.asr_status ? `ASR ${rawFile.asr_status}` : null,
    rawFile.ocr_status ? `OCR ${rawFile.ocr_status}` : null,
    rawFile.vision_status ? `视觉 ${rawFile.vision_status}` : null,
    rawFile.embedding_status ? `向量 ${rawFile.embedding_status}` : null,
  ].filter(Boolean);
  return details.length > 0 ? details.join(" · ") : "暂无扩展状态";
}

export function MaterialLibraryWorkbench() {
  const queryClient = useQueryClient();
  const clearButtonRef = useRef<HTMLButtonElement | null>(null);
  const [allowedRootId, setAllowedRootId] = useState("");
  const [sourceRelativePath, setSourceRelativePath] = useState(".");
  const [expandedRawIds, setExpandedRawIds] = useState<Record<string, boolean>>({});
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  const sourceStatus = useQuery({
    queryKey: ["material-source-status"],
    queryFn: fetchMaterialSourceStatus,
  });
  const summary = useQuery({
    queryKey: ["material-library-summary"],
    queryFn: fetchMaterialLibrarySummary,
  });
  const rawFiles = useQuery({
    queryKey: ["material-raw-files", RAW_FILE_LIMIT, 0],
    queryFn: () => fetchMaterialRawFiles({ limit: RAW_FILE_LIMIT, offset: 0 }),
  });

  const invalidateMaterialQueries = () => {
    void queryClient.invalidateQueries({ queryKey: ["material-source-status"] });
    void queryClient.invalidateQueries({ queryKey: ["material-library-summary"] });
    void queryClient.invalidateQueries({ queryKey: ["material-raw-files"] });
  };

  const saveSource = useMutation({
    mutationFn: () =>
      saveMaterialSource({
        allowed_root_id: allowedRootId,
        source_relative_path: normalizePath(sourceRelativePath),
      }),
    onSuccess: invalidateMaterialQueries,
  });
  const startIndex = useMutation({
    mutationFn: () =>
      startMaterialIndex({
        source_config_id: sourceStatus.data?.current_source?.id ?? summary.data?.current_source?.id ?? null,
        force: true,
      }),
    onSuccess: invalidateMaterialQueries,
  });
  const deleteRaw = useMutation({
    mutationFn: deleteMaterialRawFile,
    onSuccess: (result) => {
      if (result.id) {
        setExpandedRawIds((current) => {
          const next = { ...current };
          delete next[result.id ?? ""];
          return next;
        });
      }
      invalidateMaterialQueries();
    },
  });
  const clearLibrary = useMutation({
    mutationFn: clearMaterialLibrary,
    onSuccess: () => {
      setClearConfirmOpen(false);
      clearButtonRef.current?.focus();
      setExpandedRawIds({});
      invalidateMaterialQueries();
    },
  });

  useEffect(() => {
    const currentSource = sourceStatus.data?.current_source;
    if (!currentSource) {
      const firstRoot = sourceStatus.data?.allowed_roots[0]?.id;
      if (firstRoot) {
        setAllowedRootId((current) => current || firstRoot);
      }
      return;
    }
    setAllowedRootId(currentSource.allowed_root_id);
    setSourceRelativePath(currentSource.source_relative_path || ".");
  }, [sourceStatus.data]);

  const latestJob = sourceStatus.data?.latest_job ?? summary.data?.latest_job ?? null;
  const totals = summary.data?.totals;
  const actionError =
    saveSource.error || startIndex.error || deleteRaw.error || clearLibrary.error || null;
  const rawItems = rawFiles.data?.items ?? [];
  const hasCurrentSource = Boolean(sourceStatus.data?.current_source ?? summary.data?.current_source);
  const isInitialLoading = sourceStatus.isPending || summary.isPending || rawFiles.isPending;

  const closeClearConfirmation = () => {
    setClearConfirmOpen(false);
    clearButtonRef.current?.focus();
  };

  return (
    <article className="panel material-library-panel" aria-label="素材库">
      <div className="panel-heading">
        <div>
          <h2>素材库</h2>
          <span>
            {sourceStatus.data?.current_source
              ? `当前目录：${sourceStatus.data.current_source.source_display_path}`
              : "配置允许根目录下的本地素材子目录"}
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            void sourceStatus.refetch();
            void summary.refetch();
            void rawFiles.refetch();
          }}
        >
          <RefreshCw aria-hidden="true" size={18} />
          刷新
        </button>
      </div>

      {isInitialLoading && (
        <div className="runtime-status" role="status" aria-live="polite">
          正在读取素材库状态
        </div>
      )}
      {(sourceStatus.isError || summary.isError || rawFiles.isError) && (
        <div className="inline-error material-error-text" role="alert">
          {readableMaterialError(sourceStatus.error ?? summary.error ?? rawFiles.error)}
        </div>
      )}
      {actionError && (
        <div className="inline-error material-error-text" role="alert">
          {readableMaterialError(actionError)}
        </div>
      )}

      {!isInitialLoading ? (
        <>
          <section className="material-source-section" aria-label="素材来源配置">
            <form
              className="material-source-form"
              onSubmit={(event) => {
                event.preventDefault();
                saveSource.mutate();
              }}
            >
              <label>
                允许根目录
                <select
                  value={allowedRootId}
                  onChange={(event) => setAllowedRootId(event.target.value)}
                >
                  {(sourceStatus.data?.allowed_roots ?? []).map((root) => (
                    <option key={root.id} value={root.id}>
                      {root.display_name || root.alias}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                子目录
                <input
                  value={sourceRelativePath}
                  onChange={(event) => setSourceRelativePath(event.target.value)}
                  placeholder="例如 clips 或 ."
                />
              </label>
              <button
                className="primary-action"
                disabled={!allowedRootId || saveSource.isPending}
                type="submit"
              >
                <Save aria-hidden="true" size={18} />
                保存来源
              </button>
              <button
                type="button"
                disabled={!hasCurrentSource || startIndex.isPending}
                onClick={() => startIndex.mutate()}
              >
                <Search aria-hidden="true" size={18} />
                开始索引
              </button>
            </form>
          </section>

          <section
            aria-label="素材索引状态"
            aria-live="polite"
            className={`material-job-status ${latestJob?.status ?? "idle"}`}
            role="status"
          >
            <strong>素材索引状态</strong>
            <span>{jobProgressText(latestJob)}</span>
            {latestJob?.counts ? (
              <span>
                原片 {latestJob.counts.raw} · 切片 {latestJob.counts.segments} · 失败{" "}
                {latestJob.counts.failed}
              </span>
            ) : null}
            {latestJob?.error_summary ? (
              <span className="material-error-text">{latestJob.error_summary}</span>
            ) : null}
          </section>

          <section className="material-summary-section" aria-label="素材库统计">
            <div className="material-summary-grid">
              <div>
                <span>原片</span>
                <strong>{totals?.raw ?? 0}</strong>
              </div>
              <div>
                <span>切片</span>
                <strong>{totals?.segments ?? 0}</strong>
              </div>
              <div>
                <span>竖屏</span>
                <strong>{totals?.portrait ?? 0}</strong>
              </div>
              <div>
                <span>横屏</span>
                <strong>{totals?.landscape ?? 0}</strong>
              </div>
              <div>
                <span>失败</span>
                <strong>{totals?.failed ?? 0}</strong>
              </div>
            </div>
          </section>

          <section className="material-raw-list" aria-label="原始素材文件">
            <div className="material-list-heading">
              <h3>原始素材</h3>
              <button
                ref={clearButtonRef}
                className="danger-action"
                type="button"
                onClick={() => setClearConfirmOpen(true)}
              >
                <Trash2 aria-hidden="true" size={18} />
                清空素材库
              </button>
            </div>

            {clearConfirmOpen ? (
              <div
                aria-label="清空素材库确认"
                className="material-confirmation"
                role="dialog"
                aria-modal="false"
              >
                <div>
                  <strong>确认清空素材库？</strong>
                  <p>将删除已索引的原始素材记录和切片记录，本地源文件不会从目录中移除。</p>
                </div>
                <div className="material-confirmation-actions">
                  <button type="button" onClick={closeClearConfirmation}>
                    取消清空
                  </button>
                  <button
                    className="danger-action"
                    disabled={clearLibrary.isPending}
                    type="button"
                    onClick={() => clearLibrary.mutate()}
                  >
                    确认清空
                  </button>
                </div>
              </div>
            ) : null}

            {rawItems.length === 0 ? (
              <div className="empty-state">暂无原始素材。配置来源后启动索引即可生成素材记录。</div>
            ) : (
              rawItems.map((rawFile) => {
                const expanded = Boolean(expandedRawIds[rawFile.id]);
                return (
                  <div className="material-raw-row" key={rawFile.id}>
                    <button
                      aria-expanded={expanded}
                      type="button"
                      onClick={() =>
                        setExpandedRawIds((current) => ({
                          ...current,
                          [rawFile.id]: !current[rawFile.id],
                        }))
                      }
                    >
                      <ChevronDown
                        aria-hidden="true"
                        className={expanded ? "expanded" : ""}
                        size={18}
                      />
                      {expanded ? "收起" : "展开"} {rawFile.filename}
                    </button>
                    <div className="material-raw-main">
                      <strong>{rawFile.filename}</strong>
                      <span className="material-path-text">{rawFile.source_display_path}</span>
                    </div>
                    <span>{rawFile.status}</span>
                    <span>{formatBytes(rawFile.size_bytes)}</span>
                    <span>{formatDuration(rawFile.duration_seconds)}</span>
                    <span>{rawFile.segments} 个切片</span>
                    <button
                      className="danger-action"
                      disabled={deleteRaw.isPending}
                      type="button"
                      onClick={() => deleteRaw.mutate(rawFile.id)}
                    >
                      删除
                    </button>
                    {expanded ? (
                      <div className="material-raw-details">
                        <span>{rawStatusText(rawFile)}</span>
                        {rawFile.error_summary ? (
                          <span className="material-error-text">{rawFile.error_summary}</span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </section>
        </>
      ) : null}
    </article>
  );
}
