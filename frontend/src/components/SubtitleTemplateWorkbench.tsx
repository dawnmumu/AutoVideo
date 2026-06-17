import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CopyPlus, Play, RotateCcw, Save, WandSparkles } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  SubtitleTemplateSet,
  createSubtitleTemplateSet,
  fetchSubtitleTemplateSets,
  previewSubtitleTemplateSet,
  previewSubtitleTimeline,
  resetSubtitlePresetOverride,
  updateSubtitlePresetOverride,
  updateSubtitleTemplateSet,
  validateSubtitleTemplateSet,
} from "../api/subtitles";
import { selectAutoSubtitleTemplate } from "./subtitleTemplateSelection";

const editableRoles = [
  { role: "bottom", label: "底部字幕" },
  { role: "highlight", label: "强调字幕" },
  { role: "punch", label: "冲击字幕" },
] as const;

function isPresetTemplate(
  template: SubtitleTemplateSet | undefined,
  presetTemplateIds: ReadonlySet<string>,
): boolean {
  return Boolean(template && presetTemplateIds.has(template.id));
}

function blockStyle(block: Record<string, unknown> | undefined): Record<string, unknown> {
  return typeof block?.style === "object" && block.style !== null
    ? (block.style as Record<string, unknown>)
    : {};
}

function styleValue(
  template: SubtitleTemplateSet | undefined,
  role: string,
  key: string,
  fallback: string,
): string {
  const fromTemplate = template?.templates?.[role]?.[key];
  if (fromTemplate !== undefined && fromTemplate !== null) {
    return String(fromTemplate);
  }
  const fromBlock = blockStyle(template?.blocks.find((block) => block.role === role))[key];
  return fromBlock !== undefined && fromBlock !== null ? String(fromBlock) : fallback;
}

function stylePatch(
  template: SubtitleTemplateSet | undefined,
  role: string,
  patch: Record<string, unknown>,
): Partial<SubtitleTemplateSet> {
  const blocks = template?.blocks ?? [];
  return {
    templates: {
      ...(template?.templates ?? {}),
      [role]: {
        ...(template?.templates?.[role] ?? {}),
        ...patch,
      },
    },
    blocks: blocks.map((block) =>
      block.role === role
        ? {
            ...block,
            style: {
              ...blockStyle(block),
              ...patch,
            },
          }
        : block,
    ),
  };
}

function previewErrorText(error: unknown): string {
  const code =
    error instanceof Error
      ? error.message
      : typeof error === "object" && error !== null && "code" in error
        ? String(error.code)
        : "";
  return code === "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"
    ? "预览渲染不可用"
    : "预览生成失败";
}

function mutationErrorText(_error: unknown, fallback: string): string {
  return fallback;
}

function numericPatchValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function persistentStyleValue(key: string, value: string): string | number {
  if (key === "font_size_scale") {
    return numericPatchValue(value, 1);
  }
  if (key === "max_width") {
    return numericPatchValue(value, 0.86);
  }
  if (
    key === "outline_width" ||
    key === "shadow" ||
    key === "margin_v" ||
    key === "rotate" ||
    key === "skew"
  ) {
    return numericPatchValue(value, 0);
  }
  return value;
}

function createTemplateCopyInput(
  template: SubtitleTemplateSet | undefined,
  isTemplatePreset: boolean,
): {
  name: string;
  preset_id?: string;
  source_id?: string;
} {
  const name = `我的${template?.name ?? "字幕模板"}`;
  if (!template) {
    return { name };
  }
  return isTemplatePreset
    ? { name, preset_id: template.id }
    : { name, source_id: template.id };
}

type SaveTemplateVariables = {
  id: string;
  patch: Partial<SubtitleTemplateSet>;
  draftRevision: number;
};

type SaveErrorPlacement = "editor" | "preview";

