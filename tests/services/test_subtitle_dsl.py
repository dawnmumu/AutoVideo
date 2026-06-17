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
                    "margin_v": 112,
                    "max_width": 0.82,
                    "rotate": -2,
                    "skew": 6,
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
    assert result["normalized"]["templates"]["bottom"]["margin_v"] == 112
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


def test_deep_dict_returns_deep_copy_for_dict_values():
    source = {"style": {"font_family": "Inter"}}

    copied = deep_dict(source)
    copied["style"]["font_family"] = "PingFang SC"

    assert source["style"]["font_family"] == "Inter"
    assert deep_dict(["not", "a", "dict"]) == {}
