# Mix Workbench Voice Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add voice selection to the AutoVideo online remix workbench, persist the selected voice into task options and manifest, and keep desktop/mobile UI accessible and testable.

**Architecture:** Reuse the existing `/api/voices` API and Edge TTS preview path. Add a focused `VoiceSelector` React component, wire it into `OnlineRemixWorkbench`, and add backend normalization for voice options alongside the existing subtitle option normalization. The render pipeline remains unchanged; this task saves voice configuration for current tasks and future TTS audio mixing.

**Tech Stack:** FastAPI, Pydantic, pytest, React 18, TypeScript, TanStack Query, Vitest, Testing Library, Vite.

---

## File Structure

- Modify: `autovideo/services/online_mix.py`
  - Add `VoiceProviderInvalidError`.
  - Add `normalize_voice_options(options)`.
  - Merge normalized voice fields into task `options` and manifest payload.
- Modify: `autovideo/api/routes/online_mix.py`
  - Catch `VoiceProviderInvalidError` and return structured `400 VOICE_PROVIDER_INVALID`.
- Modify: `tests/api/test_online_mix.py`
  - Add backend contract tests for populated voice fields, null voice fields, missing provider default, and invalid provider.
- Create: `frontend/src/components/VoiceSelector.tsx`
  - Own voice loading, language/search filters, default selection, selected summary, preview generation, loading/error/empty states, and accessibility.
- Modify: `frontend/src/components/VoiceCenterWorkbench.tsx`
  - Reuse `voiceTags`, `readableVoiceError`, and `selectDefaultVoice` from `VoiceSelector`; keep only voice-center-specific preview controls local.
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
  - Hold selected voice state and pass normalized voice fields to `createOnlineMixTask`.
- Modify: `frontend/src/api/onlineRemix.ts`
  - Extend `CreateOnlineMixTaskInput.options` with optional voice fields.
- Modify: `frontend/src/App.test.tsx`
  - Cover component-level selector behavior, workbench integration, preview text source, task payload fields, service-unavailable submission, and responsive CSS source rules.
- Modify: `frontend/src/styles.css`
  - Add responsive voice selector styles under existing panel/form patterns.
- Modify: `README.md`
  - Document that the workbench saves voice configuration, without claiming final MP4 voiceover mixing.

---

### Task 1: Backend Voice Option Contract

**Files:**
- Modify: `tests/api/test_online_mix.py`
- Modify: `autovideo/services/online_mix.py`
- Modify: `autovideo/api/routes/online_mix.py`

- [ ] **Step 1: Write failing backend tests**

Append these tests near the existing subtitle option tests in `tests/api/test_online_mix.py`:

```python
def test_online_mix_persists_voice_options_in_task_and_manifest(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "音色任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": False,
                    "voice_id": "zh-CN-XiaoxiaoNeural",
                    "voice_name": "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
                    "voice_provider": "edge_tts",
                    "voice_locale": "zh-CN",
                    "voice_gender": "Female",
                },
            },
        )
        task = response.json()

    assert response.status_code == 201
    for payload in [
        task["options"],
        json.loads((tmp_path / "outputs" / task["id"] / "manifest.json").read_text(encoding="utf-8")),
    ]:
        assert payload["voice_id"] == "zh-CN-XiaoxiaoNeural"
        assert payload["voice_name"] == "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)"
        assert payload["voice_provider"] == "edge_tts"
        assert payload["voice_locale"] == "zh-CN"
        assert payload["voice_gender"] == "Female"


def test_online_mix_defaults_empty_voice_options_to_null(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "无音色任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {"aspect_ratio": "9:16", "subtitle_enabled": False},
            },
        )
        task = response.json()

    assert response.status_code == 201
    manifest = json.loads((tmp_path / "outputs" / task["id"] / "manifest.json").read_text(encoding="utf-8"))
    for payload in [task["options"], manifest]:
        assert payload["voice_id"] is None
        assert payload["voice_name"] is None
        assert payload["voice_provider"] is None
        assert payload["voice_locale"] is None
        assert payload["voice_gender"] is None


def test_online_mix_defaults_missing_voice_provider_to_edge_tts(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "默认 provider 音色任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": False,
                    "voice_id": "zh-CN-XiaoxiaoNeural",
                    "voice_name": "Microsoft Xiaoxiao",
                    "voice_provider": "",
                },
            },
        )

    assert response.status_code == 201
    assert response.json()["options"]["voice_provider"] == "edge_tts"


def test_online_mix_rejects_invalid_voice_provider(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()

    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "非法 provider 音色任务",
            "script": _single_shot_script(),
            "asset_strategy": "manual",
            "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
            "options": {
                "subtitle_enabled": False,
                "voice_id": "voice-1",
                "voice_provider": "fish_speech",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VOICE_PROVIDER_INVALID"
```

