from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.models import DEFAULT_TRACK, RENDERER_MODE, SCHEMA_VERSION

ROLE_FONT_SIZES: dict[str, int] = {
    "bottom": 54,
    "highlight": 60,
    "punch": 68,
}

ROLE_ANIMATIONS: dict[str, dict[str, Any]] = {
    "bottom": {"in": {"type": "fade", "duration_ms": 120}},
    "highlight": {"in": {"type": "slide_up_fade", "duration_ms": 180, "offset_y": 18}},
    "punch": {"in": {"type": "pop_in", "duration_ms": 140}},
}

LAYOUT_FIELDS = {
    "template_type",
    "position",
    "x_percent",
    "y_percent",
    "alignment",
    "angle",
    "skew_x_deg",
    "skew_y_deg",
}

DEFAULT_TEMPLATE: dict[str, Any] = {
    "font_family": "Noto Sans CJK SC",
    "font_weight": 700,
    "font_scale": 1.0,
    "italic": False,
    "letter_spacing": 0,
    "line_spacing": 1.15,
    "primary_color": "#FFFFFF",
    "accent_color": "#FFD54F",
    "outline_color": "#111111",
    "shadow_color": "#000000",
    "outline_width": 3,
    "shadow_depth": 2,
    "position": "bottom",
    "alignment": "center",
    "margin_l": 60,
    "margin_r": 60,
    "margin_v": 80,
    "x_percent": 50,
    "y_percent": 78,
    "angle": 0,
    "bottom_safe_area_ratio": 0.22,
    "max_chars_per_line": 16,
    "max_lines": 3,
    "decoration_shape": "none",
    "fade_in_ms": 80,
    "fade_out_ms": 80,
}

