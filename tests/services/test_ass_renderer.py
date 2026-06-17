from pathlib import Path

from autovideo.services import subtitles
from autovideo.services.subtitles import ass_renderer, event_enrichment, keyword_spans, template_assignment
from autovideo.services.subtitles.timeline import SubtitleEvent


def _dialogue_ranges(content: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for line in content.splitlines():
        if not line.startswith("Dialogue: "):
            continue
        fields = line.split(",", 3)
        ranges.append((_ass_time_to_centiseconds(fields[1]), _ass_time_to_centiseconds(fields[2])))
    return ranges


def _ass_time_to_centiseconds(value: str) -> int:
    hours_text, minutes_text, seconds_text = value.split(":")
    seconds, centiseconds = seconds_text.split(".")
    return (
        int(hours_text) * 360000
        + int(minutes_text) * 6000
        + int(seconds) * 100
        + int(centiseconds)
    )


def _dialogue_fields(content: str) -> list[list[str]]:
    return [line.split(",", 9) for line in content.splitlines() if line.startswith("Dialogue: ")]


def _template():
    return {
        "id": "template-1",
        "name": "字幕模板",
        "templates": {
            "bottom": {
                "font_family": "PingFang SC",
                "font_size": 54,
                "font_size_scale": 1.1,
                "primary_color": "#FFFFFF",
                "outline_width": 4,
                "shadow": 3,
                "margin_v": 112,
                "rotate": -2,
            },
            "highlight": {"font_family": "PingFang SC", "font_size": 60, "primary_color": "#FFD54F"},
            "punch": {"font_family": "PingFang SC", "font_size": 68, "primary_color": "#FFFFFF"},
        },
        "blocks": [
            {
                "id": "bottom-main",
                "role": "bottom",
                "track_id": "main",
                "style": {"font_family": "PingFang SC", "font_size": 54, "primary_color": "#FFFFFF"},
                "spans": [{"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}}],
                "animations": {"in": {"type": "fade", "duration_ms": 120}},
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
                            "track_id": "main",
                            "style": {"font_family": "PingFang SC", "font_size": 60, "primary_color": "#FFD54F"},
                            "spans": [{"selector": {"type": "keyword", "value": "效率"}, "style": {"primary_color": "#00E5FF"}}],
                            "animations": {"in": {"type": "pop_in", "duration_ms": 140}},
                        }
                    ],
                }
            ]
        },
    }


def test_assignment_keyword_enrichment_and_ass_output(tmp_path: Path):
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=2000, text="业务团队协作", template="bottom")]

    assigned = template_assignment.assign_template_roles(events, _template(), random_seed=1)
    keyworded = keyword_spans.apply_keyword_spans(
        assigned,
        _template(),
        keyword_extractor=lambda payload, context: [{"index": 1, "terms": ["团队"]}],
        sample_rate=1,
        random_seed=1,
    )
    enriched = event_enrichment.enrich_subtitle_events(keyworded, _template(), (1080, 1920))
    output_path = ass_renderer.write_ass_file(tmp_path / "subtitles.ass", enriched, _template(), (1080, 1920))

    content = output_path.read_text(encoding="utf-8")
    assert "Style: bottom" in content
    assert "PingFang SC" in content
    assert "Style: bottom,PingFang SC,59," in content
    assert ",-2,1,4,3,2,60,60,112,1" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,bottom" in content
    assert "{\\c&H4FD5FF&}团队{\\r}" in content
    assert enriched[0].track_id == "main"
    assert enriched[0].event_animations["in"]["type"] == "fade"


def test_variant_block_is_used_when_assignment_selects_variant(tmp_path: Path):
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="AI 提升效率", template="bottom")]

    assigned = template_assignment.assign_template_roles(events, _template(), random_seed=1)
    enriched = event_enrichment.enrich_subtitle_events(assigned, _template(), (1080, 1920))
    output_path = ass_renderer.write_ass_file(tmp_path / "variant.ass", enriched, _template(), (1080, 1920))

    assert enriched[0].template == "highlight"
    assert enriched[0].template_variant == "emphasis"
    assert enriched[0].event_animations["in"]["type"] == "pop_in"
    assert "{\\c&HFFE500&}效率{\\r}" in output_path.read_text(encoding="utf-8")