- [ ] **Step 2: Run backend tests and verify red**

Run:

```bash
pytest tests/api/test_online_mix.py -k "voice_options or voice_provider" -q
```

Expected: fails because `voice_id` fields are absent and `VOICE_PROVIDER_INVALID` is not implemented.

- [ ] **Step 3: Add backend normalization**

In `autovideo/services/online_mix.py`, add the exception near `SubtitleTemplateInvalidError`:

```python
class VoiceProviderInvalidError(ValueError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(provider)
```

Add voice constants and normalization near `EMPTY_SUBTITLE_OPTION_KEYS`:

```python
VOICE_OPTION_KEYS = frozenset(
    {
        "voice_id",
        "voice_name",
        "voice_provider",
        "voice_locale",
        "voice_gender",
    }
)
```

Add helper functions near `normalize_subtitle_options`:

```python
def normalize_voice_options(options: dict[str, Any]) -> dict[str, Any]:
    voice_id = _optional_text(options.get("voice_id"))
    if not voice_id:
        return {
            "voice_id": None,
            "voice_name": None,
            "voice_provider": None,
            "voice_locale": None,
            "voice_gender": None,
        }

    provider = _optional_text(options.get("voice_provider")) or "edge_tts"
    if provider != "edge_tts":
        raise VoiceProviderInvalidError(provider)

    return {
        "voice_id": voice_id,
        "voice_name": _optional_text(options.get("voice_name")),
        "voice_provider": provider,
        "voice_locale": _optional_text(options.get("voice_locale")),
        "voice_gender": _optional_text(options.get("voice_gender")),
    }
```

Then inside `create_online_mix_task`, after `subtitle_options = normalize_subtitle_options(store, options)`, add:

```python
    voice_options = normalize_voice_options(options)
```

Change sanitized options:

```python
    sanitized_options = sanitized_online_mix_options(
        {**options, **subtitle_options, **voice_options}
    )
```

Add these fields to `manifest_payload`:

```python
            "voice_id": voice_options["voice_id"],
            "voice_name": voice_options["voice_name"],
            "voice_provider": voice_options["voice_provider"],
            "voice_locale": voice_options["voice_locale"],
            "voice_gender": voice_options["voice_gender"],
```

- [ ] **Step 4: Wire structured API error**

In `autovideo/api/routes/online_mix.py`, import `VoiceProviderInvalidError` from `autovideo.services.online_mix` and add this `except` block before the generic render errors:

```python
    except VoiceProviderInvalidError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "VOICE_PROVIDER_INVALID",
            provider=exc.provider,
        ) from exc
```

- [ ] **Step 5: Run backend tests and verify green**

Run:

```bash
pytest tests/api/test_online_mix.py -k "voice_options or voice_provider" -q
```

Expected: 4 selected tests pass.

- [ ] **Step 6: Commit backend task**

Run:

```bash
git add autovideo/services/online_mix.py autovideo/api/routes/online_mix.py tests/api/test_online_mix.py
git commit -m "feat: persist online mix voice options"
```

---

### Task 2: VoiceSelector Component

**Files:**
- Create: `frontend/src/components/VoiceSelector.tsx`
- Modify: `frontend/src/components/VoiceCenterWorkbench.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing component tests for selector behavior**

In `frontend/src/App.test.tsx`, add these imports near the existing imports:

```tsx
import { useState } from "react";