PRESET_SPECS: list[dict[str, Any]] = [
    {
        "id": "bold_yellow",
        "name": "醒目黄黑大字",
        "templates": {
            "bottom": {"accent_color": "#FFB300", "outline_width": 4, "font_weight": 800},
            "highlight": {
                "accent_color": "#FFB300",
                "font_scale": 1.08,
                "outline_width": 4,
                "font_weight": 800,
            },
            "punch": {
                "primary_color": "#FFF176",
                "accent_color": "#FF5252",
                "font_scale": 1.16,
                "outline_width": 5,
                "shadow_depth": 3,
                "position": "center",
                "y_percent": 50,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "clean_white",
        "name": "清爽白字",
        "templates": {
            "bottom": {"accent_color": "#FFFFFF", "outline_width": 2, "shadow_depth": 1},
            "highlight": {
                "accent_color": "#8FD8FF",
                "outline_width": 2,
                "shadow_depth": 1,
                "font_scale": 1.04,
            },
            "punch": {
                "accent_color": "#BFEFFF",
                "outline_width": 3,
                "shadow_depth": 1,
                "font_scale": 1.1,
                "position": "center",
                "y_percent": 50,
            },
        },
    },
    {
        "id": "green_box",
        "name": "Green Box 绿框口播",
        "templates": {
            "bottom": {
                "primary_color": "#101820",
                "accent_color": "#35F06A",
                "outline_color": "#35F06A",
                "shadow_color": "#0B3D1A",
                "outline_width": 5,
                "shadow_depth": 1,
                "font_weight": 900,
                "y_percent": 76,
            },
            "highlight": {
                "primary_color": "#FFFFFF",
                "accent_color": "#35F06A",
                "outline_color": "#062A12",
                "outline_width": 4,
                "font_weight": 900,
                "y_percent": 60,
            },
            "punch": {
                "primary_color": "#35F06A",
                "accent_color": "#FFFFFF",
                "outline_color": "#061A0D",
                "outline_width": 5,
                "font_scale": 1.22,
                "position": "center",
                "y_percent": 48,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "word_pop",
        "name": "Word Pop 单词弹出",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#FF4D8D",
                "outline_color": "#160711",
                "outline_width": 4,
                "shadow_depth": 4,
                "font_scale": 1.08,
                "y_percent": 72,
                "font_weight": 900,
            },
            "highlight": {
                "primary_color": "#FF4D8D",
                "accent_color": "#FFE66D",
                "outline_color": "#160711",
                "outline_width": 5,
                "shadow_depth": 4,
                "font_scale": 1.18,
                "position": "center",
                "y_percent": 48,
                "font_weight": 900,
            },
            "punch": {
                "primary_color": "#FFE66D",
                "accent_color": "#FF4D8D",
                "outline_color": "#180E00",
                "outline_width": 6,
                "shadow_depth": 4,
                "font_scale": 1.28,
                "position": "center",
                "y_percent": 44,
                "angle": -4,
                "font_weight": 900,
                "max_lines": 1,
            },
        },
    },
    {
        "id": "karaoke_fill",
        "name": "Karaoke Fill 逐字高亮",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#00E5FF",
                "outline_color": "#001219",
                "outline_width": 3,
                "font_scale": 1.02,
                "y_percent": 80,
            },
            "highlight": {
                "primary_color": "#00E5FF",
                "accent_color": "#FFFFFF",
                "outline_color": "#001219",
                "outline_width": 4,
                "font_scale": 1.08,
                "y_percent": 80,
                "font_weight": 900,
            },
            "punch": {
                "primary_color": "#00E5FF",
                "accent_color": "#FFE66D",
                "outline_color": "#001219",
                "outline_width": 4,
                "font_scale": 1.18,
                "position": "center",
                "y_percent": 52,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "ali_abdaal",
        "name": "Ali Abdaal 白底黑字",
        "templates": {
            "bottom": {
                "primary_color": "#111827",
                "accent_color": "#F8FAFC",
                "outline_color": "#F8FAFC",
                "shadow_color": "#CBD5E1",
                "outline_width": 5,
                "shadow_depth": 1,
                "font_scale": 1.0,
                "y_percent": 76,
                "max_chars_per_line": 18,
            },
            "highlight": {
                "primary_color": "#111827",
                "accent_color": "#93C5FD",
                "outline_color": "#F8FAFC",
                "shadow_color": "#CBD5E1",
                "outline_width": 5,
                "shadow_depth": 1,
                "font_scale": 1.04,
                "y_percent": 64,
            },
            "punch": {
                "primary_color": "#111827",
                "accent_color": "#FDE68A",
                "outline_color": "#F8FAFC",
                "shadow_color": "#CBD5E1",
                "outline_width": 6,
                "shadow_depth": 1,
                "font_scale": 1.12,
                "position": "center",
                "y_percent": 50,
            },
        },
    },
    {
        "id": "interview_bar",
        "name": "访谈黑底条",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#94A3B8",
                "outline_color": "#000000",
                "shadow_color": "#000000",
                "outline_width": 2,
                "shadow_depth": 0,
                "font_scale": 0.96,
                "y_percent": 84,
                "max_chars_per_line": 20,
            },
            "highlight": {
                "primary_color": "#FFFFFF",
                "accent_color": "#60A5FA",
                "outline_color": "#000000",
                "outline_width": 3,
                "shadow_depth": 1,
                "y_percent": 84,
            },
            "punch": {
                "primary_color": "#FFFFFF",
                "accent_color": "#F97316",
                "outline_color": "#000000",
                "outline_width": 4,
                "shadow_depth": 2,
                "font_scale": 1.08,
                "position": "center",
                "y_percent": 52,
            },
        },
    },
    {
        "id": "news_bar",
        "name": "新闻标题条",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#EF4444",
                "outline_color": "#111827",
                "shadow_color": "#000000",
                "outline_width": 3,
                "shadow_depth": 1,
                "font_scale": 0.98,
                "alignment": "left",
                "x_percent": 38,
                "y_percent": 82,
                "max_chars_per_line": 22,
            },
            "highlight": {
                "primary_color": "#FFFFFF",
                "accent_color": "#FACC15",
                "outline_color": "#111827",
                "outline_width": 3,
                "shadow_depth": 1,
                "alignment": "left",
                "x_percent": 38,
                "y_percent": 70,
            },
            "punch": {
                "primary_color": "#FACC15",
                "accent_color": "#EF4444",
                "outline_color": "#111827",
                "outline_width": 5,
                "font_scale": 1.16,
                "alignment": "left",
                "position": "upper",
                "x_percent": 36,
                "y_percent": 24,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "diagonal_sticker",
        "name": "左上斜贴纸",
        "templates": {
            "bottom": {
                "primary_color": "#111111",
                "accent_color": "#FDE047",
                "outline_color": "#FDE047",
                "shadow_color": "#713F12",
                "outline_width": 5,
                "shadow_depth": 2,
                "position": "upper",
                "alignment": "left",
                "x_percent": 28,
                "y_percent": 22,
                "angle": -12,
                "font_weight": 900,
                "max_lines": 1,
            },
            "highlight": {
                "primary_color": "#111111",
                "accent_color": "#A7F3D0",
                "outline_color": "#A7F3D0",
                "shadow_color": "#064E3B",
                "outline_width": 5,
                "shadow_depth": 2,
                "position": "upper",
                "alignment": "left",
                "x_percent": 32,
                "y_percent": 30,
                "angle": -8,
                "font_weight": 900,
                "max_lines": 1,
            },
            "punch": {
                "primary_color": "#FDE047",
                "accent_color": "#111111",
                "outline_color": "#111111",
                "outline_width": 4,
                "position": "upper",
                "alignment": "left",
                "x_percent": 30,
                "y_percent": 18,
                "angle": -16,
                "font_scale": 1.2,
                "font_weight": 900,
                "max_lines": 1,
            },
        },
    },
    {
        "id": "right_comment",
        "name": "右侧评论感",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#A78BFA",
                "outline_color": "#2E1065",
                "shadow_color": "#000000",
                "outline_width": 3,
                "shadow_depth": 2,
                "alignment": "right",
                "x_percent": 74,
                "y_percent": 62,
                "angle": 4,
                "max_chars_per_line": 12,
            },
            "highlight": {
                "primary_color": "#F5F3FF",
                "accent_color": "#C4B5FD",
                "outline_color": "#2E1065",
                "outline_width": 4,
                "alignment": "right",
                "x_percent": 76,
                "y_percent": 52,
                "angle": 6,
                "max_chars_per_line": 12,
            },
            "punch": {
                "primary_color": "#C4B5FD",
                "accent_color": "#FFFFFF",
                "outline_color": "#2E1065",
                "outline_width": 5,
                "alignment": "right",
                "x_percent": 72,
                "y_percent": 42,
                "angle": 8,
                "font_scale": 1.14,
                "max_lines": 1,
            },
        },
    },
    {
        "id": "center_punch",
        "name": "中央冲击大字",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#FB7185",
                "outline_color": "#111827",
                "outline_width": 5,
                "shadow_depth": 4,
                "position": "center",
                "x_percent": 50,
                "y_percent": 52,
                "font_scale": 1.16,
                "font_weight": 900,
                "max_chars_per_line": 12,
            },
            "highlight": {
                "primary_color": "#FB7185",
                "accent_color": "#FDE68A",
                "outline_color": "#111827",
                "outline_width": 6,
                "shadow_depth": 4,
                "position": "center",
                "x_percent": 50,
                "y_percent": 48,
                "font_scale": 1.24,
                "font_weight": 900,
                "max_chars_per_line": 10,
            },
            "punch": {
                "primary_color": "#FDE68A",
                "accent_color": "#FB7185",
                "outline_color": "#111827",
                "outline_width": 7,
                "shadow_depth": 5,
                "position": "center",
                "x_percent": 50,
                "y_percent": 45,
                "angle": -3,
                "font_scale": 1.34,
                "font_weight": 900,
                "max_lines": 1,
            },
        },
    },
    {
        "id": "square_social",
        "name": "方形社媒标题",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#38BDF8",
                "outline_color": "#0F172A",
                "outline_width": 4,
                "shadow_depth": 2,
                "x_percent": 50,
                "y_percent": 70,
                "max_chars_per_line": 14,
            },
            "highlight": {
                "primary_color": "#38BDF8",
                "accent_color": "#FFFFFF",
                "outline_color": "#0F172A",
                "outline_width": 4,
                "shadow_depth": 2,
                "x_percent": 50,
                "y_percent": 58,
                "font_weight": 900,
            },
            "punch": {
                "primary_color": "#FFFFFF",
                "accent_color": "#38BDF8",
                "outline_color": "#0F172A",
                "outline_width": 5,
                "shadow_depth": 3,
                "position": "upper",
                "x_percent": 50,
                "y_percent": 28,
                "font_scale": 1.2,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "creator_green_caption",
        "name": "创作者绿字幕",
        "templates": {
            "bottom": {
                "primary_color": "#E8FFF0",
                "accent_color": "#22C55E",
                "outline_color": "#052E16",
                "shadow_color": "#031B0D",
                "outline_width": 4,
                "shadow_depth": 3,
                "font_weight": 900,
                "y_percent": 77,
                "max_width_ratio": 0.82,
            },
            "highlight": {
                "primary_color": "#22C55E",
                "accent_color": "#FFFFFF",
                "outline_color": "#052E16",
                "font_scale": 1.1,
                "font_weight": 900,
                "y_percent": 63,
                "max_width_ratio": 0.76,
            },
            "punch": {
                "primary_color": "#BBF7D0",
                "accent_color": "#22C55E",
                "outline_color": "#052E16",
                "font_scale": 1.24,
                "font_weight": 900,
                "position": "center",
                "y_percent": 47,
                "angle": -3,
                "max_width_ratio": 0.7,
            },
        },
    },
    {
        "id": "pink_pop_comment",
        "name": "粉色弹幕评论",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#FB7185",
                "outline_color": "#4A1020",
                "shadow_color": "#000000",
                "outline_width": 4,
                "shadow_depth": 3,
                "alignment": "right",
                "x_percent": 72,
                "y_percent": 66,
                "angle": 5,
                "max_chars_per_line": 12,
            },
            "highlight": {
                "primary_color": "#FFE4E6",
                "accent_color": "#F472B6",
                "outline_color": "#4A1020",
                "alignment": "right",
                "x_percent": 76,
                "y_percent": 54,
                "angle": 7,
                "font_weight": 900,
            },
            "punch": {
                "primary_color": "#FDF2F8",
                "accent_color": "#FB7185",
                "outline_color": "#4A1020",
                "alignment": "right",
                "x_percent": 68,
                "y_percent": 40,
                "angle": -6,
                "font_scale": 1.22,
                "font_weight": 900,
                "max_lines": 1,
            },
        },
    },
    {
        "id": "blue_glow_stack",
        "name": "蓝色发光叠层",
        "templates": {
            "bottom": {
                "primary_color": "#E0F2FE",
                "accent_color": "#38BDF8",
                "outline_color": "#082F49",
                "shadow_color": "#0EA5E9",
                "outline_width": 4,
                "shadow_depth": 4,
                "x_percent": 50,
                "y_percent": 72,
                "max_width_ratio": 0.86,
            },
            "highlight": {
                "primary_color": "#38BDF8",
                "accent_color": "#FFFFFF",
                "outline_color": "#082F49",
                "shadow_color": "#0EA5E9",
                "outline_width": 5,
                "shadow_depth": 4,
                "x_percent": 50,
                "y_percent": 58,
                "font_weight": 900,
            },
            "punch": {
                "primary_color": "#FFFFFF",
                "accent_color": "#7DD3FC",
                "outline_color": "#082F49",
                "shadow_color": "#0EA5E9",
                "outline_width": 6,
                "shadow_depth": 5,
                "position": "center",
                "x_percent": 50,
                "y_percent": 44,
                "font_scale": 1.26,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "minimal_lower_third",
        "name": "极简下三分之一",
        "templates": {
            "bottom": {
                "primary_color": "#F9FAFB",
                "accent_color": "#9CA3AF",
                "outline_color": "#111827",
                "outline_width": 2,
                "shadow_depth": 1,
                "alignment": "left",
                "x_percent": 34,
                "y_percent": 82,
                "font_scale": 0.94,
                "max_chars_per_line": 22,
                "max_width_ratio": 0.7,
            },
            "highlight": {
                "primary_color": "#FFFFFF",
                "accent_color": "#60A5FA",
                "outline_color": "#111827",
                "alignment": "left",
                "x_percent": 34,
                "y_percent": 72,
                "font_scale": 0.98,
            },
            "punch": {
                "primary_color": "#FFFFFF",
                "accent_color": "#FACC15",
                "outline_color": "#111827",
                "alignment": "left",
                "x_percent": 34,
                "y_percent": 62,
                "font_scale": 1.06,
                "font_weight": 900,
            },
        },
    },
    {
        "id": "split_screen_callout",
        "name": "分屏标注字幕",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#F97316",
                "outline_color": "#1C1917",
                "alignment": "left",
                "x_percent": 27,
                "y_percent": 70,
                "angle": -2,
                "max_width_ratio": 0.48,
            },
            "highlight": {
                "primary_color": "#111827",
                "accent_color": "#FDBA74",
                "outline_color": "#FDBA74",
                "alignment": "right",
                "x_percent": 73,
                "y_percent": 42,
                "angle": 2,
                "outline_width": 5,
                "max_width_ratio": 0.48,
            },
            "punch": {
                "primary_color": "#FDBA74",
                "accent_color": "#FFFFFF",
                "outline_color": "#1C1917",
                "alignment": "right",
                "x_percent": 72,
                "y_percent": 28,
                "position": "upper",
                "font_scale": 1.18,
                "font_weight": 900,
                "max_width_ratio": 0.46,
            },
        },
    },
    {
        "id": "diagonal_multi_sticker",
        "name": "多块斜贴纸",
        "templates": {
            "bottom": {
                "primary_color": "#111111",
                "accent_color": "#FDE047",
                "outline_color": "#FDE047",
                "shadow_color": "#713F12",
                "outline_width": 5,
                "shadow_depth": 2,
                "position": "bottom",
                "alignment": "left",
                "x_percent": 34,
                "y_percent": 72,
                "angle": -12,
                "skew_x_deg": 10,
                "skew_y_deg": -3,
                "font_weight": 900,
                "max_lines": 1,
                "max_width_ratio": 0.58,
            },
            "highlight": {
                "primary_color": "#083344",
                "accent_color": "#67E8F9",
                "outline_color": "#67E8F9",
                "shadow_color": "#164E63",
                "outline_width": 5,
                "shadow_depth": 2,
                "position": "center",
                "alignment": "center",
                "x_percent": 56,
                "y_percent": 52,
                "angle": 9,
                "skew_x_deg": -8,
                "font_weight": 900,
                "max_lines": 1,
                "max_width_ratio": 0.54,
            },
            "punch": {
                "primary_color": "#FDF2F8",
                "accent_color": "#F472B6",
                "outline_color": "#831843",
                "outline_width": 5,
                "position": "upper",
                "alignment": "right",
                "x_percent": 70,
                "y_percent": 26,
                "angle": -18,
                "skew_y_deg": 8,
                "font_scale": 1.2,
                "font_weight": 900,
                "max_lines": 1,
                "max_width_ratio": 0.48,
            },
        },
    },
    {
        "id": "quote_center_serif",
        "name": "居中引语字幕",
        "templates": {
            "bottom": {
                "primary_color": "#F8FAFC",
                "accent_color": "#CBD5E1",
                "outline_color": "#020617",
                "shadow_depth": 3,
                "position": "center",
                "x_percent": 50,
                "y_percent": 54,
                "font_scale": 1.04,
                "italic": True,
                "max_chars_per_line": 18,
                "max_width_ratio": 0.78,
            },
            "highlight": {
                "primary_color": "#FDE68A",
                "accent_color": "#FFFFFF",
                "outline_color": "#020617",
                "position": "center",
                "x_percent": 50,
                "y_percent": 46,
                "font_scale": 1.1,
                "italic": True,
            },
            "punch": {
                "primary_color": "#FFFFFF",
                "accent_color": "#FDE68A",
                "outline_color": "#020617",
                "position": "center",
                "x_percent": 50,
                "y_percent": 40,
                "font_scale": 1.18,
                "font_weight": 900,
                "max_lines": 1,
            },
        },
    },
    {
        "id": "duo_language_stack",
        "name": "双语堆叠字幕",
        "templates": {
            "bottom": {
                "primary_color": "#FFFFFF",
                "accent_color": "#A7F3D0",
                "outline_color": "#064E3B",
                "x_percent": 50,
                "y_percent": 78,
                "font_scale": 0.98,
                "max_chars_per_line": 20,
                "max_width_ratio": 0.88,
            },
            "highlight": {
                "primary_color": "#A7F3D0",
                "accent_color": "#FFFFFF",
                "outline_color": "#064E3B",
                "x_percent": 50,
                "y_percent": 67,
                "font_scale": 0.94,
                "font_weight": 700,
                "max_chars_per_line": 22,
                "max_width_ratio": 0.88,
            },
            "punch": {
                "primary_color": "#FDE68A",
                "accent_color": "#FFFFFF",
                "outline_color": "#78350F",
                "position": "center",
                "x_percent": 50,
                "y_percent": 50,
                "font_scale": 1.14,
                "font_weight": 900,
                "max_lines": 1,
            },
        },
    },
]


