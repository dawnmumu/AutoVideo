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
import { SubtitleRoleStyleFields } from "./SubtitleRoleStyleFields";
import type { SubtitleSpan } from "./SubtitleLocalStyleEditor";
import { selectAutoSubtitleTemplate } from "./subtitleTemplateSelection";

const editableRoles = [
  { role: "bottom", label: "底部字幕" },
  { role: "highlight", label: "强调字幕" },
  { role: "punch", label: "冲击字幕" },
] as const;

type SubtitleRole = (typeof editableRoles)[number]["role"];

type SubtitlePreviewTextEffects = {
  outlineColor: string;
  outlineWidthPx: number;
  shadowBlurPx: number;
  shadowColor: string;
  shadowOffsetPx: number;
};

const previewRoleDefaults: Record<SubtitleRole, { x: number; y: number; fontSize: number }> = {
  bottom: { x: 50, y: 78, fontSize: 54 },
  highlight: { x: 50, y: 52, fontSize: 60 },
  punch: { x: 50, y: 30, fontSize: 68 },
};
const defaultSubtitlePreviewText = "这是字幕预览，支持多个位置和不同倾斜角度";

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
      block.role === role ? blockWithStylePatch(block, role, patch) : block,
    ),
  };
}

function blockWithStylePatch(
  block: Record<string, unknown>,
  role: string,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const style = {
    ...blockStyle(block),
    ...patch,
  };
  const nextBlock = {
    ...block,
    style,
  };
  if (!hasLayoutStylePatch(patch)) {
    return nextBlock;
  }
  return {
    ...nextBlock,
    position: positionFromLayoutStyle(role, style, blockPosition(block)),
  };
}

function hasLayoutStylePatch(patch: Record<string, unknown>): boolean {
  return "x_percent" in patch || "y_percent" in patch || "alignment" in patch;
}

function positionFromLayoutStyle(
  role: string,
  style: Record<string, unknown>,
  position: Record<string, unknown>,
): Record<string, unknown> {
  const defaults =
    role in previewRoleDefaults
      ? previewRoleDefaults[role as SubtitleRole]
      : previewRoleDefaults.bottom;
  const xFallback = ratioOrPercentToPercent(position.x, defaults.x);
  const yFallback = ratioOrPercentToPercent(position.y, defaults.y);
  return {
    ...position,
    x: percentToRatio(style.x_percent, xFallback),
    y: percentToRatio(style.y_percent, yFallback),
    anchor: alignmentValue(style.alignment, alignmentValue(position.anchor, "center")),
  };
}

function ratioOrPercentToPercent(value: unknown, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  if (parsed >= 0 && parsed <= 1) {
    return parsed * 100;
  }
  return clampValue(parsed, 0, 100);
}

function percentToRatio(value: unknown, fallbackPercent: number): number {
  const parsed = Number(value);
  const percent = Number.isFinite(parsed) ? parsed : fallbackPercent;
  return Math.round(clampValue(percent, 0, 100) * 1000) / 100000;
}

function alignmentValue(value: unknown, fallback: string): string {
  return value === "left" || value === "center" || value === "right" ? value : fallback;
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
    key === "font_weight" ||
    key === "x_percent" ||
    key === "y_percent" ||
    key === "outline_width" ||
    key === "shadow" ||
    key === "margin_v" ||
    key === "rotate" ||
    key === "skew" ||
    key === "skew_y_deg"
  ) {
    return numericPatchValue(value, 0);
  }
  return value;
}

