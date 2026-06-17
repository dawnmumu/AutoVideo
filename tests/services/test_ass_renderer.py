from pathlib import Path

from autovideo.services.subtitles import ass_renderer, event_enrichment, keyword_spans, template_assignment
from autovideo.services.subtitles.timeline import SubtitleEvent


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
