from autovideo.services.subtitles import dsl_v2
from autovideo.services.subtitles.models import deep_dict


def test_validate_template_set_v2_preserves_supported_fields_and_warns_for_advanced_fields():
    payload = {
        "id": "template-1",
        "name": "动效模板",
        "schema_version": 2,
        "renderer_mode": "ass_plus",
        "is_favorite": True,
        "tracks": [{"id": "main", "kind": "subtitle", "z": 10}],
        "blocks": [
            {
                "id": "bottom-main",
                "role": "bottom",
                "track_id": "main",
                "style": {
                    "font_family": "Inter",
                    "primary_color": "#FFFFFF",
                    "outline_width": 4,
                    "shadow": 3,
                    "font_size_scale": 1.08,
                    "font_weight": 900,
                    "italic": True,
                    "letter_spacing": 1,
                    "line_spacing": 1.2,
                    "margin_l": 72,
                    "margin_r": 84,
                    "margin_v": 112,
                    "max_width": 0.82,
                    "max_width_ratio": 0.82,
                    "max_chars_per_line": 18,
                    "max_lines": 2,
                    "rotate": -2,
                    "skew": 6,
                    "skew_x_deg": 6,
                    "skew_y_deg": -3,
                    "fade_in_ms": 120,
                    "fade_out_ms": 80,
                },
                "spans": [
                    {
                        "selector": {"type": "keyword", "value": "效率"},
                        "style": {"primary_color": "#FFD54F", "font_scale": 1.15},
                    }
                ],
                "animations": {"in": {"type": "fade", "duration_ms": 120}},
                "mask": {"type": "rounded_rect"},
            }
        ],
        "template_variants": {
            "highlight": [
                {
                    "id": "emphasis",
                    "blocks": [
                        {
                            "id": "highlight-emphasis",
                            "role": "highlight",
                            "style": {"primary_color": "#FFD54F", "font_size_scale": 1.2},
                        }
                    ],
                }
            ]
        },
    }

    result = dsl_v2.validate_template_set_v2(payload)

    assert result["ok"] is True
    assert result["normalized"]["is_favorite"] is True
    assert result["normalized"]["blocks"][0]["role"] == "bottom"
    assert result["normalized"]["templates"]["bottom"]["font_family"] == "Inter"
    assert result["normalized"]["templates"]["bottom"]["font_size_scale"] == 1.08
    assert result["normalized"]["templates"]["bottom"]["font_weight"] == 900
    assert result["normalized"]["templates"]["bottom"]["italic"] is True
    assert result["normalized"]["templates"]["bottom"]["letter_spacing"] == 1
    assert result["normalized"]["templates"]["bottom"]["line_spacing"] == 1.2
    assert result["normalized"]["templates"]["bottom"]["margin_l"] == 72
    assert result["normalized"]["templates"]["bottom"]["margin_r"] == 84
    assert result["normalized"]["templates"]["bottom"]["margin_v"] == 112
    assert result["normalized"]["templates"]["bottom"]["max_width_ratio"] == 0.82
    assert result["normalized"]["templates"]["bottom"]["max_chars_per_line"] == 18
    assert result["normalized"]["templates"]["bottom"]["max_lines"] == 2
    assert result["normalized"]["templates"]["bottom"]["skew_x_deg"] == 6
    assert result["normalized"]["templates"]["bottom"]["skew_y_deg"] == -3
    assert result["normalized"]["templates"]["bottom"]["fade_in_ms"] == 120
    assert result["normalized"]["templates"]["bottom"]["fade_out_ms"] == 80
    assert result["normalized"]["template_variants"]["highlight"][0]["id"] == "emphasis"
    assert any("mask" in warning for warning in result["warnings"])


def test_validate_template_set_v2_rejects_non_object_payload():
    result = dsl_v2.validate_template_set_v2(["not", "a", "template"])

    assert result["ok"] is False
    assert result["normalized"] is None
    assert any("payload must be an object" in warning for warning in result["warnings"])


def test_normalize_blocks_strips_roles_and_skips_unsupported_roles():
    result = dsl_v2.validate_template_set_v2(
        {
            "id": "template-roles",
            "name": "Roles",
            "blocks": [
                {"id": "bottom-main", "role": " Bottom ", "style": {"font_family": "Inter"}},
                {"id": "bad-main", "role": "caption", "style": {"font_family": "Inter"}},
            ],
        }
    )

    assert result["ok"] is True
    assert [block["role"] for block in result["normalized"]["blocks"]] == ["bottom"]
    assert result["normalized"]["templates"]["bottom"]["font_family"] == "Inter"
    assert all(block["role"] != "caption" for block in result["normalized"]["blocks"])
    assert any("unsupported role" in warning and "caption" in warning for warning in result["warnings"])


def test_block_position_compiles_to_legacy_template_when_style_layout_is_absent():
    result = dsl_v2.validate_template_set_v2(
        {
            "id": "template-position",
            "name": "Position",
            "blocks": [
                {
                    "id": "bottom-main",
                    "role": "bottom",
                    "position": {"x": 0.25, "y": 0.6, "anchor": "left"},
                    "style": {"font_family": "Inter"},
                }
            ],
        }
    )

    template = result["normalized"]["templates"]["bottom"]

    assert template["x_percent"] == 25
    assert template["y_percent"] == 60
    assert template["alignment"] == "left"
    assert template["position"] == "center"


