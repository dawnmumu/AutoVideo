from pathlib import Path

from autovideo.services.subtitles import preview_renderer, template_presets


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
