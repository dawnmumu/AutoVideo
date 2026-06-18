import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CopyPlus, Play, RotateCcw, WandSparkles } from "lucide-react";
import type { CSSProperties } from "react";
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
import {
  SubtitleLocalStyleEditor,
  roleSpans,
  spansPatch,
  updateSpanAt,
} from "./SubtitleLocalStyleEditor";
import type { SubtitleSpan } from "./SubtitleLocalStyleEditor";
import { selectAutoSubtitleTemplate } from "./subtitleTemplateSelection";

const editableRoles = [
  { role: "bottom", label: "底部字幕" },
  { role: "highlight", label: "强调字幕" },
  { role: "punch", label: "冲击字幕" },
] as const;

type SubtitleRole = (typeof editableRoles)[number]["role"];

const previewRoleDefaults: Record<SubtitleRole, { x: number; y: number; fontSize: number }> = {
  bottom: { x: 50, y: 78, fontSize: 54 },
  highlight: { x: 50, y: 52, fontSize: 60 },
  punch: { x: 50, y: 30, fontSize: 68 },
};

const previewRoleLaneCandidates: Record<SubtitleRole, number[]> = {
  bottom: [78, 64, 86],
  highlight: [52, 64, 40],
  punch: [30, 18, 42],
};

function isPresetTemplate(
  template: SubtitleTemplateSet | undefined,
  presetTemplateIds: ReadonlySet<string>,
): boolean {
  return Boolean(template && presetTemplateIds.has(template.id));
}

function roleBlock(
  template: SubtitleTemplateSet | undefined,
  role: string,
): Record<string, unknown> | undefined {
  return template?.blocks.find((block) => block.role === role);
}

function blockStyle(block: Record<string, unknown> | undefined): Record<string, unknown> {
  return typeof block?.style === "object" && block.style !== null
    ? (block.style as Record<string, unknown>)
    : {};
}

