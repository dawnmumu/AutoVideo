import asyncio
import json
import os
from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services import audio_mix


class FakeVoiceProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def list_voices(self) -> list[dict[str, object]]:
        return [
            {
                "ShortName": "zh-CN-XiaoxiaoNeural",
                "FriendlyName": "Microsoft Xiaoxiao",
                "Locale": "zh-CN",
                "Gender": "Female",
                "VoiceTag": {},
            }
        ]

    async def synthesize_to_file(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str,
        volume: str,
        pitch: str,
    ) -> None:
        self.calls.append(
            {
                "text": text,
                "voice_id": voice_id,
                "output_path": output_path,
                "rate": rate,
                "volume": volume,
                "pitch": pitch,
            }
        )
        output_path.write_bytes(f"mp3:{voice_id}:{text}".encode("utf-8"))


def test_build_audio_mix_status_reports_skipped_when_audio_not_requested() -> None:
    status = audio_mix.build_audio_mix_status(
        mixed=False,
        voiceover_requested=False,
        voiceover_clip_count=0,
        bgm_requested=False,
        bgm_volume=None,
        output=None,
    )

    assert status == {
        "status": "skipped",
        "voiceover_status": "not_requested",
        "voiceover_clip_count": 0,
        "bgm_status": "not_requested",
        "bgm_volume": None,
        "output": None,
    }


def test_build_audio_mix_status_reports_requested_bgm_not_mixed() -> None:
    status = audio_mix.build_audio_mix_status(
        mixed=False,
        voiceover_requested=False,
        voiceover_clip_count=0,
        bgm_requested=True,
        bgm_volume=0.12,
        output=None,
    )

    assert status["status"] == "skipped"
    assert status["bgm_status"] == "requested_not_mixed"
    assert status["bgm_volume"] == 0.12


def test_apply_audio_mix_reports_requested_bgm_when_video_is_unavailable(
    tmp_path: Path,
) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    tracks_dir = tmp_path / "bgm" / "tracks"
    tracks_dir.mkdir(parents=True)
    (tracks_dir / "ambient.mp3").write_bytes(b"fake bgm")

    status = audio_mix.apply_audio_mix(
        settings=settings,
        output_dir=tmp_path / "outputs",
        video_path=None,
        timeline={"items": []},
        voice_options={},
        bgm_options={
            "bgm_enabled": True,
            "bgm_volume": 0.18,
            "bgm_snapshot": {"filename": "ambient.mp3"},
        },
    )

    assert status["status"] == "skipped"
    assert status["bgm_status"] == "requested_not_mixed"
    assert status["bgm_volume"] == 0.18
    assert status["output"] is None


def test_apply_audio_mix_reports_requested_voiceover_not_mixed_when_video_is_unavailable(
    tmp_path: Path,
) -> None:
    provider = FakeVoiceProvider()
    status = audio_mix.apply_audio_mix(
        settings=Settings(_env_file=None, data_dir=tmp_path),
        output_dir=tmp_path / "outputs",
        video_path=None,
        timeline={
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "duration": 2,
                    "narration": "第一句旁白",
                }
            ]
        },
        voice_options={
            "voice_id": "zh-CN-XiaoxiaoNeural",
            "voice_provider": "edge_tts",
        },
        bgm_options={},
        provider=provider,
    )

    assert status["status"] == "skipped"
    assert status["voiceover_status"] == "requested_not_mixed"
    assert status["voiceover_clip_count"] == 0
    assert status["output"] is None
    assert provider.calls == []


def test_apply_audio_mix_reports_empty_voiceover_when_video_has_no_narration(
    tmp_path: Path,
) -> None:
    provider = FakeVoiceProvider()
    video_path = tmp_path / "output.mp4"
    video_path.write_bytes(b"silent video")

    status = audio_mix.apply_audio_mix(
        settings=Settings(_env_file=None, data_dir=tmp_path),
        output_dir=tmp_path / "outputs",
        video_path=video_path,
        timeline={
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "duration": 2,
                    "narration": "   ",
                }
            ]
        },
        voice_options={
            "voice_id": "zh-CN-XiaoxiaoNeural",
            "voice_provider": "edge_tts",
        },
        bgm_options={},
        provider=provider,
    )

    assert status["status"] == "skipped"
    assert status["voiceover_status"] == "empty"
    assert status["voiceover_clip_count"] == 0
    assert status["output"] is None
    assert provider.calls == []


def test_resolve_bgm_audio_rejects_snapshot_filename_outside_tracks_dir(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)

    with pytest.raises(audio_mix.AudioMixFailedError, match="BGM"):
        audio_mix.resolve_bgm_audio(
            settings,
            {
                "bgm_enabled": True,
                "bgm_snapshot": {
                    "filename": "../escape.mp3",
                    "media_type": "audio/mpeg",
                },
            },
        )


