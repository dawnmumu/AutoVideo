from autovideo.services.subtitles import dsl_v2


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
