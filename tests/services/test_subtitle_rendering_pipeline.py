import json
import os

import pytest

from autovideo.core.settings import Settings
from autovideo.services import rendering


def _fake_ffmpeg(tmp_path):
    log_path = tmp_path / "ffmpeg-argv.json"
    ffmpeg_path = tmp_path / "fake-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(log_path)!r}).write_text(json.dumps(sys.argv[1:], ensure_ascii=False), encoding='utf-8')\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'video')\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    return str(ffmpeg_path), log_path


def _failing_fake_ffmpeg(tmp_path):
    ffmpeg_path = tmp_path / "failing-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('base render failed')\n"
        "sys.exit(12)\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    return str(ffmpeg_path)


def _burn_failing_fake_ffmpeg(tmp_path):
    ffmpeg_path = tmp_path / "burn-failing-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "if '-vf' in sys.argv:\n"
        "    sys.stderr.write('burn render failed')\n"
        "    sys.exit(17)\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'base video')\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    return str(ffmpeg_path)


def _timeline():
    return {
        "title": "字幕渲染",
        "total_duration": 1,
        "items": [
            {
                "shot_index": 1,
                "start_time": 0,
                "end_time": 1,
                "duration": 1,
                "subtitle": "AI 提升效率",
                "material_id": "material-1",
            }
        ],
    }


def _materials(tmp_path):
    material_path = tmp_path / "caption_clip.mp4"
    material_path.write_bytes(b"video")
    return {"material-1": {"storage_path": str(material_path), "content_type": "video/mp4", "source_type": "upload"}}


def _template():
    return {
        "id": "template-1",
        "name": "字幕模板",
        "templates": {
            "bottom": {"font_family": "PingFang SC", "font_size": 54, "primary_color": "#FFFFFF"},
            "highlight": {"font_family": "PingFang SC", "font_size": 60, "primary_color": "#FFD54F"},
            "punch": {"font_family": "PingFang SC", "font_size": 68, "primary_color": "#FFFFFF"},
        },
        "blocks": [],
    }


def test_render_mix_video_writes_ass_base_video_and_burned_output(tmp_path):
    ffmpeg_path, log_path = _fake_ffmpeg(tmp_path)

    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=ffmpeg_path),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[True],
    )

    assert result.status == "subtitle_burned"
    assert result.output_path == tmp_path / "outputs" / "output.mp4"
    assert (tmp_path / "outputs" / "output.base.mp4").is_file()
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()
    assert "ass=" in " ".join(json.loads(log_path.read_text(encoding="utf-8")))


def test_render_mix_video_without_ffmpeg_still_writes_timeline_srt_and_ass(tmp_path):
    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg"),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[False],
    )

    assert result.output_path is None
    assert result.status == "manifest_only"
    assert result.renderer == "ffmpeg_unavailable"
    assert result.base_video_skipped is True
    assert result.subtitle_burn_skipped is True
    assert (tmp_path / "outputs" / "timeline.json").is_file()
    assert (tmp_path / "outputs" / "subtitles.srt").is_file()
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()
    assert not (tmp_path / "outputs" / "output.base.mp4").exists()


def test_render_mix_video_without_render_items_raises_before_ffmpeg_availability(tmp_path):
    output_dir = tmp_path / "outputs"

    with pytest.raises(rendering.FfmpegRenderFailedError, match="没有可用于渲染的镜头素材"):
        rendering.render_mix_video(
            settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg"),
            output_dir=output_dir,
            timeline=_timeline(),
            materials_by_id={},
            aspect_ratio="9:16",
            subtitle_enabled=True,
            subtitle_template_set=_template(),
            source_subtitle_masks=[],
        )

    assert (output_dir / "timeline.json").is_file()
    assert (output_dir / "subtitles.srt").is_file()
    assert (output_dir / "subtitles.ass").is_file()


def test_render_mix_video_base_failure_keeps_subtitle_artifacts(tmp_path):
    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=_failing_fake_ffmpeg(tmp_path)),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[False],
    )

    assert result.output_path is None
    assert result.status == "base_video_failed"
    assert "base render failed" in result.error_summary
    assert (tmp_path / "outputs" / "timeline.json").is_file()
    assert (tmp_path / "outputs" / "subtitles.srt").is_file()
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()


def test_render_mix_video_burn_failure_keeps_base_video_and_subtitle_artifacts(tmp_path):
    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=_burn_failing_fake_ffmpeg(tmp_path)),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[False],
    )

    base_output_path = tmp_path / "outputs" / "output.base.mp4"
    assert result.status == "subtitle_burn_failed"
    assert result.output_path == base_output_path
    assert result.base_output_path == "output.base.mp4"
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()
    assert "burn render failed" in result.error_summary


def test_source_subtitle_masks_follow_material_source_and_markers(tmp_path):
    from autovideo.services.subtitles.source_masks import build_source_subtitle_masks

    captioned = tmp_path / "口播素材" / "clip.mp4"
    clean = tmp_path / "素材" / "clip.mp4"

    assert build_source_subtitle_masks("local", [str(captioned), str(clean)], subtitle_enabled=True) == [True, False]
    assert build_source_subtitle_masks("hybrid", [str(captioned)], subtitle_enabled=True) == [True]
    assert build_source_subtitle_masks("online", [str(captioned)], subtitle_enabled=True) == [False]
    assert build_source_subtitle_masks("local", [str(captioned)], subtitle_enabled=False) == [False]
