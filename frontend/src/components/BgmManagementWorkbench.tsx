import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import {
  createBgmCategory,
  deleteBgmCategory,
  deleteBgmTrack,
  fetchBgmLibrary,
  readableBgmError,
  updateBgmCategory,
  updateBgmTrack,
  uploadBgmTrack,
} from "../api/bgm";

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

function formatDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function BgmManagementWorkbench() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadCategoryId, setUploadCategoryId] = useState("");
  const [newCategoryName, setNewCategoryName] = useState("");

  const library = useQuery({
    queryKey: ["bgm-library"],
    queryFn: fetchBgmLibrary,
  });
  const invalidateLibrary = () => queryClient.invalidateQueries({ queryKey: ["bgm-library"] });

  const upload = useMutation({
    mutationFn: () => {
      if (!selectedFile) {
        throw new Error("请选择 BGM 文件");
      }
      return uploadBgmTrack({ file: selectedFile, category_id: uploadCategoryId || null });
    },
    onSuccess: () => {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      void invalidateLibrary();
    },
  });
  const createCategory = useMutation({
    mutationFn: () => createBgmCategory({ name: newCategoryName.trim() }),
    onSuccess: () => {
      setNewCategoryName("");
      void invalidateLibrary();
    },
  });
  const saveTrack = useMutation({
    mutationFn: updateBgmTrack,
    onSuccess: invalidateLibrary,
  });
  const removeTrack = useMutation({
    mutationFn: deleteBgmTrack,
    onSuccess: invalidateLibrary,
  });
  const saveCategory = useMutation({
    mutationFn: updateBgmCategory,
    onSuccess: invalidateLibrary,
  });
  const removeCategory = useMutation({
    mutationFn: deleteBgmCategory,
    onSuccess: invalidateLibrary,
  });

  const categories = library.data?.categories ?? [];
  const tracks = library.data?.items ?? [];
  const actionError =
    upload.error ||
    createCategory.error ||
    saveTrack.error ||
    removeTrack.error ||
    saveCategory.error ||
    removeCategory.error ||
    null;

  return (
    <article className="panel bgm-management-panel" aria-label="BGM 管理">
      <div className="panel-heading">
        <div>
          <h2>BGM 管理</h2>
          <span>
            {library.data
              ? `共 ${library.data.total_tracks} 条 BGM，支持 ${library.data.supported_extensions.join(", ")}`
              : "读取 BGM 列表"}
          </span>
        </div>
        <button type="button" onClick={() => void library.refetch()}>
          <RefreshCw aria-hidden="true" size={18} />
          刷新
        </button>
      </div>

      {library.isLoading ? (
        <div className="runtime-status" role="status" aria-live="polite">
          正在读取 BGM 列表
        </div>
      ) : null}
      {library.isError ? (
        <div className="inline-error" role="alert">
          <span>{readableBgmError(library.error)}</span>
          <button type="button" onClick={() => void library.refetch()}>
            <RefreshCw aria-hidden="true" size={18} />
            重试
          </button>
        </div>
      ) : null}
      {actionError ? (
        <div className="inline-error" role="alert">
          {readableBgmError(actionError)}
        </div>
      ) : null}

      <div className="bgm-workbench-grid">
        <section className="bgm-upload-panel" aria-label="上传 BGM">
          <h3>上传 BGM</h3>
          <label>
            BGM 音频文件
            <input
              ref={fileInputRef}
              accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*"
              aria-label="BGM 音频文件"
              type="file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label>
            上传分类
            <select
              value={uploadCategoryId}
              onChange={(event) => setUploadCategoryId(event.target.value)}
            >
              <option value="">未分类</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary-action"
            disabled={!selectedFile || upload.isPending}
            type="button"
            onClick={() => upload.mutate()}
          >
            {upload.isPending ? (
              <RefreshCw aria-hidden="true" size={18} />
            ) : (
              <Upload aria-hidden="true" size={18} />
            )}
            {upload.isPending ? "上传中" : "上传 BGM"}
          </button>
        </section>

        <section className="bgm-category-panel" aria-label="BGM 分类">
          <h3>BGM 分类</h3>
          <div className="bgm-inline-form">
            <label>
              新分类名
              <input
                value={newCategoryName}
                onChange={(event) => setNewCategoryName(event.target.value)}
              />
            </label>
            <button
              disabled={!newCategoryName.trim() || createCategory.isPending}
              type="button"
              onClick={() => createCategory.mutate()}
            >
              <Plus aria-hidden="true" size={18} />
              新增分类
            </button>
          </div>
          {categories.length === 0 ? (
            <div className="empty-state">
              <strong>还没有分类</strong>
              <span>新建分类后可在上传和曲目编辑中选择</span>
            </div>
          ) : null}
          {categories.map((category) => (
            <div className="bgm-category-row" key={category.id}>
              <label>
                分类名
                <input
                  aria-label={`${category.name} 分类名`}
                  defaultValue={category.name}
                  onBlur={(event) => {
                    const name = event.currentTarget.value.trim();
                    if (name && name !== category.name) {
                      saveCategory.mutate({ id: category.id, name });
                    }
                  }}
                />
              </label>
              <span>{category.track_count} 条</span>
              <button
                aria-label={`删除分类 ${category.name}`}
                type="button"
                onClick={() => {
                  if (window.confirm("确定删除这个 BGM 分类吗？分类下的 BGM 会移动到未分类。")) {
                    removeCategory.mutate(category.id);
                  }
                }}
              >
                <Trash2 aria-hidden="true" size={18} />
                删除
              </button>
            </div>
          ))}
        </section>

        <section className="bgm-list-panel" aria-label="BGM 列表">
          <h3>BGM 列表</h3>
          {tracks.length === 0 ? (
            <div className="empty-state">
              <strong>还没有 BGM</strong>
              <span>上传音频后可在这里试听、改名和归类</span>
            </div>
          ) : null}
          {tracks.map((track) => (
            <article className="bgm-track-row" key={track.id} aria-label={track.display_name}>
              <div className="bgm-track-main">
                <strong>{track.display_name}</strong>
                <span>
                  {track.original_filename} · {formatBytes(track.size_bytes)} ·{" "}
                  {formatDuration(track.duration_seconds)}
                </span>
                <span>{track.category_name}</span>
              </div>
              <audio
                aria-label={`试听 ${track.display_name}`}
                className="bgm-audio-player"
                controls
                preload="none"
                src={track.audio_url}
              />
              <label>
                BGM 名称
                <input
                  defaultValue={track.display_name}
                  onBlur={(event) => {
                    const displayName = event.currentTarget.value.trim();
                    if (displayName && displayName !== track.display_name) {
                      saveTrack.mutate({ id: track.id, display_name: displayName });
                    }
                  }}
                />
              </label>
              <label>
                分类
                <select
                  value={track.category_id ?? ""}
                  onChange={(event) =>
                    saveTrack.mutate({
                      id: track.id,
                      display_name: track.display_name,
                      category_id: event.target.value || null,
                    })
                  }
                >
                  <option value="">未分类</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                aria-label={`删除 BGM ${track.display_name}`}
                type="button"
                onClick={() => {
                  if (window.confirm(`确定删除 BGM “${track.display_name}”吗？`)) {
                    removeTrack.mutate(track.id);
                  }
                }}
              >
                <Trash2 aria-hidden="true" size={18} />
                删除
              </button>
            </article>
          ))}
        </section>
      </div>
    </article>
  );
}
