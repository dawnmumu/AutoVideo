import subprocess

import pytest

from autovideo.core.settings import Settings
from autovideo.services import rendering


def test_ffmpeg_command_burns_ass_when_subtitles_enabled(tmp_path):
    material_path = tmp_path / "clip.mp4"
    ass_path = tmp_path / "subtitles.ass"
    output_path = tmp_path / "output.mp4"
    material_path.write_bytes(b"video")
    ass_path.write_text("[Script Info]\n", encoding="utf-8")

    command = rendering._build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        render_items=[
            (
                {"duration": 1},
                {
                    "storage_path": str(material_path),
                    "content_type": "video/mp4",
                },
            )
        ],
        output_path=output_path,
        aspect_ratio="9:16",
        source_subtitle_masks=[False],
        ass_path=ass_path,
    )

    filter_index = command.index("-filter_complex") + 1
    assert "ass=" in command[filter_index]
    assert "subtitles.ass" in command[filter_index]
    assert argv_has_output(command, output_path)


def test_ffmpeg_command_escapes_ass_filter_path_special_chars(tmp_path):
    material_path = tmp_path / "clip.mp4"
    ass_path = tmp_path / "sub,clip;[v1]quote'colon:name.ass"
    output_path = tmp_path / "output.mp4"
    material_path.write_bytes(b"video")
    ass_path.write_text("[Script Info]\n", encoding="utf-8")

    command = rendering._build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        render_items=[({"duration": 1}, {"storage_path": str(material_path), "content_type": "video/mp4"})],
        output_path=output_path,
        aspect_ratio="9:16",
        source_subtitle_masks=[False],
        ass_path=ass_path,
    )

    filter_index = command.index("-filter_complex") + 1
    filter_arg = command[filter_index]
    assert "ass=filename=" in filter_arg
    assert "sub\\,clip\\;\\[v1\\]quote\\'colon\\:name.ass" in filter_arg
    assert "sub,clip" not in filter_arg
    assert "clip;" not in filter_arg
    assert "[v1]quote" not in filter_arg
    assert "colon:name.ass" not in filter_arg


def test_ffmpeg_command_masks_source_subtitles_before_concat(tmp_path):
    material_path = tmp_path / "clip.mp4"
    output_path = tmp_path / "output.mp4"
    material_path.write_bytes(b"video")

    command = rendering._build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        render_items=[
            (
                {"duration": 1},
                {
                    "storage_path": str(material_path),
                    "content_type": "video/mp4",
                },
            )
        ],
        output_path=output_path,
        aspect_ratio="9:16",
        source_subtitle_masks=[True],
        ass_path=None,
    )

    filter_index = command.index("-filter_complex") + 1
    assert "drawbox=x=0:y=1498:w=1080:h=422:color=black@1:t=fill" in command[filter_index]


def argv_has_output(command: list[str], output_path):
    return command[-1] == str(output_path)


@pytest.mark.parametrize("duration", [float("inf"), float("nan"), 301])
def test_build_render_timeline_rejects_unbounded_shot_duration(duration):
    with pytest.raises(rendering.FfmpegRenderFailedError):
        rendering.build_render_timeline(
            title="无界时长",
            script={
                "shots": [
                    {
                        "index": 1,
                        "duration": duration,
                        "narration": "旁白",
                    }
                ]
            },
            shot_materials=[{"shot_index": 1, "material_id": "material-1"}],
        )


def test_build_render_timeline_rejects_unbounded_total_duration():
    with pytest.raises(rendering.FfmpegRenderFailedError):
        rendering.build_render_timeline(
            title="总时长过长",
            script={
                "shots": [
                    {"index": 1, "duration": 200, "narration": "旁白 1"},
                    {"index": 2, "duration": 101, "narration": "旁白 2"},
                ]
            },
            shot_materials=[
                {"shot_index": 1, "material_id": "material-1"},
                {"shot_index": 2, "material_id": "material-2"},
            ],
        )


def test_render_mix_video_validates_timeline_before_ffmpeg_availability(tmp_path):
    with pytest.raises(rendering.FfmpegRenderFailedError):
        rendering.render_mix_video(
            settings=Settings(
                _env_file=None,
                data_dir=tmp_path,
                ffmpeg_path="missing-autovideo-ffmpeg-binary",
            ),
            output_dir=tmp_path / "outputs",
            timeline={
                "title": "无界 timeline",
                "total_duration": float("inf"),
                "items": [],
            },
            materials_by_id={},
            aspect_ratio="9:16",
        )


def test_render_mix_video_maps_ffmpeg_timeout_to_render_error(tmp_path, monkeypatch):
    material_path = tmp_path / "clip.mp4"
    material_path.write_bytes(b"video")

    def fake_run(*args, **kwargs):
        assert kwargs["timeout"] > 0
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(rendering.shutil, "which", lambda value: value)
    monkeypatch.setattr(rendering.subprocess, "run", fake_run)

    with pytest.raises(rendering.FfmpegRenderFailedError, match="超时"):
        rendering.render_mix_video(
            settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path="ffmpeg"),
            output_dir=tmp_path / "outputs",
            timeline={
                "title": "超时渲染",
                "total_duration": 1,
                "items": [
                    {
                        "shot_index": 1,
                        "start_time": 0,
                        "end_time": 1,
                        "duration": 1,
                        "subtitle": "字幕",
                        "material_id": "material-1",
                    }
                ],
            },
            materials_by_id={
                "material-1": {
                    "storage_path": str(material_path),
                    "content_type": "video/mp4",
                }
            },
            aspect_ratio="9:16",
        )