def test_variant_block_merges_base_defaults_before_event_overrides():
    template = _template()
    template["blocks"].append(
        {
            "id": "highlight-base",
            "role": "highlight",
            "track_id": "base-track",
            "position": {"x": 0.5, "y": 0.7},
            "style": {"font_size": 50, "primary_color": "#FFFFFF", "outline_width": 3},
            "spans": [
                {"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}},
                {"selector": {"type": "keyword", "value": "效率"}, "style": {"primary_color": "#FFFFFF"}},
            ],
            "animations": {"in": {"type": "fade"}, "out": {"type": "fade_out"}},
        }
    )
    template["template_variants"]["highlight"][0]["blocks"][0]["track_id"] = "variant-track"
    events = [
        SubtitleEvent(
            index=1,
            shot_index=1,
            start_ms=0,
            end_ms=1000,
            text="AI 提升效率",
            template="highlight",
            template_variant="emphasis",
            style={"outline_width": 5},
            spans=[{"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FF00FF"}}],
        )
    ]

    enriched = event_enrichment.enrich_subtitle_events(events, template, (1080, 1920))
    ai_spans = [
        span
        for span in enriched[0].spans
        if span.get("selector") == {"type": "keyword", "value": "AI"}
    ]
    efficiency_spans = [
        span
        for span in enriched[0].spans
        if span.get("selector") == {"type": "keyword", "value": "效率"}
    ]

    assert enriched[0].track_id == "variant-track"
    assert enriched[0].position == {"x": 0.5, "y": 0.7}
    assert enriched[0].event_animations["in"]["type"] == "pop_in"
    assert enriched[0].event_animations["out"]["type"] == "fade_out"
    assert enriched[0].style["font_size"] == 60
    assert enriched[0].style["outline_width"] == 5
    assert len(ai_spans) == 1
    assert ai_spans[0]["style"]["primary_color"] == "#FF00FF"
    assert len(efficiency_spans) == 1
    assert efficiency_spans[0]["style"]["primary_color"] == "#00E5FF"


def test_keyword_extractor_failure_keeps_events_renderable():
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="AI 办公", template="bottom")]

    result = keyword_spans.apply_keyword_spans(
        events,
        _template(),
        keyword_extractor=lambda payload, context: (_ for _ in ()).throw(RuntimeError("llm failed")),
        sample_rate=1,
        random_seed=1,
    )

    assert result[0].text == "AI 办公"
    assert result[0].keyword_spans == []


def test_keyword_extractor_failure_removes_previous_generated_spans():
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="AI 办公", template="bottom")]
    keyworded = keyword_spans.apply_keyword_spans(
        events,
        _template(),
        keyword_extractor=lambda payload, context: [{"index": 1, "terms": ["AI"]}],
        sample_rate=1,
        random_seed=1,
    )

    result = keyword_spans.apply_keyword_spans(
        keyworded,
        _template(),
        keyword_extractor=lambda payload, context: (_ for _ in ()).throw(RuntimeError("llm failed")),
        sample_rate=1,
        random_seed=1,
    )

    content = ass_renderer.render_ass(result, _template(), (1080, 1920))
    assert result[0].keyword_spans == []
    assert "{\\c&H4FD5FF&}AI{\\r}" not in content


def test_event_span_overrides_block_span_with_same_selector():
    events = [
        SubtitleEvent(
            index=1,
            shot_index=1,
            start_ms=0,
            end_ms=1000,
            text="AI 办公",
            template="bottom",
            spans=[{"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#00E5FF"}}],
        )
    ]

    enriched = event_enrichment.enrich_subtitle_events(events, _template(), (1080, 1920))
    ai_spans = [
        span
        for span in enriched[0].spans
        if span.get("selector") == {"type": "keyword", "value": "AI"}
    ]
    content = ass_renderer.render_ass(enriched, _template(), (1080, 1920))

    assert len(ai_spans) == 1
    assert ai_spans[0]["style"]["primary_color"] == "#00E5FF"
    assert "{\\c&HFFE500&}AI{\\r}" in content
    assert "{\\c&H4FD5FF&}AI{\\r}" not in content


def test_ass_renderer_emits_event_style_and_position_override_tags():
    template = _template()
    template["blocks"][0]["style"] = {"font_size": 72, "primary_color": "#00E5FF"}
    template["blocks"][0]["position"] = {"x": 0.25, "y": 0.75}
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="业务字幕", template="bottom")]

    enriched = event_enrichment.enrich_subtitle_events(events, template, (1080, 1920))
    content = ass_renderer.render_ass(enriched, template, (1080, 1920))

    assert "{\\fs72\\c&HFFE500&\\pos(270,1440)}业务字幕" in content


def test_ass_renderer_keeps_one_millisecond_event_visible():
    event = SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1, text="短", template="bottom")

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))

    assert "Dialogue: 0,0:00:00.00,0:00:00.01,bottom" in content


def test_ass_renderer_keeps_adjacent_same_track_dialogues_monotonic():
    events = [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=333, text="一", template="bottom"),
        SubtitleEvent(index=2, shot_index=1, start_ms=333, end_ms=667, text="二", template="bottom"),
        SubtitleEvent(index=3, shot_index=1, start_ms=667, end_ms=1000, text="三", template="bottom"),
    ]

    ranges = _dialogue_ranges(ass_renderer.render_ass(events, _template(), (1080, 1920)))

    assert all(end > start for start, end in ranges)
    assert ranges[1][0] >= ranges[0][1]
    assert ranges[2][0] >= ranges[1][1]