function blockPosition(block: Record<string, unknown> | undefined): Record<string, unknown> {
  return typeof block?.position === "object" && block.position !== null
    ? (block.position as Record<string, unknown>)
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
  const fromBlock = blockStyle(roleBlock(template, role))[key];
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

function numericStyleValue(
  template: SubtitleTemplateSet | undefined,
  role: string,
  key: string,
  fallback: number,
): number {
  const value = Number(styleValue(template, role, key, String(fallback)));
  return Number.isFinite(value) ? value : fallback;
}

function numericUnknownValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampValue(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function parseHexColor(value: string): { r: number; g: number; b: number } | null {
  const normalized = value.trim();
  const shortMatch = /^#([0-9a-f]{3})$/i.exec(normalized);
  if (shortMatch) {
    const [r, g, b] = shortMatch[1].split("").map((part) => parseInt(`${part}${part}`, 16));
    return { r, g, b };
  }

  const fullMatch = /^#([0-9a-f]{6})$/i.exec(normalized);
  if (!fullMatch) {
    return null;
  }

  return {
    r: parseInt(fullMatch[1].slice(0, 2), 16),
    g: parseInt(fullMatch[1].slice(2, 4), 16),
    b: parseInt(fullMatch[1].slice(4, 6), 16),
  };
}

function relativeLuminance({ r, g, b }: { r: number; g: number; b: number }): number {
  const [red, green, blue] = [r, g, b].map((channel) => {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(first: number, second: number): number {
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}

function blendRgbOver(
  foreground: { r: number; g: number; b: number; alpha: number },
  background: { r: number; g: number; b: number },
): { r: number; g: number; b: number } {
  return {
    r: foreground.r * foreground.alpha + background.r * (1 - foreground.alpha),
    g: foreground.g * foreground.alpha + background.g * (1 - foreground.alpha),
    b: foreground.b * foreground.alpha + background.b * (1 - foreground.alpha),
  };
}

function captionBackgroundForColor(color: string): string {
  const parsed = parseHexColor(color);
  if (!parsed) {
    return "rgba(17, 24, 39, 0.72)";
  }
  const textLuminance = relativeLuminance(parsed);
  const previewFrameBackground = { r: 17, g: 24, b: 39 };
  const lightBackground = {
    color: "rgba(255, 255, 255, 0.88)",
    luminance: relativeLuminance(
      blendRgbOver({ r: 255, g: 255, b: 255, alpha: 0.88 }, previewFrameBackground),
    ),
  };
  const darkBackground = {
    color: "rgba(17, 24, 39, 0.72)",
    luminance: relativeLuminance(
      blendRgbOver({ r: 17, g: 24, b: 39, alpha: 0.72 }, previewFrameBackground),
    ),
  };
  return contrastRatio(textLuminance, lightBackground.luminance) >
    contrastRatio(textLuminance, darkBackground.luminance)
    ? lightBackground.color
    : darkBackground.color;
}

function previewPercentValue(
  template: SubtitleTemplateSet | undefined,
  role: SubtitleRole,
  axis: "x" | "y",
  previewAspectRatio: string,
): number {
  const value = rawPreviewPercentValue(template, role, axis);
  if (axis === "y") {
    return previewRoleLaneValue(template, role, value, previewAspectRatio);
  }
  return value;
}

function previewRoleLaneValue(
  template: SubtitleTemplateSet | undefined,
  role: SubtitleRole,
  value: number,
  previewAspectRatio: string,
): number {
  const minGap = previewLaneMinGapPercent(previewAspectRatio);
  const occupied = editableRoles
    .slice(0, editableRoles.findIndex((item) => item.role === role))
    .map(({ role: previousRole }) =>
      previewPercentValue(template, previousRole, "y", previewAspectRatio),
    );
  if (!occupied.some((lane) => isPreviewLaneConflict(value, lane, minGap))) {
    return value;
  }

  const candidates = [
    ...previewRoleLaneCandidates[role],
    previewRoleDefaults[role].y,
    value + minGap,
    value - minGap,
    value + minGap * 2,
    value - minGap * 2,
  ];
  const safeLane = candidates.find(
    (candidate) =>
      candidate >= 8 &&
      candidate <= 92 &&
      !occupied.some((lane) => isPreviewLaneConflict(candidate, lane, minGap)),
  );
  return safeLane ?? value;
}

function previewLaneMinGapPercent(previewAspectRatio: string): number {
  return previewAspectRatio === "16:9" ? 18 : 10;
}

function isPreviewLaneConflict(first: number, second: number, minGap: number): boolean {
  return Math.abs(first - second) < minGap;
}

function rawPreviewPercentValue(
  template: SubtitleTemplateSet | undefined,
  role: SubtitleRole,
  axis: "x" | "y",
): number {
  const key = `${axis}_percent`;
  const block = roleBlock(template, role);
  const position = blockPosition(block);
  const positionValue = position[axis];
  const fallback =
    typeof positionValue === "number"
      ? positionValue <= 1
        ? positionValue * 100
        : positionValue
      : previewRoleDefaults[role][axis];
  return clampValue(numericStyleValue(template, role, key, fallback), 0, 100);
}

function previewTranslateForAlignment(alignment: string): string {
  if (alignment === "left") {
    return "translate(0, -50%)";
  }
  if (alignment === "right") {
    return "translate(-100%, -50%)";
  }
  return "translate(-50%, -50%)";
}

function subtitlePreviewCaptionStyle(
  template: SubtitleTemplateSet | undefined,
  role: SubtitleRole,
  previewAspectRatio: string,
): CSSProperties {
  const primaryColor = styleValue(template, role, "primary_color", "#FFFFFF");
  const fontSize = numericStyleValue(template, role, "font_size", previewRoleDefaults[role].fontSize);
  const fontScale = numericStyleValue(
    template,
    role,
    "font_size_scale",
    numericStyleValue(template, role, "font_scale", 1),
  );
  const maxWidth = numericStyleValue(
    template,
    role,
    "max_width",
    numericStyleValue(template, role, "max_width_ratio", 0.86),
  );
  const marginV = numericStyleValue(template, role, "margin_v", 96);
  const rotate = numericStyleValue(
    template,
    role,
    "rotate",
    numericStyleValue(template, role, "angle", 0),
  );
  const skew = numericStyleValue(
    template,
    role,
    "skew",
    numericStyleValue(template, role, "skew_x_deg", 0),
  );
  const outlineWidth = numericStyleValue(template, role, "outline_width", 2);
  const shadowDepth = numericStyleValue(
    template,
    role,
    "shadow",
    numericStyleValue(template, role, "shadow_depth", 0),
  );
  const skewY = numericStyleValue(template, role, "skew_y_deg", 0);
  const alignment = styleValue(template, role, "alignment", "center");
  const previewFontSize = Math.round(
    clampValue(fontSize / 54, 0.82, 1.35) * 16 * clampValue(fontScale, 0.6, 1.8),
  );
  const previewOutline = clampValue(outlineWidth, 0, 8) / 2;
  const previewShadow = clampValue(shadowDepth, 0, 8);

  return {
    backgroundColor: captionBackgroundForColor(primaryColor),
    color: parseHexColor(primaryColor) ? primaryColor : "#FFFFFF",
    fontFamily: styleValue(template, role, "font_family", "PingFang SC"),
    fontSize: `${previewFontSize}px`,
    left: `${previewPercentValue(template, role, "x", previewAspectRatio)}%`,
    top:
      template?.templates?.[role]?.y_percent !== undefined ||
      blockStyle(roleBlock(template, role)).y_percent !== undefined ||
      blockPosition(roleBlock(template, role)).y !== undefined
        ? `${previewPercentValue(template, role, "y", previewAspectRatio)}%`
        : `calc(${previewPercentValue(template, role, "y", previewAspectRatio)}% - ${Math.round(
            clampValue(marginV, 0, 180) / 12,
          )}px)`,
    maxWidth: `${Math.round(clampValue(maxWidth, 0.4, 1) * 100)}%`,
    textShadow:
      previewShadow > 0
        ? `0 ${Math.ceil(previewShadow / 2)}px ${previewShadow}px ${styleValue(
            template,
            role,
            "shadow_color",
            "#000000",
          )}`
        : "none",
    textAlign: alignment === "left" || alignment === "right" ? alignment : "center",
    transform: `${previewTranslateForAlignment(alignment)} rotate(${rotate}deg) skewX(${skew}deg) skewY(${skewY}deg)`,
    WebkitTextStroke:
      previewOutline > 0
        ? `${previewOutline}px ${styleValue(template, role, "outline_color", "#111111")}`
        : undefined,
  };
}

function previewSpanStyle(span: SubtitleSpan, baseFontSizePx: number): CSSProperties {
  const style = typeof span.style === "object" && span.style !== null ? span.style : {};
  const primaryColor = typeof style.primary_color === "string" ? style.primary_color : "";
  const fontScale = numericUnknownValue(style.font_scale, 1);
  const fontSize =
    style.font_size !== undefined
      ? numericUnknownValue(style.font_size, baseFontSizePx)
      : baseFontSizePx * clampValue(fontScale, 0.5, 1.8);
  const outlineWidth =
    style.outline_width !== undefined ? clampValue(numericUnknownValue(style.outline_width, 0), 0, 8) : 0;
  const shadowDepth =
    style.shadow !== undefined || style.shadow_depth !== undefined
      ? clampValue(numericUnknownValue(style.shadow ?? style.shadow_depth, 0), 0, 8)
      : 0;

  return {
    color: parseHexColor(primaryColor) ? primaryColor : undefined,
    fontFamily: typeof style.font_family === "string" ? style.font_family : undefined,
    fontSize: `${Math.round(fontSize)}px`,
    textShadow:
      shadowDepth > 0
        ? `0 ${Math.ceil(shadowDepth / 2)}px ${shadowDepth}px ${
            typeof style.shadow_color === "string" ? style.shadow_color : "#000000"
          }`
        : undefined,
    WebkitTextStroke:
      outlineWidth > 0
        ? `${outlineWidth / 2}px ${
            typeof style.outline_color === "string" ? style.outline_color : "#111111"
          }`
        : undefined,
  };
}

function spanPreviewRanges(text: string, spans: SubtitleSpan[]): Array<{ start: number; end: number; span: SubtitleSpan; spanIndex: number }> {
  const ranges: Array<{ start: number; end: number; span: SubtitleSpan; spanIndex: number }> = [];

  spans.forEach((span, spanIndex) => {
    const selector = typeof span.selector === "object" && span.selector !== null ? span.selector : {};
    const type = selector.type;
    let start = -1;
    let end = -1;

    if (type === "keyword" && typeof selector.value === "string" && selector.value) {
      start = text.indexOf(selector.value);
      if (start === -1) {
        return;
      }
      end = start + selector.value.length;
    } else if (type === "range") {
      start = Math.trunc(numericUnknownValue(selector.start, -1));
      end = Math.trunc(numericUnknownValue(selector.end, -1));
    }

    start = clampValue(start, 0, text.length);
    end = clampValue(end, 0, text.length);
    if (end <= start || ranges.some((range) => start < range.end && end > range.start)) {
      return;
    }

    ranges.push({ start, end, span, spanIndex });
  });

  return ranges.sort((first, second) => first.start - second.start);
}

function renderPreviewCaptionText(
  text: string,
  spans: SubtitleSpan[],
  role: SubtitleRole,
  baseFontSizePx: number,
) {
  const ranges = spanPreviewRanges(text, spans);
  if (!ranges.length) {
    return text;
  }

  const parts: Array<string | JSX.Element> = [];
  let cursor = 0;
  ranges.forEach((range) => {
    if (range.start > cursor) {
      parts.push(text.slice(cursor, range.start));
    }
    parts.push(
      <span
        className="subtitle-preview-local-span"
        data-testid={`subtitle-preview-local-span-${role}-${range.spanIndex}`}
        key={`${role}-${range.spanIndex}-${range.start}`}
        style={previewSpanStyle(range.span, baseFontSizePx)}
      >
        {text.slice(range.start, range.end)}
      </span>,
    );
    cursor = range.end;
  });
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return parts;
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

type SaveErrorPlacement = "editor";

export function SubtitleTemplateWorkbench() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, SubtitleTemplateSet>>({});
  const [saveErrorPlacement, setSaveErrorPlacement] = useState<SaveErrorPlacement>("editor");
  const [sampleText, setSampleText] = useState("AI 自动完成重复工作");
  const [previewAspectRatio, setPreviewAspectRatio] = useState("9:16");
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

  const setRoleSpansDraft = (role: string, spans: SubtitleSpan[]) => {
    if (!selected || !isEditable) {
      return;
    }
    resetTemplateResultState();
    nextDraftRevision(selected.id);
    setTemplateDrafts((current) => ({
      ...current,
      [selected.id]: {
        ...(current[selected.id] ?? selected),
        ...spansPatch(current[selected.id] ?? selected, role, spans),
      },
    }));
  };

  const saveRoleSpans = (role: string, spans: SubtitleSpan[]) => {
    if (!selected || !isEditable) {
      return;
    }
    resetTemplateResultState();
    setSaveErrorPlacement("editor");
    const draftRevision = nextDraftRevision(selected.id);
    const base = templateDrafts[selected.id] ?? selected;
    const patch = spansPatch(base, role, spans);
    setTemplateDrafts((current) => ({
      ...current,
      [selected.id]: {
        ...base,
        ...patch,
      },
    }));
    saveTemplate.mutate({
      id: selected.id,
      patch,
      draftRevision,
    });
  };

  const updateSpanDraft = (
    role: string,
    index: number,
    updater: (span: SubtitleSpan) => SubtitleSpan,
  ) => {
    const spans = updateSpanAt(roleSpans(selectedDraft, role), index, updater);
    setRoleSpansDraft(role, spans);
  };

  const saveSpanValue = (
    role: string,
    index: number,
    updater: (span: SubtitleSpan) => SubtitleSpan,
  ) => {
    const base = templateDrafts[selected?.id ?? ""] ?? selectedDraft;
    const spans = updateSpanAt(roleSpans(base, role), index, updater);
    saveRoleSpans(role, spans);
  };

  const addLocalSpan = (role: string) => {
    const defaultKeyword = sampleText.trim().slice(0, 2) || "AI";
    saveRoleSpans(role, [
      ...roleSpans(selectedDraft, role),
      {
        selector: { type: "keyword", value: defaultKeyword },
        style: { primary_color: "#FFD54F", font_scale: 1.08 },
      },
    ]);
  };

  const deleteLocalSpan = (role: string, index: number) => {
    saveRoleSpans(
      role,
      roleSpans(selectedDraft, role).filter((_span, spanIndex) => spanIndex !== index),
    );
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
          <div className="subtitle-preview-stack" data-layout="bounded-preview-controls">
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
            <div
              className="subtitle-preview-frame"
              data-testid="subtitle-preview-frame"
              style={{ aspectRatio: previewAspectRatio === "16:9" ? "16 / 9" : "9 / 16" }}
            >
              {editableRoles.map(({ role, label }) => {
                const captionStyle = subtitlePreviewCaptionStyle(
                  selectedDraft,
                  role,
                  previewAspectRatio,
                );
                const baseFontSize = Number.parseFloat(String(captionStyle.fontSize ?? "16")) || 16;
                return (
                  <span
                    aria-label={`${label}预览`}
                    className={`subtitle-preview-caption subtitle-preview-caption-${role}`}
                    data-testid={`subtitle-preview-caption-${role}`}
                    key={role}
                    style={captionStyle}
                  >
                    {renderPreviewCaptionText(sampleText, roleSpans(selectedDraft, role), role, baseFontSize)}
                  </span>
                );
              })}
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
            {timelinePreview.isError ? (
              <p role="alert">{previewErrorText(timelinePreview.error)}</p>
            ) : null}
          </div>
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
              <SubtitleLocalStyleEditor
                isEditable={isEditable}
                label={label}
                role={role}
                sampleText={sampleText}
                spans={roleSpans(selectedDraft, role)}
                onAdd={addLocalSpan}
                onDelete={deleteLocalSpan}
                onSaveSpanValue={saveSpanValue}
                onUpdateSpanDraft={updateSpanDraft}
              />
            </fieldset>
          ))}
        </section>
      </div>
    </article>
  );
}
