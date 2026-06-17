import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CopyPlus, Play, RotateCcw, Save, WandSparkles } from "lucide-react";
import { useMemo, useState } from "react";

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

const editableRoles = [
  { role: "bottom", label: "底部字幕" },
  { role: "highlight", label: "强调字幕" },
  { role: "punch", label: "冲击字幕" },
] as const;

function isPreset(template: SubtitleTemplateSet | undefined): boolean {
  return Boolean(template?.id.startsWith("preset-"));
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

function numericPatchValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function SubtitleTemplateWorkbench() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sampleText, setSampleText] = useState("AI 自动完成重复工作");
  const [previewAspectRatio, setPreviewAspectRatio] = useState("9:16");
  const [keyword, setKeyword] = useState("AI");
  const [keywordColor, setKeywordColor] = useState("#FFD54F");

  const templates = useQuery({
    queryKey: ["subtitle-template-sets"],
    queryFn: fetchSubtitleTemplateSets,
  });
  const allTemplates = useMemo(
    () => [...(templates.data?.presets ?? []), ...(templates.data?.items ?? [])],
    [templates.data],
  );
  const defaultTemplate =
    allTemplates.find((template) => template.is_favorite || template.favorite) ?? allTemplates[0];
  const selected =
    allTemplates.find((template) => template.id === selectedId) ?? defaultTemplate;
  const isSelectedPreset = isPreset(selected);
  const isEditable = Boolean(selected && !isSelectedPreset);
  const availableTemplateCount = allTemplates.length;

  const invalidateTemplates = () => {
    void queryClient.invalidateQueries({ queryKey: ["subtitle-template-sets"] });
  };

  const createFromPreset = useMutation({
    mutationFn: () =>
      createSubtitleTemplateSet({
        name: `我的${selected?.name ?? "字幕模板"}`,
        preset_id: selected?.id ?? null,
      }),
    onSuccess: (template) => {
      setSelectedId(template.id);
      invalidateTemplates();
    },
  });

  const saveTemplate = useMutation({
    mutationFn: (patch: Partial<SubtitleTemplateSet>) =>
      updateSubtitleTemplateSet({ id: String(selected?.id), patch }),
    onSuccess: invalidateTemplates,
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
    mutationFn: () => validateSubtitleTemplateSet(selected as SubtitleTemplateSet),
  });

  const precisePreview = useMutation({
    mutationFn: () =>
      previewSubtitleTemplateSet({
        template_set: selected as SubtitleTemplateSet,
        template_type: "bottom",
        aspect_ratio: previewAspectRatio,
        sample_text: sampleText,
      }),
  });

  const timelinePreview = useMutation({
    mutationFn: () =>
      previewSubtitleTimeline({
        template_set: selected as SubtitleTemplateSet,
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

  const saveKeywordHighlight = () => {
    if (!selected) {
      return;
    }
    saveTemplate.mutate({
      blocks: selected.blocks.map((block) =>
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
              aria-selected={selected?.id === template.id}
              key={template.id}
              type="button"
              onClick={() => setSelectedId(template.id)}
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
            onClick={() => createFromPreset.mutate()}
          >
            <CopyPlus aria-hidden="true" size={16} />
            从预设新建
          </button>
          <button
            disabled={!selected || markDefault.isPending}
            type="button"
            onClick={() => markDefault.mutate()}
          >
            <Check aria-hidden="true" size={16} />
            设为默认
          </button>
          <button
            disabled={!isSelectedPreset || resetPreset.isPending}
            type="button"
            onClick={() => resetPreset.mutate()}
          >
            <RotateCcw aria-hidden="true" size={16} />
            还原预设
          </button>
        </section>

        <section className="subtitle-preview-panel" aria-label="字幕预览">
          <label>
            <span>示例文本</span>
            <input value={sampleText} onChange={(event) => setSampleText(event.target.value)} />
          </label>
          <label>
            <span>预览画幅</span>
            <select
              value={previewAspectRatio}
              onChange={(event) => setPreviewAspectRatio(event.target.value)}
            >
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
          <label>
            <span>局部关键词</span>
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          </label>
          <label>
            <span>局部高亮色</span>
            <input
              value={keywordColor}
              onChange={(event) => setKeywordColor(event.target.value)}
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
        </section>

        <section className="subtitle-editor-panel" aria-label="字幕块编辑">
          {editableRoles.map(({ role, label }) => (
            <fieldset key={role}>
              <legend>{label}</legend>
              <label>
                <span>字体</span>
                <select
                  disabled={!isEditable || saveTemplate.isPending}
                  value={styleValue(selected, role, "font_family", "PingFang SC")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { font_family: event.target.value }))
                  }
                >
                  <option value="PingFang SC">PingFang SC</option>
                  <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
                </select>
              </label>
              <label>
                <span>主色</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  value={styleValue(selected, role, "primary_color", "#FFFFFF")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { primary_color: event.target.value }))
                  }
                />
              </label>
              <label>
                <span>字号比例</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="decimal"
                  value={styleValue(selected, role, "font_size_scale", "1")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        font_size_scale: numericPatchValue(event.target.value, 1),
                      }),
                    )
                  }
                />
              </label>
              <label>
                <span>描边宽度</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "outline_width", "2")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        outline_width: numericPatchValue(event.target.value, 0),
                      }),
                    )
                  }
                />
              </label>
              <label>
                <span>阴影强度</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "shadow", "0")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        shadow: numericPatchValue(event.target.value, 0),
                      }),
                    )
                  }
                />
              </label>
              <label>
                <span>垂直位置</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "margin_v", "96")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        margin_v: numericPatchValue(event.target.value, 0),
                      }),
                    )
                  }
                />
              </label>
              <label>
                <span>最大宽度</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="decimal"
                  value={styleValue(selected, role, "max_width", "0.86")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        max_width: numericPatchValue(event.target.value, 0.86),
                      }),
                    )
                  }
                />
              </label>
              <label>
                <span>旋转</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "rotate", "0")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        rotate: numericPatchValue(event.target.value, 0),
                      }),
                    )
                  }
                />
              </label>
              <label>
                <span>倾斜</span>
                <input
                  disabled={!isEditable || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "skew", "0")}
                  onChange={(event) =>
                    saveTemplate.mutate(
                      stylePatch(selected, role, {
                        skew: numericPatchValue(event.target.value, 0),
                      }),
                    )
                  }
                />
              </label>
            </fieldset>
          ))}
        </section>
      </div>
    </article>
  );
}