def test_ass_renderer_extends_tiny_same_track_dialogues_monotonically():
    events = [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1, text="一", template="bottom"),
        SubtitleEvent(index=2, shot_index=1, start_ms=1, end_ms=2, text="二", template="bottom"),
    ]

    ranges = _dialogue_ranges(ass_renderer.render_ass(events, _template(), (1080, 1920)))

    assert ranges == [(0, 1), (1, 2)]


def test_ass_renderer_times_independent_tracks_separately():
    events = [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1, text="主轨", template="bottom", track_id="main"),
        SubtitleEvent(index=2, shot_index=1, start_ms=0, end_ms=1, text="副轨", template="bottom", track_id="alt"),
    ]

    ranges = _dialogue_ranges(ass_renderer.render_ass(events, _template(), (1080, 1920)))

    assert ranges == [(0, 1), (0, 1)]


def test_ass_renderer_ignores_non_finite_event_style_and_position_values():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="稳定渲染",
        template="bottom",
        style={"font_size": float("nan"), "primary_color": "#00E5FF"},
        position={"x": float("inf"), "y": 0.5},
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))

    assert "\\fs54" in content
    assert "\\pos(" not in content


def test_ass_renderer_emits_event_outline_shadow_rotate_and_margin_overrides():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="样式字幕",
        template="bottom",
        style={
            "outline_width": 6,
            "outline_color": "#123456",
            "shadow_depth": 4,
            "shadow_color": "#ABCDEF",
            "rotate": -7,
            "margin_v": 88,
        },
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))
    fields = _dialogue_fields(content)[0]

    assert fields[7] == "88"
    assert "{\\bord6\\3c&H563412&\\shad4\\4c&HEFCDAB&\\frz-7}" in content


def test_keyword_reset_restores_full_event_style_overrides():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="AI 样式",
        template="bottom",
        spans=[{"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}}],
        style={
            "font_size": 72,
            "primary_color": "#00E5FF",
            "outline_width": 6,
            "outline_color": "#123456",
            "shadow": 4,
            "shadow_color": "#ABCDEF",
            "rotate": -7,
        },
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))
    reset_tags = "{\\fs72\\c&HFFE500&\\bord6\\3c&H563412&\\shad4\\4c&HEFCDAB&\\frz-7}"

    assert f"{reset_tags}{{\\c&H4FD5FF&}}AI{{\\r}}{reset_tags} 样式" in content


def test_ass_renderer_ignores_non_finite_outline_shadow_rotate_and_margin_values():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="稳定样式",
        template="bottom",
        style={
            "outline_width": float("nan"),
            "shadow_depth": float("inf"),
            "rotate": float("nan"),
            "margin_v": float("inf"),
        },
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))
    fields = _dialogue_fields(content)[0]
    dialogue = ",".join(fields)

    assert fields[7] == "0"
    assert "\\bord" not in dialogue
    assert "\\shad" not in dialogue
    assert "\\frz" not in dialogue
    assert "nan" not in dialogue.lower()
    assert "inf" not in dialogue.lower()


def test_keyword_span_restores_event_override_tags_after_reset():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="AI 办公",
        template="bottom",
        spans=[{"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}}],
        style={"font_size": 72, "primary_color": "#00E5FF"},
        position={"x": 0.25, "y": 0.75},
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))

    assert "{\\fs72\\c&HFFE500&\\pos(270,1440)}{\\c&H4FD5FF&}AI{\\r}{\\fs72\\c&HFFE500&\\pos(270,1440)} 办公" in content


def test_keyword_spans_do_not_match_inside_generated_ass_tags():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="AI H",
        template="bottom",
        spans=[
            {"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}},
            {"selector": {"type": "keyword", "value": "H"}, "style": {"primary_color": "#00E5FF"}},
        ],
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))

    assert "{\\c&H4FD5FF&}AI{\\r} {\\c&HFFE500&}H{\\r}" in content
    assert "{\\c&{" not in content


def test_keyword_span_absent_from_plain_text_does_not_match_ass_tag_text():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="AI 文案",
        template="bottom",
        spans=[
            {"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}},
            {"selector": {"type": "keyword", "value": "c"}, "style": {"primary_color": "#00E5FF"}},
        ],
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))

    assert "{\\c&H4FD5FF&}AI{\\r} 文案" in content
    assert "{\\c&HFFE500&}c{\\r}" not in content
    assert "{\\c&{" not in content


def test_overlapping_keyword_spans_skip_later_span():
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=1000,
        text="AI 提升",
        template="bottom",
        spans=[
            {"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}},
            {"selector": {"type": "keyword", "value": "AI 提升"}, "style": {"primary_color": "#00E5FF"}},
        ],
    )

    content = ass_renderer.render_ass([event], _template(), (1080, 1920))

    assert "{\\c&H4FD5FF&}AI{\\r} 提升" in content
    assert "{\\c&HFFE500&}AI 提升{\\r}" not in content


def test_subtitle_package_all_exports_task2_modules():
    assert {
        "timeline",
        "template_assignment",
        "keyword_spans",
        "event_enrichment",
        "ass_renderer",
    }.issubset(set(subtitles.__all__))