def list_presets() -> list[dict[str, Any]]:
    return [_build_preset(spec) for spec in PRESET_SPECS]


def _build_preset(spec: dict[str, Any]) -> dict[str, Any]:
    templates = {
        role: _default_template(role, spec["templates"].get(role, {}))
        for role in ROLE_FONT_SIZES
    }
    blocks = [_block(role, templates[role]) for role in ROLE_FONT_SIZES]
    return {
        "id": spec["id"],
        "name": spec["name"],
        "schema_version": SCHEMA_VERSION,
        "renderer_mode": RENDERER_MODE,
        "tracks": [copy.deepcopy(DEFAULT_TRACK)],
        "templates": templates,
        "blocks": blocks,
    }


def _default_template(role: str, overrides: dict[str, Any]) -> dict[str, Any]:
    template = copy.deepcopy(DEFAULT_TEMPLATE)
    template["template_type"] = role
    template.update(copy.deepcopy(overrides))
    if "x_percent" not in overrides:
        template["x_percent"] = _infer_horizontal_percent(template)
    if "y_percent" not in overrides:
        template["y_percent"] = _infer_vertical_percent(template)
    return template


def _block(role: str, template: dict[str, Any]) -> dict[str, Any]:
    style = _style_for_role(role, template)
    return {
        "id": f"{role}-main",
        "role": role,
        "track_id": "main",
        "position": _position_for_template(template),
        "style": style,
        "spans": _default_spans_for_role(role, style),
        "animations": copy.deepcopy(ROLE_ANIMATIONS[role]),
    }


