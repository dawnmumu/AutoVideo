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

// Generated from Python 3.12 str.casefold vs current JS toLowerCase differences; keeps frontend preview aligned with backend selection key.
const PYTHON_CASEFOLD_OVERRIDES: Record<string, string> = {
  "\u00b5": "\u03bc",
  "\u00df": "ss",
  "\u0149": "\u02bcn",
  "\u017f": "s",
  "\u01f0": "j\u030c",
  "\u0345": "\u03b9",
  "\u0390": "\u03b9\u0308\u0301",
  "\u03b0": "\u03c5\u0308\u0301",
  "\u03c2": "\u03c3",
  "\u03d0": "\u03b2",
  "\u03d1": "\u03b8",
  "\u03d5": "\u03c6",
  "\u03d6": "\u03c0",
  "\u03f0": "\u03ba",
  "\u03f1": "\u03c1",
  "\u03f5": "\u03b5",
  "\u0587": "\u0565\u0582",
  "\u13a0": "\u13a0",
  "\u13a1": "\u13a1",
  "\u13a2": "\u13a2",
  "\u13a3": "\u13a3",
  "\u13a4": "\u13a4",
  "\u13a5": "\u13a5",
  "\u13a6": "\u13a6",
  "\u13a7": "\u13a7",
  "\u13a8": "\u13a8",
  "\u13a9": "\u13a9",
  "\u13aa": "\u13aa",
  "\u13ab": "\u13ab",
  "\u13ac": "\u13ac",
  "\u13ad": "\u13ad",
  "\u13ae": "\u13ae",
  "\u13af": "\u13af",
  "\u13b0": "\u13b0",
  "\u13b1": "\u13b1",
  "\u13b2": "\u13b2",
  "\u13b3": "\u13b3",
  "\u13b4": "\u13b4",
  "\u13b5": "\u13b5",
  "\u13b6": "\u13b6",
  "\u13b7": "\u13b7",
  "\u13b8": "\u13b8",
  "\u13b9": "\u13b9",
  "\u13ba": "\u13ba",
  "\u13bb": "\u13bb",
  "\u13bc": "\u13bc",
  "\u13bd": "\u13bd",
  "\u13be": "\u13be",
  "\u13bf": "\u13bf",
  "\u13c0": "\u13c0",
  "\u13c1": "\u13c1",
  "\u13c2": "\u13c2",
  "\u13c3": "\u13c3",
  "\u13c4": "\u13c4",
  "\u13c5": "\u13c5",
  "\u13c6": "\u13c6",
  "\u13c7": "\u13c7",
  "\u13c8": "\u13c8",
  "\u13c9": "\u13c9",
  "\u13ca": "\u13ca",
  "\u13cb": "\u13cb",
  "\u13cc": "\u13cc",
  "\u13cd": "\u13cd",
  "\u13ce": "\u13ce",
  "\u13cf": "\u13cf",
  "\u13d0": "\u13d0",
  "\u13d1": "\u13d1",
  "\u13d2": "\u13d2",
  "\u13d3": "\u13d3",
  "\u13d4": "\u13d4",
  "\u13d5": "\u13d5",
  "\u13d6": "\u13d6",
  "\u13d7": "\u13d7",
  "\u13d8": "\u13d8",
  "\u13d9": "\u13d9",
  "\u13da": "\u13da",
  "\u13db": "\u13db",
  "\u13dc": "\u13dc",
  "\u13dd": "\u13dd",
  "\u13de": "\u13de",
  "\u13df": "\u13df",
  "\u13e0": "\u13e0",
  "\u13e1": "\u13e1",
  "\u13e2": "\u13e2",
  "\u13e3": "\u13e3",
  "\u13e4": "\u13e4",
  "\u13e5": "\u13e5",
  "\u13e6": "\u13e6",
  "\u13e7": "\u13e7",
  "\u13e8": "\u13e8",
  "\u13e9": "\u13e9",
  "\u13ea": "\u13ea",
  "\u13eb": "\u13eb",
  "\u13ec": "\u13ec",
  "\u13ed": "\u13ed",
  "\u13ee": "\u13ee",
  "\u13ef": "\u13ef",
  "\u13f0": "\u13f0",
  "\u13f1": "\u13f1",
  "\u13f2": "\u13f2",
  "\u13f3": "\u13f3",
  "\u13f4": "\u13f4",
  "\u13f5": "\u13f5",
  "\u13f8": "\u13f0",
  "\u13f9": "\u13f1",
  "\u13fa": "\u13f2",
  "\u13fb": "\u13f3",
  "\u13fc": "\u13f4",
  "\u13fd": "\u13f5",
  "\u1c80": "\u0432",
  "\u1c81": "\u0434",
  "\u1c82": "\u043e",
  "\u1c83": "\u0441",
  "\u1c84": "\u0442",
  "\u1c85": "\u0442",
  "\u1c86": "\u044a",
  "\u1c87": "\u0463",
  "\u1c88": "\ua64b",
  "\u1c89": "\u1c89",
  "\u1e96": "h\u0331",
  "\u1e97": "t\u0308",
  "\u1e98": "w\u030a",
  "\u1e99": "y\u030a",
  "\u1e9a": "a\u02be",
  "\u1e9b": "\u1e61",
  "\u1e9e": "ss",
  "\u1f50": "\u03c5\u0313",
  "\u1f52": "\u03c5\u0313\u0300",
  "\u1f54": "\u03c5\u0313\u0301",
  "\u1f56": "\u03c5\u0313\u0342",
  "\u1f80": "\u1f00\u03b9",
  "\u1f81": "\u1f01\u03b9",
  "\u1f82": "\u1f02\u03b9",
  "\u1f83": "\u1f03\u03b9",
  "\u1f84": "\u1f04\u03b9",
  "\u1f85": "\u1f05\u03b9",
  "\u1f86": "\u1f06\u03b9",
  "\u1f87": "\u1f07\u03b9",
  "\u1f88": "\u1f00\u03b9",
  "\u1f89": "\u1f01\u03b9",
  "\u1f8a": "\u1f02\u03b9",
  "\u1f8b": "\u1f03\u03b9",
  "\u1f8c": "\u1f04\u03b9",
  "\u1f8d": "\u1f05\u03b9",
  "\u1f8e": "\u1f06\u03b9",
  "\u1f8f": "\u1f07\u03b9",
  "\u1f90": "\u1f20\u03b9",
  "\u1f91": "\u1f21\u03b9",
  "\u1f92": "\u1f22\u03b9",
  "\u1f93": "\u1f23\u03b9",
  "\u1f94": "\u1f24\u03b9",
  "\u1f95": "\u1f25\u03b9",
  "\u1f96": "\u1f26\u03b9",
  "\u1f97": "\u1f27\u03b9",
  "\u1f98": "\u1f20\u03b9",
  "\u1f99": "\u1f21\u03b9",
  "\u1f9a": "\u1f22\u03b9",
  "\u1f9b": "\u1f23\u03b9",
  "\u1f9c": "\u1f24\u03b9",
  "\u1f9d": "\u1f25\u03b9",
  "\u1f9e": "\u1f26\u03b9",
  "\u1f9f": "\u1f27\u03b9",
  "\u1fa0": "\u1f60\u03b9",
  "\u1fa1": "\u1f61\u03b9",
  "\u1fa2": "\u1f62\u03b9",
  "\u1fa3": "\u1f63\u03b9",
  "\u1fa4": "\u1f64\u03b9",
  "\u1fa5": "\u1f65\u03b9",
  "\u1fa6": "\u1f66\u03b9",
  "\u1fa7": "\u1f67\u03b9",
  "\u1fa8": "\u1f60\u03b9",
  "\u1fa9": "\u1f61\u03b9",
  "\u1faa": "\u1f62\u03b9",
  "\u1fab": "\u1f63\u03b9",
  "\u1fac": "\u1f64\u03b9",
  "\u1fad": "\u1f65\u03b9",
  "\u1fae": "\u1f66\u03b9",
  "\u1faf": "\u1f67\u03b9",
  "\u1fb2": "\u1f70\u03b9",
  "\u1fb3": "\u03b1\u03b9",
  "\u1fb4": "\u03ac\u03b9",
  "\u1fb6": "\u03b1\u0342",
  "\u1fb7": "\u03b1\u0342\u03b9",
  "\u1fbc": "\u03b1\u03b9",
  "\u1fbe": "\u03b9",
  "\u1fc2": "\u1f74\u03b9",
  "\u1fc3": "\u03b7\u03b9",
  "\u1fc4": "\u03ae\u03b9",
  "\u1fc6": "\u03b7\u0342",
  "\u1fc7": "\u03b7\u0342\u03b9",
  "\u1fcc": "\u03b7\u03b9",
  "\u1fd2": "\u03b9\u0308\u0300",
  "\u1fd3": "\u03b9\u0308\u0301",
  "\u1fd6": "\u03b9\u0342",
  "\u1fd7": "\u03b9\u0308\u0342",
  "\u1fe2": "\u03c5\u0308\u0300",
  "\u1fe3": "\u03c5\u0308\u0301",
  "\u1fe4": "\u03c1\u0313",
  "\u1fe6": "\u03c5\u0342",
  "\u1fe7": "\u03c5\u0308\u0342",
  "\u1ff2": "\u1f7c\u03b9",
  "\u1ff3": "\u03c9\u03b9",
  "\u1ff4": "\u03ce\u03b9",
  "\u1ff6": "\u03c9\u0342",
  "\u1ff7": "\u03c9\u0342\u03b9",
  "\u1ffc": "\u03c9\u03b9",
  "\ua7cb": "\ua7cb",
  "\ua7cc": "\ua7cc",
  "\ua7ce": "\ua7ce",
  "\ua7d2": "\ua7d2",
  "\ua7d4": "\ua7d4",
  "\ua7da": "\ua7da",
  "\ua7dc": "\ua7dc",
  "\uab70": "\u13a0",
  "\uab71": "\u13a1",
  "\uab72": "\u13a2",
  "\uab73": "\u13a3",
  "\uab74": "\u13a4",
  "\uab75": "\u13a5",
  "\uab76": "\u13a6",
  "\uab77": "\u13a7",
  "\uab78": "\u13a8",
  "\uab79": "\u13a9",
  "\uab7a": "\u13aa",
  "\uab7b": "\u13ab",
  "\uab7c": "\u13ac",
  "\uab7d": "\u13ad",
  "\uab7e": "\u13ae",
  "\uab7f": "\u13af",
  "\uab80": "\u13b0",
  "\uab81": "\u13b1",
  "\uab82": "\u13b2",
  "\uab83": "\u13b3",
  "\uab84": "\u13b4",
  "\uab85": "\u13b5",
  "\uab86": "\u13b6",
  "\uab87": "\u13b7",
  "\uab88": "\u13b8",
  "\uab89": "\u13b9",
  "\uab8a": "\u13ba",
  "\uab8b": "\u13bb",
  "\uab8c": "\u13bc",
  "\uab8d": "\u13bd",
  "\uab8e": "\u13be",
  "\uab8f": "\u13bf",
  "\uab90": "\u13c0",
  "\uab91": "\u13c1",
  "\uab92": "\u13c2",
  "\uab93": "\u13c3",
  "\uab94": "\u13c4",
  "\uab95": "\u13c5",
  "\uab96": "\u13c6",
  "\uab97": "\u13c7",
  "\uab98": "\u13c8",
  "\uab99": "\u13c9",
  "\uab9a": "\u13ca",
  "\uab9b": "\u13cb",
  "\uab9c": "\u13cc",
  "\uab9d": "\u13cd",
  "\uab9e": "\u13ce",
  "\uab9f": "\u13cf",
  "\uaba0": "\u13d0",
  "\uaba1": "\u13d1",
  "\uaba2": "\u13d2",
  "\uaba3": "\u13d3",
  "\uaba4": "\u13d4",
  "\uaba5": "\u13d5",
  "\uaba6": "\u13d6",
  "\uaba7": "\u13d7",
  "\uaba8": "\u13d8",
  "\uaba9": "\u13d9",
  "\uabaa": "\u13da",
  "\uabab": "\u13db",
  "\uabac": "\u13dc",
  "\uabad": "\u13dd",
  "\uabae": "\u13de",
  "\uabaf": "\u13df",
  "\uabb0": "\u13e0",
  "\uabb1": "\u13e1",
  "\uabb2": "\u13e2",
  "\uabb3": "\u13e3",
  "\uabb4": "\u13e4",
  "\uabb5": "\u13e5",
  "\uabb6": "\u13e6",
  "\uabb7": "\u13e7",
  "\uabb8": "\u13e8",
  "\uabb9": "\u13e9",
  "\uabba": "\u13ea",
  "\uabbb": "\u13eb",
  "\uabbc": "\u13ec",
  "\uabbd": "\u13ed",
  "\uabbe": "\u13ee",
  "\uabbf": "\u13ef",
  "\ufb00": "ff",
  "\ufb01": "fi",
  "\ufb02": "fl",
  "\ufb03": "ffi",
  "\ufb04": "ffl",
  "\ufb05": "st",
  "\ufb06": "st",
  "\ufb13": "\u0574\u0576",
  "\ufb14": "\u0574\u0565",
  "\ufb15": "\u0574\u056b",
  "\ufb16": "\u057e\u0576",
  "\ufb17": "\u0574\u056d",
  "\u{10d50}": "\u{10d50}",
  "\u{10d51}": "\u{10d51}",
  "\u{10d52}": "\u{10d52}",
  "\u{10d53}": "\u{10d53}",
  "\u{10d54}": "\u{10d54}",
  "\u{10d55}": "\u{10d55}",
  "\u{10d56}": "\u{10d56}",
  "\u{10d57}": "\u{10d57}",
  "\u{10d58}": "\u{10d58}",
  "\u{10d59}": "\u{10d59}",
  "\u{10d5a}": "\u{10d5a}",
  "\u{10d5b}": "\u{10d5b}",
  "\u{10d5c}": "\u{10d5c}",
  "\u{10d5d}": "\u{10d5d}",
  "\u{10d5e}": "\u{10d5e}",
  "\u{10d5f}": "\u{10d5f}",
  "\u{10d60}": "\u{10d60}",
  "\u{10d61}": "\u{10d61}",
  "\u{10d62}": "\u{10d62}",
  "\u{10d63}": "\u{10d63}",
  "\u{10d64}": "\u{10d64}",
  "\u{10d65}": "\u{10d65}",
  "\u{16ea0}": "\u{16ea0}",
  "\u{16ea1}": "\u{16ea1}",
  "\u{16ea2}": "\u{16ea2}",
  "\u{16ea3}": "\u{16ea3}",
  "\u{16ea4}": "\u{16ea4}",
  "\u{16ea5}": "\u{16ea5}",
  "\u{16ea6}": "\u{16ea6}",
  "\u{16ea7}": "\u{16ea7}",
  "\u{16ea8}": "\u{16ea8}",
  "\u{16ea9}": "\u{16ea9}",
  "\u{16eaa}": "\u{16eaa}",
  "\u{16eab}": "\u{16eab}",
  "\u{16eac}": "\u{16eac}",
  "\u{16ead}": "\u{16ead}",
  "\u{16eae}": "\u{16eae}",
  "\u{16eaf}": "\u{16eaf}",
  "\u{16eb0}": "\u{16eb0}",
  "\u{16eb1}": "\u{16eb1}",
  "\u{16eb2}": "\u{16eb2}",
  "\u{16eb3}": "\u{16eb3}",
  "\u{16eb4}": "\u{16eb4}",
  "\u{16eb5}": "\u{16eb5}",
  "\u{16eb6}": "\u{16eb6}",
  "\u{16eb7}": "\u{16eb7}",
  "\u{16eb8}": "\u{16eb8}",
};

function casefoldForBgmSort(value: string | null | undefined): string {
  return Array.from(value || "")
    .map((char) => PYTHON_CASEFOLD_OVERRIDES[char] ?? char.toLowerCase())
    .join("");
}

function sortTracksByAutoRule(tracks: BgmTrack[]): BgmTrack[] {
  return [...tracks].sort((left, right) => {
    const leftKey = [
      casefoldForBgmSort(left.display_name || left.filename),
      casefoldForBgmSort(left.filename),
      left.id || "",
    ];
    const rightKey = [
      casefoldForBgmSort(right.display_name || right.filename),
      casefoldForBgmSort(right.filename),
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
