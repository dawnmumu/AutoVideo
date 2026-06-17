from autovideo.services.subtitles.timeline import SubtitleEvent, events_from_render_timeline


def test_events_from_render_timeline_splits_long_punctuation_text_without_breaking_decimal():
    timeline = {
        "items": [
            {
                "shot_index": 1,
                "start_time": 0,
                "end_time": 6,
                "duration": 6,
                "subtitle": "AI 能提升 3.5 倍效率，也能降低重复工作。",
            }
        ]
    }

    events = events_from_render_timeline(timeline)

    assert [event.text for event in events] == ["AI 能提升 3.5 倍效率", "也能降低重复工作"]
    assert events[0].start_ms == 0
    assert events[-1].end_ms == 6000


def test_events_from_render_timeline_uses_narration_when_subtitle_missing():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": 3,
                    "duration": 3,
                    "narration": "这是旁白",
                }
            ]
        }
    )

    assert events == [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=3000, text="这是旁白", template="bottom")
    ]


def test_events_from_render_timeline_skips_zero_duration_items():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 2,
                    "end_time": 2,
                    "duration": 0,
                    "subtitle": "不可见字幕",
                }
            ]
        }
    )

    assert events == []
