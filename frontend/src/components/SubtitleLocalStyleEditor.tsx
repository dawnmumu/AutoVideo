import type { SubtitleTemplateSet } from "../api/subtitles";

export type SubtitleSpan = {
  animation?: Record<string, unknown>;
  selector?: Record<string, unknown>;
  style?: Record<string, unknown>;
};

type SubtitleLocalStyleEditorProps = {
  isEditable: boolean;
  label: string;
  role: string;
  sampleText: string;
  spans: SubtitleSpan[];
  onAdd: (role: string) => void;
  onDelete: (role: string, index: number) => void;
  onSaveSpanValue: (
    role: string,
    index: number,
    updater: (span: SubtitleSpan) => SubtitleSpan,
  ) => void;
  onUpdateSpanDraft: (
    role: string,
    index: number,
    updater: (span: SubtitleSpan) => SubtitleSpan,
  ) => void;
};

export function roleSpans(
  template: SubtitleTemplateSet | undefined,
  role: string,
): SubtitleSpan[] {
  const spans = template?.blocks.find((block) => block.role === role)?.spans;
  return Array.isArray(spans) ? (spans as SubtitleSpan[]) : [];
}

export function spansPatch(
  template: SubtitleTemplateSet,
  role: string,
  spans: SubtitleSpan[],
): Partial<SubtitleTemplateSet> {
  const hasRoleBlock = template.blocks.some((block) => block.role === role);
  return {
    blocks: hasRoleBlock
      ? template.blocks.map((block) => (block.role === role ? { ...block, spans } : block))
      : [
          ...template.blocks,
          {
            id: `${role}-main`,
            role,
            style: { ...(template.templates?.[role] ?? {}) },
            spans,
          },
        ],
  };
}

export function updateSpanAt(
  spans: SubtitleSpan[],
  index: number,
  updater: (span: SubtitleSpan) => SubtitleSpan,
): SubtitleSpan[] {
  return spans.map((span, spanIndex) =>
    spanIndex === index ? updater(normalizeSpan(span)) : span,
  );
}

