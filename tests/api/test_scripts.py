import json

import httpx
import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def _create_fake_llm_app(tmp_path, llm_payload: dict):
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(llm_payload)
    return app


def test_generate_script_heuristic_returns_structured_shots(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "精油睡眠放松",
                "provider": "heuristic",
                "duration_seconds": 30,
                "aspect_ratio": "9:16",
                "tone": "自然可信",
                "target_audience": "睡眠质量差的年轻人",
                "selling_points": ["舒缓", "睡前仪式感"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"]
    assert payload["topic"] == "精油睡眠放松"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["duration_seconds"] == 30
    assert payload["provider"] == "heuristic"
    assert len(payload["shots"]) >= 3
    assert payload["shots"][0]["index"] == 1
    assert payload["shots"][0]["duration"] > 0
    assert payload["shots"][0]["keywords"]
    assert payload["shots"][0]["delivery"]["style"]
    selling_point_text = " ".join(
        " ".join(
            [
                shot["narration"],
                shot["subtitle"],
                " ".join(shot["keywords"]),
            ]
        )
        for shot in payload["shots"]
    )
    assert "舒缓" in selling_point_text or "睡前仪式感" in selling_point_text
    assert "天然成分" not in selling_point_text
    assert "点击下方链接" not in selling_point_text


def test_generate_script_accepts_custom_script_text(client, monkeypatch) -> None:
    from autovideo.services import script_generator

    monkeypatch.setattr(
        script_generator,
        "_enrich_plain_text_script_with_llm",
        lambda parts, topic: None,
    )

    response = client.post(
        "/api/scripts/generate",
        json={
            "topic": "疗愈型 SPA",
            "provider": "heuristic",
            "script_text": "顾客进店后明显放松。\n护理结束后，她的状态轻盈很多。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["title"] == "疗愈型 SPA"
    assert [shot["narration"] for shot in payload["shots"]] == [
        "顾客进店后明显放松。",
        "护理结束后，她的状态轻盈很多。",
    ]
    assert payload["shots"][0]["delivery"]["style"] == "natural"
    assert payload["script_text"].startswith("标题：疗愈型 SPA")


@pytest.mark.parametrize("provider", ["auto", "llm_only"])
def test_generate_script_with_script_text_uses_llm_enrichment_without_rewriting_narration(
    tmp_path,
    provider,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "疗愈型 SPA 补全标题",
            "shots": [
                {
                    "index": 1,
                    "narration": "LLM 不应改写第一句",
                    "subtitle": "进店后放松",
                    "visual_description": "顾客走进疗愈型 SPA 前台",
                    "keywords": ["SPA 前台", "顾客放松", "疗愈空间"],
                    "delivery": {"style": "gentle", "speech_rate": -8},
                },
                {
                    "index": 2,
                    "narration": "LLM 不应改写第二句",
                    "subtitle": "护理后更轻盈",
                    "visual_description": "护理结束后顾客舒展肩颈",
                    "keywords": ["护理结束", "肩颈放松", "疗愈状态"],
                    "delivery": {"style": "gentle", "speech_rate": -8},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "疗愈型 SPA",
                "provider": provider,
                "script_text": "顾客进店后明显放松。\n护理结束后，她的状态轻盈很多。",
                "max_single_duration": 8,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "llm"
    assert [shot["narration"] for shot in payload["shots"]] == [
        "顾客进店后明显放松。",
        "护理结束后，她的状态轻盈很多。",
    ]
    assert payload["shots"][0]["subtitle"] == "进店后放松"
    assert payload["shots"][0]["visual_description"] == "顾客走进疗愈型 SPA 前台"
    assert payload["shots"][0]["keywords"] == ["SPA 前台", "顾客放松", "疗愈空间"]
    assert payload["shots"][1]["keywords"] == ["护理结束", "肩颈放松", "疗愈状态"]
    assert payload["shots"][0]["delivery"]["style"] == "gentle"
    assert payload["script_text"].startswith("标题：疗愈型 SPA 补全标题")
    assert payload["analysis"]["shot_count"] == 2
    assert payload["analysis"]["max_single_duration"] == 8


def test_generate_script_auto_falls_back_when_script_text_enrichment_ignores_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "shots": [
                {
                    "index": 1,
                    "subtitle": "睡前精油",
                    "visual_description": "卧室床头柜上的精油瓶特写",
                    "keywords": ["精油", "卧室", "睡眠"],
                    "delivery": {"style": "gentle"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "script_text": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert "睡前精油" not in json.dumps(payload, ensure_ascii=False)


def test_generate_script_llm_only_rejects_script_text_enrichment_that_ignores_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "shots": [
                {
                    "index": 1,
                    "subtitle": "睡前精油",
                    "visual_description": "卧室床头柜上的精油瓶特写",
                    "keywords": ["精油", "卧室", "睡眠"],
                    "delivery": {"style": "gentle"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "script_text": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_script_text_enrichment_uses_placeholder_title(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "视频脚本",
            "shots": [
                {
                    "index": 1,
                    "subtitle": "咖啡店早高峰补全",
                    "visual_description": "咖啡店早高峰吧台特写，通勤者排队取热咖啡。",
                    "keywords": ["咖啡店", "早高峰", "热咖啡"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "script_text": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "咖啡店早高峰补全" not in serialized
    assert "吧台特写" not in serialized


def test_generate_script_llm_only_rejects_script_text_enrichment_placeholder_title(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "自定义脚本视频",
            "shots": [
                {
                    "index": 1,
                    "subtitle": "咖啡店早高峰补全",
                    "visual_description": "咖啡店早高峰吧台特写，通勤者排队取热咖啡。",
                    "keywords": ["咖啡店", "早高峰", "热咖啡"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "script_text": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_script_text_llm_enrichment_is_invalid(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient({"shots": ["bad"]})

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "疗愈型 SPA",
                "provider": "auto",
                "script_text": "顾客进店后明显放松。",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert [shot["narration"] for shot in payload["shots"]] == ["顾客进店后明显放松。"]
    assert "secret-key-should-not-leak" not in response.text


def test_generate_script_auto_falls_back_when_llm_ignores_topic(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 20,
            "shots": [
                {
                    "index": 1,
                    "duration": 10,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "睡前精油",
                    "visual_description": "卧室床头柜上的精油瓶特写",
                    "keywords": ["精油", "卧室", "睡眠"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 10,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "放松入睡",
                    "visual_description": "夜晚卧室里的人放松躺下",
                    "keywords": ["放松", "睡眠", "夜晚卧室"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 20,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["title"] == "咖啡店早高峰"
    script_text = json.dumps(payload, ensure_ascii=False)
    assert "咖啡店早高峰" in script_text
    assert "睡前精油" not in script_text


def test_generate_script_auto_falls_back_when_unrelated_narration_has_empty_visual(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 20,
            "shots": [
                {
                    "index": 1,
                    "duration": 10,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "睡前精油",
                    "visual_description": "",
                    "keywords": ["视频"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 10,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "放松入睡",
                    "visual_description": "",
                    "keywords": ["内容"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 20,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert "睡前精油" not in json.dumps(payload, ensure_ascii=False)


def test_generate_script_llm_only_rejects_unrelated_narration_with_empty_visual(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 20,
            "shots": [
                {
                    "index": 1,
                    "duration": 10,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "睡前精油",
                    "visual_description": "",
                    "keywords": ["视频"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 10,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "放松入睡",
                    "visual_description": "",
                    "keywords": ["内容"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 20,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_single_character_topic_is_ignored(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "睡前精油",
                    "visual_description": "卧室床头柜上的精油瓶特写",
                    "keywords": ["精油", "卧室", "睡眠"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 6,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "放松入睡",
                    "visual_description": "夜晚卧室里的人放松躺下",
                    "keywords": ["放松", "睡眠", "夜晚卧室"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "猫",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["title"] == "猫"
    assert "睡前精油" not in json.dumps(payload, ensure_ascii=False)


def test_generate_script_llm_only_rejects_unrelated_single_character_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "睡前精油",
                    "visual_description": "卧室床头柜上的精油瓶特写",
                    "keywords": ["精油", "卧室", "睡眠"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 6,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "放松入睡",
                    "visual_description": "夜晚卧室里的人放松躺下",
                    "keywords": ["放松", "睡眠", "夜晚卧室"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "猫",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_subtitle_masks_unrelated_narration(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "",
                    "keywords": ["咖啡店早高峰"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 6,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "",
                    "keywords": ["咖啡店早高峰"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert "睡前精油" not in json.dumps(payload, ensure_ascii=False)


def test_generate_script_llm_only_rejects_subtitle_masked_unrelated_narration(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "睡前点一滴精油，让卧室慢慢安静下来。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "",
                    "keywords": ["咖啡店早高峰"],
                    "delivery": {"style": "gentle"},
                },
                {
                    "index": 2,
                    "duration": 6,
                    "narration": "深呼吸之后，身体进入更放松的状态。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "",
                    "keywords": ["咖啡店早高峰"],
                    "delivery": {"style": "gentle"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_keywords_ignore_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["睡前精油", "夜晚卧室"],
                    "delivery": {"style": "natural"},
                },
                {
                    "index": 2,
                    "duration": 6,
                    "narration": "咖啡店店员快速完成点单，让清晨节奏更顺畅。",
                    "subtitle": "快速出杯",
                    "visual_description": "咖啡店早高峰时段，吧台店员递出外带咖啡。",
                    "keywords": ["放松睡眠", "香薰精油"],
                    "delivery": {"style": "natural"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert "睡前精油" not in json.dumps(payload, ensure_ascii=False)


def test_generate_script_llm_only_rejects_keywords_that_ignore_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["睡前精油", "夜晚卧室"],
                    "delivery": {"style": "natural"},
                },
                {
                    "index": 2,
                    "duration": 6,
                    "narration": "咖啡店店员快速完成点单，让清晨节奏更顺畅。",
                    "subtitle": "快速出杯",
                    "visual_description": "咖啡店早高峰时段，吧台店员递出外带咖啡。",
                    "keywords": ["放松睡眠", "香薰精油"],
                    "delivery": {"style": "natural"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_generic_narration_ignores_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "退休生活和家庭回忆，在旧照片里慢慢展开。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "退休生活" not in json.dumps(response.json(), ensure_ascii=False)


def test_generate_script_llm_only_rejects_generic_narration_that_ignores_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "退休生活和家庭回忆，在旧照片里慢慢展开。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_narration_and_subtitle_ignore_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "退休生活和家庭回忆，在旧照片里慢慢展开。",
                    "subtitle": "旧照片里的回忆",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "退休生活" not in json.dumps(response.json(), ensure_ascii=False)


def test_generate_script_llm_only_rejects_narration_and_subtitle_that_ignore_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "退休生活和家庭回忆，在旧照片里慢慢展开。",
                    "subtitle": "旧照片里的回忆",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_music_text_is_not_audio_cue(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "城市音乐节现场人群欢呼。",
                    "subtitle": "音乐节现场",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "音乐节" not in json.dumps(response.json(), ensure_ascii=False)


def test_generate_script_llm_only_rejects_music_text_that_is_not_audio_cue(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "城市音乐节现场人群欢呼。",
                    "subtitle": "音乐节现场",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_short_audio_cue_ignores_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "城市演唱会现场欢呼声",
                    "subtitle": "演唱会现场",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "演唱会" not in json.dumps(response.json(), ensure_ascii=False)


def test_generate_script_llm_only_rejects_short_audio_cue_that_ignores_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "城市演唱会现场欢呼声",
                    "subtitle": "演唱会现场",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_topic_subtitle_masks_audio_cue(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "城市演唱会现场欢呼声",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "演唱会" not in json.dumps(response.json(), ensure_ascii=False)


def test_generate_script_llm_only_rejects_topic_subtitle_masked_audio_cue(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "城市演唱会现场欢呼声",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_subtitle_ignores_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "睡前精油",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "睡前精油" not in json.dumps(response.json(), ensure_ascii=False)


def test_generate_script_llm_only_rejects_subtitle_that_ignores_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "睡前精油",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_generic_keywords_ignore_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["city skyline", "office workers"],
                    "delivery": {"style": "natural"},
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"


def test_generate_script_llm_only_rejects_generic_keywords_that_ignore_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["city skyline", "office workers"],
                    "delivery": {"style": "natural"},
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_mixed_keywords_ignore_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "city skyline", "office workers"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"


def test_generate_script_llm_only_rejects_mixed_keywords_that_ignore_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "咖啡店早高峰",
            "total_duration": 12,
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "city skyline", "office workers"],
                    "delivery": {"style": "natural"},
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_auto_falls_back_when_title_ignores_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 20,
            "shots": [
                {
                    "index": 1,
                    "duration": 10,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "通勤"],
                    "delivery": {"style": "natural"},
                },
                {
                    "index": 2,
                    "duration": 10,
                    "narration": "店员快速完成点单，让清晨节奏更顺畅。",
                    "subtitle": "快速出杯",
                    "visual_description": "咖啡店早高峰时段，吧台店员递出外带咖啡。",
                    "keywords": ["咖啡吧台", "早高峰", "外带咖啡"],
                    "delivery": {"style": "natural"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "auto",
                "duration_seconds": 20,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"
    assert "睡前精油短视频" not in response.text


def test_generate_script_llm_only_rejects_title_that_ignores_topic(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "睡前精油短视频",
            "total_duration": 20,
            "shots": [
                {
                    "index": 1,
                    "duration": 10,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "通勤"],
                    "delivery": {"style": "natural"},
                },
                {
                    "index": 2,
                    "duration": 10,
                    "narration": "店员快速完成点单，让清晨节奏更顺畅。",
                    "subtitle": "快速出杯",
                    "visual_description": "咖啡店早高峰时段，吧台店员递出外带咖啡。",
                    "keywords": ["咖啡吧台", "早高峰", "外带咖啡"],
                    "delivery": {"style": "natural"},
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 20,
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"


def test_generate_script_llm_only_rejects_invalid_script_text_enrichment_payload(
    tmp_path,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient({"shots": ["bad"]})

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "疗愈型 SPA",
                "provider": "llm_only",
                "script_text": "顾客进店后明显放松。",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"
    assert "secret-key-should-not-leak" not in response.text


@pytest.mark.parametrize("provider", ["heuristic", "auto"])
def test_generate_script_rejects_script_text_without_spoken_content(
    client,
    monkeypatch,
    provider,
) -> None:
    from autovideo.services import script_generator

    monkeypatch.setattr(
        script_generator,
        "_enrich_plain_text_script_with_llm",
        lambda parts, topic: None,
    )

    response = client.post(
        "/api/scripts/generate",
        json={
            "topic": "疗愈型 SPA",
            "provider": provider,
            "script_text": "...\n——\n🙂",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "SCRIPT_TEXT_INVALID",
        "message": "脚本中没有可用内容",
    }


@pytest.mark.parametrize("provider", ["auto", "llm_only"])
def test_generate_script_rejects_invalid_script_text_before_llm(
    tmp_path,
    provider,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "不应被使用",
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "这段 LLM 结果不应该被返回",
                    "subtitle": "这段 LLM 结果不应该被返回",
                    "visual_description": "valid llm shot",
                    "keywords": ["valid"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "疗愈型 SPA",
                "provider": provider,
                "script_text": "...\n——\n🙂",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SCRIPT_TEXT_INVALID"


@pytest.mark.parametrize(
    "script_text",
    [
        json.dumps(
            {
                "title": "疗愈型 SPA",
                "shots": [
                    {
                        "index": 1,
                        "duration": 3,
                        "narration": "顾客进店后明显放松。",
                        "subtitle": "顾客进店后明显放松。",
                        "visual_description": "顾客进店后明显放松。",
                        "keywords": ["视频"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        """标题：疗愈型 SPA
总时长：3秒

镜头1（3秒）
旁白：顾客进店后明显放松。
字幕：顾客进店后明显放松。
画面：顾客进店后明显放松。
关键词：视频
""",
    ],
)
def test_generate_script_repairs_low_quality_structured_script_text_metadata(
    client,
    script_text,
) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "provider": "heuristic",
            "topic": "疗愈型 SPA",
            "script_text": script_text,
        },
    )

    assert response.status_code == 200
    shot = response.json()["shots"][0]
    assert shot["visual_description"] != shot["narration"]
    assert len(shot["keywords"]) >= 2
    assert "视频" not in shot["keywords"]


def test_generate_script_returns_heuristic_provider_for_structured_script_text_without_llm_repair(
    tmp_path,
) -> None:
    class CountingLlmClient:
        calls = 0

        def generate(self, payload, settings):
            self.calls += 1
            return {"shots": ["should-not-be-used"]}

    script_text = json.dumps(
        {
            "title": "疗愈型 SPA",
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "顾客进店后明显放松。",
                    "subtitle": "进店后放松",
                    "visual_description": "顾客走进安静的 SPA 前台，肩颈逐渐放松",
                    "keywords": ["SPA 前台", "顾客放松", "疗愈空间"],
                }
            ],
        },
        ensure_ascii=False,
    )
    llm_client = CountingLlmClient()
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = llm_client

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "provider": "auto",
                "topic": "疗愈型 SPA",
                "script_text": script_text,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["shots"][0]["narration"] == "顾客进店后明显放松。"
    assert llm_client.calls == 0


@pytest.mark.parametrize(
    "script_text",
    [
        json.dumps(
            {
                "title": "坏脚本",
                "shots": [
                    {
                        "index": 1,
                        "duration": -5,
                        "narration": "这段脚本不应触发 500。",
                        "subtitle": "这段脚本不应触发 500。",
                        "visual_description": "invalid duration",
                        "keywords": ["invalid"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "title": "坏脚本",
                "shots": [
                    {
                        "index": "bad",
                        "duration": 5,
                        "narration": "这段脚本不应触发 500。",
                        "subtitle": "这段脚本不应触发 500。",
                        "visual_description": "invalid index",
                        "keywords": ["invalid"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        '{"title": "坏脚本", "shots": [',
        '请使用：\n```json\n{"title": "坏脚本", "shots": [\n```',
        '请使用：\n```json\n{"title": "坏脚本", "shots": [',
        json.dumps({"title": "坏脚本"}, ensure_ascii=False),
        json.dumps({"title": "坏脚本", "shots": []}, ensure_ascii=False),
        '```json\n{"title": "坏脚本"}\n```',
        json.dumps(
            [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "顶层数组不是脚本 schema。",
                }
            ],
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "title": "坏脚本",
                "shots": [
                    {
                        "index": 1,
                        "start_time": 5,
                        "end_time": 3,
                        "narration": "倒序时间不应被静默估算。",
                        "subtitle": "倒序时间不应被静默估算。",
                        "visual_description": "invalid time range",
                        "keywords": ["invalid"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
    ],
)
def test_generate_script_returns_400_for_malformed_json_script_text(
    tmp_path,
    script_text,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "provider": "heuristic",
                "topic": "疗愈型 SPA",
                "script_text": script_text,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "SCRIPT_TEXT_INVALID",
        "message": "脚本中没有可用内容",
    }


@pytest.mark.parametrize("duration", [0, "0", "abc", "inf"])
def test_generate_script_returns_400_for_json_script_text_with_invalid_duration(
    tmp_path,
    duration,
) -> None:
    script_text = json.dumps(
        {
            "title": "坏脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": duration,
                    "narration": "这段脚本不应被静默估算时长。",
                    "subtitle": "这段脚本不应被静默估算时长。",
                    "visual_description": "invalid duration",
                    "keywords": ["invalid"],
                }
            ],
        },
        ensure_ascii=False,
    )
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "provider": "heuristic",
                "topic": "疗愈型 SPA",
                "script_text": script_text,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SCRIPT_TEXT_INVALID"


@pytest.mark.parametrize(
    "shot_fields",
    [
        {"index": 0, "duration": 5},
        {"index": False, "duration": 5},
        {"index": None, "duration": 5},
        {"index": "", "duration": 5},
        {"duration": 5},
        {"index": 1, "duration": None},
        {"index": 1},
    ],
)
def test_generate_script_returns_400_for_json_script_text_with_invalid_required_fields(
    tmp_path,
    shot_fields,
) -> None:
    script_text = json.dumps(
        {
            "title": "坏脚本",
            "shots": [
                {
                    **shot_fields,
                    "narration": "这段脚本不应被静默修复必需字段。",
                    "subtitle": "这段脚本不应被静默修复必需字段。",
                    "visual_description": "invalid required fields",
                    "keywords": ["invalid"],
                }
            ],
        },
        ensure_ascii=False,
    )
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "provider": "heuristic",
                "topic": "疗愈型 SPA",
                "script_text": script_text,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SCRIPT_TEXT_INVALID"


@pytest.mark.parametrize(
    "shot_fields",
    [
        {"start_time": -1, "end_time": 3},
        {"start_time": 1, "end_time": -3},
        {"duration": 5, "start_time": -1, "end_time": 3},
    ],
)
def test_generate_script_returns_400_for_json_script_text_with_negative_time_points(
    tmp_path,
    shot_fields,
) -> None:
    script_text = json.dumps(
        {
            "title": "坏脚本",
            "shots": [
                {
                    "index": 1,
                    **shot_fields,
                    "narration": "这段脚本不应被静默估算时间点。",
                    "subtitle": "这段脚本不应被静默估算时间点。",
                    "visual_description": "invalid time point",
                    "keywords": ["invalid"],
                }
            ],
        },
        ensure_ascii=False,
    )
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "provider": "heuristic",
                "topic": "疗愈型 SPA",
                "script_text": script_text,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SCRIPT_TEXT_INVALID"


@pytest.mark.parametrize(
    "script_text",
    [
        """标题：坏脚本

镜头1（0秒）
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
        """标题：坏脚本
总时长：0秒

镜头1（3秒）
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
        """00:05-00:03 | 倒序镜头
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
        """-1-3 秒 | 负数开始
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
        """3--1 秒 | 负数结束
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
        """00:aa-00:03 | 非法时间
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
        """镜头1（abc秒）
旁白：顾客进店后明显放松。
字幕：进店后放松
画面：顾客走进安静的 SPA 前台
关键词：SPA 前台、顾客放松
""",
    ],
)
def test_generate_script_returns_400_for_editor_script_with_invalid_explicit_duration(
    client,
    script_text,
) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "provider": "heuristic",
            "topic": "疗愈型 SPA",
            "script_text": script_text,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SCRIPT_TEXT_INVALID"


@pytest.mark.parametrize(
    "script_text",
    [
        "3-A 计划上线。团队要先确认素材方向。",
        "3A-4B 版本对比。顾客反馈更偏好轻柔节奏。",
        "3-A | 计划上线。团队要先确认素材方向。",
        "3A-4B | 版本对比。顾客反馈更偏好轻柔节奏。",
        "3-1 | 计划上线。团队要先确认素材方向。",
        "3.1-3.0 | 版本回退计划。团队要保留旧版素材。",
        "3-1 | 秒杀活动排期。团队要先确认素材方向。",
    ],
)
def test_generate_script_accepts_plain_text_that_looks_like_a_range_header(
    client,
    script_text,
) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "provider": "heuristic",
            "topic": "疗愈型 SPA",
            "script_text": script_text,
        },
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"


@pytest.mark.parametrize(
    ("script_text", "expected_fragment"),
    [
        ("[开场] 顾客进店后明显放松。", "顾客进店后明显放松。"),
        ("[\"开场\"] 顾客进店后明显放松。", "顾客进店后明显放松。"),
        ("[\"开场\"]", "开场"),
        ("```\n顾客进店后明显放松。\n```", "顾客进店后明显放松。"),
    ],
)
def test_generate_script_accepts_plain_text_that_only_looks_like_json(
    client,
    script_text,
    expected_fragment,
) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={
            "provider": "heuristic",
            "topic": "疗愈型 SPA",
            "script_text": script_text,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert expected_fragment in payload["shots"][0]["narration"]


def test_generate_script_auto_falls_back_without_llm(client) -> None:
    assert client.app.state.settings.llm_base_url is None
    assert client.app.state.settings.llm_api_key is None
    assert client.app.state.settings.llm_model is None

    response = client.post(
        "/api/scripts/generate",
        json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"


def test_generate_script_llm_only_requires_config(client) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={"topic": "咖啡店早高峰", "provider": "llm_only"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LLM_NOT_CONFIGURED"


def test_generate_script_auto_uses_configured_llm_client(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "咖啡店早高峰柜台递咖啡的画面",
                    "keywords": ["咖啡店柜台", "通勤人群", "coffee shop"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "llm"
    assert payload["title"] == "咖啡店早高峰脚本"
    assert payload["shots"][0]["keywords"] == ["咖啡店柜台", "通勤人群", "coffee shop"]


def test_generate_script_llm_only_parses_fake_structured_response(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "精油睡眠放松脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "精油睡眠放松，从床头的一点香气开始。",
                    "subtitle": "精油睡眠放松",
                    "visual_description": "床头精油瓶与夜晚卧室放松场景",
                    "keywords": ["精油", "睡眠", "放松"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "精油睡眠放松",
                "provider": "llm_only",
                "duration_seconds": 15,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "llm"


def test_generate_script_llm_only_accepts_placeholder_title_when_shots_match_topic(
    tmp_path,
) -> None:
    app = _create_fake_llm_app(
        tmp_path,
        {
            "title": "视频脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "咖啡店早高峰，第一杯热咖啡递到通勤者手里。",
                    "subtitle": "咖啡店早高峰",
                    "visual_description": "清晨咖啡店吧台前排队取咖啡，通勤者等待外带。",
                    "keywords": ["咖啡店", "清晨", "吧台"],
                }
            ],
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 15,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "llm"
    assert payload["title"] == "咖啡店早高峰"


def test_generate_script_llm_repairs_missing_visual_metadata(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "疗愈型 SPA",
            "shots": [
                {
                    "index": 1,
                    "duration": 4,
                    "narration": "顾客进店后明显放松。",
                    "subtitle": "顾客进店后明显放松。",
                    "keywords": ["视频"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "疗愈型 SPA",
                "provider": "llm_only",
                "duration_seconds": 15,
            },
        )

    assert response.status_code == 200
    shot = response.json()["shots"][0]
    assert shot["visual_description"] != shot["narration"]
    assert len(shot["keywords"]) >= 2
    assert "视频" not in shot["keywords"]


def test_generate_script_llm_only_normalizes_common_llm_shot_aliases(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "咖啡店早高峰脚本",
            "shots": [
                {
                    "shot_id": 1,
                    "start_time": 0.0,
                    "end_time": 2.5,
                    "description": "清晨咖啡店吧台前，咖啡机蒸汽喷嘴喷出白色蒸汽，浓缩咖啡流入杯中。",
                    "audio_cue": "咖啡机高压蒸汽声",
                    "camera_movement": "微距推近",
                },
                {
                    "shot_id": 2,
                    "start_time": 2.5,
                    "end_time": 5.0,
                    "description": "咖啡店早高峰时段，顾客在柜台前排队等待，店员快速递出外带咖啡。",
                    "voiceover": "顾客快速取到清晨的第一杯咖啡",
                    "subtitle": "早高峰排队取咖啡",
                    "keywords": ["coffee queue", "takeaway coffee"],
                },
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "咖啡店早高峰",
                "provider": "llm_only",
                "duration_seconds": 12,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "llm"
    assert payload["shots"][0]["index"] == 1
    assert payload["shots"][0]["duration"] == 2.5
    assert payload["shots"][0]["narration"] == "咖啡机高压蒸汽声"
    assert payload["shots"][0]["subtitle"] == "清晨咖啡店吧台前，咖啡机蒸汽喷嘴喷出白色蒸汽，浓缩咖啡流入杯中。"
    assert payload["shots"][0]["visual_description"] == "清晨咖啡店吧台前，咖啡机蒸汽喷嘴喷出白色蒸汽，浓缩咖啡流入杯中。"
    assert "清晨咖啡店吧台前" in payload["shots"][0]["keywords"]
    assert payload["shots"][0]["delivery"]["style"] == "natural"
    assert payload["shots"][1]["index"] == 2
    assert payload["shots"][1]["keywords"] == ["coffee queue", "takeaway coffee"]


def test_generate_script_auto_falls_back_when_llm_http_or_parse_fails(
    tmp_path,
) -> None:
    from autovideo.services.scripts import LlmResponseInvalidError

    class FailingLlmClient:
        def generate(self, payload, settings):
            raise LlmResponseInvalidError()

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FailingLlmClient()

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["topic"] == "咖啡店早高峰"


def test_generate_script_handles_mixed_non_spoken_llm_shots_strictly(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    llm_payload = {
        "shots": [
            {
                "index": 1,
                "duration": 1,
                "narration": "...",
                "subtitle": "...",
                "visual_description": "ellipsis only shot",
                "keywords": ["bad shot"],
            },
            {
                "index": 2,
                "duration": 1,
                "narration": "……",
                "subtitle": "……",
                "visual_description": "chinese ellipsis only shot",
                "keywords": ["bad shot"],
            },
            {
                "index": 3,
                "duration": 1,
                "narration": "——",
                "subtitle": "——",
                "visual_description": "dash only shot",
                "keywords": ["bad shot"],
            },
            {
                "index": 4,
                "duration": 1,
                "narration": "🙂",
                "subtitle": "🙂",
                "visual_description": "emoji only shot",
                "keywords": ["bad shot"],
            },
            {
                "index": 5,
                "duration": 3,
                "narration": "正常旁白",
                "subtitle": "正常旁白",
                "visual_description": "normal shot",
                "keywords": ["normal shot"],
            },
        ]
    }
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(llm_payload)

    with TestClient(app) as client:
        llm_only_response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "llm_only"},
        )
        auto_response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert llm_only_response.status_code == 502
    assert llm_only_response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"
    assert auto_response.status_code == 200
    assert auto_response.json()["provider"] == "heuristic"


@pytest.mark.parametrize(
    "llm_payload",
    [
        {"shots": ["bad"]},
        {
            "shots": [
                {
                    "index": 1.5,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 0,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": False,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 0,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": None,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": "0",
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "start_time": 5,
                    "end_time": 3,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "start_time": -1,
                    "end_time": 3,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "start_time": -1,
                    "end_time": 3,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": True,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": float("inf"),
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": float("nan"),
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 10**400,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": "9" * 400,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "total_duration": float("inf"),
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "total_duration": float("nan"),
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "total_duration": 10**400,
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "total_duration": "9" * 400,
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": [123],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": 123,
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": True,
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": {"primary": "coffee"},
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": ["字幕"],
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": {"scene": "coffee shop morning"},
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                    "delivery": "fast",
                }
            ]
        },
        {
            "shots": [
                {
                    "shot_id": 1,
                    "start_time": 0,
                    "end_time": 5,
                    "description": "coffee shop morning",
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 2,
                    "narration": "！！！",
                    "subtitle": "！！！",
                    "visual_description": "bad punctuation only shot",
                    "keywords": ["bad shot"],
                },
                {
                    "index": 2,
                    "duration": 3,
                    "narration": "正常旁白",
                    "subtitle": "正常旁白",
                    "visual_description": "normal shot",
                    "keywords": ["normal shot"],
                },
            ]
        },
    ],
)
def test_generate_script_auto_falls_back_when_llm_shot_shape_is_invalid(
    tmp_path,
    llm_payload,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(llm_payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["topic"] == "咖啡店早高峰"
    assert "secret-key-should-not-leak" not in response.text


@pytest.mark.parametrize(
    "llm_payload",
    [
        {"shots": ["bad"]},
        {
            "shots": [
                {
                    "index": 1.5,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 0,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": False,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 0,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": None,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": "0",
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "start_time": 5,
                    "end_time": 3,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "start_time": -1,
                    "end_time": 3,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "start_time": -1,
                    "end_time": 3,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": True,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": float("inf"),
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": float("nan"),
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 10**400,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": "9" * 400,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "total_duration": float("inf"),
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "total_duration": float("nan"),
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "total_duration": 10**400,
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "total_duration": "9" * 400,
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ],
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": [123],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": 123,
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": True,
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": {"primary": "coffee"},
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": ["字幕"],
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": {"scene": "coffee shop morning"},
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee"],
                    "delivery": "fast",
                }
            ]
        },
        {
            "shots": [
                {
                    "shot_id": 1,
                    "start_time": 0,
                    "end_time": 5,
                    "description": "coffee shop morning",
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 2,
                    "narration": "！！！",
                    "subtitle": "！！！",
                    "visual_description": "bad punctuation only shot",
                    "keywords": ["bad shot"],
                },
                {
                    "index": 2,
                    "duration": 3,
                    "narration": "正常旁白",
                    "subtitle": "正常旁白",
                    "visual_description": "normal shot",
                    "keywords": ["normal shot"],
                },
            ]
        },
    ],
)
def test_generate_script_llm_only_rejects_invalid_llm_shot_shape(
    tmp_path,
    llm_payload,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(llm_payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "llm_only"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"
    assert "secret-key-should-not-leak" not in response.text


@pytest.mark.parametrize(
    "response_payload",
    [
        {"choices": []},
        {"choices": ["not-a-dict"]},
        ["not-a-dict"],
    ],
)
def test_openai_llm_client_wraps_invalid_response_shape(response_payload) -> None:
    from autovideo.services.scripts import (
        LlmResponseInvalidError,
        OpenAICompatibleLlmClient,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    settings = Settings(
        _env_file=None,
        llm_base_url="https://llm.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        llm_client = OpenAICompatibleLlmClient(http_client=http_client)

        with pytest.raises(LlmResponseInvalidError):
            llm_client.generate({"topic": "咖啡店早高峰"}, settings)


def test_openai_llm_client_uses_context_manager_for_default_http_client(
    monkeypatch,
) -> None:
    from autovideo.services import scripts
    from autovideo.services.scripts import OpenAICompatibleLlmClient

    created_clients = []

    class ContextHttpClient:
        def __init__(self) -> None:
            self.entered = False
            self.exited = False
            created_clients.append(self)

        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.exited = True

        def post(self, *args, **kwargs) -> httpx.Response:
            assert self.entered
            return httpx.Response(
                200,
                request=httpx.Request("POST", str(args[0])),
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"title":"结构化脚本","shots":[{"index":1,'
                                    '"duration":5,"narration":"旁白",'
                                    '"subtitle":"字幕",'
                                    '"visual_description":"coffee shop morning",'
                                    '"keywords":["coffee"]}]}'
                                )
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(scripts.httpx, "Client", ContextHttpClient)
    settings = Settings(
        _env_file=None,
        llm_base_url="https://llm.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )

    llm_client = OpenAICompatibleLlmClient()
    payload = llm_client.generate({"topic": "咖啡店早高峰"}, settings)

    assert payload["title"] == "结构化脚本"
    assert len(created_clients) == 1
    assert created_clients[0].entered is True
    assert created_clients[0].exited is True


def test_openai_llm_client_requests_autovideo_schema() -> None:
    from autovideo.services.scripts import OpenAICompatibleLlmClient

    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"title":"结构化脚本","shots":[{"index":1,'
                                '"duration":5,"narration":"旁白",'
                                '"subtitle":"字幕",'
                                '"visual_description":"coffee shop morning",'
                                '"keywords":["coffee"]}]}'
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(
        _env_file=None,
        llm_base_url="https://llm.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        llm_client = OpenAICompatibleLlmClient(http_client=http_client)

        llm_client.generate({"topic": "咖啡店早高峰"}, settings)

    system_prompt = captured_request["messages"][0]["content"]
    assert "AutoVideo" in system_prompt
    assert "index" in system_prompt
    assert "duration" in system_prompt
    assert "narration" in system_prompt
    assert "subtitle" in system_prompt
    assert "visual_description" in system_prompt
    assert "keywords" in system_prompt
    assert "shot_id" not in system_prompt


def test_generate_script_llm_only_returns_structured_error_on_llm_failure(
    tmp_path,
) -> None:
    from autovideo.services.scripts import LlmResponseInvalidError

    class FailingLlmClient:
        def generate(self, payload, settings):
            raise LlmResponseInvalidError("secret-key-should-not-leak")

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FailingLlmClient()

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "llm_only"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"
    assert "secret-key-should-not-leak" not in response.text


def test_generate_script_rejects_content_length_with_script_payload_limit(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_script_payload_bytes=8,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/scripts/generate",
            content=b'{"topic":"too large"}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "SCRIPT_PAYLOAD_TOO_LARGE"
    assert payload["detail"]["max_script_payload_bytes"] == 8


def test_generate_script_validates_topic_and_payload(client) -> None:
    blank_response = client.post(
        "/api/scripts/generate",
        json={"topic": "   ", "provider": "heuristic"},
    )
    assert blank_response.status_code == 400
    assert blank_response.json()["detail"]["code"] == "SCRIPT_TOPIC_REQUIRED"

    client.app.state.settings.max_script_payload_bytes = 64
    large_response = client.post(
        "/api/scripts/generate",
        json={"topic": "x"},
    )
    assert large_response.status_code == 413
    payload = large_response.json()
    assert payload["detail"]["code"] == "SCRIPT_PAYLOAD_TOO_LARGE"
    assert payload["detail"]["max_script_payload_bytes"] == 64
    assert payload["detail"]["payload_bytes"] > 64
