import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, RefreshCw, Search, Volume2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  createVoicePreview,
  fetchVoiceStatus,
  fetchVoices,
} from "../api/voices";
import type { CreateVoicePreviewInput, VoiceItem } from "../api/voices";
import { readableVoiceError, selectDefaultVoice, voiceTags } from "./VoiceSelector";

const LOCALE_OPTIONS = [
  { value: "zh-CN", label: "中文" },
  { value: "en-US", label: "英语" },
  { value: "ja-JP", label: "日语" },
  { value: "ko-KR", label: "韩语" },
];

interface VoiceDropdownProps {
  previewText: string;
  value: VoiceItem | null;
  onChange: (voice: VoiceItem | null) => void;
}

function voiceSelectLabel(voice: VoiceItem): string {
  const voiceName = voice.id
    .split("-")
    .slice(2)
    .join("-")
    .replace(/Neural$/, "");
  return [voiceName || voice.name, voice.locale, voice.gender].filter(Boolean).join(" · ");
}

export function VoiceDropdown({ previewText, value, onChange }: VoiceDropdownProps) {
  const [locale, setLocale] = useState("zh-CN");
  const [query, setQuery] = useState("");
  const provisionalVoiceIdRef = useRef<string | null>(null);

  const status = useQuery({
    queryKey: ["voice-status"],
    queryFn: fetchVoiceStatus,
  });
  const voices = useQuery({
    queryKey: ["voices", locale, query],
    queryFn: () => fetchVoices({ locale, q: query }),
  });
  const preview = useMutation({
    mutationFn: (input: CreateVoicePreviewInput) => createVoicePreview(input),
  });

  const voiceItems = useMemo(() => voices.data?.items ?? [], [voices.data?.items]);
  const statusReady = status.isSuccess || status.isError;
  const maxPreviewTextChars = status.data?.edge_tts.max_preview_text_chars ?? 300;
  const selectedVoiceId = value?.id ?? "";
  const selectedVoice = value
    ? voiceItems.find((voice) => voice.id === value.id) ?? value
    : null;
  const selectableVoiceItems =
    selectedVoice && !voiceItems.some((voice) => voice.id === selectedVoice.id)
      ? [selectedVoice, ...voiceItems]
      : voiceItems;
  const isVoiceLoading = voices.isLoading || !statusReady;
  const isVoiceUnavailable = voices.isError || voiceItems.length === 0;

  useEffect(() => {
    if (value || voices.isLoading || voices.isError || statusReady) {
      return;
    }

    const fallbackVoice = voiceItems[0] ?? null;
    if (fallbackVoice) {
      provisionalVoiceIdRef.current = fallbackVoice.id;
      onChange(fallbackVoice);
    }
  }, [onChange, statusReady, value, voiceItems, voices.isError, voices.isLoading]);

  useEffect(() => {
    if (voices.isLoading || voices.isError || !statusReady) {
      return;
    }

    const hasProvisionalVoice =
      Boolean(provisionalVoiceIdRef.current) && value?.id === provisionalVoiceIdRef.current;
    if (value && !hasProvisionalVoice) {
      return;
    }

    const nextVoice = selectDefaultVoice(
      voiceItems,
      status.data?.edge_tts.default_voice,
      value?.id ?? null,
      { preserveCurrentVoice: false },
    );

    if (nextVoice) {
      provisionalVoiceIdRef.current = null;
      onChange(nextVoice);
    }
  }, [
    onChange,
    status.data?.edge_tts.default_voice,
    statusReady,
    value,
    voiceItems,
    voices.isError,
    voices.isLoading,
  ]);

  useEffect(() => {
    preview.reset();
  }, [previewText, selectedVoiceId]);

  const canCreatePreview =
    statusReady && Boolean(selectedVoiceId) && previewText.trim().length > 0 && !preview.isPending;
  const hasCurrentPreviewAudio = Boolean(
    preview.data &&
      preview.variables?.text === previewText &&
      preview.variables.voice_id === selectedVoiceId,
  );

  return (
    <fieldset className="voice-dropdown">
      <legend>旁白音色</legend>
      <div className="voice-selector-filters voice-dropdown-filters">
        <label>
          音色语言
          <select
            disabled={isVoiceLoading}
            value={locale}
            onChange={(event) => setLocale(event.target.value)}
          >
            {LOCALE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          搜索音色
          <span className="voice-search-input">
            <Search aria-hidden="true" size={18} />
            <input
              disabled={isVoiceLoading}
              placeholder="Xiaoxiao"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                }
              }}
            />
          </span>
        </label>
      </div>
      <label>
        <span>旁白音色</span>
        <select
          disabled={isVoiceLoading || isVoiceUnavailable}
          value={selectedVoiceId}
          onChange={(event) => {
            const nextVoice = voiceItems.find((voice) => voice.id === event.target.value) ?? null;
            onChange(nextVoice);
          }}
        >
          {isVoiceLoading ? <option value="">正在读取音色</option> : null}
          {!isVoiceLoading && voiceItems.length === 0 ? <option value="">暂无音色</option> : null}
          {selectableVoiceItems.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voiceSelectLabel(voice)}
            </option>
          ))}
        </select>
      </label>

      {isVoiceLoading ? (
        <div
          aria-label="旁白音色状态"
          aria-live="polite"
          className="runtime-status"
          role="status"
        >
          {voices.isLoading ? "正在读取音色" : "正在读取音色状态"}
        </div>
      ) : null}

      {voices.isError ? (
        <div className="inline-error" role="alert">
          <span>{readableVoiceError(voices.error, maxPreviewTextChars)}</span>
          <button type="button" onClick={() => void voices.refetch()}>
            <RefreshCw aria-hidden="true" size={18} />
            重试
          </button>
        </div>
      ) : null}

      {selectedVoice ? (
        <div className="voice-selected-summary">
          <Volume2 aria-hidden="true" size={22} />
          <div>
            <strong>{selectedVoice.name}</strong>
            <span>{voiceTags(selectedVoice)}</span>
          </div>
        </div>
      ) : null}

      <div className="voice-preview-actions">
        <button
          className="primary-action"
          disabled={!canCreatePreview}
          type="button"
          onClick={() =>
            preview.mutate({
              text: previewText,
              voice_id: selectedVoiceId,
              rate: "+0%",
              volume: "+0%",
              pitch: "+0Hz",
            })
          }
        >
          {preview.isPending ? (
            <RefreshCw aria-hidden="true" size={18} />
          ) : (
            <Play aria-hidden="true" size={18} />
          )}
          {preview.isPending ? "生成中" : "试听旁白音色"}
        </button>
      </div>

      {preview.isError ? (
        <div className="inline-error" role="alert">
          {readableVoiceError(preview.error, maxPreviewTextChars)}
        </div>
      ) : null}
      {hasCurrentPreviewAudio && preview.data ? (
        <audio
          aria-label="旁白音色试听音频"
          className="voice-preview-audio"
          controls
          src={preview.data.audio_url}
        />
      ) : null}
    </fieldset>
  );
}