export function SubtitleLocalStyleEditor({
  isEditable,
  label,
  role,
  sampleText,
  spans,
  onAdd,
  onDelete,
  onSaveSpanValue,
  onUpdateSpanDraft,
}: SubtitleLocalStyleEditorProps) {
  return (
    <div className="subtitle-local-style-editor" aria-label={`${label}局部样式`}>
      <h3>局部样式</h3>
      {spans.map((span, index) => {
        const selectorType = spanSelectorType(span);
        const fallbackKeyword = sampleText.trim().slice(0, 2) || "AI";
        return (
          <div className="subtitle-local-style-row" key={`${role}-${index}`}>
            <label>
              <span>类型</span>
              <select
                aria-label={`${label}局部样式 ${index + 1} 类型`}
                disabled={!isEditable}
                value={selectorType}
                onChange={(event) => {
                  const type = event.target.value === "range" ? "range" : "keyword";
                  const updater = (current: SubtitleSpan) =>
                    setSpanSelectorTypeValue(current, type, fallbackKeyword);
                  onUpdateSpanDraft(role, index, updater);
                  onSaveSpanValue(role, index, updater);
                }}
              >
                <option value="keyword">关键词</option>
                <option value="range">范围</option>
              </select>
            </label>
            {selectorType === "keyword" ? (
              <label>
                <span>关键词</span>
                <input
                  aria-label={`${label}局部样式 ${index + 1} 关键词`}
                  disabled={!isEditable}
                  value={spanSelectorValue(span, "value", fallbackKeyword)}
                  onBlur={(event) =>
                    onSaveSpanValue(role, index, (current) =>
                      setSpanSelectorField(current, "value", event.target.value),
                    )
                  }
                  onChange={(event) =>
                    onUpdateSpanDraft(role, index, (current) =>
                      setSpanSelectorField(current, "value", event.target.value),
                    )
                  }
                />
              </label>
            ) : (
              <div className="subtitle-local-range">
                <label>
                  <span>开始</span>
                  <input
                    aria-label={`${label}局部样式 ${index + 1} 开始`}
                    disabled={!isEditable}
                    inputMode="numeric"
                    value={spanSelectorValue(span, "start", "0")}
                    onBlur={(event) =>
                      onSaveSpanValue(role, index, (current) =>
                        setSpanSelectorField(current, "start", event.target.value),
                      )
                    }
                    onChange={(event) =>
                      onUpdateSpanDraft(role, index, (current) =>
                        setSpanSelectorDraftField(current, "start", event.target.value),
                      )
                    }
                  />
                </label>
                <label>
                  <span>结束</span>
                  <input
                    aria-label={`${label}局部样式 ${index + 1} 结束`}
                    disabled={!isEditable}
                    inputMode="numeric"
                    value={spanSelectorValue(span, "end", "2")}
                    onBlur={(event) =>
                      onSaveSpanValue(role, index, (current) =>
                        setSpanSelectorField(current, "end", event.target.value),
                      )
                    }
                    onChange={(event) =>
                      onUpdateSpanDraft(role, index, (current) =>
                        setSpanSelectorDraftField(current, "end", event.target.value),
                      )
                    }
                  />
                </label>
              </div>
            )}
            <label>
              <span>颜色</span>
              <input
                aria-label={`${label}局部样式 ${index + 1} 颜色`}
                disabled={!isEditable}
                value={spanStyleValue(span, "primary_color", "#FFD54F")}
                onBlur={(event) =>
                  onSaveSpanValue(role, index, (current) =>
                    setSpanStyleField(current, "primary_color", event.target.value),
                  )
                }
                onChange={(event) =>
                  onUpdateSpanDraft(role, index, (current) =>
                    setSpanStyleField(current, "primary_color", event.target.value),
                  )
                }
              />
            </label>
            <label>
              <span>字体</span>
              <select
                aria-label={`${label}局部样式 ${index + 1} 字体`}
                disabled={!isEditable}
                value={spanStyleValue(span, "font_family", "PingFang SC")}
                onChange={(event) => {
                  const updater = (current: SubtitleSpan) =>
                    setSpanStyleField(current, "font_family", event.target.value);
                  onUpdateSpanDraft(role, index, updater);
                  onSaveSpanValue(role, index, updater);
                }}
              >
                <option value="PingFang SC">PingFang SC</option>
                <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
              </select>
            </label>
            <label>
              <span>字号</span>
              <input
                aria-label={`${label}局部样式 ${index + 1} 字号`}
                disabled={!isEditable}
                inputMode="decimal"
                value={spanStyleValue(span, "font_scale", "1")}
                onBlur={(event) =>
                  onSaveSpanValue(role, index, (current) =>
                    setSpanStyleField(current, "font_scale", event.target.value),
                  )
                }
                onChange={(event) =>
                  onUpdateSpanDraft(role, index, (current) =>
                    setSpanStyleDraftField(current, "font_scale", event.target.value),
                  )
                }
              />
            </label>
            <label>
              <span>描边</span>
              <input
                aria-label={`${label}局部样式 ${index + 1} 描边`}
                disabled={!isEditable}
                inputMode="numeric"
                value={spanStyleValue(span, "outline_width", "0")}
                onBlur={(event) =>
                  onSaveSpanValue(role, index, (current) =>
                    setSpanStyleField(current, "outline_width", event.target.value),
                  )
                }
                onChange={(event) =>
                  onUpdateSpanDraft(role, index, (current) =>
                    setSpanStyleDraftField(current, "outline_width", event.target.value),
                  )
                }
              />
            </label>
            <label>
              <span>动画</span>
              <select
                aria-label={`${label}局部样式 ${index + 1} 动画`}
                disabled={!isEditable}
                value={spanAnimationType(span)}
                onChange={(event) => {
                  const updater = (current: SubtitleSpan) =>
                    setSpanAnimationType(current, event.target.value);
                  onUpdateSpanDraft(role, index, updater);
                  onSaveSpanValue(role, index, updater);
                }}
              >
                <option value="none">无动画</option>
                <option value="fade">淡入</option>
                <option value="slide_up_fade">上滑淡入</option>
                <option value="pop_in">弹出</option>
              </select>
            </label>
            <button
              aria-label={`删除${label}局部样式 ${index + 1}`}
              disabled={!isEditable}
              type="button"
              onClick={() => onDelete(role, index)}
            >
              删除
            </button>
          </div>
        );
      })}
      <button
        aria-label={`新增${label}局部样式`}
        disabled={!isEditable}
        type="button"
        onClick={() => onAdd(role)}
      >
        添加局部样式
      </button>
    </div>
  );
}