import type { VoiceItem } from "./api/voices";
import { VoiceSelector, selectDefaultVoice } from "./components/VoiceSelector";
```

Add this helper near `renderApp()`:

```tsx
function renderVoiceSelectorHarness({
  previewText = "睡前点一滴精油，让卧室慢慢安静下来。",
  initialVoice = null,
}: {
  previewText?: string;
  initialVoice?: VoiceItem | null;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  function Harness() {
    const [selectedVoice, setSelectedVoice] = useState<VoiceItem | null>(initialVoice);

    return (
      <VoiceSelector
        compact
        previewText={previewText}
        value={selectedVoice}
        onChange={setSelectedVoice}
      />
    );
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}
```

Add these tests near the existing voice center tests:

```tsx
it("selects the default voice through the shared VoiceSelector helper", () => {
  const voiceItems: VoiceItem[] = [
    {
      id: "en-US-JennyNeural",
      name: "Microsoft Jenny Online (Natural) - English (United States)",
      provider: "edge_tts",
      locale: "en-US",
      gender: "Female",
      content_categories: ["General"],
      personalities: ["Friendly"],
    },
    {
      id: "zh-CN-XiaoxiaoNeural",
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
      provider: "edge_tts",
      locale: "zh-CN",
      gender: "Female",
      content_categories: ["General"],
      personalities: ["Warm", "Friendly"],
    },
  ];

  expect(
    selectDefaultVoice(voiceItems, "zh-CN-XiaoxiaoNeural", null, {
      preserveCurrentVoice: false,
    })?.id,
  ).toBe("zh-CN-XiaoxiaoNeural");
  expect(
    selectDefaultVoice(voiceItems, "zh-CN-XiaoxiaoNeural", "en-US-JennyNeural", {
      preserveCurrentVoice: false,
    })?.id,
  ).toBe("zh-CN-XiaoxiaoNeural");
  expect(
    selectDefaultVoice(voiceItems, "zh-CN-XiaoxiaoNeural", "en-US-JennyNeural", {
      preserveCurrentVoice: true,
    })?.id,
  ).toBe("en-US-JennyNeural");
  expect(
    selectDefaultVoice(voiceItems, null, null, { preserveCurrentVoice: false })?.id,
  ).toBe("en-US-JennyNeural");
  expect(
    selectDefaultVoice(voiceItems, "missing-default", "missing-current", {
      preserveCurrentVoice: true,
    })?.id,
  ).toBe("en-US-JennyNeural");
  expect(
    selectDefaultVoice([], "zh-CN-XiaoxiaoNeural", null, {
      preserveCurrentVoice: false,
    }),
  ).toBeNull();
});

it("waits for voice status before falling back to the first VoiceSelector voice", async () => {
  let resolveStatus: (
    value: Awaited<ReturnType<typeof fetchVoiceStatus>>,
  ) => void = () => undefined;
  const statusPromise = new Promise<Awaited<ReturnType<typeof fetchVoiceStatus>>>((resolve) => {
    resolveStatus = resolve;
  });
  mockedFetchVoiceStatus.mockReturnValueOnce(statusPromise);
  mockedFetchVoices.mockResolvedValueOnce({
    provider: "edge_tts",
    total: 2,
    items: [
      {
        id: "en-US-JennyNeural",
        name: "Microsoft Jenny Online (Natural) - English (United States)",
        provider: "edge_tts",
        locale: "en-US",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Friendly"],
      },
      {
        id: "zh-CN-XiaoxiaoNeural",
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
        provider: "edge_tts",
        locale: "zh-CN",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Warm", "Friendly"],
      },
    ],
  });
  renderVoiceSelectorHarness();

  const firstVoice = await screen.findByRole("button", {
    name: "Microsoft Jenny Online (Natural) - English (United States)",
  });
  const defaultVoice = screen.getByRole("button", {
    name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
  });
  expect(firstVoice).toHaveAttribute("aria-pressed", "false");
  expect(defaultVoice).toHaveAttribute("aria-pressed", "false");

  await act(async () => {
    resolveStatus({
      edge_tts: {
        enabled: true,
        provider: "edge_tts",
        requires_api_key: false,
        default_voice: "zh-CN-XiaoxiaoNeural",
        max_preview_text_chars: 180,
      },
      fish_speech: {
        configured: false,
        enabled: false,
      },
    });
    await statusPromise;
  });

  await waitFor(() => {
    expect(defaultVoice).toHaveAttribute("aria-pressed", "true");
  });
  expect(firstVoice).toHaveAttribute("aria-pressed", "false");
});

it("falls back to the first VoiceSelector voice when status fails", async () => {
  mockedFetchVoiceStatus.mockRejectedValueOnce(new VoiceApiError("VOICE_STATUS_FAILED", 503));
  renderVoiceSelectorHarness();

  expect(
    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    }),
  ).toHaveAttribute("aria-pressed", "true");
});

it("falls back to the first VoiceSelector voice when status has no default voice", async () => {
  mockedFetchVoiceStatus.mockResolvedValueOnce({
    edge_tts: {
      enabled: true,
      provider: "edge_tts",
      requires_api_key: false,
      default_voice: "",
      max_preview_text_chars: 180,
    },
    fish_speech: {
      configured: false,
      enabled: false,
    },
  });
  renderVoiceSelectorHarness();

  expect(
    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    }),
  ).toHaveAttribute("aria-pressed", "true");
});

it("falls back to the first VoiceSelector voice when the default voice is missing from the list", async () => {
  mockedFetchVoiceStatus.mockResolvedValueOnce({
    edge_tts: {
      enabled: true,
      provider: "edge_tts",
      requires_api_key: false,
      default_voice: "missing-voice",
      max_preview_text_chars: 180,
    },
    fish_speech: {
      configured: false,
      enabled: false,
    },
  });
  renderVoiceSelectorHarness();

  expect(
    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    }),
  ).toHaveAttribute("aria-pressed", "true");
});

