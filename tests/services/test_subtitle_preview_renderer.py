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


def test_preview_ass_scales_font_size_to_match_live_preview_display(tmp_path: Path):
    preset = template_presets.list_presets()[0]

    preview_ass = preview_renderer._write_preview_ass(
        tmp_path / "scaled-font.ass",
        preset,
        "bottom",
        DEFAULT_SUBTITLE_PREVIEW_TEXT,
        1200,
        (1080, 1920),
        match_live_preview_font_size=True,
    ).read_text(encoding="utf-8")

    assert "\\fs62" in preview_ass
    assert "\\fs65" in preview_ass


def test_preview_ass_uses_frontend_rounding_for_half_pixel_font_size(tmp_path: Path):
    template_set = {
        "blocks": [
            {
                "role": "bottom",
                "style": {
                    "font_size": 54,
                    "font_size_scale": 1.03125,
                },
                "spans": [],
            }
        ]
    }

    preview_ass = preview_renderer._write_preview_ass(
        tmp_path / "half-pixel-font.ass",
        template_set,
        "bottom",
        "半像素字号",
        1200,
        (1080, 1920),
        match_live_preview_font_size=True,
    ).read_text(encoding="utf-8")

    assert "\\fs66" in preview_ass


def test_preview_ass_scales_explicit_span_font_size_to_match_live_preview_display(tmp_path: Path):
    template_set = {
        "blocks": [
            {
                "role": "bottom",
                "style": {},
                "spans": [
                    {
                        "selector": {"type": "range", "start": 0, "end": 2},
                        "style": {"font_size": 24},
                    }
                ],
            }
        ]
    }

    preview_ass = preview_renderer._write_preview_ass(
        tmp_path / "span-font-size.ass",
        template_set,
        "bottom",
        "显式字号",
        1200,
        (1080, 1920),
        match_live_preview_font_size=True,
    ).read_text(encoding="utf-8")

    assert "\\fs93" in preview_ass


def test_preview_timeline_keeps_original_block_font_size(tmp_path: Path, monkeypatch):
    captured_ass = []

    def fake_run_preview_command(command, output_path):
        ass_argument = command[command.index("-vf") + 1]
        ass_path = Path(ass_argument.removeprefix("ass=filename="))
        captured_ass.append(ass_path.read_text(encoding="utf-8"))
        output_path.write_bytes(b"mp4")

    monkeypatch.setattr(preview_renderer, "_resolve_ffmpeg", lambda ffmpeg_path: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preview_renderer, "_run_preview_command", fake_run_preview_command)

    preview_renderer.render_preview_timeline(
        "ffmpeg",
        {"blocks": [{"role": "bottom", "style": {"font_size": 54}, "spans": []}]},
        "bottom",
        "9:16",
        "时间线预览",
        1200,
        tmp_path,
    )

    assert "\\fs54" in captured_ass[0]
    assert "\\fs62" not in captured_ass[0]


def test_preview_ass_uses_style_layout_fields_without_caption_board(tmp_path: Path):
    template_set = {
        "templates": {
            "bottom": {
                "font_family": "PingFang SC",
                "font_size": 54,
                "primary_color": "#FFFFFF",
                "outline_color": "#654321",
                "shadow_color": "#123456",
                "background_color": "#000000",
            }
        },
        "blocks": [
            {
                "role": "bottom",
                "style": {
                    "font_size": 72,
                    "primary_color": "#00E5FF",
                    "outline_color": "#654321",
                    "shadow_color": "#123456",
                    "background_color": "#000000",
                    "x_percent": 40,
                    "y_percent": 62,
                    "alignment": "left",
                },
                "spans": [],
            }
        ],
    }

    preview_ass = preview_renderer._write_preview_ass(
        tmp_path / "style-position.ass",
        template_set,
        "bottom",
        "样式定位",
        1200,
        (1080, 1920),
    ).read_text(encoding="utf-8")

    assert "\\an4\\pos(432,1190.4)" in preview_ass
    assert "BackColour, Bold" in preview_ass
    bottom_style = next(line for line in preview_ass.splitlines() if line.startswith("Style: bottom,"))
    assert "&H00563412" in bottom_style
    assert "&H00000000" not in bottom_style


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


def test_preview_png_captures_frame_after_subtitle_fade_in(tmp_path: Path, monkeypatch):
    commands = []

    def fake_run_preview_command(command, output_path):
        commands.append(command)
        output_path.write_bytes(b"png")

    monkeypatch.setattr(preview_renderer, "_resolve_ffmpeg", lambda ffmpeg_path: "/usr/bin/ffmpeg")
    monkeypatch.setattr(preview_renderer, "_run_preview_command", fake_run_preview_command)

    preview_renderer.render_preview_png(
        "ffmpeg",
        {"blocks": [{"role": "bottom", "style": {"fade_in_ms": 120}, "spans": []}]},
        "bottom",
        "9:16",
        "淡入字幕",
        tmp_path,
    )

    command = commands[0]
    assert command[command.index("-ss") + 1] == "0.600"
    assert command.index("-ss") > command.index("-vf")
    assert command.index("-frames:v") > command.index("-ss")


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
