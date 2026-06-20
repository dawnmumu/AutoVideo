import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, RefreshCw, Volume2 } from "lucide-react";
import { useEffect, useMemo } from "react";

import {
  createVoicePreview,
  fetchVoiceStatus,
  fetchVoices,
} from "../api/voices";
import type { CreateVoicePreviewInput, VoiceItem } from "../api/voices";
import { readableVoiceError, selectDefaultVoice, voiceTags } from "./VoiceSelector";

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
  const status = useQuery({
    queryKey: ["voice-status"],
    queryFn: fetchVoiceStatus,
  });
  const voices = useQuery({
    queryKey: ["voices", "all", ""],
    queryFn: () => fetchVoices({ locale: "", q: "" }),
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

  const canCreatePreview =
    Boolean(selectedVoiceId) && previewText.trim().length > 0 && !preview.isPending;
  const hasCurrentPreviewAudio = Boolean(
    preview.data &&
      preview.variables?.text === previewText &&
      preview.variables.voice_id === selectedVoiceId,
  );

  return (
    <fieldset className="voice-dropdown">
      <legend>旁白音色</legend>
      <label>
        <span>旁白音色</span>
        <select
          disabled={voices.isLoading || voices.isError || voiceItems.length === 0}
          value={selectedVoiceId}
          onChange={(event) => {
            const nextVoice = voiceItems.find((voice) => voice.id === event.target.value) ?? null;
            onChange(nextVoice);
          }}
        >
          {voices.isLoading ? <option value="">正在读取音色</option> : null}
          {!voices.isLoading && voiceItems.length === 0 ? <option value="">暂无音色</option> : null}
          {voiceItems.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voiceSelectLabel(voice)}
            </option>
          ))}
        </select>
      </label>

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