it("keeps a manually selected VoiceSelector voice instead of the Edge TTS default voice", async () => {
  const user = userEvent.setup();
  mockedFetchVoices.mockResolvedValueOnce({
    provider: "edge_tts",
    total: 2,
    items: [
      {
        id: "en-US-JennyNeural",
        name: "Microsoft Jenny Online (Natural) - English (United States)",
        provider: "edge_tts",
        locale: "en-US",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Friendly"],
      },
      {
        id: "zh-CN-XiaoxiaoNeural",
        name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
        provider: "edge_tts",
        locale: "zh-CN",
        gender: "Female",
        content_categories: ["General"],
        personalities: ["Warm", "Friendly"],
      },
    ],
  });
  renderVoiceSelectorHarness();

  await user.click(
    await screen.findByRole("button", {
      name: "Microsoft Jenny Online (Natural) - English (United States)",
    }),
  );
  await waitFor(() => {
    expect(
      screen.getByRole("button", {
        name: "Microsoft Jenny Online (Natural) - English (United States)",
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});

it("renders VoiceSelector with the default Edge TTS voice", async () => {
  renderVoiceSelectorHarness();

  expect(await screen.findByRole("group", { name: "旁白音色" })).toBeInTheDocument();
  expect(
    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("音色语言")).toHaveDisplayValue("中文");
  expect(mockedFetchVoiceStatus).toHaveBeenCalledTimes(1);
  expect(mockedFetchVoices).toHaveBeenCalledWith({ locale: "zh-CN", q: "" });
});

it("previews the selected VoiceSelector voice with provided narration text", async () => {
  const user = userEvent.setup();
  renderVoiceSelectorHarness({ previewText: "睡前点一滴精油，让卧室慢慢安静下来。" });

  await screen.findByRole("button", {
    name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
  });
  await user.click(screen.getByRole("button", { name: "试听旁白音色" }));

  await waitFor(() => {
    expect(mockedCreateVoicePreview).toHaveBeenCalledWith({
      text: "睡前点一滴精油，让卧室慢慢安静下来。",
      voice_id: "zh-CN-XiaoxiaoNeural",
      rate: "+0%",
      volume: "+0%",
      pitch: "+0Hz",
    });
  });
});
```

- [ ] **Step 2: Run front-end tests and verify red**

Run:

```bash
cd frontend
npm test -- --run src/App.test.tsx -t "VoiceSelector"
```

Expected: fails because `./components/VoiceSelector` and `selectDefaultVoice` do not exist yet.

- [ ] **Step 3: Create VoiceSelector component**

Create `frontend/src/components/VoiceSelector.tsx`:

```tsx
import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, RefreshCw, Search, Volume2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { VoiceItem } from "../api/voices";
import {
  VoiceApiError,
  createVoicePreview,
  fetchVoiceStatus,
  fetchVoices,
} from "../api/voices";

const LOCALE_OPTIONS = [
  { value: "zh-CN", label: "中文" },
  { value: "en-US", label: "英语" },
  { value: "ja-JP", label: "日语" },
  { value: "ko-KR", label: "韩语" },
];

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
  options: { preserveCurrentVoice: boolean },
): VoiceItem | null {
  if (options.preserveCurrentVoice && currentVoiceId) {
    const currentVoice = voiceItems.find((voice) => voice.id === currentVoiceId);
    if (currentVoice) {
      return currentVoice;
    }
  }
  return voiceItems.find((voice) => voice.id === defaultVoice) ?? voiceItems[0] ?? null;
}

export interface VoiceSelectorProps {
  compact?: boolean;
  previewText: string;
  value: VoiceItem | null;
  onChange: (voice: VoiceItem | null) => void;
}

export function VoiceSelector({ compact = false, previewText, value, onChange }: VoiceSelectorProps) {
  const [locale, setLocale] = useState("zh-CN");
  const [query, setQuery] = useState("");
  const [hasManualVoiceSelection, setHasManualVoiceSelection] = useState(false);

  const status = useQuery({
    queryKey: ["voice-status"],
    queryFn: fetchVoiceStatus,
  });
  const voices = useQuery({
    queryKey: ["voices", locale, query],
    queryFn: () => fetchVoices({ locale, q: query }),
  });
  const preview = useMutation({
    mutationFn: () =>
      createVoicePreview({
        text: previewText,
        voice_id: value?.id ?? "",
        rate: "+0%",
        volume: "+0%",
        pitch: "+0Hz",
      }),
  });

  const voiceItems = useMemo(() => voices.data?.items ?? [], [voices.data?.items]);
  const maxPreviewTextChars = status.data?.edge_tts.max_preview_text_chars ?? 300;
  const statusReady = status.isSuccess || status.isError;

  useEffect(() => {
    if (voices.isLoading || voices.isError || !statusReady) {
      return;
    }
    const nextVoice = selectDefaultVoice(
      voiceItems,
      status.isSuccess ? status.data.edge_tts.default_voice : null,
      value?.id,
      { preserveCurrentVoice: hasManualVoiceSelection },
    );
    if ((nextVoice?.id ?? null) !== (value?.id ?? null)) {
      onChange(nextVoice);
    }
  }, [
    hasManualVoiceSelection,
    onChange,
    status.isError,
    status.isSuccess,
    status.data?.edge_tts.default_voice,
    statusReady,
    value?.id,
    voiceItems,
    voices.isError,
    voices.isLoading,
  ]);

  const canPreview = Boolean(value?.id) && previewText.trim().length > 0 && !preview.isPending;

  return (
    <fieldset className={`voice-selector ${compact ? "compact" : ""}`} aria-label="旁白音色">
      <legend>旁白音色</legend>
      <div className="voice-selector-filters">
        <label>
          <span>音色语言</span>
          <select value={locale} onChange={(event) => setLocale(event.target.value)}>
            {LOCALE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>搜索音色</span>
          <span className="voice-search-input">
            <Search aria-hidden="true" size={18} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
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
              aria-pressed={voice.id === value?.id}
              className={voice.id === value?.id ? "active" : ""}
              key={voice.id}
              type="button"
              onClick={() => {
                setHasManualVoiceSelection(true);
                onChange(voice);
              }}
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
          <strong>{value?.name ?? "未选择音色"}</strong>
          {value ? <span>{voiceTags(value)}</span> : null}
        </div>
      </div>
      <div className="voice-preview-actions">
        <button
          className="primary-action"
          disabled={!canPreview}
          type="button"
          onClick={() => preview.mutate()}
        >
          {preview.isPending ? <RefreshCw aria-hidden="true" size={18} /> : <Play aria-hidden="true" size={18} />}
          {preview.isPending ? "生成中" : "试听旁白音色"}
        </button>
      </div>
      {preview.isError ? (
        <div className="inline-error" role="alert">
          {readableVoiceError(preview.error, maxPreviewTextChars)}
        </div>
      ) : null}
      {preview.data ? (
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
```

- [ ] **Step 4: Reuse selector helpers in VoiceCenterWorkbench**

In `frontend/src/components/VoiceCenterWorkbench.tsx`, replace local `voiceTags`, `detailNumber`, and `readableError` duplicates by importing:

```tsx
import { readableVoiceError, selectDefaultVoice, voiceTags } from "./VoiceSelector";
```

Remove `VoiceApiError` from the existing `../api/voices` import because error formatting now comes from `readableVoiceError`. Keep `signedPercent`, `signedPitch`, and the full preview controls local to `VoiceCenterWorkbench`. Add manual-selection state next to the existing `selectedVoiceId` state:

```tsx
  const [selectedVoiceId, setSelectedVoiceId] = useState("");
  const [hasManualVoiceSelection, setHasManualVoiceSelection] = useState(false);
```

Add `statusReady` next to `voiceItems`, then replace the current `selectedVoice` calculation:

```tsx
  const statusReady = status.isSuccess || status.isError;
  const selectedVoice = statusReady
    ? selectDefaultVoice(
        voiceItems,
        status.isSuccess ? status.data.edge_tts.default_voice : null,
        selectedVoiceId,
        { preserveCurrentVoice: hasManualVoiceSelection },
      )
    : voiceItems.find((voice) => voice.id === selectedVoiceId) ?? null;
```

Replace the default-selection effect with the same helper:

```tsx
  useEffect(() => {
    if (voices.isLoading || voices.isError || !statusReady) {
      return;
    }
    const nextVoice = selectDefaultVoice(
      voiceItems,
      status.isSuccess ? status.data.edge_tts.default_voice : null,
      selectedVoiceId,
      { preserveCurrentVoice: hasManualVoiceSelection },
    );
    const nextVoiceId = nextVoice?.id ?? "";
    if (nextVoiceId !== selectedVoiceId) {
      setSelectedVoiceId(nextVoiceId);
    }
  }, [
    hasManualVoiceSelection,
    selectedVoiceId,
    status.isError,
    status.isSuccess,
    status.data?.edge_tts.default_voice,
    statusReady,
    voiceItems,
    voices.isError,
    voices.isLoading,
  ]);
```

Update the voice list button handler so user clicks are marked as manual choices:

```tsx
                  onClick={() => {
                    setHasManualVoiceSelection(true);
                    setSelectedVoiceId(voice.id);
                  }}
```

Replace calls to `readableError(...)` with `readableVoiceError(...)`.

- [ ] **Step 5: Run front-end tests and verify green**

Run:

```bash
cd frontend
npm test -- --run src/App.test.tsx -t "VoiceSelector|voice center"
```

Expected: selected tests pass.

- [ ] **Step 6: Commit selector task**

Run:

```bash
git add frontend/src/components/VoiceSelector.tsx frontend/src/components/VoiceCenterWorkbench.tsx frontend/src/App.test.tsx
git commit -m "feat: add reusable voice selector"
```

---

### Task 3: Mix Workbench Integration and Responsive Styling

**Files:**
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
- Modify: `frontend/src/api/onlineRemix.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing workbench integration tests**

In `frontend/src/App.test.tsx`, add these tests near the existing online remix form tests:

```tsx
it("shows workbench voice selection with the default Edge TTS voice", async () => {
  renderApp();

  expect(await screen.findByRole("group", { name: "旁白音色" })).toBeInTheDocument();
  expect(
    await screen.findByRole("button", {
      name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
    }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("音色语言")).toHaveDisplayValue("中文");
  expect(mockedFetchVoiceStatus).toHaveBeenCalledTimes(1);
  expect(mockedFetchVoices).toHaveBeenCalledWith({ locale: "zh-CN", q: "" });
});

it("previews the selected workbench voice with the first script narration", async () => {
  const user = userEvent.setup();
  mockedGenerateScript.mockResolvedValueOnce({
    id: "script-1",
    title: "睡前精油短视频",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [
      {
        index: 1,
        duration: 5,
        narration: "睡前点一滴精油，让卧室慢慢安静下来。",
        subtitle: "睡前放松",
        visual_description: "relaxing bedroom night",
        keywords: ["relaxing bedroom night"],
      },
    ],
  });
  renderApp();

  await screen.findByRole("button", {
    name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
  });
  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await screen.findByDisplayValue("睡前精油短视频");
  await user.click(screen.getByRole("button", { name: "试听旁白音色" }));

  await waitFor(() => {
    expect(mockedCreateVoicePreview).toHaveBeenCalledWith({
      text: "睡前点一滴精油，让卧室慢慢安静下来。",
      voice_id: "zh-CN-XiaoxiaoNeural",
      rate: "+0%",
      volume: "+0%",
      pitch: "+0Hz",
    });
  });
});
```

- [ ] **Step 2: Write failing task payload tests**

In `frontend/src/App.test.tsx`, add these tests near the online remix task creation tests:

```tsx
it("sends the selected voice when creating an online remix task", async () => {
  const user = userEvent.setup();
  mockedGenerateScript.mockResolvedValueOnce({
    id: "script-1",
    title: "睡前精油短视频",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [
      {
        index: 1,
        duration: 5,
        narration: "旁白 1",
        subtitle: "字幕 1",
        visual_description: "relaxing bedroom night",
        keywords: ["relaxing bedroom night"],
      },
    ],
  });
  mockedCreateOnlineMixTask.mockResolvedValueOnce({
    id: "task-1",
    title: "睡前精油短视频",
    output: { download_url: "/api/tasks/task-1/output" },
  });
  renderApp();

  await screen.findByRole("button", {
    name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
  });
  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await screen.findByDisplayValue("睡前精油短视频");
  await user.click(screen.getByRole("button", { name: "创建任务" }));

  await waitFor(() => {
    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          voice_id: "zh-CN-XiaoxiaoNeural",
          voice_name: "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
          voice_provider: "edge_tts",
          voice_locale: "zh-CN",
          voice_gender: "Female",
        }),
      }),
    );
  });
});

it("creates an online remix task with null voice fields when the voice service is unavailable", async () => {
  const user = userEvent.setup();
  mockedFetchVoices.mockRejectedValueOnce(new VoiceApiError("VOICE_LIST_FAILED", 503));
  mockedGenerateScript.mockResolvedValueOnce({
    id: "script-1",
    title: "无音色服务短视频",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [
      {
        index: 1,
        duration: 5,
        narration: "旁白 1",
        subtitle: "字幕 1",
        visual_description: "relaxing bedroom night",
        keywords: ["relaxing bedroom night"],
      },
    ],
  });
  mockedCreateOnlineMixTask.mockResolvedValueOnce({
    id: "task-1",
    title: "无音色服务短视频",
    output: { download_url: "/api/tasks/task-1/output" },
  });
  renderApp();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "无法读取 Edge TTS 音色，请检查网络后重试。",
  );
  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await screen.findByDisplayValue("无音色服务短视频");
  await user.click(screen.getByRole("button", { name: "创建任务" }));

  await waitFor(() => {
    expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          voice_id: null,
          voice_name: null,
          voice_provider: null,
          voice_locale: null,
          voice_gender: null,
        }),
      }),
    );
  });
});
```

- [ ] **Step 3: Write failing responsive CSS source assertions**

In `frontend/src/App.test.tsx`, add this source assertion near the existing `stylesCss` tests:

```tsx
it("keeps the workbench voice selector responsive without hover-only dependencies", () => {
  expect(stylesCss).toMatch(
    /@media \(max-width: 1160px\) \{[\s\S]*?\.voice-selector-filters[\s\S]*?grid-template-columns:\s*1fr;/,
  );
  expect(stylesCss).toMatch(
    /@media \(max-width: 760px\) \{[\s\S]*?\.voice-selector-filters[\s\S]*?grid-template-columns:\s*1fr;/,
  );
  expect(stylesCss).toMatch(
    /\.voice-selector input,\s*\.voice-selector select,\s*\.voice-selector button \{[\s\S]*?min-height:\s*44px;/,
  );
  expect(stylesCss).toMatch(
    /\.voice-preview-audio \{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*100%;/,
  );
  expect(stylesCss).not.toMatch(/\.voice-selector[^{,]*:hover/);
});
```

- [ ] **Step 4: Run Task 3 tests and verify red**

Run:

```bash
cd frontend
npm test -- --run src/App.test.tsx -t "workbench voice|selected voice|voice service is unavailable|voice selector responsive"
```

Expected: fails because the workbench does not render `VoiceSelector`, task payloads do not include voice fields, and the responsive CSS assertions are not implemented.

- [ ] **Step 5: Extend API type**

In `frontend/src/api/onlineRemix.ts`, extend `CreateOnlineMixTaskInput.options`:

```ts
    voice_id?: string | null;
    voice_name?: string | null;
    voice_provider?: "edge_tts" | null;
    voice_locale?: string | null;
    voice_gender?: string | null;
```

- [ ] **Step 6: Wire VoiceSelector into OnlineRemixWorkbench**

In `frontend/src/components/OnlineRemixWorkbench.tsx`, import:

```tsx
import type { VoiceItem } from "../api/voices";
import { VoiceSelector } from "./VoiceSelector";
```

Add state near subtitle state:

```tsx
  const [selectedVoice, setSelectedVoice] = useState<VoiceItem | null>(null);
```

Add helper before `createTask`:

```tsx
  const voicePreviewText =
    script?.shots.find((shot) => shot.narration.trim())?.narration.trim() ||
    (topic.trim()
      ? `你好，这是一条关于${topic.trim().slice(0, 20)}的视频旁白试听。`
      : "你好，这是一段视频旁白试听，你可以先听听这款人声是否适合当前视频。");
```

Add voice fields inside `options` for `createOnlineMixTask`:

```tsx
          voice_id: selectedVoice?.id ?? null,
          voice_name: selectedVoice?.name ?? null,
          voice_provider: selectedVoice?.provider ?? null,
          voice_locale: selectedVoice?.locale ?? null,
          voice_gender: selectedVoice?.gender ?? null,
```

Render the selector after `</fieldset>` for subtitle settings and before the primary generate button:

```tsx
        <VoiceSelector
          compact
          previewText={voicePreviewText}
          value={selectedVoice}
          onChange={setSelectedVoice}
        />
```

- [ ] **Step 7: Add responsive styles**

In `frontend/src/styles.css`, include `.voice-selector` in the same input/button patterns as `.subtitle-settings`:

```css
.subtitle-template-list,
.subtitle-preview-panel,
.subtitle-editor-panel,
.subtitle-settings,
.voice-selector {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.voice-selector {
  grid-column: 1 / -1;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-strong);
  padding: 14px;
}

.voice-selector legend {
  color: var(--text);
  font-weight: 700;
  padding: 0 4px;
}

.voice-selector-filters {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(0, 1fr);
  gap: 12px;
}

.voice-selector label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.4;
}

.voice-selector input,
.voice-selector select,
.voice-selector button {
  min-height: 44px;
}

.voice-selector input,
.voice-selector select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font: inherit;
  padding: 10px 12px;
}

.voice-preview-audio {
  width: 100%;
  max-width: 100%;
}
```

In both existing `@media (max-width: 1160px)` and `@media (max-width: 760px)` grid lists, add `.voice-selector-filters` so the filter controls stack before they can overflow:

```css
  .online-remix-form,
  .shot-fields,
  .voice-filter-row,
  .voice-selector-filters,
  .voice-slider-grid,
  .voice-clone-panel,
  .shot-actions,
  .create-task-row,
  .candidate-row,
  .task-output-card,
  .inline-error,
  .local-material-dialog {
    grid-template-columns: 1fr;
  }
```

Do not add hover-only behavior for selecting voices; selected state must be driven by `aria-pressed` and click/tap.

- [ ] **Step 8: Run front-end tests and build**

Run:

```bash
cd frontend
npm test -- --run src/App.test.tsx
npm run build
```

Expected: all front-end tests pass and production build succeeds.

- [ ] **Step 9: Commit integration task**

Run:

```bash
git add frontend/src/components/OnlineRemixWorkbench.tsx frontend/src/api/onlineRemix.ts frontend/src/styles.css frontend/src/App.test.tsx
git commit -m "feat: wire voice selection into remix workbench"
```

---

### Task 4: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`
- Use existing app/browser verification tools; no production code files should be modified in this task unless a verification failure exposes a concrete bug.

- [ ] **Step 1: Update README wording**

In `README.md`, update current stage bullets to include:

```markdown
- 混剪工作台可选择 Microsoft Edge TTS 旁白音色，并把音色配置保存到任务 `options` 和 `manifest.json`
```

In the voice center paragraph, add:

```markdown
混剪工作台会复用同一套音色列表和试听能力保存旁白音色配置；当前最终视频还未混入 TTS 旁白音频。
```

In the `POST /api/online-mix/tasks` API section, add:

```markdown
`options` 可包含 `voice_id`、`voice_name`、`voice_provider`、`voice_locale` 和 `voice_gender`，用于保存旁白音色配置；首版仅支持 `edge_tts`，暂不把 TTS 音频混入最终 MP4。
```

- [ ] **Step 2: Run full targeted verification**

Run from repo root:

```bash
pytest tests/api/test_online_mix.py
cd frontend
npm test -- --run src/App.test.tsx
npm run build
```

Expected: all commands pass.

- [ ] **Step 3: Start local dev server for visual checks**

Run:

```bash
./scripts/dev.sh
```

If port `5173` is occupied, run the Vite command manually with another port:

```bash
cd frontend
npm run dev -- --port 5174
```

Expected: the app is available at the printed local URL.

- [ ] **Step 4: Verify desktop and mobile UI**

Using browser automation, verify these conditions:

```js
const metrics = await page.evaluate(() => {
  const controls = Array.from(
    document.querySelectorAll(
      ".voice-selector select, .voice-selector input, .voice-selector button",
    ),
  ).map((node) => ({
    text: node.textContent || node.getAttribute("aria-label") || node.getAttribute("name") || node.tagName,
    height: Math.round(node.getBoundingClientRect().height),
  }));
  return {
    bodyScrollWidth: document.body.scrollWidth,
    innerWidth: window.innerWidth,
    controls,
    hasVoiceSelector: Boolean(document.querySelector(".voice-selector")),
    hasAudioOverflow:
      document.querySelector(".voice-preview-audio")?.getBoundingClientRect().right >
      window.innerWidth,
  };
});
```

Expected at `375x812`:

- `metrics.hasVoiceSelector === true`
- `metrics.bodyScrollWidth <= metrics.innerWidth`
- every voice selector input/select/button has `height >= 44`
- `metrics.hasAudioOverflow !== true`
- language, search, voice selection, and preview interactions work by click/tap.

- [ ] **Step 5: Commit docs and verification adjustments**

Run:

```bash
git add README.md
git commit -m "docs: document remix voice selection"
```

If visual verification required CSS or test fixes, include those files in the same commit and mention the exact fix in the commit body.

---

## Final Gate After All Tasks

- [ ] Run final status:

```bash
git status --short --branch
git log --oneline --decorate -5
```

- [ ] Run required verification:

```bash
pytest tests/api/test_online_mix.py
cd frontend
npm test -- --run src/App.test.tsx
npm run build
```

- [ ] Run local pre-PR review with `superpowers:requesting-code-review` against the full branch diff. Provide the reviewer:
  - `docs/superpowers/specs/2026-06-20-mix-workbench-voice-selection-design.md`
  - this plan file
  - `git fetch origin main` followed by `git diff origin/main...HEAD --`
  - current `git diff HEAD --` and `git diff --cached --`

- [ ] Fix any actionable findings through a separate fix subagent, rerun targeted tests, and repeat review until `Ready` with no actionable findings.

- [ ] Push branch and create a ready PR.

- [ ] After PR creation, run the required PR-level `superpowers:requesting-code-review` loop, fix findings if any, push again, and repeat until clean.