def test_build_audio_mix_command_mixes_narration_and_bgm(tmp_path: Path) -> None:
    video_path = tmp_path / "output.mp4"
    narration_path = tmp_path / "narration-1.mp3"
    bgm_path = tmp_path / "bgm.mp3"
    mixed_path = tmp_path / "output.audio-mix.mp4"

    command = audio_mix._build_audio_mix_command(
        ffmpeg_binary="ffmpeg",
        video_path=video_path,
        output_path=mixed_path,
        total_duration=5.0,
        narration_clips=[
            {
                "path": narration_path,
                "start_time": 1.2,
                "duration": 2.5,
            }
        ],
        bgm_path=bgm_path,
        bgm_volume=0.12,
    )

    assert command[:3] == ["ffmpeg", "-y", "-i"]
    assert str(video_path) in command
    assert "-stream_loop" in command
    assert str(bgm_path) in command
    filter_arg = command[command.index("-filter_complex") + 1]
    assert "adelay=1200|1200" in filter_arg
    assert "volume=0.12" in filter_arg
    assert "amix=inputs=2" in filter_arg
    final_filter = filter_arg.rsplit(";", 1)[-1]
    assert final_filter.endswith(",apad,atrim=0:5,asetpts=PTS-STARTPTS[aout]")
    assert command[command.index("-map") + 1] == "0:v:0"
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "[aout]"
    assert command[-1] == str(mixed_path)


def test_build_audio_mix_command_uses_single_audio_source_without_amix(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "output.mp4"
    bgm_path = tmp_path / "bgm.mp3"
    mixed_path = tmp_path / "output.audio-mix.mp4"

    command = audio_mix._build_audio_mix_command(
        ffmpeg_binary="ffmpeg",
        video_path=video_path,
        output_path=mixed_path,
        total_duration=5.0,
        narration_clips=[],
        bgm_path=bgm_path,
        bgm_volume=0.2,
    )

    filter_arg = command[command.index("-filter_complex") + 1]
    assert "volume=0.2" in filter_arg
    assert "amix=" not in filter_arg
    assert "[bgm]atrim=0:5,setpts" not in filter_arg
    assert filter_arg.endswith("[bgm]apad,atrim=0:5,asetpts=PTS-STARTPTS[aout]")


def test_build_audio_mix_command_pads_narration_only_output_to_total_duration(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "output.mp4"
    narration_path = tmp_path / "narration-1.mp3"
    mixed_path = tmp_path / "output.audio-mix.mp4"

    command = audio_mix._build_audio_mix_command(
        ffmpeg_binary="ffmpeg",
        video_path=video_path,
        output_path=mixed_path,
        total_duration=5.0,
        narration_clips=[
            {
                "path": narration_path,
                "start_time": 0.0,
                "duration": 1.0,
            }
        ],
        bgm_path=None,
        bgm_volume=None,
    )

    filter_arg = command[command.index("-filter_complex") + 1]
    final_filter = filter_arg.rsplit(";", 1)[-1]
    assert final_filter == "[narration0]apad,atrim=0:5,asetpts=PTS-STARTPTS[aout]"
    assert "atrim=0:1" not in final_filter
    assert "-shortest" in command


def test_prepare_narration_clips_writes_one_clip_per_narrated_timeline_item(
    tmp_path: Path,
) -> None:
    provider = FakeVoiceProvider()
    clips = asyncio.run(
        audio_mix.prepare_narration_clips(
            settings=Settings(_env_file=None, data_dir=tmp_path),
            output_dir=tmp_path / "outputs",
            timeline={
                "items": [
                    {
                        "shot_index": 1,
                        "start_time": 0,
                        "duration": 2,
                        "narration": "第一句旁白",
                    },
                    {
                        "shot_index": 2,
                        "start_time": 2,
                        "duration": 2,
                        "narration": "   ",
                    },
                    {
                        "shot_index": 3,
                        "start_time": 4,
                        "duration": 1,
                        "narration": "第三句旁白",
                    },
                ]
            },
            voice_options={
                "voice_id": "zh-CN-XiaoxiaoNeural",
                "voice_provider": "edge_tts",
            },
            provider=provider,
        )
    )

    assert [clip["shot_index"] for clip in clips] == [1, 3]
    assert [clip["start_time"] for clip in clips] == [0.0, 4.0]
    assert [call["text"] for call in provider.calls] == ["第一句旁白", "第三句旁白"]
    assert all(call["voice_id"] == "zh-CN-XiaoxiaoNeural" for call in provider.calls)
    assert all(Path(clip["path"]).is_file() for clip in clips)


def test_mix_audio_into_video_replaces_final_output_with_mixed_file(tmp_path: Path) -> None:
    ffmpeg_path = tmp_path / "fake-ffmpeg"
    log_path = tmp_path / "audio-mix-argv.json"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        f"pathlib.Path({str(log_path)!r}).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'mixed video')\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    video_path = tmp_path / "output.mp4"
    video_path.write_bytes(b"silent video")
    narration_path = tmp_path / "narration.mp3"
    narration_path.write_bytes(b"voice")

    result = audio_mix.mix_audio_into_video(
        ffmpeg_binary=str(ffmpeg_path),
        video_path=video_path,
        total_duration=3.0,
        narration_clips=[
            {
                "path": narration_path,
                "start_time": 0.0,
                "duration": 3.0,
            }
        ],
        bgm_path=None,
        bgm_volume=None,
    )

    assert result == video_path
    assert video_path.read_bytes() == b"mixed video"
    argv = json.loads(log_path.read_text(encoding="utf-8"))
    assert argv[-1].endswith("output.audio-mix.tmp.mp4")
