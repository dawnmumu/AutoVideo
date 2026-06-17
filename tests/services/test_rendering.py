import subprocess

import pytest

from autovideo.core.settings import Settings
from autovideo.services import rendering


def test_ffmpeg_command_keeps_subtitles_as_sidecar_only(tmp_path):
    material_path = tmp_path / "clip.mp4"
    subtitle_path = tmp_path / "subtitles.srt"
    output_path = tmp_path / "output.mp4"
    material_path.write_bytes(b"video")
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕\n", encoding="utf-8")

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
        subtitles_path=subtitle_path,
        output_path=output_path,
        aspect_ratio="9:16",
    )

    filter_index = command.index("-filter_complex") + 1
    assert "subtitles=" not in command[filter_index]
    assert "drawtext=" not in command[filter_index]
    assert str(subtitle_path) not in command
    assert "-c:s" not in command
    assert "mov_text" not in command


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
