import subprocess
from types import SimpleNamespace

import pytest

from autovideo.services import rendering
from autovideo.services.subtitles import ffmpeg_burner


def test_burn_ass_subtitles_escapes_filter_path_special_chars(tmp_path, monkeypatch):
    input_path = tmp_path / "input.mp4"
    ass_path = tmp_path / "sub,clip;[v1]quote'colon:name.ass"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"video")
    ass_path.write_text("[Script Info]\n", encoding="utf-8")
    captured_command = []

    def fake_run(command, **kwargs):
        del kwargs
        captured_command.extend(command)
        output_path.write_bytes(b"burned")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(ffmpeg_burner.subprocess, "run", fake_run)

    assert ffmpeg_burner.burn_ass_subtitles("ffmpeg", input_path, ass_path, output_path, 10) == output_path

    vf_arg = captured_command[captured_command.index("-vf") + 1]
    assert "ass=filename=" in vf_arg
    assert "sub\\,clip\\;\\[v1\\]quote\\'colon\\:name.ass" in vf_arg
    assert "sub,clip" not in vf_arg
    assert "clip;" not in vf_arg
    assert "[v1]quote" not in vf_arg
    assert "colon:name.ass" not in vf_arg


def test_burn_ass_subtitles_timeout_raises_render_error(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr=b"burn timeout detail")

    monkeypatch.setattr(ffmpeg_burner.subprocess, "run", fake_run)

    with pytest.raises(rendering.FfmpegRenderFailedError, match="字幕烧录超时") as exc_info:
        ffmpeg_burner.burn_ass_subtitles(
            "ffmpeg",
            tmp_path / "input.mp4",
            tmp_path / "subtitles.ass",
            tmp_path / "output.mp4",
            0.01,
        )

    assert "burn timeout detail" in exc_info.value.stderr


def test_burn_ass_subtitles_nonzero_raises_with_stderr(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        del command, kwargs
        return SimpleNamespace(returncode=12, stderr="burn failed detail", stdout="")

    monkeypatch.setattr(ffmpeg_burner.subprocess, "run", fake_run)

    with pytest.raises(rendering.FfmpegRenderFailedError, match="字幕烧录失败") as exc_info:
        ffmpeg_burner.burn_ass_subtitles(
            "ffmpeg",
            tmp_path / "input.mp4",
            tmp_path / "subtitles.ass",
            tmp_path / "output.mp4",
            10,
        )

    assert "burn failed detail" in exc_info.value.stderr


def test_burn_ass_subtitles_missing_output_raises(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        del command, kwargs
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(ffmpeg_burner.subprocess, "run", fake_run)

    with pytest.raises(rendering.FfmpegRenderFailedError, match="未生成字幕烧录输出视频"):
        ffmpeg_burner.burn_ass_subtitles(
            "ffmpeg",
            tmp_path / "input.mp4",
            tmp_path / "subtitles.ass",
            tmp_path / "output.mp4",
            10,
        )