def _style_for_role(role: str, template: dict[str, Any]) -> dict[str, Any]:
    style: dict[str, Any] = {"font_size": ROLE_FONT_SIZES[role]}
    for key, value in template.items():
        if key in LAYOUT_FIELDS:
            continue
        style[key] = copy.deepcopy(value)

    style["template_type"] = role
    style["position"] = copy.deepcopy(template.get("position", DEFAULT_TEMPLATE["position"]))
    style["alignment"] = copy.deepcopy(template.get("alignment", DEFAULT_TEMPLATE["alignment"]))
    style["x_percent"] = copy.deepcopy(template.get("x_percent", DEFAULT_TEMPLATE["x_percent"]))
    style["y_percent"] = copy.deepcopy(template.get("y_percent", DEFAULT_TEMPLATE["y_percent"]))
    style["angle"] = copy.deepcopy(template.get("angle", DEFAULT_TEMPLATE["angle"]))
    if "font_scale" in style and "font_size_scale" not in style:
        style["font_size_scale"] = style["font_scale"]
    style["rotate"] = copy.deepcopy(template.get("angle", 0))
    style["max_width"] = copy.deepcopy(template.get("max_width_ratio", 0.9))
    style["max_width_ratio"] = copy.deepcopy(template.get("max_width_ratio", 0.9))
    style["skew_x_deg"] = copy.deepcopy(template.get("skew_x_deg", 0))
    style["skew_y_deg"] = copy.deepcopy(template.get("skew_y_deg", 0))
    if "skew" not in style:
        style["skew"] = copy.deepcopy(style["skew_x_deg"])

    return style


