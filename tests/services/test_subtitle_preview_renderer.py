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


def test_preview_png_uses_neutral_ffmpeg_background(tmp_path: Path, monkeypatch):
    commands = []

    def fake_run_preview_command(command, output_path):
        commands.append(command)
        output_path.write_bytes(b"png")

    monkeypatch.setattr(preview_renderer, "_resolve_ffmpeg", lambda ffmpeg_path: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preview_renderer, "_run_preview_command", fake_run_preview_command)

    preview_renderer.render_preview_png(
        "ffmpeg",
        {"blocks": [{"role": "bottom", "style": {}, "spans": []}]},
        "bottom",
        "9:16",
        "浅色预览",
        tmp_path,
    )

    input_filter = commands[0][commands[0].index("-i") + 1]
    assert "color=c=black" not in input_filter
    assert "color=c=0xE2E8F0" in input_filter


def test_preview_timeline_uses_neutral_ffmpeg_background(tmp_path: Path, monkeypatch):
    commands = []

    def fake_run_preview_command(command, output_path):
        commands.append(command)
        output_path.write_bytes(b"mp4")

    monkeypatch.setattr(preview_renderer, "_resolve_ffmpeg", lambda ffmpeg_path: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preview_renderer, "_run_preview_command", fake_run_preview_command)

    preview_renderer.render_preview_timeline(
        "ffmpeg",
        {"blocks": [{"role": "bottom", "style": {}, "spans": []}]},
        "bottom",
        "9:16",
        "浅色时间线预览",
        1200,
        tmp_path,
    )

    input_filter = commands[0][commands[0].index("-i") + 1]
    assert "color=c=black" not in input_filter
    assert "color=c=0xE2E8F0" in input_filter
