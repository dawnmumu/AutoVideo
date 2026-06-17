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


def test_events_from_render_timeline_skips_negative_time_items():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": -2,
                    "end_time": -1,
                    "subtitle": "片头幽灵字幕",
                }
            ]
        }
    )

    assert events == []


def test_events_from_render_timeline_keeps_short_duration_split_events_visible():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": 0.001,
                    "duration": 0.001,
                    "subtitle": "a,b,c",
                }
            ]
        }
    )

    assert events
    assert all(event.end_ms > event.start_ms for event in events)
    assert "".join(event.text for event in events) == "abc"


def test_events_from_render_timeline_does_not_emit_zero_width_weighted_splits():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": 0.002,
                    "duration": 0.002,
                    "subtitle": "短,这是一段很长的字幕",
                }
            ]
        }
    )

    assert events
    assert all(event.end_ms > event.start_ms for event in events)
    assert "".join(event.text for event in events) == "短这是一段很长的字幕"


def test_events_from_render_timeline_skips_non_finite_times():
    assert events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": "nan",
                    "end_time": 1,
                    "subtitle": "无效开始时间",
                }
            ]
        }
    ) == []
    assert events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": "inf",
                    "subtitle": "无效结束时间",
                }
            ]
        }
    ) == []


def test_events_from_render_timeline_rejects_explicit_invalid_end_time_without_duration_fallback():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": "nan",
                    "duration": 1,
                    "subtitle": "无效结束时间不回退",
                }
            ]
        }
    )

    assert events == []


def test_events_from_render_timeline_uses_duration_when_end_time_missing_or_empty():
    missing_events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "duration": 1,
                    "subtitle": "缺失结束时间",
                }
            ]
        }
    )
    empty_events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": "",
                    "duration": 1,
                    "subtitle": "空结束时间",
                }
            ]
        }
    )

    assert missing_events == [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="缺失结束时间", template="bottom")
    ]
    assert empty_events == [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="空结束时间", template="bottom")
    ]


def test_events_from_render_timeline_uses_default_shot_index_for_non_finite_value():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": float("nan"),
                    "start_time": 0,
                    "end_time": 1,
                    "subtitle": "有效字幕",
                }
            ]
        }
    )

    assert events == [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="有效字幕", template="bottom")
    ]