function normalizeSpan(span: SubtitleSpan | undefined): SubtitleSpan {
  return {
    animation:
      typeof span?.animation === "object" && span.animation !== null
        ? { ...span.animation }
        : undefined,
    selector:
      typeof span?.selector === "object" && span.selector !== null ? { ...span.selector } : {},
    style: typeof span?.style === "object" && span.style !== null ? { ...span.style } : {},
  };
}

function spanSelectorType(span: SubtitleSpan): "keyword" | "range" {
  return span.selector?.type === "range" ? "range" : "keyword";
}

function spanSelectorValue(
  span: SubtitleSpan,
  key: "value" | "start" | "end",
  fallback: string,
): string {
  const value = span.selector?.[key];
  return value === undefined || value === null ? fallback : String(value);
}

function spanStyleValue(span: SubtitleSpan, key: string, fallback: string): string {
  const value = span.style?.[key];
  return value === undefined || value === null ? fallback : String(value);
}

function spanAnimationType(span: SubtitleSpan): string {
  const value = span.animation?.type;
  if (value === "fade_in") {
    return "fade";
  }
  if (value === "slide_up") {
    return "slide_up_fade";
  }
  return typeof value === "string" && value ? value : "none";
}

function setSpanAnimationType(span: SubtitleSpan, type: string): SubtitleSpan {
  if (type === "none") {
    const { animation: _animation, ...rest } = span;
    return rest;
  }
  if (type !== "fade" && type !== "slide_up_fade" && type !== "pop_in") {
    return span;
  }
  return {
    ...span,
    animation: {
      ...(span.animation ?? {}),
      type,
    },
  };
}

function setSpanSelectorTypeValue(
  span: SubtitleSpan,
  type: "keyword" | "range",
  fallbackKeyword: string,
): SubtitleSpan {
  return {
    ...span,
    selector:
      type === "range"
        ? { type: "range", start: 0, end: 2 }
        : { type: "keyword", value: spanSelectorValue(span, "value", fallbackKeyword) },
  };
}

function setSpanSelectorField(
  span: SubtitleSpan,
  key: "value" | "start" | "end",
  value: string,
): SubtitleSpan {
  const nextValue = key === "value" ? value : numericPatchValue(value, key === "start" ? 0 : 2);
  return setSpanSelectorRawField(span, key, nextValue);
}

function setSpanSelectorDraftField(
  span: SubtitleSpan,
  key: "start" | "end",
  value: string,
): SubtitleSpan {
  return setSpanSelectorRawField(span, key, value);
}

function setSpanSelectorRawField(
  span: SubtitleSpan,
  key: "value" | "start" | "end",
  value: string | number,
): SubtitleSpan {
  return {
    ...span,
    selector: {
      ...(span.selector ?? {}),
      type: spanSelectorType(span),
      [key]: value,
    },
  };
}

function setSpanStyleField(span: SubtitleSpan, key: string, value: string): SubtitleSpan {
  return setSpanStyleRawField(span, key, persistentSpanStyleValue(key, value));
}

function setSpanStyleDraftField(span: SubtitleSpan, key: string, value: string): SubtitleSpan {
  return setSpanStyleRawField(span, key, value);
}

function setSpanStyleRawField(
  span: SubtitleSpan,
  key: string,
  value: string | number,
): SubtitleSpan {
  return {
    ...span,
    style: {
      ...(span.style ?? {}),
      [key]: value,
    },
  };
}

function numericPatchValue(value: string, fallback: number): number {
  if (!value.trim()) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function persistentSpanStyleValue(key: string, value: string): string | number {
  if (key === "font_scale") {
    return numericPatchValue(value, 1);
  }
  if (key === "outline_width" || key === "shadow") {
    return numericPatchValue(value, 0);
  }
  return value;
}