def _position_for_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "x": _percent_to_ratio(template.get("x_percent"), 0.5),
        "y": _percent_to_ratio(template.get("y_percent"), 0.78),
        "anchor": _anchor_from_alignment(template.get("alignment"), "center"),
    }


def _anchor_from_alignment(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in {"left", "center", "right"} else fallback


def _percent_to_ratio(value: Any, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return fallback
    return max(0, min(1, float(value) / 100))


def _default_spans_for_role(role: str, style: dict[str, Any]) -> list[dict[str, Any]]:
    primary_color = str(style.get("primary_color") or "#FFFFFF")
    accent_color = str(style.get("accent_color") or "#FFD54F")
    outline_color = str(style.get("outline_color") or "#111827")
    outline_width = _clamp_number(style.get("outline_width"), 0, 8, 3)
    shadow_depth = _clamp_number(style.get("shadow_depth"), 0, 8, 2)
    scale = _clamp_number(style.get("font_size_scale", style.get("font_scale")), 0.5, 1.8, 1)

    if role == "highlight":
        return [
            {
                "selector": {"type": "keyword", "value": "预览"},
                "style": {
                    "primary_color": accent_color,
                    "outline_color": outline_color,
                    "font_scale": _clamp_number(scale + 0.08, 0.5, 1.8, 1.08),
                    "outline_width": min(outline_width + 1, 8),
                },
            }
        ]
    if role == "punch":
        return [
            {
                "selector": {"type": "range", "start": 0, "end": 2},
                "style": {
                    "primary_color": accent_color,
                    "accent_color": primary_color,
                    "font_scale": _clamp_number(scale + 0.12, 0.5, 1.8, 1.12),
                    "shadow_depth": min(shadow_depth + 1, 8),
                },
            }
        ]
    return [
        {
            "selector": {"type": "keyword", "value": "字幕"},
            "style": {
                "primary_color": accent_color,
                "outline_color": outline_color,
                "font_scale": _clamp_number(scale + 0.06, 0.5, 1.8, 1.06),
            },
        }
    ]


def _clamp_number(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return fallback
    return float(max(minimum, min(maximum, value)))


def _infer_horizontal_percent(template: dict[str, Any]) -> int:
    alignment = str(template.get("alignment") or DEFAULT_TEMPLATE["alignment"])
    if alignment == "left":
        return 25
    if alignment == "right":
        return 75
    return 50


def _infer_vertical_percent(template: dict[str, Any]) -> int:
    position = str(template.get("position") or DEFAULT_TEMPLATE["position"])
    if position == "upper":
        return 18
    if position == "center":
        return 50
    return 78
