import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useMemo } from "react";

import { fetchBgmLibrary, readableBgmError } from "../api/bgm";
import type { BgmCategory, BgmTrack } from "../api/bgm";

export interface SelectedBgm {
  enabled: boolean;
  categoryId: string;
  trackId: string;
  volume: number;
}

interface BgmSelectorProps {
  value: SelectedBgm;
  onChange: (value: SelectedBgm) => void;
  onOpenBgmManagement?: () => void;
}

function trackLabel(track: BgmTrack): string {
  return track.display_name || track.filename;
}

function sortTracksByAutoRule(tracks: BgmTrack[]): BgmTrack[] {
  return [...tracks].sort((left, right) => {
    const leftLabel = trackLabel(left);
    const rightLabel = trackLabel(right);
    if (leftLabel === rightLabel) {
      return 0;
    }
    return leftLabel > rightLabel ? 1 : -1;
  });
}

function selectDefaultCategory(categories: BgmCategory[], tracks: BgmTrack[]): string {
  const categoryWithTracks = categories.find((category) =>
    tracks.some((track) => track.category_id === category.id),
  );
  return categoryWithTracks?.id ?? categories[0]?.id ?? "";
}

export function BgmSelector({ value, onChange, onOpenBgmManagement }: BgmSelectorProps) {
  const library = useQuery({
    queryKey: ["bgm-library"],
    queryFn: fetchBgmLibrary,
  });

  const categories = library.data?.categories ?? [];
  const tracks = library.data?.items ?? [];
  const currentCategory = categories.find((category) => category.id === value.categoryId);
  const defaultCategoryId = useMemo(
    () => selectDefaultCategory(categories, tracks),
    [categories, tracks],
  );
  const currentCategoryTracks = useMemo(
    () =>
      sortTracksByAutoRule(
        tracks.filter((track) => track.category_id === value.categoryId),
      ),
    [tracks, value.categoryId],
  );
  const selectedTrack = currentCategoryTracks.find((track) => track.id === value.trackId) ?? null;
  const previewTrack = selectedTrack ?? currentCategoryTracks[0] ?? null;

  useEffect(() => {
    if (library.isLoading || library.isError || categories.length === 0) {
      return;
    }

    if (!value.categoryId || !currentCategory) {
      onChange({ ...value, categoryId: defaultCategoryId, trackId: "" });
    }
  }, [
    categories.length,
    currentCategory,
    defaultCategoryId,
    library.isError,
    library.isLoading,
    onChange,
    value,
  ]);

  const updateValue = (patch: Partial<SelectedBgm>) => {
    onChange({ ...value, ...patch });
  };

  return (
    <fieldset aria-label="BGM 设置" className="bgm-selector">
      <legend>BGM 设置</legend>

      {library.isLoading ? (
        <div className="runtime-status" role="status" aria-live="polite">
          正在读取 BGM 库
        </div>
      ) : null}

      {library.isError ? (
        <div className="inline-error" role="alert">
          <span>{readableBgmError(library.error)}</span>
          <button type="button" onClick={() => void library.refetch()}>
            <RefreshCw aria-hidden="true" size={16} />
            重试
          </button>
        </div>
      ) : null}

      {!library.isLoading && !library.isError ? (
        <>
          <label className="switch-row">
            <input
              aria-label="启用 BGM"
              checked={value.enabled}
              onChange={(event) => updateValue({ enabled: event.target.checked })}
              type="checkbox"
            />
            <span>启用 BGM</span>
          </label>

          <label>
            <span>BGM 分类</span>
            <select
              aria-label="BGM 分类"
              disabled={!value.enabled || categories.length === 0}
              value={value.categoryId}
              onChange={(event) => updateValue({ categoryId: event.target.value, trackId: "" })}
            >
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>具体 BGM</span>
            <select
              aria-label="具体 BGM"
              disabled={!value.enabled || !value.categoryId}
              value={value.trackId}
              onChange={(event) => updateValue({ trackId: event.target.value })}
            >
              <option value="">从当前分类自动选择</option>
              {currentCategoryTracks.map((track) => (
                <option key={track.id} value={track.id}>
                  {trackLabel(track)}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>BGM 音量</span>
            <input
              aria-label="BGM 音量"
              disabled={!value.enabled}
              max="1"
              min="0"
              onChange={(event) => updateValue({ volume: Number(event.target.value) })}
              step="0.01"
              type="range"
              value={value.volume}
            />
          </label>

          <div className="bgm-selector-preview">
            <div>
              <strong>{previewTrack ? trackLabel(previewTrack) : "暂无可试听 BGM"}</strong>
              <span>{currentCategory?.name ?? "未选择分类"}</span>
            </div>
            <button type="button" onClick={onOpenBgmManagement}>
              去 BGM 管理页
            </button>
          </div>

          {value.enabled && previewTrack ? (
            <audio
              aria-label="BGM 试听音频"
              className="bgm-selector-audio"
              controls
              src={previewTrack.audio_url}
            />
          ) : null}
        </>
      ) : null}
    </fieldset>
  );
}
