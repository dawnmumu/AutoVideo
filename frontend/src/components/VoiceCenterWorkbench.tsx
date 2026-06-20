import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CircleAlert,
  CircleCheck,
  Play,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Volume2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  createVoicePreview,
  fetchVoiceStatus,
  fetchVoices,
} from "../api/voices";
import { readableVoiceError, selectDefaultVoice, voiceTags } from "./VoiceSelector";

const LOCALE_OPTIONS = [
  { value: "zh-CN", label: "中文" },
  { value: "en-US", label: "英语" },
  { value: "ja-JP", label: "日语" },
  { value: "ko-KR", label: "韩语" },
];

function signedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value}%`;
}

function signedPitch(value: number): string {
  return `${value >= 0 ? "+" : ""}${value}Hz`;
}

export function VoiceCenterWorkbench() {
  const [locale, setLocale] = useState("zh-CN");
  const [query, setQuery] = useState("");
  const [selectedVoiceId, setSelectedVoiceId] = useState("");
  const [hasManualVoiceSelection, setHasManualVoiceSelection] = useState(false);
  const [previewText, setPreviewText] = useState("你好，欢迎使用 AutoVideo。");
  const [rate, setRate] = useState(0);
  const [volume, setVolume] = useState(0);
  const [pitch, setPitch] = useState(0);

  const status = useQuery({
    queryKey: ["voice-status"],
    queryFn: fetchVoiceStatus,
  });
  const voices = useQuery({
    queryKey: ["voices", locale, query],
    queryFn: () => fetchVoices({ locale, q: query }),
  });

  const voiceItems = useMemo(() => voices.data?.items ?? [], [voices.data?.items]);
  const statusReady = status.isSuccess || status.isError;
  const defaultVoiceId = status.data?.edge_tts.default_voice ?? null;
  const selectedVoice = useMemo(() => {
    if (!statusReady) {
      return voiceItems.find((voice) => voice.id === selectedVoiceId) ?? null;
    }
    return selectDefaultVoice(voiceItems, defaultVoiceId, selectedVoiceId || null, {
      preserveCurrentVoice: hasManualVoiceSelection,
    });
  }, [defaultVoiceId, hasManualVoiceSelection, selectedVoiceId, statusReady, voiceItems]);
  const maxPreviewTextChars = status.data?.edge_tts.max_preview_text_chars ?? 300;

  const preview = useMutation({
    mutationFn: () =>
      createVoicePreview({
        text: previewText,
        voice_id: selectedVoice?.id ?? selectedVoiceId,
        rate: signedPercent(rate),
        volume: signedPercent(volume),
        pitch: signedPitch(pitch),
      }),
  });

  useEffect(() => {
    if (voices.isLoading || voices.isError || !statusReady) {
      return;
    }
    const nextVoice = selectDefaultVoice(voiceItems, defaultVoiceId, selectedVoiceId || null, {
      preserveCurrentVoice: hasManualVoiceSelection,
    });
    const nextVoiceId = nextVoice?.id ?? "";
    if (nextVoiceId !== selectedVoiceId) {
      setSelectedVoiceId(nextVoiceId);
    }
  }, [
    defaultVoiceId,
    hasManualVoiceSelection,
    selectedVoiceId,
    statusReady,
    voiceItems,
    voices.isError,
    voices.isLoading,
  ]);

  const canCreatePreview =
    Boolean(selectedVoice?.id) && previewText.trim().length > 0 && !preview.isPending;

  return (
    <article className="panel voice-center-panel" aria-label="音色中心">
      <div className="panel-heading">
        <div>
          <h2>微软 Edge TTS 免费音色试听</h2>
          <span>
            {status.data?.fish_speech.enabled
              ? "Edge TTS 与 Fish Speech 就绪。"
              : "Edge TTS 就绪，Fish Speech 待配置。"}
          </span>
        </div>
        <div className="status-inline" aria-label="音色服务状态">
          <span className="status-pill succeeded">
            <CircleCheck aria-hidden="true" size={16} />
            Edge TTS
          </span>
          <span className={`status-pill ${status.data?.fish_speech.enabled ? "succeeded" : "partial"}`}>
            {status.data?.fish_speech.enabled ? (
              <CircleCheck aria-hidden="true" size={16} />
            ) : (
              <CircleAlert aria-hidden="true" size={16} />
            )}
            Fish Speech
          </span>
        </div>
      </div>

      <div className="voice-center-grid">
        <section aria-label="音色列表" className="voice-list-panel">
          <div className="voice-filter-row">
            <label>
              语言
              <select value={locale} onChange={(event) => setLocale(event.target.value)}>
                {LOCALE_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              搜索
              <span className="voice-search-input">
                <Search aria-hidden="true" size={18} />
                <input
                  aria-label="搜索音色"
                  placeholder="Xiaoxiao"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
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
            <div className="voice-list" role="list" aria-label="微软 Edge TTS 音色">
              {voiceItems.map((voice) => (
                <button
                  aria-label={voice.name}
                  aria-pressed={voice.id === selectedVoice?.id}
                  className={voice.id === selectedVoice?.id ? "active" : ""}
                  key={voice.id}
                  type="button"
                  onClick={() => {
                    setHasManualVoiceSelection(true);
                    setSelectedVoiceId(voice.id);
                  }}
                >
                  <span>{voice.name}</span>
                  <small>{voiceTags(voice)}</small>
                </button>
              ))}
            </div>
          )}
        </section>

        <section aria-label="音色试听" className="voice-preview-panel">
          <div className="voice-selected-summary">
            <Volume2 aria-hidden="true" size={22} />
            <div>
              <strong>{selectedVoice?.name ?? "未选择音色"}</strong>
              {selectedVoice ? <span>{voiceTags(selectedVoice)}</span> : null}
            </div>
          </div>

          <div className="voice-textarea-field">
            <label htmlFor="voice-preview-text">试听文案</label>
            <textarea
              id="voice-preview-text"
              maxLength={maxPreviewTextChars}
              value={previewText}
              onChange={(event) => setPreviewText(event.target.value)}
            />
            <span aria-label="试听文案长度" className="voice-text-count">
              {previewText.length} / {maxPreviewTextChars}
            </span>
          </div>

          <div className="voice-slider-grid" aria-label="试听参数">
            <label>
              语速 {signedPercent(rate)}
              <input
                max="50"
                min="-50"
                step="5"
                type="range"
                value={rate}
                onChange={(event) => setRate(Number(event.target.value))}
              />
            </label>
            <label>
              音量 {signedPercent(volume)}
              <input
                max="50"
                min="-50"
                step="5"
                type="range"
                value={volume}
                onChange={(event) => setVolume(Number(event.target.value))}
              />
            </label>
            <label>
              音高 {signedPitch(pitch)}
              <input
                max="50"
                min="-50"
                step="5"
                type="range"
                value={pitch}
                onChange={(event) => setPitch(Number(event.target.value))}
              />
            </label>
          </div>

          <div className="voice-preview-actions">
            <button
              className="primary-action"
              disabled={!canCreatePreview}
              type="button"
              onClick={() => preview.mutate()}
            >
              {preview.isPending ? (
                <RefreshCw aria-hidden="true" size={18} />
              ) : (
                <Play aria-hidden="true" size={18} />
              )}
              {preview.isPending ? "生成中" : "生成试听"}
            </button>
            <span>
              <SlidersHorizontal aria-hidden="true" size={18} />
              {signedPercent(rate)} / {signedPercent(volume)} / {signedPitch(pitch)}
            </span>
          </div>

          {preview.isError ? (
            <div className="inline-error" role="alert">
              {readableVoiceError(preview.error, maxPreviewTextChars)}
            </div>
          ) : null}
          {preview.data ? (
            <audio
              aria-label="音色试听音频"
              className="voice-preview-audio"
              controls
              src={preview.data.audio_url}
            />
          ) : null}
        </section>
      </div>

      <section aria-label="Fish Speech 音色复刻" className="voice-clone-panel">
        <div>
          <strong>Fish Speech 音色复刻</strong>
          <span>
            {status.data?.fish_speech.enabled
              ? "AUTOVIDEO_FISH_SPEECH_URL 已配置"
              : "未配置 AUTOVIDEO_FISH_SPEECH_URL"}
          </span>
        </div>
        <button disabled={!status.data?.fish_speech.enabled} type="button">
          音色复刻
        </button>
      </section>
    </article>
  );
}
