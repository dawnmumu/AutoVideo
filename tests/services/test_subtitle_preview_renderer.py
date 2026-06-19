from pathlib import Path

from autovideo.services.subtitles import preview_renderer, template_presets

DEFAULT_SUBTITLE_PREVIEW_TEXT = "这是字幕预览，支持多个位置和不同倾斜角度"


def test_preview_ass_uses_block_animation_effects(tmp_path: Path):
    preset = template_presets.list_presets()[0]

    highlight_ass = preview_renderer._write_preview_ass(
        tmp_path / "highlight.ass",
        preset,
        "highlight",
        "强调字幕",
        1200,
        (1080, 1920),
    ).read_text(encoding="utf-8")
    punch_ass = preview_renderer._write_preview_ass(
        tmp_path / "punch.ass",
        preset,
        "punch",
        "冲击字幕",
        1200,
        (1080, 1920),
    ).read_text(encoding="utf-8")

    assert "\\move(" in highlight_ass
    assert "\\fad(180,80)" in highlight_ass
    assert "\\fscx80\\fscy80\\t(0,140,\\fscx100\\fscy100)" in punch_ass


def test_preview_ass_uses_current_default_text_for_empty_sample_text(tmp_path: Path):
    template_set = {
        "blocks": [
            {
                "role": "bottom",
                "style": {},
                "spans": [],
            }
        ]
    }

    preview_ass = preview_renderer._write_preview_ass(
        tmp_path / "empty-sample.ass",
        template_set,
        "bottom",
        "",
        1200,
        (1080, 1920),
    ).read_text(encoding="utf-8")

    assert DEFAULT_SUBTITLE_PREVIEW_TEXT[:6] in preview_ass
    assert DEFAULT_SUBTITLE_PREVIEW_TEXT[-4:] in preview_ass
    assert "AI 提升效率" not in preview_ass