function styleFieldFallback(role: string, key: string): string {
  const defaults =
    role in previewRoleDefaults
      ? previewRoleDefaults[role as SubtitleRole]
      : previewRoleDefaults.bottom;
  switch (key) {
    case "accent_color":
      return "#FFD54F";
    case "alignment":
      return "center";
    case "background_color":
    case "shadow_color":
      return "#000000";
    case "decoration_shape":
      return "none";
    case "font_family":
      return "PingFang SC";
    case "font_size_scale":
      return "1";
    case "max_width":
      return "0.86";
    case "outline_color":
      return "#111111";
    case "outline_width":
      return "2";
    case "primary_color":
      return "#FFFFFF";
    case "rotate":
    case "shadow":
    case "skew":
    case "skew_y_deg":
      return "0";
    case "x_percent":
      return String(defaults.x);
    case "y_percent":
      return String(defaults.y);
    default:
      return "";
  }
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

function previewEffectPixels(value: number, scale: number): number {
  const rounded = Math.round(clampValue(value, 0, 12) * scale * 100) / 100;
  return rounded > 0 && rounded < 0.5 ? 0.5 : rounded;
}

function cssPixels(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}px`;
}

function subtitlePreviewTextEffects(
  template: SubtitleTemplateSet | undefined,
  role: SubtitleRole,
): SubtitlePreviewTextEffects {
  const outlineWidth = numericStyleValue(template, role, "outline_width", 2);
  const shadowDepth = numericStyleValue(
    template,
    role,
    "shadow",
    numericStyleValue(template, role, "shadow_depth", 0),
  );
  const shadowOffsetPx = previewEffectPixels(shadowDepth, 0.55);
  return {
    outlineColor: styleValue(template, role, "outline_color", "#111111"),
    outlineWidthPx: previewEffectPixels(outlineWidth, 0.25),
    shadowBlurPx: previewEffectPixels(shadowDepth, 1.1),
    shadowColor: styleValue(template, role, "shadow_color", "#000000"),
    shadowOffsetPx,
  };
}

function subtitlePreviewCaptionStyle(
  template: SubtitleTemplateSet | undefined,
  role: SubtitleRole,
  previewAspectRatio: string,
  effects: SubtitlePreviewTextEffects,
): CSSProperties {
  const primaryColor = styleValue(template, role, "primary_color", "#FFFFFF");
  const safePrimaryColor = parseHexColor(primaryColor) ? primaryColor : "#FFFFFF";
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
  const skewY = numericStyleValue(template, role, "skew_y_deg", 0);
  const alignment = styleValue(template, role, "alignment", "center");
  const previewFontSize = Math.round(
    clampValue(fontSize / 54, 0.82, 1.35) * 16 * clampValue(fontScale, 0.6, 1.8),
  );

  return {
    color: safePrimaryColor,
    fontFamily: styleValue(template, role, "font_family", "PingFang SC"),
    fontSize: `${previewFontSize}px`,
    fontWeight: numericStyleValue(template, role, "font_weight", 700),
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
      effects.shadowOffsetPx > 0
        ? `${cssPixels(effects.shadowOffsetPx)} ${cssPixels(effects.shadowOffsetPx)} ${cssPixels(
            Math.max(1, effects.shadowBlurPx),
          )} ${effects.shadowColor}, 0 0 ${cssPixels(effects.outlineWidthPx)} ${effects.outlineColor}`
        : "none",
    textAlign: alignment === "left" || alignment === "right" ? alignment : "center",
    transform: `${previewTranslateForAlignment(alignment)} rotate(${rotate}deg) skewX(${skew}deg) skewY(${skewY}deg)`,
    paintOrder: "stroke fill",
    WebkitTextFillColor: safePrimaryColor,
    WebkitTextStroke:
      effects.outlineWidthPx > 0 ? `${cssPixels(effects.outlineWidthPx)} ${effects.outlineColor}` : undefined,
  };
}

function previewSpanStyle(
  span: SubtitleSpan,
  baseFontSizePx: number,
  inheritedEffects: SubtitlePreviewTextEffects,
): CSSProperties {
  const style = typeof span.style === "object" && span.style !== null ? span.style : {};
  const primaryColor = typeof style.primary_color === "string" ? style.primary_color : "";
  const safePrimaryColor = parseHexColor(primaryColor) ? primaryColor : undefined;
  const fontScale = numericUnknownValue(style.font_scale, 1);
  const fontSize =
    style.font_size !== undefined
      ? numericUnknownValue(style.font_size, baseFontSizePx)
      : baseFontSizePx * clampValue(fontScale, 0.5, 1.8);
  const hasOutlineOverride =
    style.outline_width !== undefined || typeof style.outline_color === "string";
  const outlineWidth =
    style.outline_width !== undefined
      ? previewEffectPixels(numericUnknownValue(style.outline_width, 0), 0.25)
      : inheritedEffects.outlineWidthPx;
  const outlineColor =
    typeof style.outline_color === "string" ? style.outline_color : inheritedEffects.outlineColor;
  const hasShadowOverride =
    style.shadow !== undefined ||
    style.shadow_depth !== undefined ||
    typeof style.shadow_color === "string";
  const shadowDepth =
    style.shadow !== undefined || style.shadow_depth !== undefined
      ? numericUnknownValue(style.shadow ?? style.shadow_depth, 0)
      : inheritedEffects.shadowOffsetPx / 0.55;
  const shadowOffset = previewEffectPixels(shadowDepth, 0.55);
  const shadowBlur = Math.max(1, previewEffectPixels(shadowDepth, 1.1));
  const shadowColor =
    typeof style.shadow_color === "string" ? style.shadow_color : inheritedEffects.shadowColor;

  return {
    color: safePrimaryColor,
    fontFamily: typeof style.font_family === "string" ? style.font_family : undefined,
    fontSize: `${Math.round(fontSize)}px`,
    paintOrder: "stroke fill",
    textShadow:
      hasShadowOverride && shadowOffset > 0
        ? `${cssPixels(shadowOffset)} ${cssPixels(shadowOffset)} ${cssPixels(shadowBlur)} ${shadowColor}`
        : undefined,
    WebkitTextFillColor: safePrimaryColor,
    WebkitTextStroke:
      hasOutlineOverride && outlineWidth > 0 ? `${cssPixels(outlineWidth)} ${outlineColor}` : undefined,
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
  inheritedEffects: SubtitlePreviewTextEffects,
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
        style={previewSpanStyle(range.span, baseFontSizePx, inheritedEffects)}
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
  const [sampleText, setSampleText] = useState(defaultSubtitlePreviewText);
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
    const nextValue = persistentStyleValue(key, value);
    const currentSavedValue = persistentStyleValue(
      key,
      styleValue(selected, role, key, key === "sample_text" ? sampleText : styleFieldFallback(role, key)),
    );
    if (Object.is(nextValue, currentSavedValue)) {
      return;
    }
    resetTemplateResultState();
    setSaveErrorPlacement("editor");
    const draftRevision = nextDraftRevision(selected.id);
    const base = templateDrafts[selected.id] ?? selected;
    const patch = stylePatch(base, role, { [key]: nextValue });
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
    const currentSpans = roleSpans(base, role);
    const spans = updateSpanAt(currentSpans, index, updater);
    if (selected && subtitleSpansEqual(roleSpans(selected, role), spans)) {
      return;
    }
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
            <div className="subtitle-preview-screen" data-testid="subtitle-preview-screen">
              <div
                className="subtitle-preview-frame"
                data-testid="subtitle-preview-frame"
                style={{ aspectRatio: previewAspectRatio === "16:9" ? "16 / 9" : "9 / 16" }}
              >
                <div className="subtitle-preview-safe-area" data-testid="subtitle-preview-safe-area" />
                {editableRoles.map(({ role, label }) => {
                  const effects = subtitlePreviewTextEffects(selectedDraft, role);
                  const captionText = styleValue(selectedDraft, role, "sample_text", sampleText);
                  const captionStyle = subtitlePreviewCaptionStyle(
                    selectedDraft,
                    role,
                    previewAspectRatio,
                    effects,
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
                      {renderPreviewCaptionText(
                        captionText,
                        roleSpans(selectedDraft, role),
                        role,
                        baseFontSize,
                        effects,
                      )}
                    </span>
                  );
                })}
              </div>
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
              <SubtitleRoleStyleFields
                isEditable={isEditable}
                role={role}
                roleDefaults={previewRoleDefaults[role]}
                sampleText={sampleText}
                styleValue={(styleRole, key, fallback) =>
                  styleValue(selectedDraft, styleRole, key, fallback)
                }
                onSaveStyleValue={saveStyleValue}
                onUpdateStyleDraft={updateStyleDraft}
              />
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

function subtitleSpansEqual(first: SubtitleSpan[], second: SubtitleSpan[]): boolean {
  return stableJson(first.map(normalizeSubtitleSpanForCompare)) === stableJson(second.map(normalizeSubtitleSpanForCompare));
}

function normalizeSubtitleSpanForCompare(span: SubtitleSpan): SubtitleSpan {
  return {
    animation:
      typeof span.animation === "object" && span.animation !== null
        ? sortRecord(span.animation)
        : undefined,
    selector:
      typeof span.selector === "object" && span.selector !== null
        ? sortRecord(span.selector)
        : {},
    style: typeof span.style === "object" && span.style !== null ? sortRecord(span.style) : {},
  };
}

function sortRecord(record: Record<string, unknown>): Record<string, unknown> {
  return Object.keys(record)
    .sort()
    .reduce<Record<string, unknown>>((result, key) => {
      const value = record[key];
      result[key] =
        typeof value === "object" && value !== null && !Array.isArray(value)
          ? sortRecord(value as Record<string, unknown>)
          : value;
      return result;
    }, {});
}

function stableJson(value: unknown): string {
  return JSON.stringify(value);
}
