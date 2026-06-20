import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, RefreshCw, Search, Volume2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  VoiceApiError,
  createVoicePreview,
  fetchVoiceStatus,
  fetchVoices,
} from "../api/voices";
import type { CreateVoicePreviewInput, VoiceItem } from "../api/voices";

const LOCALE_OPTIONS = [
  { value: "zh-CN", label: "中文" },
  { value: "en-US", label: "英语" },
  { value: "ja-JP", label: "日语" },
  { value: "ko-KR", label: "韩语" },
];

interface SelectDefaultVoiceOptions {
  preserveCurrentVoice: boolean;
}

export interface VoiceSelectorProps {
  compact?: boolean;
  previewText: string;
  value: VoiceItem | null;
  onChange: (voice: VoiceItem | null) => void;
}

export function voiceTags(voice: VoiceItem): string {
  return [voice.locale, voice.gender, ...voice.personalities].filter(Boolean).join(" · ");
}

function detailNumber(error: VoiceApiError, key: string): number | null {
  const value = error.detail[key];
  return typeof value === "number" ? value : null;
}

export function readableVoiceError(error: unknown, maxPreviewTextChars: number): string {
  if (error instanceof VoiceApiError) {
    if (error.code === "VOICE_LIST_FAILED") {
      return "无法读取 Edge TTS 音色，请检查网络后重试。";
    }
    if (error.code === "VOICE_PREVIEW_TEXT_TOO_LONG") {
      const maxChars = detailNumber(error, "max_chars") ?? maxPreviewTextChars;
      return `试听文案不能超过 ${maxChars} 个字`;
    }
    if (error.code === "VOICE_NOT_FOUND") {
      return "当前音色不可用，请重新选择。";
    }
    if (error.code === "VOICE_PREVIEW_FAILED") {
      return "试听生成失败，请稍后重试。";
    }
  }
  return "音色请求失败，请稍后重试。";
}

export function selectDefaultVoice(
  voiceItems: VoiceItem[],
  defaultVoice: string | null | undefined,
  currentVoiceId: string | null | undefined,
  { preserveCurrentVoice }: SelectDefaultVoiceOptions,
): VoiceItem | null {
  if (voiceItems.length === 0) {
    return null;
  }

  if (preserveCurrentVoice && currentVoiceId) {
    const currentVoice = voiceItems.find((voice) => voice.id === currentVoiceId);
    if (currentVoice) {
      return currentVoice;
    }
  }

  if (defaultVoice) {
    const edgeDefaultVoice = voiceItems.find((voice) => voice.id === defaultVoice);
    if (edgeDefaultVoice) {
      return edgeDefaultVoice;
    }
  }

  return voiceItems[0] ?? null;
}

export function VoiceSelector({
  compact = false,
  previewText,
  value,
  onChange,
}: VoiceSelectorProps) {
  const [locale, setLocale] = useState("zh-CN");
  const [query, setQuery] = useState("");

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

  useEffect(() => {
    if (value || voices.isLoading || voices.isError || !statusReady) {
      return;
    }

    const nextVoice = selectDefaultVoice(
      voiceItems,
      status.data?.edge_tts.default_voice,
      null,
      { preserveCurrentVoice: false },
    );

    if (nextVoice) {
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

  const handleVoiceChange = (voice: VoiceItem) => {
    onChange(voice);
  };

  const canCreatePreview =
    Boolean(selectedVoiceId) && previewText.trim().length > 0 && !preview.isPending;
  const hasCurrentPreviewAudio = Boolean(
    preview.data &&
      preview.variables?.text === previewText &&
      preview.variables.voice_id === selectedVoiceId,
  );

  return (
    <fieldset
      aria-label="旁白音色"
      className={compact ? "voice-selector compact" : "voice-selector"}
    >
      <legend>旁白音色</legend>

      <div className="voice-selector-filters">
        <label>
          音色语言
          <select value={locale} onChange={(event) => setLocale(event.target.value)}>
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

      {voices.isLoading ? (
        <div className="runtime-status" role="status" aria-live="polite">
          正在读取音色
        </div>
      ) : voices.isError ? (
        <div className="inline-error" role="alert">
          <span>{readableVoiceError(voices.error, maxPreviewTextChars)}</span>
          <button type="button" onClick={() => void voices.refetch()}>
            <RefreshCw aria-hidden="true" size={18} />
            重试
          </button>
        </div>
      ) : voiceItems.length === 0 ? (
        <div className="empty-state">
          <strong>没有匹配音色</strong>
          <span>切换语言或搜索词</span>
        </div>
      ) : (
        <div className="voice-list" role="group" aria-label="微软 Edge TTS 音色">
          {voiceItems.map((voice) => (
            <button
              aria-label={voice.name}
              aria-pressed={voice.id === selectedVoice?.id}
              className={voice.id === selectedVoice?.id ? "active" : ""}
              key={voice.id}
              type="button"
              onClick={() => handleVoiceChange(voice)}
            >
              <span>{voice.name}</span>
              <small>{voiceTags(voice)}</small>
            </button>
          ))}
        </div>
      )}

      <div className="voice-selected-summary">
        <Volume2 aria-hidden="true" size={22} />
        <div>
          <strong>{selectedVoice?.name ?? "未选择音色"}</strong>
          {selectedVoice ? <span>{voiceTags(selectedVoice)}</span> : null}
        </div>
      </div>

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