export function SubtitleTemplateWorkbench() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, SubtitleTemplateSet>>({});
  const [saveErrorPlacement, setSaveErrorPlacement] = useState<SaveErrorPlacement>("editor");
  const [sampleText, setSampleText] = useState("AI 自动完成重复工作");
  const [previewAspectRatio, setPreviewAspectRatio] = useState("9:16");
  const [keyword, setKeyword] = useState("AI");
  const [keywordColor, setKeywordColor] = useState("#FFD54F");
  const draftRevisionByTemplate = useRef<Record<string, number>>({});

  const templates = useQuery({
    queryKey: ["subtitle-template-sets"],
    queryFn: fetchSubtitleTemplateSets,
  });
  const customTemplates = templates.data?.items ?? [];
  const presetTemplates = templates.data?.presets ?? [];
  const presetTemplateIds = useMemo(
    () => new Set(presetTemplates.map((template) => template.id)),
    [presetTemplates],
  );
  const allTemplates = useMemo(
    () => [...presetTemplates, ...customTemplates],
    [customTemplates, presetTemplates],
  );
  const defaultTemplate = selectAutoSubtitleTemplate(customTemplates, presetTemplates);
  const selected =
    allTemplates.find((template) => template.id === selectedId) ?? defaultTemplate;
  const selectedDraft = selected ? (templateDrafts[selected.id] ?? selected) : undefined;
  const isSelectedPreset = isPresetTemplate(selected, presetTemplateIds);
  const isEditable = Boolean(selected && !isSelectedPreset);
  const availableTemplateCount = allTemplates.length;

  const invalidateTemplates = () => {
    void queryClient.invalidateQueries({ queryKey: ["subtitle-template-sets"] });
  };

  const nextDraftRevision = (templateId: string): number => {
    const revision = (draftRevisionByTemplate.current[templateId] ?? 0) + 1;
    draftRevisionByTemplate.current[templateId] = revision;
    return revision;
  };

  const saveTemplate = useMutation({
    mutationFn: ({ id, patch }: SaveTemplateVariables) =>
      updateSubtitleTemplateSet({ id, patch }),
    onSuccess: (template, variables) => {
      if (draftRevisionByTemplate.current[variables.id] !== variables.draftRevision) {
        return;
      }
      setTemplateDrafts((current) => ({ ...current, [template.id]: template }));
      invalidateTemplates();
    },
  });

  const markDefault = useMutation({
    mutationFn: () =>
      isSelectedPreset
        ? updateSubtitlePresetOverride({
            id: String(selected?.id),
            patch: { is_favorite: true },
          })
        : updateSubtitleTemplateSet({
            id: String(selected?.id),
            patch: { is_favorite: true },
          }),
    onSuccess: invalidateTemplates,
  });

  const resetPreset = useMutation({
    mutationFn: () => resetSubtitlePresetOverride(String(selected?.id)),
    onSuccess: invalidateTemplates,
  });

  const validateTemplate = useMutation({
    mutationFn: () => validateSubtitleTemplateSet(selectedDraft as SubtitleTemplateSet),
  });

  const precisePreview = useMutation({
    mutationFn: () =>
      previewSubtitleTemplateSet({
        template_set: selectedDraft as SubtitleTemplateSet,
        template_type: "bottom",
        aspect_ratio: previewAspectRatio,
        sample_text: sampleText,
      }),
  });

  const timelinePreview = useMutation({
    mutationFn: () =>
      previewSubtitleTimeline({
        template_set: selectedDraft as SubtitleTemplateSet,
        template_type: "bottom",
        aspect_ratio: previewAspectRatio,
        sample_text: sampleText,
        duration_ms: 1200,
      }),
  });

  const imagePreviewSrc = precisePreview.data
    ? `data:${precisePreview.data.mime_type};base64,${precisePreview.data.data}`
    : "";
  const timelinePreviewSrc = timelinePreview.data
    ? `data:${timelinePreview.data.mime_type};base64,${timelinePreview.data.data}`
    : "";

  const resetPreviewResultState = () => {
    validateTemplate.reset();
    precisePreview.reset();
    timelinePreview.reset();
  };

  const createFromPreset = useMutation({
    mutationFn: () => createSubtitleTemplateSet(createTemplateCopyInput(selected, isSelectedPreset)),
    onSuccess: (template) => {
      resetPreviewResultState();
      saveTemplate.reset();
      markDefault.reset();
      resetPreset.reset();
      setSelectedId(template.id);
      invalidateTemplates();
    },
  });

  const resetTemplateResultState = () => {
    resetPreviewResultState();
    createFromPreset.reset();
    markDefault.reset();
    resetPreset.reset();
    saveTemplate.reset();
  };

  const handleSelectTemplate = (templateId: string) => {
    resetTemplateResultState();
    setSelectedId(templateId);
  };

  const handleSampleTextChange = (value: string) => {
    resetTemplateResultState();
    setSampleText(value);
  };

  const handlePreviewAspectRatioChange = (value: string) => {
    resetTemplateResultState();
    setPreviewAspectRatio(value);
  };

  const handleKeywordChange = (value: string) => {
    resetTemplateResultState();
    setKeyword(value);
  };

  const handleKeywordColorChange = (value: string) => {
    resetTemplateResultState();
    setKeywordColor(value);
  };

  const updateStyleDraft = (role: string, key: string, value: string) => {
    if (!selected || !isEditable) {
      return;
    }
    resetTemplateResultState();
    nextDraftRevision(selected.id);
    setTemplateDrafts((current) => {
      const base = current[selected.id] ?? selected;
      return {
        ...current,
        [selected.id]: {
          ...base,
          ...stylePatch(base, role, { [key]: value }),
        },
      };
    });
  };

  const saveStyleValue = (role: string, key: string, value: string) => {
    if (!selected || !isEditable) {
      return;
    }
    resetTemplateResultState();
    setSaveErrorPlacement("editor");
    const draftRevision = nextDraftRevision(selected.id);
    const base = templateDrafts[selected.id] ?? selected;
    const patch = stylePatch(base, role, { [key]: persistentStyleValue(key, value) });
    const nextTemplate = { ...base, ...patch };
    setTemplateDrafts((current) => ({ ...current, [selected.id]: nextTemplate }));
    saveTemplate.mutate({ id: selected.id, patch, draftRevision });
  };

  const saveKeywordHighlight = () => {
    if (!selected || !selectedDraft) {
      return;
    }
    resetTemplateResultState();
    setSaveErrorPlacement("preview");
    const draftRevision = nextDraftRevision(selected.id);
    const patch = {
      blocks: selectedDraft.blocks.map((block) =>
        block.role === "bottom"
          ? {
              ...block,
              spans: [
                ...(Array.isArray(block.spans) ? block.spans : []),
                {
                  selector: { type: "keyword", value: keyword },
                  style: { primary_color: keywordColor },
                },
              ],
            }
          : block,
      ),
    };
    setTemplateDrafts((current) => ({
      ...current,
      [selected.id]: {
        ...selectedDraft,
        ...patch,
      },
    }));
    saveTemplate.mutate({
      id: selected.id,
      patch,
      draftRevision,
    });
  };

  return (
    <article
      aria-label="字幕模板"
      className="panel subtitle-template-workbench"
      data-mobile-layout="stacked-template-preview-editor"
    >
      <div className="panel-heading">
        <h2>字幕模板</h2>
        <div className="status-inline" aria-live="polite">
          <span>{selected ? `当前模板：${selected.name}` : "暂无可用字幕模板"}</span>
        </div>
      </div>
      <div aria-live="polite" className="runtime-status" role="status">
        {templates.isLoading
          ? "正在加载模板"
          : templates.isError
            ? "模板加载失败"
            : `可用模板 ${availableTemplateCount} 个`}
      </div>

      <div className="subtitle-workbench-grid">
        <section
          aria-label="字幕模板列表"
          className="subtitle-template-list"
          data-mobile-layout="horizontal-scroll-on-mobile"
        >
          {allTemplates.map((template) => (
            <button
              aria-pressed={selected?.id === template.id}
              key={template.id}
              type="button"
              onClick={() => handleSelectTemplate(template.id)}
            >
              <span>{template.name}</span>
              {template.is_favorite || template.favorite ? (
                <strong aria-hidden="true">默认</strong>
              ) : null}
            </button>
          ))}
          <button
            disabled={!selected || createFromPreset.isPending}
            type="button"
            onClick={() => {
              resetTemplateResultState();
              createFromPreset.mutate();
            }}
          >
            <CopyPlus aria-hidden="true" size={16} />
            从预设新建
          </button>
          <button
            disabled={!selected || markDefault.isPending}
            type="button"
            onClick={() => {
              resetTemplateResultState();
              markDefault.mutate();
            }}
          >
            <Check aria-hidden="true" size={16} />
            设为默认
          </button>
          <button
            disabled={!isSelectedPreset || resetPreset.isPending}
            type="button"
            onClick={() => {
              resetTemplateResultState();
              resetPreset.mutate();
            }}
          >
            <RotateCcw aria-hidden="true" size={16} />
            还原预设
          </button>
          {createFromPreset.isError ? (
            <p role="alert">
              {mutationErrorText(createFromPreset.error, "字幕模板新建失败")}
            </p>
          ) : null}
          {markDefault.isError ? (
            <p role="alert">
              {mutationErrorText(markDefault.error, "默认字幕模板设置失败")}
            </p>
          ) : null}
          {resetPreset.isError ? (
            <p role="alert">{mutationErrorText(resetPreset.error, "预设还原失败")}</p>
          ) : null}
        </section>

        <section className="subtitle-preview-panel" aria-label="字幕预览">
          <label>
            <span>示例文本</span>
            <input
              value={sampleText}
              onChange={(event) => handleSampleTextChange(event.target.value)}
            />
          </label>
          <label>
            <span>预览画幅</span>
            <select
              value={previewAspectRatio}
              onChange={(event) => handlePreviewAspectRatioChange(event.target.value)}
            >
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
          <label>
            <span>局部关键词</span>
            <input value={keyword} onChange={(event) => handleKeywordChange(event.target.value)} />
          </label>
          <label>
            <span>局部高亮色</span>
            <input
              value={keywordColor}
              onChange={(event) => handleKeywordColorChange(event.target.value)}
            />
          </label>
          <div
            className="subtitle-preview-frame"
            data-testid="subtitle-preview-frame"
            style={{ aspectRatio: previewAspectRatio === "16:9" ? "16 / 9" : "9 / 16" }}
          >
            <span>{sampleText}</span>
          </div>
          <div className="button-row">
            <button
              disabled={!selected || validateTemplate.isPending}
              type="button"
              onClick={() => validateTemplate.mutate()}
            >
              <Check aria-hidden="true" size={16} />
              校验模板
            </button>
            <button
              disabled={!isEditable || saveTemplate.isPending}
              type="button"
              onClick={saveKeywordHighlight}
            >
              <Save aria-hidden="true" size={16} />
              保存局部高亮
            </button>
            <button
              disabled={!selected || precisePreview.isPending}
              type="button"
              onClick={() => precisePreview.mutate()}
            >
              <WandSparkles aria-hidden="true" size={16} />
              精准预览
            </button>
            <button
              disabled={!selected || timelinePreview.isPending}
              type="button"
              onClick={() => timelinePreview.mutate()}
            >
              <Play aria-hidden="true" size={16} />
              时间线预览
            </button>
          </div>
          {saveTemplate.isError && saveErrorPlacement === "preview" ? (
            <p role="alert">
              {mutationErrorText(saveTemplate.error, "字幕模板保存失败")}
            </p>
          ) : null}
          {imagePreviewSrc ? <img alt="字幕精准预览" src={imagePreviewSrc} /> : null}
          {timelinePreviewSrc ? (
            <video controls data-testid="subtitle-timeline-preview" src={timelinePreviewSrc}>
              <track kind="captions" />
            </video>
          ) : null}
          {validateTemplate.data?.warnings.length ? (
            <p role="alert">{validateTemplate.data.warnings.join("；")}</p>
          ) : null}
          {precisePreview.isError ? (
            <p role="alert">{previewErrorText(precisePreview.error)}</p>
          ) : null}
          {timelinePreview.isError ? (
            <p role="alert">{previewErrorText(timelinePreview.error)}</p>
          ) : null}
        </section>

        <section className="subtitle-editor-panel" aria-label="字幕块编辑">
          {saveTemplate.isError && saveErrorPlacement === "editor" ? (
            <p role="alert">
              {mutationErrorText(saveTemplate.error, "字幕模板保存失败")}
            </p>
          ) : null}
          {editableRoles.map(({ role, label }) => (
            <fieldset key={role}>
              <legend>{label}</legend>
              <label>
                <span>字体</span>
                <select
                  disabled={!isEditable}
                  value={styleValue(selectedDraft, role, "font_family", "PingFang SC")}
                  onChange={(event) => {
                    updateStyleDraft(role, "font_family", event.target.value);
                    saveStyleValue(role, "font_family", event.target.value);
                  }}
                >
                  <option value="PingFang SC">PingFang SC</option>
                  <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
                </select>
              </label>
              <label>
                <span>主色</span>
                <input
                  disabled={!isEditable}
                  value={styleValue(selectedDraft, role, "primary_color", "#FFFFFF")}
                  onBlur={(event) => saveStyleValue(role, "primary_color", event.target.value)}
                  onChange={(event) =>
                    updateStyleDraft(role, "primary_color", event.target.value)
                  }
                />
              </label>
              <label>
                <span>字号比例</span>
                <input
                  disabled={!isEditable}
                  inputMode="decimal"
                  value={styleValue(selectedDraft, role, "font_size_scale", "1")}
                  onBlur={(event) => saveStyleValue(role, "font_size_scale", event.target.value)}
                  onChange={(event) =>
                    updateStyleDraft(role, "font_size_scale", event.target.value)
                  }
                />
              </label>
              <label>
                <span>描边宽度</span>
                <input
                  disabled={!isEditable}
                  inputMode="numeric"
                  value={styleValue(selectedDraft, role, "outline_width", "2")}
                  onBlur={(event) => saveStyleValue(role, "outline_width", event.target.value)}
                  onChange={(event) =>
                    updateStyleDraft(role, "outline_width", event.target.value)
                  }
                />
              </label>
              <label>
                <span>阴影强度</span>
                <input
                  disabled={!isEditable}
                  inputMode="numeric"
                  value={styleValue(selectedDraft, role, "shadow", "0")}
                  onBlur={(event) => saveStyleValue(role, "shadow", event.target.value)}
                  onChange={(event) => updateStyleDraft(role, "shadow", event.target.value)}
                />
              </label>
              <label>
                <span>垂直位置</span>
                <input
                  disabled={!isEditable}
                  inputMode="numeric"
                  value={styleValue(selectedDraft, role, "margin_v", "96")}
                  onBlur={(event) => saveStyleValue(role, "margin_v", event.target.value)}
                  onChange={(event) => updateStyleDraft(role, "margin_v", event.target.value)}
                />
              </label>
              <label>
                <span>最大宽度</span>
                <input
                  disabled={!isEditable}
                  inputMode="decimal"
                  value={styleValue(selectedDraft, role, "max_width", "0.86")}
                  onBlur={(event) => saveStyleValue(role, "max_width", event.target.value)}
                  onChange={(event) => updateStyleDraft(role, "max_width", event.target.value)}
                />
              </label>
              <label>
                <span>旋转</span>
                <input
                  disabled={!isEditable}
                  inputMode="numeric"
                  value={styleValue(selectedDraft, role, "rotate", "0")}
                  onBlur={(event) => saveStyleValue(role, "rotate", event.target.value)}
                  onChange={(event) => updateStyleDraft(role, "rotate", event.target.value)}
                />
              </label>
              <label>
                <span>倾斜</span>
                <input
                  disabled={!isEditable}
                  inputMode="numeric"
                  value={styleValue(selectedDraft, role, "skew", "0")}
                  onBlur={(event) => saveStyleValue(role, "skew", event.target.value)}
                  onChange={(event) => updateStyleDraft(role, "skew", event.target.value)}
                />
              </label>
            </fieldset>
          ))}
        </section>
      </div>
    </article>
  );
}