def test_style_layout_fields_take_precedence_over_block_position():
    result = dsl_v2.validate_template_set_v2(
        {
            "id": "template-layout-priority",
            "name": "Layout Priority",
            "blocks": [
                {
                    "id": "bottom-main",
                    "role": "bottom",
                    "position": {"x": 0.25, "y": 0.6, "anchor": "left"},
                    "style": {
                        "font_family": "Inter",
                        "position": "bottom",
                        "alignment": "right",
                        "x_percent": 80,
                        "y_percent": 78,
                    },
                }
            ],
        }
    )

    template = result["normalized"]["templates"]["bottom"]

    assert template["x_percent"] == 80
    assert template["y_percent"] == 78
    assert template["alignment"] == "right"
    assert template["position"] == "bottom"


def test_numeric_style_fields_are_coerced_or_dropped_with_warning():
    result = dsl_v2.validate_template_set_v2(
        {
            "id": "template-style",
            "name": "Style",
            "blocks": [
                {
                    "id": "bottom-main",
                    "role": "bottom",
                    "style": {
                        "font_size": "64",
                        "outline_width": "wide",
                        "shadow_depth": None,
                        "shadow": "3",
                        "font_size_scale": "1.1",
                        "font_scale": False,
                        "margin_v": "112",
                        "max_width": "bad",
                        "rotate": "-2",
                        "skew": 6,
                    },
                }
            ],
        }
    )

    style = result["normalized"]["blocks"][0]["style"]
    template = result["normalized"]["templates"]["bottom"]

    assert style["font_size"] == 64
    assert style["shadow"] == 3
    assert style["font_size_scale"] == 1.1
    assert style["margin_v"] == 112
    assert style["rotate"] == -2
    assert style["skew"] == 6
    assert "outline_width" not in style
    assert "shadow_depth" not in style
    assert "font_scale" not in style
    assert "max_width" not in style
    assert template["outline_width"] == 3
    assert template["shadow_depth"] == 3
    assert any("outline_width" in warning for warning in result["warnings"])
    assert any("font_scale" in warning for warning in result["warnings"])


def test_invalid_renderer_templates_and_block_fields_are_sanitized():
    result = dsl_v2.validate_template_set_v2(
        {
            "id": "template-shapes",
            "name": "Shapes",
            "renderer_mode": {"bad": "shape"},
            "templates": {
                "bottom": "bad",
                "caption": {"font_family": "Caption"},
                "highlight": {"font_family": "Legacy Highlight"},
            },
            "blocks": [
                {
                    "id": "bottom-main",
                    "role": "bottom",
                    "style": {"font_family": "Inter", "primary_color": "#FFFFFF"},
                    "mask": {"type": "rounded_rect"},
                    "unknown_field": {"keep": False},
                }
            ],
        }
    )

    block = result["normalized"]["blocks"][0]

    assert result["ok"] is True
    assert result["normalized"]["renderer_mode"] == "ass_plus"
    assert isinstance(result["normalized"]["templates"]["bottom"], dict)
    assert result["normalized"]["templates"]["bottom"]["font_family"] == "Inter"
    assert result["normalized"]["templates"]["highlight"]["font_family"] == "Legacy Highlight"
    assert "caption" not in result["normalized"]["templates"]
    assert "unknown_field" not in block
    assert "mask" not in block
    assert any("renderer_mode" in warning for warning in result["warnings"])
    assert any("template" in warning and "bottom" in warning for warning in result["warnings"])
    assert any("template" in warning and "caption" in warning for warning in result["warnings"])
    assert any("unknown block field" in warning and "unknown_field" in warning for warning in result["warnings"])


def test_block_shape_fields_are_normalized_to_safe_types():
    result = dsl_v2.validate_template_set_v2(
        {
            "id": "template-block-shapes",
            "name": "Block Shapes",
            "blocks": [
                {
                    "id": {},
                    "role": "bottom",
                    "track_id": [],
                    "position": "bad",
                    "animations": ["bad"],
                    "style": {"font_family": "Inter"},
                }
            ],
        }
    )

    block = result["normalized"]["blocks"][0]

    assert result["ok"] is True
    assert block["position"] == {}
    assert block["animations"] == {}
    assert isinstance(block["id"], str)
    assert block["id"]
    assert isinstance(block["track_id"], str)
    assert block["track_id"] == "main"
    assert any("position" in warning for warning in result["warnings"])
    assert any("animations" in warning for warning in result["warnings"])


def test_deep_dict_returns_deep_copy_for_dict_values():
    source = {"style": {"font_family": "Inter"}}

    copied = deep_dict(source)
    copied["style"]["font_family"] = "PingFang SC"

    assert source["style"]["font_family"] == "Inter"
    assert deep_dict(["not", "a", "dict"]) == {}
