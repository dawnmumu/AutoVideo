import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useMemo } from "react";

import { fetchBgmLibrary, readableBgmError } from "../api/bgm";
import type { BgmCategory, BgmTrack } from "../api/bgm";

const UNCLASSIFIED_CATEGORY_VALUE = "__unclassified__";

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

function normalizedSortValue(value: string | null | undefined): string {
  return (value || "").toLowerCase();
}

function sortTracksByAutoRule(tracks: BgmTrack[]): BgmTrack[] {
  return [...tracks].sort((left, right) => {
    const leftKey = [
      normalizedSortValue(left.display_name || left.filename),
      normalizedSortValue(left.filename),
      left.id || "",
    ];
    const rightKey = [
      normalizedSortValue(right.display_name || right.filename),
      normalizedSortValue(right.filename),
      right.id || "",
    ];

    for (const [index, leftValue] of leftKey.entries()) {
      const rightValue = rightKey[index];
      if (leftValue < rightValue) {
        return -1;
      }
      if (leftValue > rightValue) {
        return 1;
      }
    }

    return 0;
  });
}

function selectDefaultCategory(categories: BgmCategory[], tracks: BgmTrack[]): string {
  const categoryWithTracks = categories.find((category) =>
    tracks.some((track) => track.category_id === category.id),
  );
  return categoryWithTracks?.id ?? categories[0]?.id ?? "";
}

function sameSelectedBgm(left: SelectedBgm, right: SelectedBgm): boolean {
  return (
    left.enabled === right.enabled &&
    left.categoryId === right.categoryId &&
    left.trackId === right.trackId &&
    left.volume === right.volume
  );
}

export function BgmSelector({ value, onChange, onOpenBgmManagement }: BgmSelectorProps) {
  const library = useQuery({
    queryKey: ["bgm-library"],
    queryFn: fetchBgmLibrary,
  });

  const categories = library.data?.categories ?? [];
  const tracks = library.data?.items ?? [];
  const unclassifiedTracks = useMemo(
    () => sortTracksByAutoRule(tracks.filter((track) => track.category_id === null)),
    [tracks],
  );
  const selectedUnclassifiedTrack = unclassifiedTracks.find(
    (track) => track.id === value.trackId,
  );
  const isUnclassifiedSelected = !value.categoryId && Boolean(selectedUnclassifiedTrack);
  const selectedCategoryValue = isUnclassifiedSelected
    ? UNCLASSIFIED_CATEGORY_VALUE
    : value.categoryId;
  const currentCategory = categories.find((category) => category.id === value.categoryId);
  const defaultCategoryId = useMemo(
    () => selectDefaultCategory(categories, tracks),
    [categories, tracks],
  );
  const currentCategoryTracks = useMemo(
    () => {
      if (isUnclassifiedSelected) {
        return unclassifiedTracks;
      }
      return sortTracksByAutoRule(
        tracks.filter((track) => track.category_id === value.categoryId),
      );
    },
    [isUnclassifiedSelected, tracks, unclassifiedTracks, value.categoryId],
  );
  const selectedTrack = currentCategoryTracks.find((track) => track.id === value.trackId) ?? null;
  const previewTrack =
    selectedTrack ?? (isUnclassifiedSelected ? null : currentCategoryTracks[0]) ?? null;
  const hasUnclassifiedTracks = unclassifiedTracks.length > 0;

  useEffect(() => {
    if (library.isLoading || library.isError) {
      return;
    }

    let nextValue = value;
    const validExplicitTrack = value.trackId
      ? currentCategoryTracks.some((track) => track.id === value.trackId)
      : true;

    if (value.categoryId) {
      if (!currentCategory) {
        if (defaultCategoryId) {
          nextValue = { ...value, categoryId: defaultCategoryId, trackId: "" };
        } else if (hasUnclassifiedTracks) {
          nextValue = { ...value, categoryId: "", trackId: unclassifiedTracks[0].id };
        } else {
          nextValue = { ...value, categoryId: "", trackId: "" };
        }
      } else if (!validExplicitTrack) {
        nextValue = { ...value, trackId: "" };
      }
    } else if (value.trackId) {
      if (!selectedUnclassifiedTrack) {
        if (defaultCategoryId) {
          nextValue = { ...value, categoryId: defaultCategoryId, trackId: "" };
        } else if (hasUnclassifiedTracks) {
          nextValue = { ...value, categoryId: "", trackId: unclassifiedTracks[0].id };
        } else {
          nextValue = { ...value, categoryId: "", trackId: "" };
        }
      }
    } else if (defaultCategoryId) {
      nextValue = { ...value, categoryId: defaultCategoryId, trackId: "" };
    } else if (hasUnclassifiedTracks) {
      nextValue = { ...value, categoryId: "", trackId: unclassifiedTracks[0].id };
    }

    if (!sameSelectedBgm(value, nextValue)) {
      onChange(nextValue);
    }
  }, [
    currentCategory,
    currentCategoryTracks,
    defaultCategoryId,
    hasUnclassifiedTracks,
    library.isError,
    library.isLoading,
    onChange,
    selectedUnclassifiedTrack,
    unclassifiedTracks,
    value,
  ]);

  const updateValue = (patch: Partial<SelectedBgm>) => {
    onChange({ ...value, ...patch });
  };
  const handleCategoryChange = (nextCategoryValue: string) => {
    if (nextCategoryValue === UNCLASSIFIED_CATEGORY_VALUE) {
      updateValue({ categoryId: "", trackId: unclassifiedTracks[0]?.id ?? "" });
      return;
    }

    updateValue({ categoryId: nextCategoryValue, trackId: "" });
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
              disabled={!value.enabled || (categories.length === 0 && !hasUnclassifiedTracks)}
              value={selectedCategoryValue}
              onChange={(event) => handleCategoryChange(event.target.value)}
            >
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
              {hasUnclassifiedTracks ? (
                <option value={UNCLASSIFIED_CATEGORY_VALUE}>未分类</option>
              ) : null}
            </select>
          </label>

          <label>
            <span>具体 BGM</span>
            <select
              aria-label="具体 BGM"
              disabled={
                !value.enabled || !selectedCategoryValue || currentCategoryTracks.length === 0
              }
              value={value.trackId}
              onChange={(event) => updateValue({ trackId: event.target.value })}
            >
              {!isUnclassifiedSelected ? <option value="">从当前分类自动选择</option> : null}
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
              <span>{isUnclassifiedSelected ? "未分类" : currentCategory?.name ?? "未选择分类"}</span>
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
