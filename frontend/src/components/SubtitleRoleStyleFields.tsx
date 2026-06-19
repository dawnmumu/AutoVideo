type SubtitleRoleStyleFieldsProps = {
  isEditable: boolean;
  role: string;
  roleDefaults: {
    x: number;
    y: number;
  };
  sampleText: string;
  styleValue: (role: string, key: string, fallback: string) => string;
  onSaveStyleValue: (role: string, key: string, value: string) => void;
  onUpdateStyleDraft: (role: string, key: string, value: string) => void;
};

export function SubtitleRoleStyleFields({
  isEditable,
  role,
  roleDefaults,
  sampleText,
  styleValue,
  onSaveStyleValue,
  onUpdateStyleDraft,
}: SubtitleRoleStyleFieldsProps) {
  const updateAndSave = (key: string, value: string) => {
    onUpdateStyleDraft(role, key, value);
    onSaveStyleValue(role, key, value);
  };

  return (
    <div className="subtitle-editor-fields">
      <label className="subtitle-field-wide">
        <span>文本</span>
        <input
          disabled={!isEditable}
          value={styleValue(role, "sample_text", sampleText)}
          onBlur={(event) => onSaveStyleValue(role, "sample_text", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "sample_text", event.target.value)}
        />
      </label>
      <label>
        <span>横向位置 %</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "x_percent", String(roleDefaults.x))}
          onBlur={(event) => onSaveStyleValue(role, "x_percent", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "x_percent", event.target.value)}
        />
      </label>
      <label>
        <span>纵向位置 %</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "y_percent", String(roleDefaults.y))}
          onBlur={(event) => onSaveStyleValue(role, "y_percent", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "y_percent", event.target.value)}
        />
      </label>
      <label>
        <span>对齐</span>
        <select
          disabled={!isEditable}
          value={styleValue(role, "alignment", "center")}
          onChange={(event) => updateAndSave("alignment", event.target.value)}
        >
          <option value="center">居中</option>
          <option value="left">左对齐</option>
          <option value="right">右对齐</option>
        </select>
      </label>
      <label>
        <span>字号</span>
        <input
          disabled={!isEditable}
          inputMode="decimal"
          value={styleValue(role, "font_size_scale", "1")}
          onBlur={(event) => onSaveStyleValue(role, "font_size_scale", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "font_size_scale", event.target.value)}
        />
      </label>
      <label>
        <span>最大宽度</span>
        <input
          disabled={!isEditable}
          inputMode="decimal"
          value={styleValue(role, "max_width", "0.86")}
          onBlur={(event) => onSaveStyleValue(role, "max_width", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "max_width", event.target.value)}
        />
      </label>
      <label>
        <span>字体</span>
        <select
          disabled={!isEditable}
          value={styleValue(role, "font_family", "PingFang SC")}
          onChange={(event) => updateAndSave("font_family", event.target.value)}
        >
          <option value="PingFang SC">PingFang SC</option>
          <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
        </select>
      </label>
      <label>
        <span>颜色</span>
        <input
          disabled={!isEditable}
          value={styleValue(role, "primary_color", "#FFFFFF")}
          onBlur={(event) => onSaveStyleValue(role, "primary_color", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "primary_color", event.target.value)}
        />
      </label>
      <label>
        <span>背景</span>
        <input
          disabled={!isEditable}
          value={styleValue(role, "background_color", "#000000")}
          onBlur={(event) => onSaveStyleValue(role, "background_color", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "background_color", event.target.value)}
        />
      </label>
      <label>
        <span>强调色</span>
        <input
          disabled={!isEditable}
          value={styleValue(role, "accent_color", "#FFD54F")}
          onBlur={(event) => onSaveStyleValue(role, "accent_color", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "accent_color", event.target.value)}
        />
      </label>
      <label>
        <span>括号装饰</span>
        <select
          disabled={!isEditable}
          value={styleValue(role, "decoration_shape", "none")}
          onChange={(event) => updateAndSave("decoration_shape", event.target.value)}
        >
          <option value="none">不加</option>
          <option value="brackets">方括号</option>
          <option value="corner">角标</option>
        </select>
      </label>
      <label>
        <span>描边</span>
        <input
          disabled={!isEditable}
          value={styleValue(role, "outline_color", "#111111")}
          onBlur={(event) => onSaveStyleValue(role, "outline_color", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "outline_color", event.target.value)}
        />
      </label>
      <label>
        <span>阴影</span>
        <input
          disabled={!isEditable}
          value={styleValue(role, "shadow_color", "#000000")}
          onBlur={(event) => onSaveStyleValue(role, "shadow_color", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "shadow_color", event.target.value)}
        />
      </label>
      <label>
        <span>描边宽度</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "outline_width", "2")}
          onBlur={(event) => onSaveStyleValue(role, "outline_width", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "outline_width", event.target.value)}
        />
      </label>
      <label>
        <span>阴影强度</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "shadow", "0")}
          onBlur={(event) => onSaveStyleValue(role, "shadow", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "shadow", event.target.value)}
        />
      </label>
      <label>
        <span>旋转</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "rotate", "0")}
          onBlur={(event) => onSaveStyleValue(role, "rotate", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "rotate", event.target.value)}
        />
      </label>
      <label>
        <span>X 倾斜</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "skew", "0")}
          onBlur={(event) => onSaveStyleValue(role, "skew", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "skew", event.target.value)}
        />
      </label>
      <label>
        <span>Y 倾斜</span>
        <input
          disabled={!isEditable}
          inputMode="numeric"
          value={styleValue(role, "skew_y_deg", "0")}
          onBlur={(event) => onSaveStyleValue(role, "skew_y_deg", event.target.value)}
          onChange={(event) => onUpdateStyleDraft(role, "skew_y_deg", event.target.value)}
        />
      </label>
    </div>
  );
}
