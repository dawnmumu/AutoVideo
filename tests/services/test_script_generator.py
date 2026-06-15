from autovideo.services import script_generator


def test_has_spoken_content_requires_chinese_letters_or_numbers():
    assert script_generator.has_spoken_content("中文")
    assert script_generator.has_spoken_content("abc")
    assert script_generator.has_spoken_content("123")
    assert script_generator.has_spoken_content("先等等……")
    assert not script_generator.has_spoken_content("...")
    assert not script_generator.has_spoken_content("……")
    assert not script_generator.has_spoken_content("——")
    assert not script_generator.has_spoken_content("🙂")


def test_analyze_script_text_accepts_plain_chinese_script(monkeypatch):
    script_text = "星云草木在晨雾里慢慢展开。\n\n银色露珠沿着叶脉滚落。"

    monkeypatch.setattr(
        script_generator,
        "_enrich_plain_text_script_with_llm",
        lambda parts, topic: None,
    )

    result = script_generator.analyze_script_text(
        script_text,
        topic="测试",
        max_single_duration=8,
    )

    script = result["script"]
    analysis = result["analysis"]

    assert script.title == "测试"
    assert [shot.narration for shot in script.shots] == [
        "星云草木在晨雾里慢慢展开。",
        "银色露珠沿着叶脉滚落。",
    ]
    assert script.shots[0].delivery is not None
    assert analysis["shot_count"] == 2
    assert analysis["segment_count"] == 1


def test_build_script_from_data_preserves_subtitle_and_delivery_payload():
    script = script_generator.build_script_from_data(
        {
            "title": "剧情",
            "shots": [
                {
                    "index": 1,
                    "duration": 2.5,
                    "narration": "这一步必须稳住。",
                    "subtitle": "稳住这一步",
                    "visual_description": "人物冷静看向屏幕",
                    "keywords": "人物、屏幕",
                    "delivery": {
                        "style": "professional",
                        "emotion": "neutral",
                        "emotion_scale": 3,
                        "speech_rate": -6,
                        "loudness_rate": 0,
                        "pause_profile": "normal",
                    },
                }
            ],
        },
        fallback_title="剧情",
        scale_to_target=False,
    )

    shot = script.shots[0]
    assert shot.subtitle == "稳住这一步"
    assert shot.keywords == ["人物", "屏幕"]
    assert shot.delivery is not None
    assert shot.delivery.style == "professional"
    assert shot.delivery.emotion == "neutral"
    assert shot.delivery.speech_rate == -6


def test_build_script_from_data_allows_missing_or_none_keywords():
    script = script_generator.build_script_from_data(
        {
            "title": "咖啡店早高峰",
            "shots": [
                {
                    "index": 1,
                    "duration": 2,
                    "narration": "店员递出第一杯热咖啡。",
                    "subtitle": "第一杯热咖啡",
                    "visual_description": "店员把热咖啡递给通勤顾客",
                },
                {
                    "index": 2,
                    "duration": 2,
                    "narration": "顾客拿到咖啡后快速出发。",
                    "subtitle": "快速出发",
                    "visual_description": "通勤顾客手拿咖啡走出门店",
                    "keywords": None,
                },
            ],
        },
        fallback_title="咖啡店早高峰",
        scale_to_target=False,
    )

    assert len(script.shots) == 2
    assert all(shot.keywords for shot in script.shots)


def test_parse_editor_script_accepts_time_ranges_and_skips_titles(monkeypatch):
    script_text = """30 秒视频脚本：疗愈型 SPA，美业下一个风口

0-3 秒｜开场钩子
画面：都市女性下班后疲惫走进 SPA 空间。
旁白：
“未来的美业，不只是变美，而是让人真正放松下来。”

3-8 秒｜痛点共鸣
画面：熬夜、压力、肩颈僵硬、情绪疲惫的快切镜头。
旁白：
“现代女性缺的，不只是护肤项目，而是一次能释放压力、安抚情绪的身心疗愈。”

屏幕字幕结尾：
“疗愈型 SPA｜美业下一个增长机会”
"""

    monkeypatch.setattr(
        script_generator,
        "_enrich_plain_text_script_with_llm",
        lambda parts, topic: None,
    )

    result = script_generator.optimize_script_text(
        script_text,
        topic="疗愈型 SPA",
        max_single_duration=8,
    )

    script = result["script"]
    assert len(script.shots) == 2
    assert script.total_duration == 8
    assert [shot.duration for shot in script.shots] == [3, 5]
    assert script.shots[0].visual_description == "都市女性下班后疲惫走进 SPA 空间。"
    assert script.shots[0].narration == "“未来的美业，不只是变美，而是让人真正放松下来。”"
    assert all("开场钩子" not in shot.narration for shot in script.shots)
    assert all("屏幕字幕结尾" not in shot.narration for shot in script.shots)


def test_format_script_for_editor_outputs_subtitle_line():
    script = script_generator.VideoScript(
        title="剧情",
        total_duration=3,
        shots=[
            script_generator.SceneShot(
                index=1,
                duration=3,
                narration="这一步必须稳住，先不要急着下判断。",
                subtitle="先稳住，不急着判断",
                visual_description="人物冷静看向屏幕",
                keywords=["人物", "屏幕"],
                delivery=script_generator.build_delivery_for_narration(
                    "这一步必须稳住，先不要急着下判断。"
                ),
            )
        ],
    )

    formatted = script_generator.format_script_for_editor(script)

    assert "旁白：这一步必须稳住，先不要急着下判断。" in formatted
    assert "字幕：先稳住，不急着判断" in formatted
